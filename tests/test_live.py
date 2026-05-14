import json
from pathlib import Path

from tx5dr_device_panel.config import PanelConfig
from tx5dr_device_panel.live import _is_ptt_active
from tx5dr_device_panel.live import LivePanelRunner
from tx5dr_device_panel.models import RenderFrame

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


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

    def fake_render_snapshot(snapshot, language="zh", metrics=None):
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

    def fake_render_snapshot(snapshot, language="zh", metrics=None):
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


def test_live_ft8_overflow_uses_dynamic_animation_schedule(monkeypatch):
    now = 0.0
    monkeypatch.setattr("tx5dr_device_panel.live.time.monotonic", lambda: now)
    monkeypatch.setattr("tx5dr_device_panel.live.time.time", lambda: 0.0)

    class Sink:
        def display(self, image, tx_active=False, animated=False):
            self.animated = animated
            return True

        def flush_pending(self):
            return False

    sink = Sink()
    monkeypatch.setattr("tx5dr_device_panel.live.read_network_status", lambda: {})
    monkeypatch.setattr("tx5dr_device_panel.live.render_snapshot", lambda snapshot, language="zh", metrics=None: RenderFrame())
    runner = LivePanelRunner(PanelConfig(), sink=sink)
    payload = json.loads((FIXTURES / "ft8.json").read_text())
    payload["updatedAt"] = 0
    payload["ft8"]["recentFramesSlotId"] = "FT8-LIVE"
    payload["ft8"]["recentFrames"] = [
        {"slotId": "FT8-LIVE", "message": f"MSG {index}"} for index in range(10)
    ]
    runner.store.now_ms = lambda: 0
    runner.store.apply({"type": "snapshot", "payload": payload})
    runner._sync_ft8_scroll_timeline(now)

    now = 1.0
    assert runner._should_render_ft8_scroll() is False

    now = 2.0
    assert runner._should_render_ft8_scroll() is True
    runner._render_current(update_clock=True, advance_ft8_scroll=True)
    assert sink.animated is True
    assert runner._next_ft8_scroll_at is not None
    assert runner._next_ft8_scroll_at > now


def test_live_second_render_does_not_reset_ft8_scroll_deadline(monkeypatch):
    now = 0.0
    monkeypatch.setattr("tx5dr_device_panel.live.time.monotonic", lambda: now)
    monkeypatch.setattr("tx5dr_device_panel.live.time.time", lambda: 0.0)
    monkeypatch.setattr("tx5dr_device_panel.live.read_network_status", lambda: {})
    monkeypatch.setattr("tx5dr_device_panel.live.render_snapshot", lambda snapshot, language="zh", metrics=None: RenderFrame())
    runner = LivePanelRunner(PanelConfig(), sink=type("Sink", (), {"display": lambda *args, **kwargs: True, "flush_pending": lambda self: False})())
    payload = json.loads((FIXTURES / "ft8.json").read_text())
    payload["updatedAt"] = 0
    payload["ft8"]["recentFramesSlotId"] = "FT8-LIVE"
    payload["ft8"]["recentFrames"] = [
        {"slotId": "FT8-LIVE", "message": f"MSG {index}"} for index in range(10)
    ]
    runner.store.apply({"type": "snapshot", "payload": payload})
    runner._sync_ft8_scroll_timeline(now)
    deadline = runner._next_ft8_scroll_at
    scroll_wall = runner._ft8_scroll_wall_ms

    now = 1.0
    runner._render_current(update_clock=True)

    assert runner._next_ft8_scroll_at == deadline
    assert runner._ft8_scroll_wall_ms == scroll_wall


def test_live_duplicate_ft8_batch_does_not_reset_scroll_deadline(monkeypatch):
    now = 0.0
    monkeypatch.setattr("tx5dr_device_panel.live.time.monotonic", lambda: now)
    monkeypatch.setattr("tx5dr_device_panel.live.time.time", lambda: 0.0)
    monkeypatch.setattr("tx5dr_device_panel.live.read_network_status", lambda: {})
    monkeypatch.setattr("tx5dr_device_panel.live.render_snapshot", lambda snapshot, language="zh", metrics=None: RenderFrame())
    runner = LivePanelRunner(PanelConfig(), sink=type("Sink", (), {"display": lambda *args, **kwargs: True, "flush_pending": lambda self: False})())
    payload = json.loads((FIXTURES / "ft8.json").read_text())
    payload["updatedAt"] = 0
    payload["ft8"]["recentFramesSlotId"] = "FT8-LIVE"
    payload["ft8"]["recentFrames"] = [
        {"slotId": "FT8-LIVE", "message": f"MSG {index}"} for index in range(10)
    ]
    runner.store.apply({"type": "snapshot", "payload": payload})
    runner._sync_ft8_scroll_timeline(now)
    deadline = runner._next_ft8_scroll_at

    now = 0.5
    runner.store.apply({"type": "snapshot", "payload": payload})
    runner._sync_ft8_scroll_timeline(now)

    assert runner._next_ft8_scroll_at == deadline


def test_live_new_ft8_batch_reschedules_after_current_dwell(monkeypatch):
    now = 0.0
    monkeypatch.setattr("tx5dr_device_panel.live.time.monotonic", lambda: now)
    monkeypatch.setattr("tx5dr_device_panel.live.time.time", lambda: 0.0)
    monkeypatch.setattr("tx5dr_device_panel.live.read_network_status", lambda: {})
    monkeypatch.setattr("tx5dr_device_panel.live.render_snapshot", lambda snapshot, language="zh", metrics=None: RenderFrame())
    runner = LivePanelRunner(PanelConfig(), sink=type("Sink", (), {"display": lambda *args, **kwargs: True, "flush_pending": lambda self: False})())
    payload = json.loads((FIXTURES / "ft8.json").read_text())
    payload["updatedAt"] = 0
    payload["ft8"]["recentFramesSlotId"] = "FT8-LIVE"
    payload["ft8"]["recentFrames"] = [
        {"slotId": "FT8-LIVE", "message": f"MSG {index}"} for index in range(10)
    ]
    runner.store.apply({"type": "snapshot", "payload": payload})
    runner._sync_ft8_scroll_timeline(now)
    first_deadline = runner._next_ft8_scroll_at

    now = 0.5
    changed = json.loads(json.dumps(payload))
    changed["updatedAt"] = 500
    changed["ft8"]["recentFrames"].append({"slotId": "FT8-LIVE", "message": "MSG 10"})
    runner.store.apply({"type": "snapshot", "payload": changed})
    runner._sync_ft8_scroll_timeline(now)

    assert runner._next_ft8_scroll_at is not None
    assert runner._next_ft8_scroll_at > first_deadline
    assert runner._next_ft8_scroll_at > now


def test_live_loop_sleep_uses_nearest_deadline_without_busy_loop(monkeypatch):
    now = 0.0
    monkeypatch.setattr("tx5dr_device_panel.live.time.monotonic", lambda: now)
    monkeypatch.setattr("tx5dr_device_panel.live.time.time", lambda: 0.0)
    runner = LivePanelRunner(PanelConfig(), sink=type("Sink", (), {"display": lambda *args, **kwargs: True, "flush_pending": lambda self: False})())
    payload = json.loads((FIXTURES / "ft8.json").read_text())
    payload["updatedAt"] = 0
    payload["ft8"]["recentFramesSlotId"] = "FT8-LIVE"
    payload["ft8"]["recentFrames"] = [
        {"slotId": "FT8-LIVE", "message": f"MSG {index}"} for index in range(10)
    ]
    runner.store.apply({"type": "snapshot", "payload": payload})
    runner._sync_ft8_scroll_timeline(now)

    now = 1.82
    delay = runner._loop_sleep_seconds(now)

    assert runner.min_loop_sleep <= delay <= runner.max_loop_sleep
    assert delay < 0.1


def test_live_ft8_own_rows_suppress_other_overflow_animation():
    runner = LivePanelRunner(PanelConfig(), sink=type("Sink", (), {"display": lambda *args, **kwargs: True, "flush_pending": lambda self: False})())
    payload = json.loads((FIXTURES / "ft8.json").read_text())
    payload["station"] = {"callsign": "BG5DRB", "callsigns": ["BG5AAA", "BG5BBB"]}
    payload["ft8"]["recentFramesSlotId"] = "FT8-LIVE"
    payload["ft8"]["recentFrames"] = [
        *[{"slotId": "FT8-LIVE", "message": f"BG5AAA K{index}ABC R-12"} for index in range(2)],
        *[{"slotId": "FT8-LIVE", "message": f"BG5BBB K{index}ABC R-12"} for index in range(2)],
        *[{"slotId": "FT8-LIVE", "message": f"MSG {index}"} for index in range(20)],
    ]
    runner.store.now_ms = lambda: 0
    runner.store.apply({"type": "snapshot", "payload": payload})

    assert runner._should_render_ft8_scroll() is False
