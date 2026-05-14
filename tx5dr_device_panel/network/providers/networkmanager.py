from __future__ import annotations

from typing import Any

from tx5dr_device_panel.network.control import (
    NetworkControlResult,
    WifiNetwork,
    validate_ssid,
    validate_wifi_password,
)


class NetworkManagerController:
    def __init__(self, client: NetworkManagerDbusClient | None = None) -> None:
        self.client = client or NetworkManagerDbusClient()

    async def scan_wifi(self) -> NetworkControlResult:
        return await self._run("scan_wifi", self.client.scan_wifi)

    async def connect_wifi(self, ssid: str, password: str) -> NetworkControlResult:
        if error := validate_ssid(ssid):
            return _error("connect_wifi", "invalid_ssid", error)
        if error := validate_wifi_password(password):
            return _error("connect_wifi", "invalid_password", error)
        return await self._run("connect_wifi", self.client.connect_wifi, ssid, password)

    async def disconnect_wifi(self) -> NetworkControlResult:
        return await self._run("disconnect_wifi", self.client.disconnect_wifi)

    async def start_hotspot(self, ssid: str, password: str) -> NetworkControlResult:
        if error := validate_ssid(ssid):
            return _error("start_hotspot", "invalid_ssid", error)
        if error := validate_wifi_password(password):
            return _error("start_hotspot", "invalid_password", error)
        return await self._run("start_hotspot", self.client.start_hotspot, ssid, password)

    async def stop_hotspot(self) -> NetworkControlResult:
        return await self._run("stop_hotspot", self.client.stop_hotspot)

    async def _run(self, action: str, method, *args: Any) -> NetworkControlResult:
        try:
            result = await method(*args)
        except MissingDbusDependencyError:
            return _error(action, "missing_dependency", "Install tx5dr-device-panel[network-control].")
        except Exception as exc:
            return _error(action, "networkmanager_error", _safe_error_message(exc))
        if isinstance(result, list):
            return NetworkControlResult(ok=True, action=action, code="ok", message="OK", networks=result)
        return NetworkControlResult(ok=True, action=action, code="ok", message="OK")


class MissingDbusDependencyError(RuntimeError):
    pass


class NetworkManagerDbusClient:
    async def scan_wifi(self) -> list[WifiNetwork]:
        bus, nm = await self._networkmanager()
        device_path = await self._wifi_device_path(nm)
        if not device_path:
            return []
        wireless = await self._interface(bus, device_path, "org.freedesktop.NetworkManager.Device.Wireless")
        with _ignore_dbus_errors():
            await wireless.call_request_scan({})
        networks: list[WifiNetwork] = []
        for access_point_path in await wireless.call_get_access_points():
            access_point = await self._interface(
                bus,
                access_point_path,
                "org.freedesktop.NetworkManager.AccessPoint",
            )
            ssid = _decode_ssid(await access_point.get_ssid())
            if ssid:
                networks.append(
                    WifiNetwork(
                        ssid=ssid,
                        signal=int(await access_point.get_strength()),
                        security=_security_label(
                            await access_point.get_wpa_flags(),
                            await access_point.get_rsn_flags(),
                        ),
                    )
                )
        return networks

    async def connect_wifi(self, ssid: str, password: str) -> None:
        bus, nm = await self._networkmanager()
        device_path = await self._wifi_device_path(nm)
        if not device_path:
            raise RuntimeError("No Wi-Fi device is available.")
        access_point_path = await self._access_point_path(bus, device_path, ssid)
        settings = _wifi_connection_settings(ssid, password)
        await nm.call_add_and_activate_connection(settings, device_path, access_point_path or "/")

    async def disconnect_wifi(self) -> None:
        bus, nm = await self._networkmanager()
        device_path = await self._wifi_device_path(nm)
        if not device_path:
            raise RuntimeError("No Wi-Fi device is available.")
        device = await self._interface(bus, device_path, "org.freedesktop.NetworkManager.Device")
        active_connection = await device.get_active_connection()
        if active_connection and active_connection != "/":
            await nm.call_deactivate_connection(active_connection)

    async def start_hotspot(self, ssid: str, password: str) -> None:
        _bus, nm = await self._networkmanager()
        device_path = await self._wifi_device_path(nm)
        if not device_path:
            raise RuntimeError("No Wi-Fi device is available.")
        await nm.call_add_and_activate_connection(_hotspot_connection_settings(ssid, password), device_path, "/")

    async def stop_hotspot(self) -> None:
        await self.disconnect_wifi()

    async def _networkmanager(self):
        bus = await self._bus()
        nm = await self._interface(
            bus,
            "/org/freedesktop/NetworkManager",
            "org.freedesktop.NetworkManager",
        )
        return bus, nm

    async def _bus(self):
        try:
            from dbus_next.aio import MessageBus
            from dbus_next.constants import BusType
        except Exception as exc:
            raise MissingDbusDependencyError from exc
        return await MessageBus(bus_type=BusType.SYSTEM).connect()

    async def _interface(self, bus, path: str, interface_name: str):
        introspection = await bus.introspect("org.freedesktop.NetworkManager", path)
        proxy = bus.get_proxy_object("org.freedesktop.NetworkManager", path, introspection)
        return proxy.get_interface(interface_name)

    async def _wifi_device_path(self, nm) -> str | None:
        for device_path in await nm.call_get_devices():
            bus, _nm = await self._networkmanager()
            device = await self._interface(bus, device_path, "org.freedesktop.NetworkManager.Device")
            if await device.get_device_type() == 2:
                return device_path
        return None

    async def _access_point_path(self, bus, device_path: str, ssid: str) -> str | None:
        wireless = await self._interface(bus, device_path, "org.freedesktop.NetworkManager.Device.Wireless")
        for access_point_path in await wireless.call_get_access_points():
            access_point = await self._interface(
                bus,
                access_point_path,
                "org.freedesktop.NetworkManager.AccessPoint",
            )
            if _decode_ssid(await access_point.get_ssid()) == ssid:
                return access_point_path
        return None


def _wifi_connection_settings(ssid: str, password: str) -> dict[str, dict[str, Any]]:
    return {
        "connection": {
            "id": _variant("s", ssid),
            "type": _variant("s", "802-11-wireless"),
            "autoconnect": _variant("b", True),
        },
        "802-11-wireless": {
            "ssid": _variant("ay", list(ssid.encode("utf-8"))),
            "mode": _variant("s", "infrastructure"),
        },
        "802-11-wireless-security": {
            "key-mgmt": _variant("s", "wpa-psk"),
            "psk": _variant("s", password),
        },
        "ipv4": {"method": _variant("s", "auto")},
        "ipv6": {"method": _variant("s", "auto")},
    }


def _hotspot_connection_settings(ssid: str, password: str) -> dict[str, dict[str, Any]]:
    settings = _wifi_connection_settings(ssid, password)
    settings["connection"]["id"] = _variant("s", "tx5dr-setup-hotspot")
    settings["802-11-wireless"]["mode"] = _variant("s", "ap")
    settings["ipv4"]["method"] = _variant("s", "shared")
    settings["ipv6"]["method"] = _variant("s", "ignore")
    return settings


def _variant(signature: str, value: Any) -> Any:
    try:
        from dbus_next.signature import Variant
    except Exception:
        return {"signature": signature, "value": value}
    return Variant(signature, value)


def _decode_ssid(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, list):
        return bytes(value).decode("utf-8", errors="replace")
    return str(value or "")


def _security_label(wpa_flags: int, rsn_flags: int) -> str:
    return "open" if int(wpa_flags or 0) == 0 and int(rsn_flags or 0) == 0 else "secured"


def _safe_error_message(exc: Exception) -> str:
    text = str(exc) or exc.__class__.__name__
    lowered = text.lower()
    if "psk" in lowered or "password" in lowered:
        return "NetworkManager operation failed."
    return text


def _error(action: str, code: str, message: str) -> NetworkControlResult:
    return NetworkControlResult(ok=False, action=action, code=code, message=message)


class _ignore_dbus_errors:
    def __enter__(self):
        return None

    def __exit__(self, *_args) -> bool:
        return True
