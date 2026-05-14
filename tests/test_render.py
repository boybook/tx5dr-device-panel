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
    assert renderer._font_for_size(12).path.endswith("fusion-pixel-12px-monospaced-zh_hans.ttf")
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


def test_access_page_uses_localized_engine_stopped_guidance():
    store = PanelStore()
    snapshot = store.apply({"type": "snapshot", "payload": json.loads((FIXTURES / "access.json").read_text())})

    zh_texts = [command.text for command in render_snapshot(snapshot, language="zh").commands if command.kind == "text"]
    en_texts = [command.text for command in render_snapshot(snapshot, language="en").commands if command.kind == "text"]

    assert "TX-5DR" in zh_texts
    assert "TX-5DR" in en_texts
    assert "引擎未启动" in zh_texts
    assert "打开后台启动" in zh_texts
    assert "192.168.1.10:8076" in zh_texts
    assert "ENGINE STOPPED" in en_texts
    assert "OPEN WEB UI" in en_texts


def test_access_page_prioritizes_no_network_over_server_or_engine_guidance():
    store = PanelStore()
    payload = json.loads((FIXTURES / "boot.json").read_text())
    payload["access"]["lastError"] = "server down"
    snapshot = store.apply({"type": "snapshot", "payload": payload})
    texts = [command.text for command in render_snapshot(snapshot, language="zh").commands if command.kind == "text"]

    assert "设备未联网" in texts
    assert "连接网线/WiFi" in texts
    assert "IP --" in texts
    assert "后端离线" not in texts
    assert "引擎未启动" not in texts


def test_access_page_shows_server_down_when_network_is_available():
    store = PanelStore()
    payload = json.loads((FIXTURES / "access.json").read_text())
    payload["access"]["lastError"] = "Connection refused"
    snapshot = store.apply({"type": "snapshot", "payload": payload})
    texts = [command.text for command in render_snapshot(snapshot, language="en").commands if command.kind == "text"]

    assert "SERVER OFF" in texts
    assert "LOGIN CONSOLE" in texts
    assert "RUN tx5dr doctor" in texts
    assert "192.168.1.10:8076" not in texts


def test_access_page_does_not_fallback_to_local_domain_without_server_url():
    store = PanelStore()
    payload = json.loads((FIXTURES / "access.json").read_text())
    payload["access"]["localUrl"] = None
    payload["access"]["localUrls"] = []
    snapshot = store.apply({"type": "snapshot", "payload": payload})
    texts = [command.text for command in render_snapshot(snapshot, language="zh").commands if command.kind == "text"]

    assert "后台不可用" in texts
    assert all("tx5dr.local" not in str(text) for text in texts)


def test_access_page_guides_hotspot_join_when_hotspot_ssid_is_available():
    store = PanelStore()
    snapshot = store.apply({"type": "snapshot", "payload": json.loads((FIXTURES / "network.json").read_text())})
    texts = [command.text for command in render_snapshot(snapshot, language="en").commands if command.kind == "text"]

    assert "ENGINE STOPPED" in texts
    assert "JOIN TX5DR" in texts
    assert "10.42.0.1:8076" in texts


def test_access_page_carousel_rotates_network_detail_deterministically():
    payload = json.loads((FIXTURES / "network.json").read_text())
    payload["updatedAt"] = 0
    first = PanelStore().apply({"type": "snapshot", "payload": payload})
    payload["updatedAt"] = 3000
    second = PanelStore().apply({"type": "snapshot", "payload": payload})

    first_frame = render_snapshot(first, language="en")
    first_again = render_snapshot(first, language="en")
    second_texts = [command.text for command in render_snapshot(second, language="en").commands if command.kind == "text"]

    assert first_frame.commands == first_again.commands
    assert "SSID TX5DR" not in [command.text for command in first_frame.commands if command.kind == "text"]
    assert "SSID TX5DR" in second_texts


def test_access_page_carousel_rotates_server_provided_local_urls():
    payload = json.loads((FIXTURES / "access.json").read_text())
    payload["access"]["localUrls"] = ["http://192.168.1.10:8076", "http://10.0.0.5:8076"]
    payload["updatedAt"] = 0
    first = PanelStore().apply({"type": "snapshot", "payload": payload})
    payload["updatedAt"] = 3000
    second = PanelStore().apply({"type": "snapshot", "payload": payload})

    first_texts = [command.text for command in render_snapshot(first, language="zh").commands if command.kind == "text"]
    second_texts = [command.text for command in render_snapshot(second, language="zh").commands if command.kind == "text"]

    assert "192.168.1.10:8076" in first_texts
    assert "10.0.0.5:8076" in second_texts


def test_access_page_uses_minimal_centered_title_and_particle_field():
    snapshot = PanelStore().apply({"type": "snapshot", "payload": json.loads((FIXTURES / "access.json").read_text())})
    frame = render_snapshot(snapshot, language="zh")
    text_commands = {command.text: command for command in frame.commands if command.kind == "text"}

    assert "TX-5DR" in text_commands
    assert "ACCESS" not in text_commands
    assert text_commands["引擎未启动"].font_size == 12
    assert text_commands["引擎未启动"].fill == 0
    assert text_commands["引擎未启动"].y == 19
    assert any(command.kind == "filled_rect" and command.y == 18 and command.y2 == 31 for command in frame.commands)
    assert not any(command.kind == "filled_rect" and command.y == 55 and command.x2 and command.x2 - command.x > 8 for command in frame.commands)
    assert not any(command.kind == "rect" and command.y == 23 and command.y2 == 40 for command in frame.commands)
    assert sum(1 for command in frame.commands if command.kind in {"filled_rect", "rect", "line"} and command.y >= 11) >= 8


def test_access_page_has_no_full_content_border():
    store = PanelStore()
    snapshot = store.apply({"type": "snapshot", "payload": json.loads((FIXTURES / "access.json").read_text())})
    frame = render_snapshot(snapshot)

    assert not any(
        command.kind == "rect" and (command.x, command.y, command.x2, command.y2) == (0, 10, 127, 63)
        for command in frame.commands
    )
    assert any(command.kind == "line" and (command.x, command.y, command.x2, command.y2) == (0, 9, 127, 9) for command in frame.commands)
    assert not any(command.kind == "line" and (command.x, command.y, command.x2, command.y2) == (0, 10, 0, 63) for command in frame.commands)
    assert not any(command.kind == "line" and (command.x, command.y, command.x2, command.y2) == (127, 10, 127, 63) for command in frame.commands)
    assert not any(command.kind == "line" and (command.x, command.y, command.x2, command.y2) == (0, 63, 127, 63) for command in frame.commands)


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
        "access.json": "TX-5DR",
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


def test_status_bar_draws_network_icons_for_wifi_wired_and_disconnected_states():
    wifi = PanelStore().apply({
        "type": "snapshot",
        "payload": {
            "network": {
                "connected": True,
                "interface": "en0",
                "ip": "192.168.1.20",
                "ssid": None,
                "transport": "wifi",
            }
        },
    })
    wired = PanelStore().apply({"type": "snapshot", "payload": json.loads((FIXTURES / "access.json").read_text())})
    offline = PanelStore().apply({"type": "snapshot", "payload": json.loads((FIXTURES / "boot.json").read_text())})

    wifi_commands = render_snapshot(wifi).commands
    wired_commands = render_snapshot(wired).commands
    offline_commands = render_snapshot(offline).commands

    assert _has_pixel(wifi_commands, 120, 2)
    assert _has_pixel(wifi_commands, 119, 3)
    assert _has_pixel(wired_commands, 120, 1)
    assert _has_pixel(wired_commands, 119, 4)
    assert _has_pixel(wired_commands, 124, 4)
    assert _has_pixel(offline_commands, 119, 1)
    assert _has_pixel(offline_commands, 126, 8)


def test_status_bar_ignores_ssid_when_transport_is_unknown():
    snapshot = PanelStore().apply({
        "type": "snapshot",
        "payload": {
            "network": {
                "connected": True,
                "ip": "192.168.1.20",
                "ssid": "Lab",
                "transport": "unknown",
            }
        },
    })
    commands = render_snapshot(snapshot).commands

    assert _has_pixel(commands, 119, 1)
    assert _has_pixel(commands, 126, 8)


def test_status_bar_right_text_avoids_network_icon_area():
    expected_right_labels = {
        "access.json": "TX-5DR",
        "ft8.json": "FT8·7.074",
        "voice.json": "FM·145.500",
    }

    for fixture_name, right_label in expected_right_labels.items():
        store = PanelStore()
        payload = json.loads((FIXTURES / fixture_name).read_text())
        snapshot = store.apply({"type": "snapshot", "payload": payload})
        frame = render_snapshot(snapshot)
        command = next(
            command for command in frame.commands if command.kind == "text" and command.text == right_label
        )

        assert command.x + _test_text_width(right_label) <= 116


def test_status_bar_network_icon_uses_inverse_fill_when_ptt_is_active():
    store = PanelStore()
    payload = json.loads((FIXTURES / "network.json").read_text())
    payload["radio"] = {"ptt": True}
    snapshot = store.apply({"type": "snapshot", "payload": payload})
    frame = render_snapshot(snapshot)

    assert any(
        command.kind == "filled_rect"
        and command.fill == 0
        and (command.x, command.y, command.x2, command.y2) == (120, 2, 120, 2)
        for command in frame.commands
    )


def test_voice_monitor_uses_large_centered_status_lines_without_title():
    store = PanelStore()
    payload = json.loads((FIXTURES / "voice.json").read_text())
    snapshot = store.apply({"type": "snapshot", "payload": payload})
    frame = render_snapshot(snapshot)
    text_commands = {command.text: command for command in frame.commands if command.kind == "text"}

    assert "VOICE MONITOR" not in text_commands
    assert text_commands["145.500"].font_size == 16
    assert (text_commands["145.500"].x, text_commands["145.500"].y) == (36, 20)
    assert (text_commands["MODE FM"].x, text_commands["MODE FM"].y) == (50, 42)
    assert (text_commands["PTT FREE LIVE"].x, text_commands["PTT FREE LIVE"].y) == (38, 52)


def _test_text_width(text: str) -> int:
    return sum(8 if ord(char) > 127 else 4 for char in text)


def _has_pixel(commands, x: int, y: int, fill: int = 1) -> bool:
    return any(
        command.kind == "filled_rect"
        and command.fill == fill
        and (command.x, command.y, command.x2, command.y2) == (x, y, x, y)
        for command in commands
    )
