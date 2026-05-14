from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import asyncio
import contextlib
import time
from typing import Protocol

from PIL import Image

from tx5dr_device_panel.config import PanelConfig
from tx5dr_device_panel.ft8_display import ft8_scroll_metrics
from tx5dr_device_panel.network import read_network_status
from tx5dr_device_panel.render.framebuffer import FramebufferRenderer
from tx5dr_device_panel.render.oled_luma import OledLumaBackend
from tx5dr_device_panel.server import DeviceUiServerClient
from tx5dr_device_panel.state import PanelStore
from tx5dr_device_panel.ui import render_snapshot
from tx5dr_device_panel.ui.text_metrics import TextMetrics


class ImageSink(Protocol):
    def display(self, image: Image.Image, tx_active: bool = False, animated: bool = False) -> bool:
        ...

    def flush_pending(self) -> bool:
        ...


class PngSink:
    def __init__(self, path: Path) -> None:
        self.path = path

    def display(self, image: Image.Image, tx_active: bool = False, animated: bool = False) -> bool:
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

    def display(self, image: Image.Image, tx_active: bool = False, animated: bool = False) -> bool:
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
    min_loop_sleep = 0.05
    max_loop_sleep = 0.25
    access_animation_seconds = 0.25

    def __init__(self, config: PanelConfig, sink: ImageSink | None = None) -> None:
        self.config = config
        self.store = PanelStore()
        self._monotonic_origin = time.monotonic()
        self._wall_origin_ms = int(time.time() * 1000)
        self.store.now_ms = self._wall_ms
        self.client = DeviceUiServerClient(config.server)
        self.renderer = FramebufferRenderer(
            font_path=config.display.font_path,
            font_size=config.display.font_size,
        )
        self.metrics = TextMetrics(
            font_path=config.display.font_path,
            font_size=config.display.font_size,
        )
        self.sink = sink or self._create_sink()
        self._last_rendered_second = -1
        self._ft8_scroll_state_key: tuple[object, ...] | None = None
        self._ft8_scroll_wall_ms: int | None = None
        self._next_ft8_scroll_at: float | None = None
        self._pending_ft8_scroll_wall_ms: int | None = None
        self._next_access_animation_at = 0.0
        self._last_network_refresh = 0.0
        self._network_status: dict[str, object] = {}

    async def run(self) -> None:
        flush_task = asyncio.create_task(self._flush_loop())
        try:
            async for event in self.client.connect_forever():
                self.store.apply(event)
                self._sync_ft8_scroll_timeline()
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
            await asyncio.sleep(self._loop_sleep_seconds())
            flush_pending = getattr(self.sink, "flush_pending", None)
            if flush_pending and flush_pending():
                self._commit_pending_ft8_scroll()

            now = time.monotonic()
            if self._is_access_page(self.store.snapshot):
                if now >= self._next_access_animation_at:
                    self._render_current(update_clock=True)
                    self._next_access_animation_at = now + self.access_animation_seconds
                continue
            if self._should_render_ft8_scroll(now):
                self._render_current(update_clock=True, advance_ft8_scroll=True)
                continue
            current_second = self._wall_ms(now) // 1000
            if current_second != self._last_rendered_second:
                self._render_current(update_clock=True)

    def _render_current(
        self,
        update_clock: bool = False,
        force_network: bool = False,
        advance_ft8_scroll: bool = False,
    ) -> bool:
        now = time.monotonic()
        self._sync_ft8_scroll_timeline(now)
        scroll_wall_ms = (
            self._next_ft8_scroll_wall_ms()
            if advance_ft8_scroll
            else self._pending_ft8_scroll_wall_ms
        )
        snapshot = deepcopy(self.store.snapshot)
        if update_clock:
            snapshot["updatedAt"] = self._wall_ms(now)
        self._inject_ft8_scroll_clock(snapshot, scroll_wall_ms=scroll_wall_ms)
        if force_network or now - self._last_network_refresh > 5:
            self._network_status = read_network_status()
            self._last_network_refresh = now
        snapshot["network"] = {**snapshot.get("network", {}), **self._network_status}
        if self.store.last_error:
            snapshot["access"] = {**snapshot.get("access", {}), "lastError": self.store.last_error}
        animated = self._is_access_page(snapshot) or self._is_ft8_scroll_active(snapshot)
        image = self.renderer.render(
            render_snapshot(snapshot, language=self.config.language, metrics=self.metrics)
        )
        displayed = self.sink.display(
            image,
            tx_active=_is_ptt_active(snapshot),
            animated=animated,
        )
        if advance_ft8_scroll and scroll_wall_ms is not None:
            if displayed or getattr(self.sink, "_pending_image", None) is None:
                self._commit_ft8_scroll(scroll_wall_ms, now)
            else:
                self._pending_ft8_scroll_wall_ms = scroll_wall_ms
        elif self._pending_ft8_scroll_wall_ms is not None and displayed:
            self._commit_pending_ft8_scroll()
        self._last_rendered_second = self._wall_ms(now) // 1000
        return displayed

    def _is_access_page(self, snapshot: dict) -> bool:
        engine = snapshot.get("engine") or {}
        return not bool(engine.get("running"))

    def _is_ft8_page(self, snapshot: dict) -> bool:
        engine = snapshot.get("engine") or {}
        if not engine.get("running"):
            return False
        mode_name = str((engine.get("currentMode") or {}).get("name") or engine.get("mode") or "").upper()
        return engine.get("mode") not in {"voice", "cw"} and mode_name not in {"VOICE", "SSB", "AM", "FM", "CW"}

    def _is_ft8_scroll_active(self, snapshot: dict) -> bool:
        if not self._is_ft8_page(snapshot):
            return False
        return ft8_scroll_metrics(snapshot, _station_callsign(snapshot)).active

    def _should_render_ft8_scroll(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        if not self._is_ft8_page(self.store.snapshot):
            return False
        if self._pending_ft8_scroll_wall_ms is not None:
            return False
        self._sync_ft8_scroll_timeline(now)
        return self._next_ft8_scroll_at is not None and now >= self._next_ft8_scroll_at

    def _sync_ft8_scroll_timeline(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        snapshot = self.store.snapshot
        if not self._is_ft8_page(snapshot):
            self._clear_ft8_scroll_timeline()
            return
        metrics = ft8_scroll_metrics(self.store.snapshot, _station_callsign(self.store.snapshot))
        if not metrics.active:
            self._clear_ft8_scroll_timeline()
            return

        ft8 = snapshot.get("ft8") if isinstance(snapshot.get("ft8"), dict) else {}
        display = ft8.get("_display") if isinstance(ft8.get("_display"), dict) else {}
        state_key = (
            display.get("slotId"),
            display.get("scrollAnchorIndex"),
            display.get("scrollAnchorTimeMs"),
            display.get("uniqueCount"),
            metrics.dwell_ms,
        )
        if state_key == self._ft8_scroll_state_key and self._next_ft8_scroll_at is not None:
            return

        self._ft8_scroll_state_key = state_key
        anchor_time = display.get("scrollAnchorTimeMs")
        self._ft8_scroll_wall_ms = int(anchor_time) if isinstance(anchor_time, (int, float)) else self._wall_ms(now)
        self._next_ft8_scroll_at = now + metrics.dwell_ms / 1000
        self._pending_ft8_scroll_wall_ms = None

    def _clear_ft8_scroll_timeline(self) -> None:
        self._ft8_scroll_state_key = None
        self._ft8_scroll_wall_ms = None
        self._next_ft8_scroll_at = None
        self._pending_ft8_scroll_wall_ms = None

    def _next_ft8_scroll_wall_ms(self) -> int | None:
        if not self._is_ft8_page(self.store.snapshot):
            return None
        metrics = ft8_scroll_metrics(self.store.snapshot, _station_callsign(self.store.snapshot))
        if not metrics.active:
            return None
        base = self._ft8_scroll_wall_ms
        if base is None:
            ft8 = self.store.snapshot.get("ft8") if isinstance(self.store.snapshot.get("ft8"), dict) else {}
            display = ft8.get("_display") if isinstance(ft8.get("_display"), dict) else {}
            anchor_time = display.get("scrollAnchorTimeMs")
            base = int(anchor_time) if isinstance(anchor_time, (int, float)) else self._wall_ms()
        return base + metrics.dwell_ms

    def _commit_pending_ft8_scroll(self) -> None:
        if self._pending_ft8_scroll_wall_ms is None:
            return
        self._commit_ft8_scroll(self._pending_ft8_scroll_wall_ms, time.monotonic())
        self._pending_ft8_scroll_wall_ms = None

    def _commit_ft8_scroll(self, scroll_wall_ms: int, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        metrics = ft8_scroll_metrics(self.store.snapshot, _station_callsign(self.store.snapshot))
        self._ft8_scroll_wall_ms = scroll_wall_ms
        self._next_ft8_scroll_at = now + metrics.dwell_ms / 1000 if metrics.active else None

    def _inject_ft8_scroll_clock(self, snapshot: dict, scroll_wall_ms: int | None = None) -> None:
        if not self._is_ft8_page(snapshot):
            return
        metrics = ft8_scroll_metrics(snapshot, _station_callsign(snapshot))
        if not metrics.active:
            return
        ft8 = snapshot.get("ft8") if isinstance(snapshot.get("ft8"), dict) else None
        if ft8 is None:
            return
        display = ft8.get("_display") if isinstance(ft8.get("_display"), dict) else {}
        live_scroll_at = scroll_wall_ms if scroll_wall_ms is not None else self._ft8_scroll_wall_ms
        if live_scroll_at is None:
            return
        ft8["_display"] = {**display, "renderScrollAtMs": int(live_scroll_at)}

    def _loop_sleep_seconds(self, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        deadlines = [self._next_second_deadline(now)]
        if self._pending_ft8_scroll_wall_ms is not None:
            deadlines.append(now + self.min_loop_sleep)
        if self._is_access_page(self.store.snapshot):
            deadlines.append(max(now, self._next_access_animation_at))
        else:
            self._sync_ft8_scroll_timeline(now)
            if self._next_ft8_scroll_at is not None:
                deadlines.append(self._next_ft8_scroll_at)
        delay = min(deadlines) - now
        return max(self.min_loop_sleep, min(self.max_loop_sleep, delay))

    def _next_second_deadline(self, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        wall_ms = self._wall_ms(now)
        next_second_ms = ((wall_ms // 1000) + 1) * 1000
        return self._monotonic_origin + (next_second_ms - self._wall_origin_ms) / 1000

    def _wall_ms(self, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        return int(self._wall_origin_ms + (now - self._monotonic_origin) * 1000)


def _is_ptt_active(snapshot: dict) -> bool:
    radio = snapshot.get("radio") or {}
    return bool(radio.get("ptt"))


def _station_callsign(snapshot: dict) -> str | None:
    station = snapshot.get("station") if isinstance(snapshot.get("station"), dict) else {}
    callsign = station.get("callsign")
    return callsign.strip().upper() if isinstance(callsign, str) and callsign.strip() else None
