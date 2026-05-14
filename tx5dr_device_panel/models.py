from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


DISPLAY_WIDTH = 128
DISPLAY_HEIGHT = 64


@dataclass(frozen=True)
class DrawCommand:
    kind: Literal["text", "line", "rect", "filled_rect", "bar_graph", "invert_region"]
    x: int = 0
    y: int = 0
    x2: int | None = None
    y2: int | None = None
    text: str | None = None
    value: float | None = None
    width: int | None = None
    height: int | None = None
    fill: int = 1
    font_size: int | None = None


@dataclass
class RenderFrame:
    width: int = DISPLAY_WIDTH
    height: int = DISPLAY_HEIGHT
    commands: list[DrawCommand] = field(default_factory=list)

    def add(self, command: DrawCommand) -> None:
        self.commands.append(command)

    def text(self, x: int, y: int, text: str, fill: int = 1, font_size: int | None = None) -> None:
        self.add(DrawCommand("text", x=x, y=y, text=text, fill=fill, font_size=font_size))

    def line(self, x: int, y: int, x2: int, y2: int, fill: int = 1) -> None:
        self.add(DrawCommand("line", x=x, y=y, x2=x2, y2=y2, fill=fill))

    def rect(self, x: int, y: int, x2: int, y2: int, fill: int = 1) -> None:
        self.add(DrawCommand("rect", x=x, y=y, x2=x2, y2=y2, fill=fill))

    def filled_rect(self, x: int, y: int, x2: int, y2: int, fill: int = 1) -> None:
        self.add(DrawCommand("filled_rect", x=x, y=y, x2=x2, y2=y2, fill=fill))

    def bar_graph(self, x: int, y: int, width: int, height: int, value: float) -> None:
        self.add(DrawCommand("bar_graph", x=x, y=y, width=width, height=height, value=value))

    def invert_region(self, x: int, y: int, x2: int, y2: int) -> None:
        self.add(DrawCommand("invert_region", x=x, y=y, x2=x2, y2=y2))


Snapshot = dict[str, Any]


DEFAULT_SNAPSHOT: Snapshot = {
    "server": {"status": "ok", "version": "unknown", "webPort": None},
    "station": {"callsign": None, "callsigns": []},
    "operators": [],
    "engine": {"running": False, "mode": None, "currentMode": None, "state": None},
    "radio": {"connected": False, "frequency": None, "radioMode": None, "ptt": False, "tx": False},
    "ft8": {
        "slot": None,
        "utc": None,
        "cycle": None,
        "periodMs": None,
        "recentDecodeRawMessages": [],
        "lastDecodeRawMessage": None,
        "recentFramesSlotId": None,
        "recentFramesSlotStartMs": None,
        "recentFrames": [],
        "currentTx": {
            "active": False,
            "operatorIds": [],
            "messages": [],
            "lastMessage": None,
            "slotStartMs": None,
        },
    },
    "voice": {
        "active": False,
        "radioMode": None,
        "pttLocked": False,
        "pttLockedByLabel": None,
        "keyerActive": False,
        "keyerMode": None,
        "keyerSlotId": None,
    },
    "cw": {
        "active": False,
        "decoder": {
            "enabled": False,
            "active": False,
            "state": "disabled",
            "muted": False,
            "committedText": "",
            "pendingText": "",
            "lastDecodeAt": None,
            "updatedAt": 0,
        },
        "keyer": {
            "active": False,
            "mode": None,
            "messageId": None,
            "currentText": None,
            "lastText": None,
        },
        "currentTx": {
            "active": False,
            "messages": [],
            "lastMessage": None,
        },
    },
    "access": {"localUrl": None, "localUrls": []},
    "network": {
        "connected": False,
        "interface": None,
        "ip": None,
        "ssid": None,
        "hotspot": False,
        "transport": "unknown",
        "source": "default",
        "details": {},
    },
    "updatedAt": 0,
}
