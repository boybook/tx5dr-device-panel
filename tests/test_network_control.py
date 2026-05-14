import asyncio

from tx5dr_device_panel.network.control import WifiNetwork, get_network_controller, validate_ssid
from tx5dr_device_panel.network.providers.networkmanager import (
    MissingDbusDependencyError,
    NetworkManagerController,
    _hotspot_connection_settings,
    _wifi_connection_settings,
)


def test_control_factory_returns_unsupported_on_non_linux():
    controller = get_network_controller(system="Darwin")

    result = asyncio.run(controller.scan_wifi())

    assert result.ok is False
    assert result.code == "unsupported_platform"


def test_control_validation_rejects_invalid_wifi_requests_without_password_leak():
    controller = NetworkManagerController(client=FakeClient())

    short_password = asyncio.run(controller.connect_wifi("TX5DR", "secret"))
    empty_ssid = asyncio.run(controller.start_hotspot("", "supersecret"))

    assert short_password.ok is False
    assert short_password.code == "invalid_password"
    assert "secret" not in short_password.message
    assert empty_ssid.ok is False
    assert empty_ssid.code == "invalid_ssid"


def test_networkmanager_controller_delegates_scan_connect_and_hotspot_actions():
    client = FakeClient()
    controller = NetworkManagerController(client=client)

    scan = asyncio.run(controller.scan_wifi())
    connect = asyncio.run(controller.connect_wifi("Home", "password123"))
    hotspot = asyncio.run(controller.start_hotspot("TX5DR", "password123"))
    disconnect = asyncio.run(controller.disconnect_wifi())
    stop = asyncio.run(controller.stop_hotspot())

    assert scan.ok is True
    assert scan.networks == [WifiNetwork(ssid="Home", signal=90, security="secured")]
    assert connect.ok is True
    assert hotspot.ok is True
    assert disconnect.ok is True
    assert stop.ok is True
    assert client.calls == [
        ("scan_wifi",),
        ("connect_wifi", "Home", "password123"),
        ("start_hotspot", "TX5DR", "password123"),
        ("disconnect_wifi",),
        ("stop_hotspot",),
    ]


def test_networkmanager_controller_reports_missing_dbus_dependency():
    controller = NetworkManagerController(client=MissingDependencyClient())

    result = asyncio.run(controller.scan_wifi())

    assert result.ok is False
    assert result.code == "missing_dependency"


def test_networkmanager_errors_do_not_leak_passwords():
    controller = NetworkManagerController(client=LeakyClient())

    result = asyncio.run(controller.connect_wifi("Home", "password123"))

    assert result.ok is False
    assert result.code == "networkmanager_error"
    assert "password123" not in result.message
    assert "psk" not in result.message.lower()


def test_networkmanager_settings_use_expected_wifi_and_hotspot_shapes():
    wifi = _wifi_connection_settings("Home", "password123")
    hotspot = _hotspot_connection_settings("TX5DR", "password123")

    assert set(wifi) == {
        "connection",
        "802-11-wireless",
        "802-11-wireless-security",
        "ipv4",
        "ipv6",
    }
    assert _variant_value(wifi["802-11-wireless"]["mode"]) == "infrastructure"
    assert _variant_value(wifi["ipv4"]["method"]) == "auto"
    assert _variant_value(hotspot["connection"]["id"]) == "tx5dr-setup-hotspot"
    assert _variant_value(hotspot["802-11-wireless"]["mode"]) == "ap"
    assert _variant_value(hotspot["ipv4"]["method"]) == "shared"
    assert _variant_value(hotspot["ipv6"]["method"]) == "ignore"


def test_validate_ssid_rejects_empty_and_oversized_values():
    assert validate_ssid("") == "SSID is required."
    assert validate_ssid("好" * 11) == "SSID must be 32 bytes or fewer."
    assert validate_ssid("TX5DR") is None


class FakeClient:
    def __init__(self):
        self.calls = []

    async def scan_wifi(self):
        self.calls.append(("scan_wifi",))
        return [WifiNetwork(ssid="Home", signal=90, security="secured")]

    async def connect_wifi(self, ssid, password):
        self.calls.append(("connect_wifi", ssid, password))

    async def disconnect_wifi(self):
        self.calls.append(("disconnect_wifi",))

    async def start_hotspot(self, ssid, password):
        self.calls.append(("start_hotspot", ssid, password))

    async def stop_hotspot(self):
        self.calls.append(("stop_hotspot",))


class MissingDependencyClient:
    async def scan_wifi(self):
        raise MissingDbusDependencyError


class LeakyClient:
    async def connect_wifi(self, ssid, password):
        raise RuntimeError(f"NetworkManager failed with psk={password}")


def _variant_value(value):
    return value["value"] if isinstance(value, dict) else value.value
