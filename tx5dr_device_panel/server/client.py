from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import websockets

from tx5dr_device_panel.config import ServerConfig


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
        async with websockets.connect(ws_url, additional_headers={"Authorization": f"Bearer {jwt}"}) as ws:
            async for message in ws:
                if isinstance(message, bytes):
                    message = message.decode("utf-8")
                yield json.loads(message)

    async def connect_forever(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            try:
                token = read_session_token(self.config.token_file)
                session = await self.create_session(token)
                jwt = session["jwt"]
                yield {"type": "bootstrap", "payload": await self.bootstrap(jwt)}
                async for event in self.ws_events(jwt):
                    yield event
                yield {"type": "error", "payload": {"message": "Device UI websocket disconnected"}}
                await asyncio.sleep(self.config.reconnect_seconds)
            except Exception as exc:
                yield {"type": "error", "payload": {"message": str(exc)}}
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
