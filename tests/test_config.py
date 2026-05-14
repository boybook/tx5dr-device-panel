import argparse

from tx5dr_device_panel.config import load_config
from tx5dr_device_panel.cli import build_parser
from tx5dr_device_panel.logging_config import resolve_log_level


def test_cli_overrides_defaults():
    args = argparse.Namespace(
        config=None,
        server_url="http://server:8076",
        device_id="panel-x",
        token_file="/tmp/token",
        backend="snapshot",
        scale=6,
        font_path="/tmp/fusion-pixel-8px-monospaced-zh_hans.ttf",
        font_size=8,
        language="en",
        controller="sh1106",
        protocol="spi",
    )

    config = load_config(args)

    assert config.server.base_url == "http://server:8076"
    assert config.server.device_id == "panel-x"
    assert config.display.backend == "snapshot"
    assert config.display.font_path == "/tmp/fusion-pixel-8px-monospaced-zh_hans.ttf"
    assert config.display.font_size == 8
    assert config.language == "en"
    assert config.hardware.controller == "sh1106"
    assert config.hardware.protocol == "spi"


def test_log_level_defaults_to_info_and_allows_cli_override(monkeypatch):
    monkeypatch.delenv("TX5DR_PANEL_LOG_LEVEL", raising=False)

    parser = build_parser()
    args = parser.parse_args(["--log-level", "debug", "live"])

    assert resolve_log_level(None) == "INFO"
    assert resolve_log_level(args.log_level) == "DEBUG"


def test_log_level_can_come_from_environment(monkeypatch):
    monkeypatch.setenv("TX5DR_PANEL_LOG_LEVEL", "warning")

    assert resolve_log_level(None) == "WARNING"
    assert resolve_log_level("ERROR") == "ERROR"
