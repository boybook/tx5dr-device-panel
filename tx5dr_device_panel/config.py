from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from tx5dr_device_panel.fonts import (
    DEFAULT_FUSION_PIXEL_FONT_PATH,
    DEFAULT_FUSION_PIXEL_FONT_SIZE,
)


DEFAULT_CONFIG_PATH = Path("/etc/tx5dr/device-panel.yaml")
DEV_CONFIG_PATH = Path("./device-panel.dev.yaml")


@dataclass(frozen=True)
class ServerConfig:
    base_url: str = "http://127.0.0.1:8076"
    device_id: str = "tx5dr-oled-panel"
    token_file: str = ".device-ui-token"
    reconnect_seconds: float = 2.0


@dataclass(frozen=True)
class DisplayConfig:
    width: int = 128
    height: int = 64
    backend: str = "preview"
    scale: int = 4
    font_path: str = DEFAULT_FUSION_PIXEL_FONT_PATH
    font_size: int = DEFAULT_FUSION_PIXEL_FONT_SIZE


@dataclass(frozen=True)
class HardwareConfig:
    controller: str = "ssd1306"
    protocol: str = "i2c"
    i2c_bus: int = 1
    i2c_address: int = 0x3C
    spi_port: int = 0
    spi_device: int = 0
    spi_dc: int = 24
    spi_rst: int | None = 25
    spi_cs: int | None = None
    sh1106_column_offset: int = 2


@dataclass(frozen=True)
class PanelConfig:
    server: ServerConfig = ServerConfig()
    display: DisplayConfig = DisplayConfig()
    hardware: HardwareConfig = HardwareConfig()
    language: str = "zh"


def load_config(args: argparse.Namespace | None = None) -> PanelConfig:
    config_value = getattr(args, "config", None) or os.getenv("TX5DR_PANEL_CONFIG")
    config_path = Path(config_value) if config_value else None
    data: dict[str, Any] = {}
    if config_path:
        data = _load_yaml(config_path)
    elif DEV_CONFIG_PATH.exists():
        data = _load_yaml(DEV_CONFIG_PATH)
    elif DEFAULT_CONFIG_PATH.exists():
        data = _load_yaml(DEFAULT_CONFIG_PATH)

    config = _from_mapping(data)
    config = _apply_env(config)
    config = _apply_cli(config, args)
    return config


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Config file must be a mapping: {path}")
    return loaded


def _from_mapping(data: dict[str, Any]) -> PanelConfig:
    server = ServerConfig(**{**ServerConfig().__dict__, **(data.get("server") or {})})
    display = DisplayConfig(**{**DisplayConfig().__dict__, **(data.get("display") or {})})
    hardware = HardwareConfig(**{**HardwareConfig().__dict__, **(data.get("hardware") or {})})
    language = str(data.get("language") or PanelConfig().language)
    return PanelConfig(server=server, display=display, hardware=hardware, language=language)


def _apply_env(config: PanelConfig) -> PanelConfig:
    server = config.server
    display = config.display
    hardware = config.hardware
    language = config.language
    if value := os.getenv("TX5DR_PANEL_SERVER_URL"):
        server = replace(server, base_url=value)
    if value := os.getenv("TX5DR_PANEL_DEVICE_ID"):
        server = replace(server, device_id=value)
    if value := os.getenv("TX5DR_PANEL_TOKEN_FILE"):
        server = replace(server, token_file=value)
    if value := os.getenv("TX5DR_PANEL_BACKEND"):
        display = replace(display, backend=value)
    if value := os.getenv("TX5DR_PANEL_FONT_PATH"):
        display = replace(display, font_path=value)
    if value := os.getenv("TX5DR_PANEL_FONT_SIZE"):
        display = replace(display, font_size=int(value))
    if value := os.getenv("TX5DR_PANEL_LANGUAGE"):
        language = value
    if value := os.getenv("TX5DR_PANEL_CONTROLLER"):
        hardware = replace(hardware, controller=value)
    if value := os.getenv("TX5DR_PANEL_PROTOCOL"):
        hardware = replace(hardware, protocol=value)
    return PanelConfig(server=server, display=display, hardware=hardware, language=language)


def _apply_cli(config: PanelConfig, args: argparse.Namespace | None) -> PanelConfig:
    if args is None:
        return config
    server = config.server
    display = config.display
    hardware = config.hardware
    language = config.language
    if getattr(args, "server_url", None):
        server = replace(server, base_url=args.server_url)
    if getattr(args, "device_id", None):
        server = replace(server, device_id=args.device_id)
    if getattr(args, "token_file", None):
        server = replace(server, token_file=args.token_file)
    if getattr(args, "backend", None):
        display = replace(display, backend=args.backend)
    if getattr(args, "scale", None):
        display = replace(display, scale=args.scale)
    if getattr(args, "font_path", None):
        display = replace(display, font_path=args.font_path)
    if getattr(args, "font_size", None):
        display = replace(display, font_size=args.font_size)
    if getattr(args, "language", None):
        language = args.language
    if getattr(args, "controller", None):
        hardware = replace(hardware, controller=args.controller)
    if getattr(args, "protocol", None):
        hardware = replace(hardware, protocol=args.protocol)
    return PanelConfig(server=server, display=display, hardware=hardware, language=language)
