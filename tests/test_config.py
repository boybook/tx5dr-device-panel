import argparse

from tx5dr_device_panel.config import load_config


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
        controller="sh1106",
        protocol="spi",
    )

    config = load_config(args)

    assert config.server.base_url == "http://server:8076"
    assert config.server.device_id == "panel-x"
    assert config.display.backend == "snapshot"
    assert config.display.font_path == "/tmp/fusion-pixel-8px-monospaced-zh_hans.ttf"
    assert config.display.font_size == 8
    assert config.hardware.controller == "sh1106"
    assert config.hardware.protocol == "spi"
