from tx5dr_device_panel.config import PanelConfig
from tx5dr_device_panel.live import _is_ptt_active
from tx5dr_device_panel.live import LivePanelRunner
from tx5dr_device_panel.models import RenderFrame


def test_live_tx_refresh_uses_only_real_ptt_state():
    assert _is_ptt_active({"radio": {"ptt": True, "tx": False}, "ft8": {"currentTx": {"active": False}}})
    assert not _is_ptt_active({"radio": {"ptt": False, "tx": True}, "ft8": {"currentTx": {"active": True}}})


def test_live_render_injects_last_error_without_persisting_it(monkeypatch):
    captured = {}

    class Sink:
        def display(self, image, tx_active=False, animated=False):
            captured["animated"] = animated
            return True

        def flush_pending(self):
            return False

    def fake_render_snapshot(snapshot, language="zh"):
        captured["snapshot"] = snapshot
        captured["language"] = language
        return RenderFrame()

    monkeypatch.setattr(
        "tx5dr_device_panel.live.read_network_status",
        lambda: {"connected": True, "ip": "192.168.1.10", "interface": "eth0", "ssid": None},
    )
    monkeypatch.setattr("tx5dr_device_panel.live.render_snapshot", fake_render_snapshot)

    runner = LivePanelRunner(PanelConfig(language="en"), sink=Sink())
    runner.store.apply({"type": "error", "payload": {"message": "server down"}})
    runner._render_current(force_network=True)

    assert captured["language"] == "en"
    assert captured["animated"] is True
    assert captured["snapshot"]["access"]["lastError"] == "server down"
    assert "lastError" not in runner.store.snapshot["access"]

    runner.store.apply({"type": "snapshot", "payload": {"engine": {"running": False}}})
    runner._render_current()

    assert "lastError" not in captured["snapshot"]["access"]


def test_live_error_after_running_snapshot_renders_access_page(monkeypatch):
    captured = {}

    class Sink:
        def display(self, image, tx_active=False, animated=False):
            captured["tx_active"] = tx_active
            captured["animated"] = animated
            return True

        def flush_pending(self):
            return False

    def fake_render_snapshot(snapshot, language="zh"):
        captured["snapshot"] = snapshot
        return RenderFrame()

    monkeypatch.setattr("tx5dr_device_panel.live.read_network_status", lambda: {})
    monkeypatch.setattr("tx5dr_device_panel.live.render_snapshot", fake_render_snapshot)

    runner = LivePanelRunner(PanelConfig(), sink=Sink())
    runner.store.apply({
        "type": "snapshot",
        "payload": {
            "engine": {"running": True, "mode": "ft8"},
            "radio": {"connected": True, "ptt": True},
            "access": {"localUrl": "http://192.168.1.10:8076"},
        },
    })
    runner.store.apply({"type": "error", "payload": {"message": "websocket disconnected"}})
    runner._render_current()

    assert captured["snapshot"]["engine"]["running"] is False
    assert captured["snapshot"]["radio"]["ptt"] is False
    assert captured["snapshot"]["access"]["lastError"] == "websocket disconnected"
    assert captured["animated"] is True
    assert captured["tx_active"] is False
