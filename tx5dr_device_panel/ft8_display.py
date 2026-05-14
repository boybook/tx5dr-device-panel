from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Any


FT8_VISIBLE_ROWS = 4
FT8_MIN_DWELL_MS = 250
FT8_MAX_DWELL_MS = 2500
FT8_DEFAULT_PERIOD_MS = 15_000
FT4_DEFAULT_PERIOD_MS = 7_500


@dataclass(frozen=True)
class Ft8ScrollMetrics:
    active: bool
    dwell_ms: int


def entry_message(entry: Any) -> str:
    if isinstance(entry, dict):
        message = entry.get("message")
        return message if isinstance(message, str) else ""
    return str(entry) if entry is not None else ""


def normalize_message(value: str) -> str:
    return " ".join(value.split()).upper()


def ft8_period_ms(snapshot: dict[str, Any]) -> int:
    ft8 = snapshot.get("ft8") if isinstance(snapshot.get("ft8"), dict) else {}
    period = ft8.get("periodMs")
    if isinstance(period, (int, float)) and period > 0:
        return int(period)

    engine = snapshot.get("engine") if isinstance(snapshot.get("engine"), dict) else {}
    current_mode = engine.get("currentMode") if isinstance(engine.get("currentMode"), dict) else {}
    slot_ms = current_mode.get("slotMs")
    if isinstance(slot_ms, (int, float)) and slot_ms > 0:
        return int(slot_ms)

    mode_name = str(current_mode.get("name") or engine.get("mode") or "").upper()
    return FT4_DEFAULT_PERIOD_MS if "FT4" in mode_name else FT8_DEFAULT_PERIOD_MS


def scroll_step(item_count: int, rows: int = FT8_VISIBLE_ROWS) -> int:
    if item_count <= 8:
        configured = 1
    elif item_count <= 16:
        configured = 2
    else:
        configured = 4
    return max(1, min(configured, max(1, rows)))


def scroll_starts(item_count: int, rows: int) -> list[int]:
    if item_count <= rows or rows <= 0:
        return [0]
    max_start = max(0, item_count - rows)
    step = scroll_step(item_count, rows)
    starts = list(range(0, max_start + 1, step))
    if starts[-1] != max_start:
        starts.append(max_start)
    return starts


def scroll_dwell_ms(snapshot: dict[str, Any], item_count: int, rows: int = FT8_VISIBLE_ROWS) -> int:
    starts = scroll_starts(item_count, rows)
    if len(starts) <= 1:
        return FT8_MAX_DWELL_MS
    budget = ft8_period_ms(snapshot) * 0.5
    dwell = int(budget / len(starts))
    return max(FT8_MIN_DWELL_MS, min(FT8_MAX_DWELL_MS, dwell))


def scroll_start_index(
    snapshot: dict[str, Any],
    item_count: int,
    rows: int,
    *,
    default_start: int = 0,
) -> int:
    starts = scroll_starts(item_count, rows)
    if len(starts) <= 1:
        return 0

    ft8 = snapshot.get("ft8") if isinstance(snapshot.get("ft8"), dict) else {}
    display = ft8.get("_display") if isinstance(ft8.get("_display"), dict) else {}
    render_scroll_at = display.get("renderScrollAtMs")
    updated_at = render_scroll_at if isinstance(render_scroll_at, (int, float)) else snapshot.get("updatedAt")
    anchor_time = display.get("scrollAnchorTimeMs")
    anchor_index = display.get("scrollAnchorIndex")
    if not isinstance(updated_at, (int, float)) or not isinstance(anchor_time, (int, float)):
        return min(max(0, default_start), starts[-1])

    start_at = int(anchor_index) if isinstance(anchor_index, (int, float)) else default_start
    start_at = min(max(0, start_at), starts[-1])
    elapsed = max(0, int(updated_at - anchor_time))
    advanced = floor(elapsed / scroll_dwell_ms(snapshot, item_count, rows)) * scroll_step(
        item_count,
        rows,
    )
    return min(starts[-1], start_at + advanced)


def ft8_display_entries(snapshot: dict[str, Any]) -> list[Any]:
    ft8 = snapshot.get("ft8") if isinstance(snapshot.get("ft8"), dict) else {}
    frames = ft8.get("recentFrames")
    if isinstance(frames, list) and frames:
        return [entry for entry in frames if entry_message(entry)]
    messages = ft8.get("recentDecodeRawMessages")
    if isinstance(messages, list):
        return [message for message in messages if entry_message(message)]
    return []


def is_own_entry(entry: Any, own_callsign: str | None) -> bool:
    own = (own_callsign or "").strip().upper()
    return bool(own and own in entry_message(entry).upper())


def ft8_scroll_metrics(snapshot: dict[str, Any], own_callsign: str | None = None) -> Ft8ScrollMetrics:
    entries = ft8_display_entries(snapshot)
    own_entries = [entry for entry in entries if is_own_entry(entry, own_callsign)]
    if len(own_entries) >= FT8_VISIBLE_ROWS:
        active_count = len(own_entries)
        rows = FT8_VISIBLE_ROWS
    else:
        fixed_rows = len(own_entries)
        rows = FT8_VISIBLE_ROWS - fixed_rows
        active_count = len([entry for entry in entries if not is_own_entry(entry, own_callsign)])

    active = rows > 0 and active_count > rows
    return Ft8ScrollMetrics(
        active=active,
        dwell_ms=scroll_dwell_ms(snapshot, active_count, rows) if active else FT8_MAX_DWELL_MS,
    )
