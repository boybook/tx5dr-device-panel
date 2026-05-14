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
    frame = render_snapshot(snapshot)

    rects = [command for command in frame.commands if command.kind == "rect"]
    assert any((rect.x, rect.y, rect.x2, rect.y2) == (0, 0, 127, 63) for rect in rects)
    assert any(command.kind == "filled_rect" and command.y == 0 for command in frame.commands)


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
