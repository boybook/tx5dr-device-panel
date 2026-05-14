from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import time
from typing import Any, Callable

from tx5dr_device_panel.ft8_display import entry_message, normalize_message, scroll_start_index
from tx5dr_device_panel.models import DEFAULT_SNAPSHOT, Snapshot


@dataclass
class Ft8DisplayState:
    slot_id: str | None = None
    slot_start_ms: int | float | None = None
    entries: list[Any] = field(default_factory=list)
    first_received_at_ms: int | None = None
    last_batch_signature: tuple[str, ...] = field(default_factory=tuple)
    scroll_anchor_index: int = 0
    scroll_anchor_time_ms: int | None = None


@dataclass
class PanelStore:
    snapshot: Snapshot = field(default_factory=lambda: deepcopy(DEFAULT_SNAPSHOT))
    now_ms: Callable[[], int] = field(default_factory=lambda: lambda: int(time.time() * 1000))
    last_error: str | None = None
    _ft8_display: Ft8DisplayState = field(default_factory=Ft8DisplayState, init=False, repr=False)

    def apply(self, event: dict[str, Any]) -> Snapshot:
        next_snapshot, self.last_error = reduce_event(self.snapshot, event)
        if self.last_error is not None:
            self._ft8_display = Ft8DisplayState()
        elif next_snapshot is not self.snapshot:
            self._apply_ft8_cycle_window(next_snapshot)
        self.snapshot = next_snapshot
        return self.snapshot

    def _apply_ft8_cycle_window(self, snapshot: Snapshot) -> None:
        engine = snapshot.get("engine")
        ft8 = snapshot.get("ft8")
        if (
            isinstance(engine, dict)
            and not engine.get("running")
            and (not isinstance(ft8, dict) or _frame_batch_slot_id(ft8) is None)
        ):
            self._ft8_display = Ft8DisplayState()
            return

        if not isinstance(ft8, dict):
            self._ft8_display = Ft8DisplayState()
            return

        current_ft8 = self.snapshot.get("ft8")
        previous_ft8 = current_ft8 if isinstance(current_ft8, dict) else {}
        frame_slot_id = _frame_batch_slot_id(ft8)
        incoming_entries = _frame_entries(ft8, frame_slot_id)

        if frame_slot_id is None:
            _carry_previous_ft8_display(ft8, previous_ft8)
            _attach_display_metadata(ft8, self._ft8_display)
            return

        if not incoming_entries:
            _carry_previous_ft8_display(ft8, previous_ft8)
            _attach_display_metadata(ft8, self._ft8_display)
            return

        now_ms = self.now_ms()
        batch_signature = _batch_signature(incoming_entries)
        if self._ft8_display.slot_id != frame_slot_id:
            self._ft8_display = Ft8DisplayState(
                slot_id=frame_slot_id,
                slot_start_ms=_slot_start_ms(ft8, incoming_entries),
                entries=_dedupe_entries(incoming_entries),
                first_received_at_ms=now_ms,
                last_batch_signature=batch_signature,
                scroll_anchor_index=0,
                scroll_anchor_time_ms=now_ms,
            )
        else:
            if batch_signature != self._ft8_display.last_batch_signature:
                previous_for_scroll = deepcopy(self.snapshot)
                if isinstance(snapshot.get("updatedAt"), (int, float)):
                    previous_for_scroll["updatedAt"] = snapshot["updatedAt"]
                self._ft8_display.scroll_anchor_index = scroll_start_index(
                    previous_for_scroll,
                    len(self._ft8_display.entries),
                    4,
                )
                self._ft8_display.scroll_anchor_time_ms = now_ms
            self._ft8_display.last_batch_signature = batch_signature
            self._ft8_display.entries = _merge_entries(self._ft8_display.entries, incoming_entries)
            self._ft8_display.slot_start_ms = (
                self._ft8_display.slot_start_ms or _slot_start_ms(ft8, incoming_entries)
            )

        _apply_ft8_display_state(ft8, self._ft8_display)


def reduce_event(current: Snapshot, event: dict[str, Any]) -> tuple[Snapshot, str | None]:
    event_type = event.get("type")
    if event_type in {"snapshot", "bootstrap"} and isinstance(event.get("payload"), dict):
        next_snapshot = _deep_merge(DEFAULT_SNAPSHOT, event["payload"])
        return next_snapshot, None
    if event_type == "error":
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        return _offline_snapshot(current), str(payload.get("message") or "Unknown server error")
    return current, None


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _offline_snapshot(current: Snapshot) -> Snapshot:
    snapshot = deepcopy(DEFAULT_SNAPSHOT)
    access = current.get("access")
    if isinstance(access, dict):
        snapshot["access"] = _deep_merge(snapshot["access"], access)
    network = current.get("network")
    if isinstance(network, dict):
        snapshot["network"] = _deep_merge(snapshot["network"], network)
    return snapshot


def _frame_batch_slot_id(ft8: dict[str, Any]) -> str | None:
    slot_id = ft8.get("recentFramesSlotId")
    if isinstance(slot_id, str) and slot_id:
        return slot_id
    frames = ft8.get("recentFrames")
    if isinstance(frames, list) and frames:
        frame = frames[0]
        if isinstance(frame, dict):
            frame_slot_id = frame.get("slotId")
            if isinstance(frame_slot_id, str) and frame_slot_id:
                return frame_slot_id
    return None


def _frame_entries(ft8: dict[str, Any], slot_id: str | None) -> list[Any]:
    frames = ft8.get("recentFrames")
    if isinstance(frames, list):
        return [deepcopy(frame) for frame in frames if entry_message(frame)]
    messages = ft8.get("recentDecodeRawMessages")
    if not isinstance(messages, list) or not slot_id:
        return []
    return [{"slotId": slot_id, "message": message} for message in messages if entry_message(message)]


def _slot_start_ms(ft8: dict[str, Any], entries: list[Any]) -> int | float | None:
    value = ft8.get("recentFramesSlotStartMs")
    if isinstance(value, (int, float)):
        return value
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("slotStartMs"), (int, float)):
            return entry["slotStartMs"]
    return None


def _batch_signature(entries: list[Any]) -> tuple[str, ...]:
    return tuple(normalize_message(entry_message(entry)) for entry in entries if entry_message(entry))


def _dedupe_entries(entries: list[Any]) -> list[Any]:
    return _merge_entries([], entries)


def _merge_entries(existing: list[Any], incoming: list[Any]) -> list[Any]:
    merged: list[Any] = []
    positions: dict[str, int] = {}
    for entry in [*existing, *incoming]:
        key = normalize_message(entry_message(entry))
        if not key:
            continue
        if key in positions:
            merged[positions[key]] = _merge_entry(merged[positions[key]], entry)
        else:
            positions[key] = len(merged)
            merged.append(deepcopy(entry))
    return merged


def _merge_entry(existing: Any, incoming: Any) -> Any:
    if not isinstance(existing, dict) or not isinstance(incoming, dict):
        return deepcopy(existing if _entry_score(existing) >= _entry_score(incoming) else incoming)

    base = deepcopy(incoming if _entry_score(incoming) > _entry_score(existing) else existing)
    other = existing if base == incoming else incoming
    for key in (
        "slotId",
        "slotStartMs",
        "snr",
        "freq",
        "dt",
        "message",
        "operatorId",
        "country",
        "countryZh",
        "countryEn",
        "countryCode",
    ):
        if _has_value(base.get(key)):
            continue
        value = other.get(key)
        if _has_value(value):
            base[key] = deepcopy(value)
    return base


def _entry_score(entry: Any) -> float:
    if not isinstance(entry, dict):
        return 1 if entry_message(entry) else 0
    score = 1 if entry_message(entry) else 0
    for key in ("countryZh", "countryEn", "country", "countryCode"):
        if _has_value(entry.get(key)):
            score += 4
    for key in ("freq", "dt", "operatorId", "slotStartMs"):
        if _has_value(entry.get(key)):
            score += 1
    snr = entry.get("snr")
    if isinstance(snr, (int, float)):
        score += 1 + max(-50, min(50, snr)) / 100
    return score


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value)
    return True


def _apply_ft8_display_state(ft8: dict[str, Any], state: Ft8DisplayState) -> None:
    messages = [entry_message(entry) for entry in state.entries if entry_message(entry)]
    ft8["recentFrames"] = deepcopy(state.entries)
    ft8["recentFramesSlotId"] = state.slot_id
    ft8["recentFramesSlotStartMs"] = state.slot_start_ms
    ft8["recentDecodeRawMessages"] = messages
    ft8["lastDecodeRawMessage"] = messages[-1] if messages else None
    _attach_display_metadata(ft8, state)


def _attach_display_metadata(ft8: dict[str, Any], state: Ft8DisplayState) -> None:
    ft8["_display"] = {
        "slotId": state.slot_id,
        "firstReceivedAtMs": state.first_received_at_ms,
        "scrollAnchorIndex": state.scroll_anchor_index,
        "scrollAnchorTimeMs": state.scroll_anchor_time_ms,
        "uniqueCount": len(state.entries),
    }


def _carry_previous_ft8_display(ft8: dict[str, Any], previous_ft8: dict[str, Any]) -> None:
    previous_frames = previous_ft8.get("recentFrames")
    previous_messages = previous_ft8.get("recentDecodeRawMessages")
    ft8["recentFrames"] = deepcopy(previous_frames if isinstance(previous_frames, list) else [])
    ft8["recentFramesSlotId"] = previous_ft8.get("recentFramesSlotId")
    ft8["recentFramesSlotStartMs"] = previous_ft8.get("recentFramesSlotStartMs")
    ft8["recentDecodeRawMessages"] = deepcopy(
        previous_messages if isinstance(previous_messages, list) else []
    )
    ft8["lastDecodeRawMessage"] = previous_ft8.get("lastDecodeRawMessage")
