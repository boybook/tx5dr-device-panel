from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tx5dr_device_panel.models import RenderFrame, Snapshot


STATUS_BAR_BOTTOM = 9
STATUS_BAR_LEFT_X = 2
STATUS_BAR_RIGHT_X = 126
STATUS_BAR_LEFT_WIDTH = 54
STATUS_BAR_RIGHT_MIN_X = 58


@dataclass(frozen=True)
class StatusBar:
    left: str
    right: str
    ptt_active: bool = False


def render_status_bar(frame: RenderFrame, snapshot: Snapshot, page: str, ptt_active: bool) -> None:
    status = build_status_bar(snapshot, page, ptt_active)
    fill = 0 if status.ptt_active else 1
    frame.filled_rect(0, 0, 127, STATUS_BAR_BOTTOM, fill=1 if status.ptt_active else 0)
    frame.line(0, STATUS_BAR_BOTTOM, 127, STATUS_BAR_BOTTOM, fill=1)
    frame.text(STATUS_BAR_LEFT_X, 1, _clip_to_width(status.left, STATUS_BAR_LEFT_WIDTH), fill=fill)
    _right_text(frame, STATUS_BAR_RIGHT_X, 1, _clip_to_width(status.right, _right_width()), fill=fill)


def build_status_bar(snapshot: Snapshot, page: str, ptt_active: bool) -> StatusBar:
    return StatusBar(
        left=f"UTC {_utc_text(snapshot)}",
        right=_right_label(snapshot, page),
        ptt_active=ptt_active,
    )


def format_frequency(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "--.---"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.3f}"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return str(value)


def _right_label(snapshot: Snapshot, page: str) -> str:
    if page == "access":
        return "ACCESS"
    radio = snapshot.get("radio") or {}
    mode = _display_mode(snapshot, page)
    frequency = format_frequency(radio.get("frequency"))
    return mode if frequency == "--.---" else f"{mode}·{frequency}"


def _display_mode(snapshot: Snapshot, page: str) -> str:
    if page == "ft8":
        ft8 = snapshot.get("ft8") or {}
        slot = ft8.get("slot") or {}
        if isinstance(slot, dict) and slot.get("mode"):
            return str(slot["mode"]).upper()
        return _mode_name(snapshot).upper() or "FT8"
    if page == "voice":
        radio = snapshot.get("radio") or {}
        voice = snapshot.get("voice") or {}
        return str(voice.get("radioMode") or radio.get("radioMode") or _mode_name(snapshot) or "VOICE").upper()
    return page.upper()


def _mode_name(snapshot: Snapshot) -> str:
    engine = snapshot.get("engine") or {}
    current = engine.get("currentMode") or {}
    if isinstance(current, dict) and current.get("name"):
        return str(current["name"])
    return str(engine.get("mode") or "")


def _utc_text(snapshot: Snapshot) -> str:
    updated_at = snapshot.get("updatedAt")
    if isinstance(updated_at, (int, float)) and updated_at > 0:
        total_seconds = int(updated_at / 1000) % 86_400
        return f"{total_seconds // 3600:02d}:{(total_seconds // 60) % 60:02d}:{total_seconds % 60:02d}"
    return "--:--:--"


def _right_width() -> int:
    return STATUS_BAR_RIGHT_X - STATUS_BAR_RIGHT_MIN_X


def _right_text(frame: RenderFrame, right_x: int, y: int, text: str, fill: int = 1) -> None:
    frame.text(max(STATUS_BAR_RIGHT_MIN_X, right_x - _text_width(text)), y, text, fill=fill)


def _clip_to_width(value: str, max_width: int) -> str:
    if _text_width(value) <= max_width:
        return value
    marker = ">"
    marker_width = _text_width(marker)
    if max_width <= marker_width:
        return ""
    result = ""
    for char in value:
        if _text_width(result + char) > max_width - marker_width:
            break
        result += char
    return result + marker


def _text_width(text: str) -> int:
    return sum(8 if ord(char) > 127 else 4 for char in text)
