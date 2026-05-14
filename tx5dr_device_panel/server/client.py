from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import websockets

from tx5dr_device_panel.config import ServerConfig

logger = logging.getLogger("tx5dr.panel.server")


class DeviceUiServerClient:
    def __init__(self, config: ServerConfig) -> None:
        self.config = config

    async def health(self) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.config.base_url, timeout=5.0) as client:
            response = await client.get("/api/device-ui/health")
            response.raise_for_status()
            return response.json()

    async def create_session(self, session_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.config.base_url, timeout=5.0) as client:
            response = await client.post(
                "/api/device-ui/session",
                json={"deviceId": self.config.device_id, "sessionToken": session_token},
            )
            response.raise_for_status()
            return response.json()

    async def bootstrap(self, jwt: str) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.config.base_url, timeout=5.0) as client:
            response = await client.get(
                "/api/device-ui/bootstrap",
                headers={"Authorization": f"Bearer {jwt}"},
            )
            response.raise_for_status()
            return response.json()

    async def ws_events(self, jwt: str) -> AsyncIterator[dict[str, Any]]:
        ws_url = self._ws_url()
        logger.info("Connecting Device UI websocket url=%s", ws_url)
        async with websockets.connect(ws_url, additional_headers={"Authorization": f"Bearer {jwt}"}) as ws:
            logger.info("Device UI websocket connected url=%s", ws_url)
            async for message in ws:
                if isinstance(message, bytes):
                    message = message.decode("utf-8")
                yield json.loads(message)
        logger.warning("Device UI websocket disconnected url=%s", ws_url)

    async def connect_forever(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            try:
                logger.info(
                    "Requesting Device UI session server=%s device_id=%s token_file=%s",
                    self.config.base_url,
                    self.config.device_id,
                    self.config.token_file,
                )
                token = read_session_token(self.config.token_file)
                session = await self.create_session(token)
                jwt = session["jwt"]
                logger.info(
                    "Device UI session established device_id=%s session_id=%s expires_at=%s",
                    session.get("deviceId", self.config.device_id),
                    session.get("sessionId"),
                    session.get("expiresAt"),
                )
                logger.info("Fetching Device UI bootstrap")
                bootstrap = await self.bootstrap(jwt)
                engine = bootstrap.get("engine") if isinstance(bootstrap.get("engine"), dict) else {}
                logger.info(
                    "Device UI bootstrap received engine_running=%s mode=%s",
                    engine.get("running"),
                    engine.get("mode") or (engine.get("currentMode") or {}).get("name"),
                )
                yield {"type": "bootstrap", "payload": bootstrap}
                async for event in self.ws_events(jwt):
                    logger.debug("Device UI WS event type=%s", event.get("type"))
                    yield event
                logger.warning(
                    "Device UI websocket disconnected; retrying in %.1fs",
                    self.config.reconnect_seconds,
                )
                yield {"type": "error", "payload": {"message": "Device UI websocket disconnected"}}
                await asyncio.sleep(self.config.reconnect_seconds)
            except Exception as exc:
                message = safe_error_message(exc)
                logger.warning(
                    "Device UI connection failed; retrying in %.1fs: %s",
                    self.config.reconnect_seconds,
                    message,
                    exc_info=logger.isEnabledFor(logging.DEBUG),
                )
                yield {"type": "error", "payload": {"message": message}}
                await asyncio.sleep(self.config.reconnect_seconds)

    def _ws_url(self) -> str:
        base = self.config.base_url.rstrip("/")
        if base.startswith("https://"):
            return "wss://" + base.removeprefix("https://") + "/api/device-ui/ws"
        return "ws://" + base.removeprefix("http://") + "/api/device-ui/ws"


def read_session_token(path: str) -> str:
    token = Path(path).expanduser().read_text(encoding="utf-8").strip()
    if not token:
        raise ValueError("Device UI token file is empty")
    return token


def safe_error_message(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        request = exc.request
        response = exc.response
        return (
            f"HTTP {response.status_code} {request.method} "
            f"{request.url.scheme}://{request.url.host}{request.url.path}"
        )
    if isinstance(exc, httpx.RequestError):
        request = exc.request
        return (
            f"{exc.__class__.__name__} "
            f"{request.url.scheme}://{request.url.host}{request.url.path}: "
            f"{_redact(str(exc))}"
        )
    return f"{exc.__class__.__name__}: {_redact(str(exc))}"


def _redact(value: str) -> str:
    redacted = re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer <redacted>", value, flags=re.IGNORECASE)
    redacted = re.sub(r"txdr_device_[A-Za-z0-9._-]+", "txdr_device_<redacted>", redacted)
    redacted = re.sub(
        r"\b[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
        "<jwt-redacted>",
        redacted,
    )
    return redacted
