from __future__ import annotations


class GpioButtons:
    """Future extension point; MVP is display-only and never mutates server state."""

    def poll(self) -> None:
        return None
