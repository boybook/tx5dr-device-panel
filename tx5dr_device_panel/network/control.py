from __future__ import annotations

import platform
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class WifiNetwork:
    ssid: str
    signal: int | None = None
    security: str | None = None


@dataclass(frozen=True)
class NetworkControlResult:
    ok: bool
    action: str
    code: str
    message: str
    networks: list[WifiNetwork] = field(default_factory=list)


class NetworkController(Protocol):
    async def scan_wifi(self) -> NetworkControlResult:
        ...

    async def connect_wifi(self, ssid: str, password: str) -> NetworkControlResult:
        ...

    async def disconnect_wifi(self) -> NetworkControlResult:
        ...

    async def start_hotspot(self, ssid: str, password: str) -> NetworkControlResult:
        ...

    async def stop_hotspot(self) -> NetworkControlResult:
        ...


def get_network_controller(system: str | None = None) -> NetworkController:
    if (system or platform.system()).lower() != "linux":
        return UnsupportedNetworkController("unsupported_platform")
    try:
        from tx5dr_device_panel.network.providers.networkmanager import NetworkManagerController
    except Exception:
        return UnsupportedNetworkController("missing_networkmanager_provider")
    return NetworkManagerController()


class UnsupportedNetworkController:
    def __init__(self, code: str = "unsupported") -> None:
        self.code = code

    async def scan_wifi(self) -> NetworkControlResult:
        return self._result("scan_wifi")

    async def connect_wifi(self, ssid: str, password: str) -> NetworkControlResult:
        return self._result("connect_wifi")

    async def disconnect_wifi(self) -> NetworkControlResult:
        return self._result("disconnect_wifi")

    async def start_hotspot(self, ssid: str, password: str) -> NetworkControlResult:
        return self._result("start_hotspot")

    async def stop_hotspot(self) -> NetworkControlResult:
        return self._result("stop_hotspot")

    def _result(self, action: str) -> NetworkControlResult:
        return NetworkControlResult(
            ok=False,
            action=action,
            code=self.code,
            message="Network control is only supported on Linux with NetworkManager.",
        )


def validate_ssid(ssid: str) -> str | None:
    if not ssid or not ssid.strip():
        return "SSID is required."
    encoded = ssid.encode("utf-8")
    if len(encoded) > 32:
        return "SSID must be 32 bytes or fewer."
    return None


def validate_wifi_password(password: str) -> str | None:
    if not password:
        return "Wi-Fi password is required."
    if not 8 <= len(password) <= 63:
        return "Wi-Fi password must be between 8 and 63 characters."
    return None
