from __future__ import annotations

import json
from pathlib import Path

from tx5dr_device_panel.render.framebuffer import FramebufferRenderer
from tx5dr_device_panel.state import PanelStore
from tx5dr_device_panel.ui import render_snapshot


def render_fixture_to_png(fixture: Path, output: Path) -> Path:
    data = json.loads(fixture.read_text(encoding="utf-8"))
    store = PanelStore()
    snapshot = store.apply({"type": "snapshot", "payload": data})
    image = FramebufferRenderer().render(render_snapshot(snapshot))
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    return output
