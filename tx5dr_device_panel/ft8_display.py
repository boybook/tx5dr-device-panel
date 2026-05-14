from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import floor
from typing import Any


FT8_VISIBLE_ROWS = 4
FT8_MIN_DWELL_MS = 250
FT8_MAX_DWELL_MS = 2500
FT8_DEFAULT_PERIOD_MS = 15_000
FT4_DEFAULT_PERIOD_MS = 7_500
FT8_CYCLE_HEADER_KIND = "ft8_cycle_header"


@dataclass(frozen=True)
class Ft8ScrollMetrics:
    active: bool
    dwell_ms: int


def entry_message(entry: Any) -> str:
    if isinstance(entry, dict):
        message = entry.get("message")
        return message if isinstance(message, str) else ""
    return str(entry) if entry is not None else ""


def is_cycle_header(entry: Any) -> bool:
    return isinstance(entry, dict) and entry.get("_kind") == FT8_CYCLE_HEADER_KIND


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
    display = ft8.get("_display") if isinstance(ft8.get("_display"), dict) else {}
    entries = display.get("entries")
    if isinstance(entries, list):
        return [entry for entry in entries if entry_message(entry)]

    entries = ft8_decode_entries(snapshot)
    header = ft8_cycle_header_entry(snapshot)
    return [header, *entries] if header else entries


def ft8_decode_entries(snapshot: dict[str, Any]) -> list[Any]:
    ft8 = snapshot.get("ft8") if isinstance(snapshot.get("ft8"), dict) else {}
    frames = ft8.get("recentFrames")
    if isinstance(frames, list) and frames:
        return [entry for entry in frames if entry_message(entry)]
    messages = ft8.get("recentDecodeRawMessages")
    if isinstance(messages, list):
        return [message for message in messages if entry_message(message)]
    return []


def ft8_cycle_header_entry(snapshot: dict[str, Any]) -> dict[str, str] | None:
    label = ft8_cycle_header_label(snapshot)
    return {"_kind": FT8_CYCLE_HEADER_KIND, "message": label} if label else None


def ft8_cycle_header_label(snapshot: dict[str, Any]) -> str:
    ft8 = snapshot.get("ft8") if isinstance(snapshot.get("ft8"), dict) else {}
    time_label = _cycle_time_label(ft8)
    if not time_label:
        return ""

    mode = _cycle_mode_label(snapshot, ft8)
    band = _band_label(snapshot)
    parts = [time_label]
    if band:
        parts.append(band)
    if mode:
        parts.append(mode)
    return " · ".join(parts)


def is_own_entry(entry: Any, own_callsign: str | None) -> bool:
    if is_cycle_header(entry):
        return False
    own = (own_callsign or "").strip().upper()
    return bool(own and own in entry_message(entry).upper())


def ft8_scroll_metrics(snapshot: dict[str, Any], own_callsign: str | None = None) -> Ft8ScrollMetrics:
    entries = ft8_display_entries(snapshot)
    has_header = any(is_cycle_header(entry) for entry in entries)
    own_entries = [entry for entry in entries if is_own_entry(entry, own_callsign)]
    if has_header and own_entries:
        rows_after_header = FT8_VISIBLE_ROWS - 1
        if len(own_entries) >= rows_after_header:
            active_count = len(own_entries)
            rows = rows_after_header
        else:
            rows = rows_after_header - len(own_entries)
            active_count = len([
                entry
                for entry in entries
                if not is_cycle_header(entry) and not is_own_entry(entry, own_callsign)
            ])
    elif len(own_entries) >= FT8_VISIBLE_ROWS:
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


def _cycle_time_label(ft8: dict[str, Any]) -> str:
    slot = ft8.get("slot") if isinstance(ft8.get("slot"), dict) else {}
    for value in (ft8.get("recentFramesSlotStartMs"), slot.get("startMs")):
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, UTC).strftime("%H:%M:%S UTC")
    for value in (ft8.get("utc"), slot.get("utcSeconds")):
        if isinstance(value, (int, float)):
            total_seconds = int(value) % 86_400
            return (
                f"{total_seconds // 3600:02d}:"
                f"{(total_seconds // 60) % 60:02d}:"
                f"{total_seconds % 60:02d} UTC"
            )
    return ""


def _cycle_mode_label(snapshot: dict[str, Any], ft8: dict[str, Any]) -> str:
    slot = ft8.get("slot") if isinstance(ft8.get("slot"), dict) else {}
    if slot.get("mode"):
        return str(slot["mode"]).upper()
    engine = snapshot.get("engine") if isinstance(snapshot.get("engine"), dict) else {}
    current = engine.get("currentMode") if isinstance(engine.get("currentMode"), dict) else {}
    return str(current.get("name") or engine.get("mode") or "FT8").upper()


def _band_label(snapshot: dict[str, Any]) -> str:
    radio = snapshot.get("radio") if isinstance(snapshot.get("radio"), dict) else {}
    frequency = radio.get("frequency")
    if not isinstance(frequency, (int, float)) or frequency <= 0:
        return ""
    mhz = frequency / 1_000_000
    bands = (
        ("160m", 1.8, 2.0),
        ("80m", 3.5, 4.0),
        ("60m", 5.0, 5.5),
        ("40m", 7.0, 7.3),
        ("30m", 10.1, 10.15),
        ("20m", 14.0, 14.35),
        ("17m", 18.068, 18.168),
        ("15m", 21.0, 21.45),
        ("12m", 24.89, 24.99),
        ("10m", 28.0, 29.7),
        ("6m", 50.0, 54.0),
        ("2m", 144.0, 148.0),
        ("70cm", 420.0, 450.0),
    )
    for label, lower, upper in bands:
        if lower <= mhz <= upper:
            return label
    return ""
