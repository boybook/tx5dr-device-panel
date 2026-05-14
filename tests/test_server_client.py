import asyncio
import logging

from tx5dr_device_panel.config import ServerConfig
from tx5dr_device_panel.server.client import DeviceUiServerClient
from tx5dr_device_panel.server.client import safe_error_message


def test_connect_forever_reports_clean_ws_disconnect_before_reconnect(tmp_path):
    token_file = tmp_path / ".device-ui-token"
    token_file.write_text("token", encoding="utf-8")
    client = FakeClient(ServerConfig(token_file=str(token_file), reconnect_seconds=99))

    asyncio.run(_assert_disconnect_event(client))


def test_connect_forever_logs_session_bootstrap_and_disconnect(tmp_path, caplog):
    token_file = tmp_path / ".device-ui-token"
    token_file.write_text("token", encoding="utf-8")
    client = FakeClient(ServerConfig(token_file=str(token_file), reconnect_seconds=99))

    caplog.set_level(logging.INFO, logger="tx5dr.panel.server")
    asyncio.run(_assert_logged_connection_cycle(client))

    text = caplog.text
    assert "Requesting Device UI session" in text
    assert "Device UI session established" in text
    assert "Device UI bootstrap received" in text
    assert "Device UI websocket disconnected; retrying" in text


def test_connect_forever_logs_safe_reconnect_errors(tmp_path, caplog):
    token_file = tmp_path / ".device-ui-token"
    token_file.write_text("txdr_device_supersecret", encoding="utf-8")
    client = FailingClient(ServerConfig(token_file=str(token_file), reconnect_seconds=99))

    caplog.set_level(logging.INFO, logger="tx5dr.panel.server")
    events = client.connect_forever()
    event = asyncio.run(anext(events))
    asyncio.run(events.aclose())

    assert event["type"] == "error"
    assert "txdr_device_<redacted>" in event["payload"]["message"]
    assert "Device UI connection failed; retrying" in caplog.text
    assert "supersecret" not in caplog.text
    assert "supersecret" not in event["payload"]["message"]


def test_safe_error_message_redacts_bearer_tokens_and_jwts():
    message = safe_error_message(
        RuntimeError(
            "Authorization: Bearer abcdefghijklmnop "
            "jwt=aaaaaaaaaa.bbbbbbbbbb.cccccccccc txdr_device_secret"
        )
    )

    assert "Bearer <redacted>" in message
    assert "<jwt-redacted>" in message
    assert "txdr_device_<redacted>" in message
    assert "abcdefghijklmnop" not in message
    assert "aaaaaaaaaa.bbbbbbbbbb.cccccccccc" not in message
    assert "secret" not in message


async def _assert_disconnect_event(client: DeviceUiServerClient) -> None:
    events = client.connect_forever()
    assert await anext(events) == {"type": "bootstrap", "payload": {"engine": {"running": True}}}
    assert await anext(events) == {"type": "snapshot", "payload": {"engine": {"running": True}}}
    disconnect = await anext(events)

    assert disconnect["type"] == "error"
    assert disconnect["payload"]["message"] == "Device UI websocket disconnected"


async def _assert_logged_connection_cycle(client: DeviceUiServerClient) -> None:
    events = client.connect_forever()
    assert await anext(events) == {"type": "bootstrap", "payload": {"engine": {"running": True}}}
    assert await anext(events) == {"type": "snapshot", "payload": {"engine": {"running": True}}}
    disconnect = await anext(events)
    assert disconnect["type"] == "error"
    await events.aclose()


class FakeClient(DeviceUiServerClient):
    async def create_session(self, session_token: str):
        return {"jwt": "jwt"}

    async def bootstrap(self, jwt: str):
        return {"engine": {"running": True}}

    async def ws_events(self, jwt: str):
        yield {"type": "snapshot", "payload": {"engine": {"running": True}}}


class FailingClient(DeviceUiServerClient):
    async def create_session(self, session_token: str):
        raise RuntimeError(f"server rejected {session_token}")
