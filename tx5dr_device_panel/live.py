from __future__ import annotations

from pathlib import Path
import asyncio
import contextlib
import time
from typing import Protocol

from PIL import Image

from tx5dr_device_panel.config import PanelConfig
from tx5dr_device_panel.network import read_network_status
from tx5dr_device_panel.render.framebuffer import FramebufferRenderer
from tx5dr_device_panel.render.oled_luma import OledLumaBackend
from tx5dr_device_panel.server import DeviceUiServerClient
from tx5dr_device_panel.state import PanelStore
from tx5dr_device_panel.ui import render_snapshot


class ImageSink(Protocol):
    def display(self, image: Image.Image, tx_active: bool = False) -> bool:
        ...

    def flush_pending(self) -> bool:
        ...


class PngSink:
    def __init__(self, path: Path) -> None:
        self.path = path

    def display(self, image: Image.Image, tx_active: bool = False) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        image.save(self.path)
        return True

    def flush_pending(self) -> bool:
        return False


class PygamePreviewSink:
    def __init__(self, scale: int = 4) -> None:
        import pygame

        self.pygame = pygame
        self.scale = max(1, scale)
        pygame.init()
        self.surface = pygame.display.set_mode((128 * self.scale, 64 * self.scale))
        pygame.display.set_caption("TX-5DR Device Panel Live Preview")
        self.clock = pygame.time.Clock()

    def display(self, image: Image.Image, tx_active: bool = False) -> bool:
        self._handle_events()
        image = image.convert("RGB").resize((128 * self.scale, 64 * self.scale), Image.Resampling.NEAREST)
        frame = self.pygame.image.frombuffer(
            image.tobytes(),
            (128 * self.scale, 64 * self.scale),
            "RGB",
        )
        self.surface.blit(frame, (0, 0))
        self.pygame.display.flip()
        self.clock.tick(30)
        return True

    def flush_pending(self) -> bool:
        self._handle_events()
        self.clock.tick(30)
        return False

    def _handle_events(self) -> None:
        for event in self.pygame.event.get():
            if event.type == self.pygame.QUIT:
                self.pygame.quit()
                raise KeyboardInterrupt
            if event.type == self.pygame.KEYDOWN and event.key in {
                self.pygame.K_ESCAPE,
                self.pygame.K_q,
            }:
                self.pygame.quit()
                raise KeyboardInterrupt


class LivePanelRunner:
    def __init__(self, config: PanelConfig, sink: ImageSink | None = None) -> None:
        self.config = config
        self.store = PanelStore()
        self.client = DeviceUiServerClient(config.server)
        self.renderer = FramebufferRenderer(
            font_path=config.display.font_path,
            font_size=config.display.font_size,
        )
        self.sink = sink or self._create_sink()
        self._last_rendered_second = -1
        self._last_network_refresh = 0.0
        self._network_status: dict[str, object] = {}

    async def run(self) -> None:
        flush_task = asyncio.create_task(self._flush_loop())
        try:
            async for event in self.client.connect_forever():
                self.store.apply(event)
                self._render_current(update_clock=True, force_network=True)
        finally:
            flush_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await flush_task

    def _create_sink(self) -> ImageSink:
        if self.config.display.backend == "oled":
            return OledLumaBackend(self.config.hardware)
        if self.config.display.backend == "preview":
            return PygamePreviewSink(scale=self.config.display.scale)
        return PngSink(Path("out/live.png"))

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(0.25)
            flush_pending = getattr(self.sink, "flush_pending", None)
            if flush_pending:
                flush_pending()
            current_second = int(time.time())
            if current_second != self._last_rendered_second:
                self._render_current(update_clock=True)

    def _render_current(self, update_clock: bool = False, force_network: bool = False) -> None:
        snapshot = self.store.snapshot
        if update_clock:
            snapshot["updatedAt"] = int(time.time() * 1000)
        now = time.monotonic()
        if force_network or now - self._last_network_refresh > 5:
            self._network_status = read_network_status()
            self._last_network_refresh = now
        snapshot["network"] = {**snapshot.get("network", {}), **self._network_status}
        image = self.renderer.render(
            render_snapshot(snapshot, language=self.config.language)
        )
        self.sink.display(image, tx_active=_is_ptt_active(snapshot))
        self._last_rendered_second = int(time.time())


def _is_ptt_active(snapshot: dict) -> bool:
    radio = snapshot.get("radio") or {}
    return bool(radio.get("ptt"))
