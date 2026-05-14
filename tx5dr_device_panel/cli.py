from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from tx5dr_device_panel.config import load_config
from tx5dr_device_panel.live import LivePanelRunner
from tx5dr_device_panel.logging_config import LOG_LEVELS, configure_logging
from tx5dr_device_panel.render.preview import run_preview
from tx5dr_device_panel.render.snapshot import render_fixture_to_png

logger = logging.getLogger("tx5dr.panel.cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tx5dr-device-panel")
    parser.add_argument("--config")
    parser.add_argument("--server-url")
    parser.add_argument("--device-id")
    parser.add_argument("--token-file")
    parser.add_argument("--backend", choices=["preview", "oled", "snapshot"])
    parser.add_argument("--scale", type=int)
    parser.add_argument("--font-path")
    parser.add_argument("--font-size", type=int)
    parser.add_argument("--language", choices=["zh", "en"], help="Global panel UI language")
    parser.add_argument("--controller", choices=["ssd1306", "sh1106"])
    parser.add_argument("--protocol", choices=["i2c", "spi"])
    parser.add_argument("--log-level", choices=LOG_LEVELS, type=str.upper, help="Logging level")
    sub = parser.add_subparsers(dest="command", required=True)

    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("--fixture", required=True)
    snapshot.add_argument("--output", required=True)

    preview = sub.add_parser("preview")
    preview.add_argument("--fixture", action="append", required=True)

    sub.add_parser("live")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    log_level = configure_logging(getattr(args, "log_level", None))
    config = load_config(args)
    logger.info(
        "Device panel command=%s log_level=%s backend=%s server=%s device_id=%s token_file=%s",
        args.command,
        log_level,
        config.display.backend,
        config.server.base_url,
        config.server.device_id,
        config.server.token_file,
    )

    if args.command == "snapshot":
        logger.info("Rendering snapshot fixture=%s output=%s", args.fixture, args.output)
        render_fixture_to_png(
            Path(args.fixture),
            Path(args.output),
            font_path=config.display.font_path,
            font_size=config.display.font_size,
            language=config.language,
        )
        return 0
    if args.command == "preview":
        logger.info("Starting fixture preview fixtures=%s scale=%s", args.fixture, config.display.scale)
        run_preview(
            [Path(item) for item in args.fixture],
            scale=config.display.scale,
            font_path=config.display.font_path,
            font_size=config.display.font_size,
            language=config.language,
        )
        return 0
    if args.command == "live":
        logger.info("Starting live panel")
        asyncio.run(_live(config))
        return 0
    parser.error("unknown command")
    return 2


async def _live(config) -> None:
    await LivePanelRunner(config).run()
