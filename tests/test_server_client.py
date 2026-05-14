import asyncio

from tx5dr_device_panel.config import ServerConfig
from tx5dr_device_panel.server.client import DeviceUiServerClient


def test_connect_forever_reports_clean_ws_disconnect_before_reconnect(tmp_path):
    token_file = tmp_path / ".device-ui-token"
    token_file.write_text("token", encoding="utf-8")
    client = FakeClient(ServerConfig(token_file=str(token_file), reconnect_seconds=99))

    asyncio.run(_assert_disconnect_event(client))


async def _assert_disconnect_event(client: DeviceUiServerClient) -> None:
    events = client.connect_forever()
    assert await anext(events) == {"type": "bootstrap", "payload": {"engine": {"running": True}}}
    assert await anext(events) == {"type": "snapshot", "payload": {"engine": {"running": True}}}
    disconnect = await anext(events)

    assert disconnect["type"] == "error"
    assert disconnect["payload"]["message"] == "Device UI websocket disconnected"


class FakeClient(DeviceUiServerClient):
    async def create_session(self, session_token: str):
        return {"jwt": "jwt"}

    async def bootstrap(self, jwt: str):
        return {"engine": {"running": True}}

    async def ws_events(self, jwt: str):
        yield {"type": "snapshot", "payload": {"engine": {"running": True}}}
