from __future__ import annotations

import platform
import socket
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path


Transport = str


@dataclass(frozen=True)
class NetworkStatus:
    connected: bool
    interface: str | None
    ip: str | None
    ssid: str | None
    hotspot: bool = False
    transport: Transport = "unknown"
    source: str = "generic"
    details: dict[str, object] = field(default_factory=dict)


def read_network_status() -> dict[str, object]:
    system = platform.system().lower()
    if system == "darwin":
        return asdict(_darwin_status())
    if system == "linux":
        return asdict(_linux_status())
    return asdict(_generic_status())


def _darwin_status() -> NetworkStatus:
    interface = _darwin_default_interface()
    ip = _darwin_interface_ip(interface) if interface else None
    transport = _darwin_transport(interface) if interface else "unknown"
    ssid = _darwin_ssid(interface) if interface and transport == "wifi" else None
    return NetworkStatus(
        connected=bool(ip),
        interface=interface,
        ip=ip,
        ssid=ssid,
        transport=transport,
        source="darwin",
    )


def _linux_status() -> NetworkStatus:
    interface = _linux_default_interface()
    ip = _linux_interface_ip(interface) if interface else None
    transport = _linux_transport(interface) if interface else "unknown"
    return NetworkStatus(
        connected=bool(ip),
        interface=interface,
        ip=ip,
        ssid=None,
        transport=transport if ip else "unknown",
        source="linux-fallback",
    )


def _generic_status() -> NetworkStatus:
    ip = _local_ip()
    return NetworkStatus(
        connected=ip is not None,
        interface=None,
        ip=ip,
        ssid=None,
        transport="unknown",
        source="generic",
    )


def _darwin_default_interface() -> str | None:
    output = _run_command(["route", "-n", "get", "default"])
    if not output:
        return None
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("interface:"):
            return stripped.split(":", 1)[1].strip() or None
    return None


def _darwin_interface_ip(interface: str) -> str | None:
    return _run_command(["ipconfig", "getifaddr", interface])


def _darwin_transport(interface: str | None) -> Transport:
    if not interface:
        return "unknown"
    for item in _darwin_hardware_ports():
        if item.get("device") != interface:
            continue
        port = str(item.get("port") or "").lower()
        if "wi-fi" in port or "airport" in port:
            return "wifi"
        if "ethernet" in port or "thunderbolt" in port:
            return "wired"
    return _interface_name_transport(interface)


def _darwin_hardware_ports() -> list[dict[str, str]]:
    output = _run_command(["networksetup", "-listallhardwareports"])
    if not output:
        return []
    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in output.splitlines():
        if line.startswith("Hardware Port:"):
            if current:
                entries.append(current)
            current = {"port": line.split(":", 1)[1].strip()}
        elif line.startswith("Device:") and current:
            current["device"] = line.split(":", 1)[1].strip()
    if current:
        entries.append(current)
    return entries


def _darwin_ssid(interface: str) -> str | None:
    output = _run_command(["networksetup", "-getairportnetwork", interface])
    if not output or "not associated" in output.lower():
        return None
    if ":" in output:
        return output.split(":", 1)[1].strip() or None
    return None


def _linux_default_interface(route_path: Path = Path("/proc/net/route")) -> str | None:
    if not route_path.exists():
        return None
    try:
        with route_path.open("r", encoding="utf-8") as handle:
            for line in handle.readlines()[1:]:
                fields = line.split()
                if len(fields) > 1 and fields[1] == "00000000":
                    return fields[0]
    except OSError:
        return None
    return None


def _linux_interface_ip(interface: str) -> str | None:
    output = _run_command(["ip", "-4", "-o", "addr", "show", "dev", interface])
    if output:
        for part in output.split():
            if "/" in part and part.count(".") == 3:
                return part.split("/", 1)[0]
    return _local_ip()


def _linux_transport(interface: str | None, sys_class_net: Path = Path("/sys/class/net")) -> Transport:
    if not interface:
        return "unknown"
    if (sys_class_net / interface / "wireless").exists():
        return "wifi"
    return _interface_name_transport(interface)


def _interface_name_transport(interface: str) -> Transport:
    lowered = interface.lower()
    if lowered.startswith(("wl", "wlan", "wifi")):
        return "wifi"
    if lowered.startswith(("en", "eth")):
        return "wired"
    return "unknown"


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


def _run_command(command: list[str], timeout: float = 1.0) -> str | None:
    try:
        output = subprocess.check_output(command, text=True, stderr=subprocess.DEVNULL, timeout=timeout)
    except Exception:
        return None
    return output.strip() or None
