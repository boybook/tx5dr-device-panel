from __future__ import annotations

import logging
import os


LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
LOG_LEVEL_ENV = "TX5DR_PANEL_LOG_LEVEL"


def resolve_log_level(cli_value: str | None = None) -> str:
    value = cli_value or os.getenv(LOG_LEVEL_ENV) or "INFO"
    normalized = value.strip().upper()
    return normalized if normalized in LOG_LEVELS else "INFO"


def configure_logging(level: str | None = None) -> str:
    resolved = resolve_log_level(level)
    logging.basicConfig(
        level=getattr(logging, resolved),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    return resolved
