from __future__ import annotations

import json
from pathlib import Path

from tx5dr_device_panel.render.framebuffer import FramebufferRenderer
from tx5dr_device_panel.render.framebuffer import DEFAULT_FUSION_PIXEL_FONT_SIZE
from tx5dr_device_panel.state import PanelStore
from tx5dr_device_panel.ui import render_snapshot


def render_fixture_to_png(
    fixture: Path,
    output: Path,
    font_path: str | None = None,
    font_size: int = DEFAULT_FUSION_PIXEL_FONT_SIZE,
    language: str = "zh",
) -> Path:
    data = json.loads(fixture.read_text(encoding="utf-8"))
    store = PanelStore()
    snapshot = store.apply({"type": "snapshot", "payload": data})
    image = FramebufferRenderer(font_path=font_path, font_size=font_size).render(
        render_snapshot(snapshot, language=language)
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    return output
