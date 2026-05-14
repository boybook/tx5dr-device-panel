import json
from pathlib import Path

from tx5dr_device_panel.models import DISPLAY_HEIGHT, DISPLAY_WIDTH
from tx5dr_device_panel.render.framebuffer import FramebufferRenderer
from tx5dr_device_panel.state import PanelStore
from tx5dr_device_panel.ui import render_snapshot


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_all_fixtures_render_within_command_bounds():
    for fixture in FIXTURES.glob("*.json"):
        store = PanelStore()
        snapshot = store.apply({"type": "snapshot", "payload": json.loads(fixture.read_text())})
        frame = render_snapshot(snapshot)
        assert frame.width == DISPLAY_WIDTH
        assert frame.height == DISPLAY_HEIGHT
        for command in frame.commands:
            assert 0 <= command.x < DISPLAY_WIDTH
            assert 0 <= command.y < DISPLAY_HEIGHT
            if command.x2 is not None:
                assert 0 <= command.x2 < DISPLAY_WIDTH
            if command.y2 is not None:
                assert 0 <= command.y2 < DISPLAY_HEIGHT
        image = FramebufferRenderer().render(frame)
        assert image.size == (DISPLAY_WIDTH, DISPLAY_HEIGHT)


def test_ptt_draws_global_indicator_and_border():
    store = PanelStore()
    snapshot = store.apply({"type": "snapshot", "payload": json.loads((FIXTURES / "ft8.json").read_text())})
    snapshot["radio"]["ptt"] = True
    snapshot["radio"]["tx"] = True
    snapshot["ft8"]["currentTx"]["active"] = True
    frame = render_snapshot(snapshot)

    rects = [command for command in frame.commands if command.kind == "rect"]
    texts = [command.text for command in frame.commands if command.kind == "text" and command.y == 1]
    footer_texts = [command for command in frame.commands if command.kind == "text" and command.y == 55]

    assert any((rect.x, rect.y, rect.x2, rect.y2) == (0, 0, 127, 63) for rect in rects)
    assert any(command.kind == "filled_rect" and command.y == 0 and command.fill == 1 for command in frame.commands)
    assert any(command.kind == "filled_rect" and command.y == 55 and command.fill == 1 for command in frame.commands)
    assert any(command.text == "TX" and command.fill == 0 for command in footer_texts)
    assert any(text and text.startswith("UTC ") for text in texts)
    assert not any(text and text.startswith("TX ") for text in texts)


def test_tx_armed_without_ptt_only_highlights_footer_tx_label():
    store = PanelStore()
    snapshot = store.apply({"type": "snapshot", "payload": json.loads((FIXTURES / "ft8.json").read_text())})
    snapshot["radio"]["ptt"] = False
    snapshot["radio"]["tx"] = True
    snapshot["ft8"]["currentTx"]["active"] = True
    snapshot["ft8"]["currentTx"]["lastMessage"] = "CQ BG5DRB PM95"
    frame = render_snapshot(snapshot)

    rects = [command for command in frame.commands if command.kind == "rect"]
    footer_texts = [command for command in frame.commands if command.kind == "text" and command.y == 55]

    assert not any((rect.x, rect.y, rect.x2, rect.y2) == (0, 0, 127, 63) for rect in rects)
    assert not any(command.kind == "filled_rect" and command.y == 0 and command.fill == 1 for command in frame.commands)
    assert any(command.kind == "filled_rect" and command.y == 55 and command.fill == 1 for command in frame.commands)
    assert any(command.text == "TX" and command.fill == 0 for command in footer_texts)
    assert any(command.text == "CQ BG5DRB PM95" for command in footer_texts)


def test_idle_ft8_has_no_tx_highlight_or_footer_badge():
    store = PanelStore()
    snapshot = store.apply({"type": "snapshot", "payload": json.loads((FIXTURES / "ft8.json").read_text())})
    snapshot["radio"]["ptt"] = False
    snapshot["radio"]["tx"] = False
    snapshot["ft8"]["currentTx"]["active"] = False
    frame = render_snapshot(snapshot)

    rects = [command for command in frame.commands if command.kind == "rect"]
    footer_texts = [command.text for command in frame.commands if command.kind == "text" and command.y == 55]

    assert not any((rect.x, rect.y, rect.x2, rect.y2) == (0, 0, 127, 63) for rect in rects)
    assert not any(command.kind == "filled_rect" and command.y == 0 and command.fill == 1 for command in frame.commands)
    assert not any(command.kind == "filled_rect" and command.y == 55 and command.fill == 1 for command in frame.commands)
    assert "RX MONITOR" in footer_texts


def test_renderer_uses_bundled_fusion_pixel_font_and_supports_chinese_text():
    renderer = FramebufferRenderer()

    assert renderer.font_path.endswith("fusion-pixel-8px-monospaced-zh_hans.ttf")
    assert renderer.font.getbbox("中文状态")[2] > 0
    frame = render_snapshot(
        {
            "engine": {"running": False},
            "access": {"localUrl": "http://设备.local:8076"},
            "network": {"connected": True, "ip": "192.168.1.10", "ssid": "测试网络"},
            "updatedAt": 1778697600000,
        }
    )
    image = renderer.render(frame)
    assert image.getbbox() is not None


def test_ft8_monitor_uses_server_callsign_for_highlight_and_new_status_items():
    store = PanelStore()
    payload = json.loads((FIXTURES / "ft8.json").read_text())
    payload["updatedAt"] = 43_215_000
    payload["ft8"]["utc"] = 43_215
    payload["ft8"]["recentDecodeRawMessages"] = [
        "CQ JA1AAA PM95",
        "CQ VK2XYZ QF56",
        "K1ABC BG5DRB -10",
        "CQ W6AAA CM87",
        "CQ DL1AAA JO62",
        "BG5DRB K1ABC R-12",
    ]
    payload["ft8"]["recentFramesSlotId"] = "FT8-1"
    payload["ft8"]["recentFramesSlotStartMs"] = 15_000
    payload["ft8"]["recentFrames"] = [
        {
            "slotId": "FT8-1",
            "slotStartMs": 15_000,
            "message": message,
            "countryZh": "日本·东京",
            "countryEn": "Japan·Tokyo",
        }
        for message in payload["ft8"]["recentDecodeRawMessages"]
    ]
    payload["ft8"]["recentFrames"].extend(
        {"slotId": "FT8-1", "slotStartMs": 15_000, "message": str(i)} for i in range(4)
    )
    snapshot = store.apply({"type": "snapshot", "payload": payload})

    frame = render_snapshot(snapshot)
    texts = [command.text for command in frame.commands if command.kind == "text"]

    assert any(text and "UTC 12:00:15" in text for text in texts)
    assert "FT8·7.074" in texts
    assert "120015 ×10" in texts
    assert "日本·东京" in texts
    assert sum(
        1
        for command in frame.commands
        if command.kind == "text" and command.x == 2 and command.y in {13, 23, 33, 43}
    ) == 4
    assert any(command.kind == "filled_rect" and command.y in {13, 23, 33, 43} for command in frame.commands)


def test_ft8_country_labels_use_server_fields_and_global_language_parameter():
    store = PanelStore()
    payload = json.loads((FIXTURES / "ft8.json").read_text())
    payload["ft8"]["recentFramesSlotId"] = "FT8-1"
    payload["ft8"]["recentFrames"] = [
        {
            "slotId": "FT8-1",
            "message": "CQ JA1AAA PM95",
            "countryZh": "日本·东京",
            "countryEn": "Japan",
        },
    ]
    snapshot = store.apply({"type": "snapshot", "payload": payload})

    zh_texts = [
        command.text
        for command in render_snapshot(snapshot, language="zh").commands
        if command.kind == "text"
    ]
    en_texts = [
        command.text
        for command in render_snapshot(snapshot, language="en").commands
        if command.kind == "text"
    ]

    assert "日本·东京" in zh_texts
    assert "Japan" in en_texts


def test_status_bar_component_is_shared_by_access_ft8_and_voice_pages():
    expected_right_labels = {
        "access.json": "ACCESS",
        "ft8.json": "FT8·7.074",
        "voice.json": "FM·145.500",
    }

    for fixture_name, right_label in expected_right_labels.items():
        store = PanelStore()
        payload = json.loads((FIXTURES / fixture_name).read_text())
        payload["updatedAt"] = 43_215_000
        snapshot = store.apply({"type": "snapshot", "payload": payload})
        frame = render_snapshot(snapshot)
        texts = [command.text for command in frame.commands if command.kind == "text" and command.y == 1]

        assert "UTC 12:00:15" in texts
        assert right_label in texts
