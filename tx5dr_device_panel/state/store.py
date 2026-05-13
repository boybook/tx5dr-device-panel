from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from tx5dr_device_panel.models import DEFAULT_SNAPSHOT, Snapshot


@dataclass
class PanelStore:
    snapshot: Snapshot = field(default_factory=lambda: deepcopy(DEFAULT_SNAPSHOT))
    last_error: str | None = None

    def apply(self, event: dict[str, Any]) -> Snapshot:
        self.snapshot, self.last_error = reduce_event(self.snapshot, event)
        return self.snapshot


def reduce_event(current: Snapshot, event: dict[str, Any]) -> tuple[Snapshot, str | None]:
    event_type = event.get("type")
    if event_type in {"snapshot", "bootstrap"} and isinstance(event.get("payload"), dict):
        next_snapshot = _deep_merge(DEFAULT_SNAPSHOT, event["payload"])
        return next_snapshot, None
    if event_type == "error":
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        return current, str(payload.get("message") or "Unknown server error")
    return current, None


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result
