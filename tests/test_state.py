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


def test_ft8_decodes_are_scoped_to_current_cycle_frames():
    store = PanelStore()

    first = store.apply({
        "type": "snapshot",
        "payload": {
            "ft8": {
                "cycle": 1,
                "recentDecodeRawMessages": ["OLD A", "OLD B", "NOW A"],
                "recentFramesSlotId": "FT8-1",
                "recentFramesSlotStartMs": 15_000,
                "recentFrames": [{"slotId": "FT8-1", "slotStartMs": 15_000, "message": "NOW A"}],
                "lastDecodeRawMessage": "NOW A",
            }
        },
    })
    assert first["ft8"]["recentDecodeRawMessages"] == ["NOW A"]

    next_slot = store.apply({
        "type": "snapshot",
        "payload": {
            "ft8": {
                "cycle": 2,
                "recentDecodeRawMessages": ["OLD A", "OLD B", "NOW A"],
                "recentFramesSlotId": "FT8-1",
                "recentFramesSlotStartMs": 15_000,
                "recentFrames": [{"slotId": "FT8-1", "slotStartMs": 15_000, "message": "NOW A"}],
                "lastDecodeRawMessage": "NOW A",
            }
        },
    })
    assert next_slot["ft8"]["recentDecodeRawMessages"] == ["NOW A"]
    assert next_slot["ft8"]["recentFrames"] == [{"slotId": "FT8-1", "slotStartMs": 15_000, "message": "NOW A"}]
    assert next_slot["ft8"]["lastDecodeRawMessage"] == "NOW A"

    current_cycle = store.apply({
        "type": "snapshot",
        "payload": {
            "ft8": {
                "cycle": 2,
                "recentDecodeRawMessages": ["OLD A", "NOW B", "NOW C"],
                "recentFramesSlotId": "FT8-2",
                "recentFramesSlotStartMs": 30_000,
                "recentFrames": [
                    {"slotId": "FT8-2", "slotStartMs": 30_000, "message": "NOW B"},
                    {"slotId": "FT8-2", "slotStartMs": 30_000, "message": "NOW C"},
                ],
                "lastDecodeRawMessage": "NOW C",
            }
        },
    })
    assert current_cycle["ft8"]["recentDecodeRawMessages"] == ["NOW B", "NOW C"]
    assert current_cycle["ft8"]["lastDecodeRawMessage"] == "NOW C"


def test_ft8_empty_frame_batch_keeps_previous_display_when_slot_id_changes():
    store = PanelStore()
    store.apply({
        "type": "snapshot",
        "payload": {
            "ft8": {
                "recentFramesSlotId": "FT8-1",
                "recentFrames": [{"slotId": "FT8-1", "message": "OLD"}],
            }
        },
    })

    snapshot = store.apply({
        "type": "snapshot",
        "payload": {
            "ft8": {
                "recentFramesSlotId": "FT8-2",
                "recentFrames": [],
                "recentDecodeRawMessages": ["OLD"],
                "lastDecodeRawMessage": "OLD",
            }
        },
    })

    assert snapshot["ft8"]["recentFrames"] == [{"slotId": "FT8-1", "message": "OLD"}]
    assert snapshot["ft8"]["recentDecodeRawMessages"] == ["OLD"]
    assert snapshot["ft8"]["lastDecodeRawMessage"] == "OLD"
