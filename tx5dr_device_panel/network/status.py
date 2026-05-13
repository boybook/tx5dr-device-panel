from __future__ import annotations

import os
import socket
import subprocess
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class NetworkStatus:
    connected: bool
    interface: str | None
    ip: str | None
    ssid: str | None
    hotspot: bool = False


def read_network_status() -> dict[str, object]:
    ip = _local_ip()
    return asdict(
        NetworkStatus(
            connected=ip is not None,
            interface=_default_interface(),
            ip=ip,
            ssid=_ssid(),
            hotspot=False,
        )
    )


def _local_ip() -> str | None:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
        finally:
            sock.close()
    except OSError:
        return None


def _default_interface() -> str | None:
    if os.path.exists("/proc/net/route"):
        try:
            with open("/proc/net/route", "r", encoding="utf-8") as handle:
                for line in handle.readlines()[1:]:
                    fields = line.split()
                    if len(fields) > 1 and fields[1] == "00000000":
                        return fields[0]
        except OSError:
            return None
    return None


def _ssid() -> str | None:
    airport = (
        "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/"
        "Resources/airport"
    )
    if not os.path.exists(airport):
        return None
    try:
        output = subprocess.check_output([airport, "-I"], text=True, timeout=1)
    except Exception:
        return None
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("SSID:"):
            return stripped.split(":", 1)[1].strip() or None
    return None
