from tx5dr_device_panel.state import PanelStore


def test_snapshot_event_merges_safe_defaults():
    store = PanelStore()
    snapshot = store.apply({"type": "snapshot", "payload": {"engine": {"running": True, "mode": "voice"}}})

    assert snapshot["engine"]["running"] is True
    assert snapshot["radio"]["connected"] is False
    assert snapshot["ft8"]["currentTx"]["active"] is False


def test_error_event_does_not_replace_snapshot():
    store = PanelStore()
    before = store.snapshot
    after = store.apply({"type": "error", "payload": {"message": "server down"}})

    assert after is before
    assert store.last_error == "server down"
