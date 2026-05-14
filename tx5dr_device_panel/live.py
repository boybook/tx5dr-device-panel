from __future__ import annotations

from pathlib import Path
import asyncio
import contextlib
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

    async def run(self) -> None:
        flush_task = asyncio.create_task(self._flush_loop())
        try:
            async for event in self.client.connect_forever():
                snapshot = self.store.apply(event)
                snapshot["network"] = {**snapshot.get("network", {}), **read_network_status()}
                image = self.renderer.render(render_snapshot(snapshot))
                self.sink.display(image, tx_active=_is_tx(snapshot))
        finally:
            flush_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await flush_task

    def _create_sink(self) -> ImageSink:
        if self.config.display.backend == "oled":
            return OledLumaBackend(self.config.hardware)
        return PngSink(Path("out/live.png"))

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(0.25)
            flush_pending = getattr(self.sink, "flush_pending", None)
            if flush_pending:
                flush_pending()


def _is_tx(snapshot: dict) -> bool:
    radio = snapshot.get("radio") or {}
    current_tx = ((snapshot.get("ft8") or {}).get("currentTx") or {})
    return bool(radio.get("ptt") or radio.get("tx") or current_tx.get("active"))
