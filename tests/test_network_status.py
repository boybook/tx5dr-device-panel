from pathlib import Path

from tx5dr_device_panel.network import status


def test_darwin_status_uses_default_wifi_interface_even_without_ssid(monkeypatch):
    def fake_run(command, timeout=1.0):
        if command == ["route", "-n", "get", "default"]:
            return "gateway: 192.168.1.1\ninterface: en0"
        if command == ["ipconfig", "getifaddr", "en0"]:
            return "192.168.1.20"
        if command == ["networksetup", "-listallhardwareports"]:
            return "Hardware Port: Wi-Fi\nDevice: en0\nEthernet Address: aa:bb"
        if command == ["networksetup", "-getairportnetwork", "en0"]:
            return "You are not associated with an AirPort network."
        return None

    monkeypatch.setattr(status, "_run_command", fake_run)
    result = status._darwin_status()

    assert result.connected is True
    assert result.interface == "en0"
    assert result.ip == "192.168.1.20"
    assert result.transport == "wifi"
    assert result.ssid is None


def test_linux_fallback_marks_wireless_sysfs_interface_as_wifi(tmp_path, monkeypatch):
    wireless = tmp_path / "wlan0" / "wireless"
    wireless.mkdir(parents=True)
    original_transport = status._linux_transport
    monkeypatch.setattr(status, "_run_command", lambda command, timeout=1.0: "1: wlan0 inet 10.0.0.2/24")
    monkeypatch.setattr(status, "_linux_default_interface", lambda: "wlan0")
    monkeypatch.setattr(status, "_linux_transport", lambda interface: original_transport(interface, tmp_path))

    result = status._linux_status()

    assert result.connected is True
    assert result.interface == "wlan0"
    assert result.ip == "10.0.0.2"
    assert result.transport == "wifi"


def test_linux_fallback_marks_ethernet_interface_as_wired(monkeypatch):
    monkeypatch.setattr(status, "_run_command", lambda command, timeout=1.0: "1: eth0 inet 192.168.2.9/24")
    monkeypatch.setattr(status, "_linux_default_interface", lambda: "eth0")

    result = status._linux_status()

    assert result.connected is True
    assert result.transport == "wired"


def test_linux_fallback_reports_disconnected_without_ip(monkeypatch):
    monkeypatch.setattr(status, "_run_command", lambda command, timeout=1.0: None)
    monkeypatch.setattr(status, "_local_ip", lambda: None)
    monkeypatch.setattr(status, "_linux_default_interface", lambda: "wlan0")

    result = status._linux_status()

    assert result.connected is False
    assert result.transport == "unknown"


def test_linux_default_interface_parses_proc_route(tmp_path: Path):
    route = tmp_path / "route"
    route.write_text(
        "Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT\n"
        "wlan0 00000000 0101A8C0 0003 0 0 600 00000000 0 0 0\n",
        encoding="utf-8",
    )

    assert status._linux_default_interface(route) == "wlan0"
