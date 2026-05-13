from __future__ import annotations

from typing import Any

from tx5dr_device_panel.models import DISPLAY_HEIGHT, DISPLAY_WIDTH, RenderFrame, Snapshot


def render_snapshot(snapshot: Snapshot) -> RenderFrame:
    frame = RenderFrame(DISPLAY_WIDTH, DISPLAY_HEIGHT)
    _status_bar(frame, snapshot)
    page = _select_page(snapshot)
    if page == "access":
        _render_access(frame, snapshot)
    elif page == "voice":
        _render_voice(frame, snapshot)
    else:
        _render_ft8(frame, snapshot)
    _tx_overlay(frame, snapshot)
    return frame


def _select_page(snapshot: Snapshot) -> str:
    engine = snapshot.get("engine") or {}
    if not engine.get("running"):
        return "access"
    mode_name = _mode_name(snapshot).upper()
    if engine.get("mode") == "voice" or mode_name in {"VOICE", "SSB", "AM", "FM"}:
        return "voice"
    return "ft8"


def _status_bar(frame: RenderFrame, snapshot: Snapshot) -> None:
    tx = _is_tx(snapshot)
    frame.filled_rect(0, 0, 127, 9, fill=1 if tx else 0)
    frame.line(0, 9, 127, 9, fill=1)
    utc = _utc_text(snapshot)
    slot = ((snapshot.get("ft8") or {}).get("cycle"))
    label = f"TX {utc}" if tx else f"UTC {utc}"
    if slot is not None:
        label = f"{label} S{slot}"
    frame.text(2, 1, _clip(label, 20), fill=0 if tx else 1)


def _render_access(frame: RenderFrame, snapshot: Snapshot) -> None:
    network = snapshot.get("network") or {}
    access = snapshot.get("access") or {}
    frame.text(2, 13, "ACCESS / SETUP")
    status = "NET OK" if network.get("connected") else "NET WAIT"
    frame.text(2, 24, status)
    if network.get("ip"):
        frame.text(52, 24, _clip(str(network["ip"]), 12))
    if network.get("ssid"):
        frame.text(2, 34, _clip(f"SSID {network['ssid']}", 20))
    url = access.get("localUrl") or "http://tx5dr.local"
    frame.text(2, 48, _clip(url.replace("http://", ""), 20))
    frame.rect(0, 10, 127, 63)


def _render_ft8(frame: RenderFrame, snapshot: Snapshot) -> None:
    ft8 = snapshot.get("ft8") or {}
    radio = snapshot.get("radio") or {}
    frame.text(2, 12, _clip(f"FT8 {format_frequency(radio.get('frequency'))}", 20))
    decodes = list(ft8.get("recentDecodeRawMessages") or [])[-3:]
    for idx, message in enumerate(decodes):
        frame.text(2, 23 + idx * 9, _clip(str(message), 20))
    tx = ft8.get("currentTx") or {}
    tx_text = tx.get("lastMessage") or (tx.get("messages") or [None])[-1] or "RX MONITOR"
    frame.line(0, 53, 127, 53)
    frame.text(2, 55, _clip(f"TX {tx_text}" if tx.get("active") else str(tx_text), 20))


def _render_voice(frame: RenderFrame, snapshot: Snapshot) -> None:
    radio = snapshot.get("radio") or {}
    voice = snapshot.get("voice") or {}
    frame.text(2, 13, "VOICE MONITOR")
    frame.text(2, 26, _clip(format_frequency(radio.get("frequency")), 20))
    mode = voice.get("radioMode") or radio.get("radioMode") or "--"
    frame.text(2, 38, _clip(f"MODE {mode}", 20))
    ptt = "PTT LOCK" if voice.get("pttLocked") else "PTT FREE"
    keyer = "KEYER" if voice.get("keyerActive") else "LIVE"
    frame.text(2, 50, _clip(f"{ptt} {keyer}", 20))


def _tx_overlay(frame: RenderFrame, snapshot: Snapshot) -> None:
    if not _is_tx(snapshot):
        return
    frame.rect(0, 0, 127, 63)
    frame.rect(1, 1, 126, 62)


def _is_tx(snapshot: Snapshot) -> bool:
    radio = snapshot.get("radio") or {}
    ft8_tx = ((snapshot.get("ft8") or {}).get("currentTx") or {}).get("active")
    return bool(radio.get("ptt") or radio.get("tx") or ft8_tx)


def _mode_name(snapshot: Snapshot) -> str:
    engine = snapshot.get("engine") or {}
    current = engine.get("currentMode") or {}
    if isinstance(current, dict) and current.get("name"):
        return str(current["name"])
    return str(engine.get("mode") or "")


def _utc_text(snapshot: Snapshot) -> str:
    ft8 = snapshot.get("ft8") or {}
    utc_seconds = ft8.get("utc")
    if isinstance(utc_seconds, (int, float)):
        return f"{int(utc_seconds // 3600) % 24:02d}:{int(utc_seconds // 60) % 60:02d}"
    updated_at = snapshot.get("updatedAt")
    if isinstance(updated_at, (int, float)) and updated_at > 0:
        total_seconds = int(updated_at / 1000) % 86_400
        return f"{total_seconds // 3600:02d}:{(total_seconds // 60) % 60:02d}"
    return "--:--"


def format_frequency(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "--.---"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.3f}"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return str(value)


def _clip(value: str, chars: int) -> str:
    return value if len(value) <= chars else value[: max(0, chars - 1)] + ">"
