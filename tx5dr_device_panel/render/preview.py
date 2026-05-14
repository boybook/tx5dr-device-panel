from __future__ import annotations

import json
from pathlib import Path

from tx5dr_device_panel.render.framebuffer import FramebufferRenderer
from tx5dr_device_panel.render.framebuffer import DEFAULT_FUSION_PIXEL_FONT_SIZE
from tx5dr_device_panel.state import PanelStore
from tx5dr_device_panel.ui import render_snapshot


def run_preview(
    fixtures: list[Path],
    scale: int = 4,
    font_path: str | None = None,
    font_size: int = DEFAULT_FUSION_PIXEL_FONT_SIZE,
    language: str = "zh",
) -> None:
    import pygame

    pygame.init()
    renderer = FramebufferRenderer(font_path=font_path, font_size=font_size)
    index = 0
    surface = pygame.display.set_mode((128 * scale, 64 * scale))
    pygame.display.set_caption("TX-5DR Device Panel Preview")
    clock = pygame.time.Clock()

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in {pygame.K_ESCAPE, pygame.K_q}:
                    running = False
                elif event.key in {pygame.K_RIGHT, pygame.K_SPACE}:
                    index = (index + 1) % len(fixtures)
                elif event.key == pygame.K_LEFT:
                    index = (index - 1) % len(fixtures)

        snapshot = _load_fixture(fixtures[index])
        image = renderer.render(render_snapshot(snapshot, language=language)).convert("RGB")
        raw = image.resize((128 * scale, 64 * scale)).tobytes()
        frame = pygame.image.frombuffer(raw, (128 * scale, 64 * scale), "RGB")
        surface.blit(frame, (0, 0))
        pygame.display.flip()
        clock.tick(10)

    pygame.quit()


def _load_fixture(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    store = PanelStore()
    return store.apply({"type": "snapshot", "payload": data})
