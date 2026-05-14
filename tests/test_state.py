from tx5dr_device_panel.state import PanelStore


def test_snapshot_event_merges_safe_defaults():
    store = PanelStore()
    snapshot = store.apply({"type": "snapshot", "payload": {"engine": {"running": True, "mode": "voice"}}})

    assert snapshot["engine"]["running"] is True
    assert snapshot["radio"]["connected"] is False
    assert snapshot["ft8"]["currentTx"]["active"] is False


def test_error_event_resets_stale_running_snapshot_to_access_state():
    store = PanelStore()
    store.apply({
        "type": "snapshot",
        "payload": {
            "engine": {"running": True, "mode": "ft8"},
            "radio": {"connected": True, "frequency": 7_074_000, "ptt": True},
            "ft8": {"recentDecodeRawMessages": ["STALE"]},
            "access": {"localUrl": "http://192.168.1.10:8076"},
            "network": {"connected": True, "ip": "192.168.1.10", "transport": "wifi"},
        },
    })
    after = store.apply({"type": "error", "payload": {"message": "server down"}})

    assert after["engine"]["running"] is False
    assert after["radio"]["connected"] is False
    assert after["radio"]["ptt"] is False
    assert after["ft8"]["recentDecodeRawMessages"] == []
    assert after["access"]["localUrl"] == "http://192.168.1.10:8076"
    assert after["network"]["connected"] is True
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
    assert first["ft8"]["_display"]["entries"][0]["_kind"] == "ft8_cycle_header"
    assert first["ft8"]["_display"]["entries"][0]["message"] == "00:00:15 UTC · FT8"
    assert first["ft8"]["_display"]["entries"][1]["message"] == "NOW A"
    assert first["ft8"]["_display"]["slotId"] == "FT8-1"
    assert first["ft8"]["_display"]["slotStartMs"] == 15_000

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
    assert len(next_slot["ft8"]["_display"]["entries"]) == 2

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
    assert current_cycle["ft8"]["_display"]["entries"][0]["message"] == "00:00:30 UTC · FT8"
    assert current_cycle["ft8"]["_display"]["slotId"] == "FT8-2"
    assert current_cycle["ft8"]["_display"]["slotStartMs"] == 30_000
    assert [entry["message"] for entry in current_cycle["ft8"]["_display"]["entries"][1:]] == ["NOW B", "NOW C"]


def test_ft8_empty_frame_batch_keeps_previous_display_when_slot_id_changes():
    store = PanelStore()
    store.apply({
        "type": "snapshot",
        "payload": {
            "ft8": {
                "recentFramesSlotId": "FT8-1",
                "recentFramesSlotStartMs": 0,
                "recentFrames": [{"slotId": "FT8-1", "slotStartMs": 0, "message": "OLD"}],
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

    assert snapshot["ft8"]["recentFrames"] == [{"slotId": "FT8-1", "slotStartMs": 0, "message": "OLD"}]
    assert snapshot["ft8"]["recentDecodeRawMessages"] == ["OLD"]
    assert snapshot["ft8"]["lastDecodeRawMessage"] == "OLD"
    assert snapshot["ft8"]["_display"]["entries"][0]["slotId"] == "FT8-1"
    assert snapshot["ft8"]["_display"]["entries"][1]["message"] == "OLD"


def test_ft8_empty_first_batch_does_not_create_cycle_header():
    store = PanelStore()
    snapshot = store.apply({
        "type": "snapshot",
        "payload": {
            "radio": {"frequency": 7_074_000},
            "engine": {"running": True, "mode": "ft8", "currentMode": {"name": "FT8"}},
            "ft8": {
                "slot": {"id": "FT8-EMPTY", "startMs": 15_000, "mode": "FT8"},
                "recentFramesSlotId": "FT8-EMPTY",
                "recentFramesSlotStartMs": 15_000,
                "recentFrames": [],
            },
        },
    })

    assert snapshot["ft8"]["recentFrames"] == []
    assert snapshot["ft8"]["recentDecodeRawMessages"] == []
    assert snapshot["ft8"]["_display"]["entries"] == []


def test_ft8_repeated_same_slot_batch_is_deduplicated_and_does_not_reset_anchor():
    now = 0
    store = PanelStore(now_ms=lambda: now)
    frames = [
        {"slotId": "FT8-1", "message": "CQ JA1AAA PM95", "snr": -20},
        {"slotId": "FT8-1", "message": "CQ JA1AAA PM95", "snr": -5, "countryZh": "日本"},
        {"slotId": "FT8-1", "message": "CQ VK2XYZ QF56"},
    ]

    first = store.apply({
        "type": "snapshot",
        "payload": {
            "updatedAt": 0,
            "ft8": {"recentFramesSlotId": "FT8-1", "recentFramesSlotStartMs": 0, "recentFrames": frames},
        },
    })
    now = 6000
    duplicate = store.apply({
        "type": "snapshot",
        "payload": {
            "updatedAt": 6000,
            "ft8": {"recentFramesSlotId": "FT8-1", "recentFramesSlotStartMs": 0, "recentFrames": frames},
        },
    })

    assert first["ft8"]["recentDecodeRawMessages"] == ["CQ JA1AAA PM95", "CQ VK2XYZ QF56"]
    assert duplicate["ft8"]["recentDecodeRawMessages"] == ["CQ JA1AAA PM95", "CQ VK2XYZ QF56"]
    assert duplicate["ft8"]["recentFrames"][0]["countryZh"] == "日本"
    assert duplicate["ft8"]["recentFrames"][0]["snr"] == -5
    assert duplicate["ft8"]["_display"]["scrollAnchorTimeMs"] == 0
    assert [entry["message"] for entry in duplicate["ft8"]["_display"]["entries"]].count("CQ JA1AAA PM95") == 1
    assert sum(1 for entry in duplicate["ft8"]["_display"]["entries"] if entry.get("_kind") == "ft8_cycle_header") == 1


def test_ft8_same_slot_new_messages_preserve_scroll_progress():
    now = 0
    store = PanelStore(now_ms=lambda: now)
    first_frames = [{"slotId": "FT8-1", "message": f"MSG {index}"} for index in range(10)]
    store.apply({
        "type": "snapshot",
        "payload": {
            "updatedAt": 0,
            "ft8": {
                "periodMs": 15_000,
                "recentFramesSlotId": "FT8-1",
                "recentFramesSlotStartMs": 0,
                "recentFrames": first_frames,
            },
        },
    })

    now = 6000
    next_snapshot = store.apply({
        "type": "snapshot",
        "payload": {
            "updatedAt": 6000,
            "ft8": {
                "periodMs": 15_000,
                "recentFramesSlotId": "FT8-1",
                "recentFramesSlotStartMs": 0,
                "recentFrames": [*first_frames, {"slotId": "FT8-1", "message": "MSG 10"}],
            },
        },
    })

    assert next_snapshot["ft8"]["recentDecodeRawMessages"][-1] == "MSG 10"
    assert next_snapshot["ft8"]["_display"]["entries"][0]["_kind"] == "ft8_cycle_header"
    assert next_snapshot["ft8"]["_display"]["entries"][-1]["message"] == "MSG 10"
    assert next_snapshot["ft8"]["_display"]["scrollAnchorIndex"] > 0
    assert next_snapshot["ft8"]["_display"]["scrollAnchorTimeMs"] == 6000
