from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from tx5dr_device_panel.models import DEFAULT_SNAPSHOT, Snapshot


@dataclass
class PanelStore:
    snapshot: Snapshot = field(default_factory=lambda: deepcopy(DEFAULT_SNAPSHOT))
    last_error: str | None = None
    _displayed_frame_slot_id: str | None = field(default=None, init=False, repr=False)

    def apply(self, event: dict[str, Any]) -> Snapshot:
        next_snapshot, self.last_error = reduce_event(self.snapshot, event)
        if next_snapshot is not self.snapshot and self.last_error is None:
            self._apply_ft8_cycle_window(next_snapshot)
        self.snapshot = next_snapshot
        return self.snapshot

    def _apply_ft8_cycle_window(self, snapshot: Snapshot) -> None:
        ft8 = snapshot.get("ft8")
        if not isinstance(ft8, dict):
            self._displayed_frame_slot_id = None
            return

        current_ft8 = self.snapshot.get("ft8")
        previous_ft8 = current_ft8 if isinstance(current_ft8, dict) else {}
        frame_slot_id = _frame_batch_slot_id(ft8)
        frame_messages = _frame_messages(ft8.get("recentFrames"))

        if frame_slot_id is None:
            _carry_previous_ft8_display(ft8, previous_ft8)
            return

        self._displayed_frame_slot_id = frame_slot_id
        if frame_messages:
            ft8["recentDecodeRawMessages"] = frame_messages
            ft8["lastDecodeRawMessage"] = frame_messages[-1]
        else:
            _carry_previous_ft8_display(ft8, previous_ft8)


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


def _frame_messages(frames: Any) -> list[str]:
    if not isinstance(frames, list):
        return []
    messages: list[str] = []
    for frame in frames:
        if isinstance(frame, dict):
            message = frame.get("message")
            if isinstance(message, str) and message:
                messages.append(message)
    return messages


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
