from __future__ import annotations

from typing import Any

from tx5dr_device_panel.models import DISPLAY_HEIGHT, DISPLAY_WIDTH, RenderFrame, Snapshot
from tx5dr_device_panel.ui.status_bar import format_frequency, render_status_bar


FT8_TEXT_X = 2
FT8_COUNTRY_RIGHT_X = 126
FT8_COUNTRY_WIDTH = 44
FT8_COUNTRY_GAP = 4
FT8_FOOTER_Y = 55


def render_snapshot(snapshot: Snapshot, language: str = "zh") -> RenderFrame:
    frame = RenderFrame(DISPLAY_WIDTH, DISPLAY_HEIGHT)
    page = _select_page(snapshot)
    render_status_bar(frame, snapshot, page=page, ptt_active=_is_ptt_active(snapshot))
    if page == "access":
        _render_access(frame, snapshot)
    elif page == "voice":
        _render_voice(frame, snapshot)
    else:
        _render_ft8(frame, snapshot, language=language)
    _ptt_overlay(frame, snapshot)
    return frame


def _select_page(snapshot: Snapshot) -> str:
    engine = snapshot.get("engine") or {}
    if not engine.get("running"):
        return "access"
    mode_name = _mode_name(snapshot).upper()
    if engine.get("mode") == "voice" or mode_name in {"VOICE", "SSB", "AM", "FM"}:
        return "voice"
    return "ft8"


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


def _render_ft8(frame: RenderFrame, snapshot: Snapshot, language: str) -> None:
    ft8 = snapshot.get("ft8") or {}
    own = _station_callsign(snapshot)
    decodes = _decode_window(_decode_entries(ft8), snapshot, own_callsign=own)
    for idx, entry in enumerate(decodes):
        y = 13 + idx * 10
        message = _entry_message(entry)
        country = _country_label(entry, language)
        country_text = _clip_width(country, FT8_COUNTRY_WIDTH) if country else ""
        country_width = _text_width(country_text)
        country_left = FT8_COUNTRY_RIGHT_X - country_width
        text_width = (
            DISPLAY_WIDTH - FT8_TEXT_X - 1
            if not country_text
            else max(8, country_left - FT8_COUNTRY_GAP - FT8_TEXT_X)
        )
        text = _clip_width(message, text_width)
        if own and own in message.upper():
            _inverse_text(frame, FT8_TEXT_X, y, text)
        else:
            frame.text(FT8_TEXT_X, y, text)
        if country_text:
            _right_text(frame, FT8_COUNTRY_RIGHT_X, y, country_text)
    tx = ft8.get("currentTx") or {}
    tx_text = tx.get("lastMessage") or (tx.get("messages") or [None])[-1] or "RX MONITOR"
    frame.line(0, 53, 127, 53)
    count = _cycle_message_count(ft8)
    count_label = f"{_cycle_utc_compact(ft8)} ×{count}"
    _render_ft8_footer(
        frame,
        tx_text=str(tx_text),
        tx_armed=_is_tx_armed(snapshot),
        ptt_active=_is_ptt_active(snapshot),
        count_label=count_label,
    )
    _right_text(frame, 126, 55, count_label)


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


def _ptt_overlay(frame: RenderFrame, snapshot: Snapshot) -> None:
    if not _is_ptt_active(snapshot):
        return
    frame.rect(0, 0, 127, 63)
    frame.rect(1, 1, 126, 62)


def _is_ptt_active(snapshot: Snapshot) -> bool:
    radio = snapshot.get("radio") or {}
    return bool(radio.get("ptt"))


def _is_tx_armed(snapshot: Snapshot) -> bool:
    return bool(((snapshot.get("ft8") or {}).get("currentTx") or {}).get("active"))


def _render_ft8_footer(
    frame: RenderFrame,
    tx_text: str,
    tx_armed: bool,
    ptt_active: bool,
    count_label: str,
) -> None:
    count_width = _text_width(count_label)
    content_right = 126 - count_width - 4
    tx_indicator_active = tx_armed or ptt_active
    if not tx_indicator_active:
        frame.text(2, FT8_FOOTER_Y, _clip_width(tx_text, content_right - 2))
        return

    label = "TX"
    label_width = _text_width(label)
    frame.filled_rect(1, FT8_FOOTER_Y, 2 + label_width, 63, fill=1)
    frame.text(2, FT8_FOOTER_Y, label, fill=0)
    message_x = 2 + label_width + 4
    frame.text(message_x, FT8_FOOTER_Y, _clip_width(tx_text, max(8, content_right - message_x)))


def _mode_name(snapshot: Snapshot) -> str:
    engine = snapshot.get("engine") or {}
    current = engine.get("currentMode") or {}
    if isinstance(current, dict) and current.get("name"):
        return str(current["name"])
    return str(engine.get("mode") or "")


def _clip(value: str, chars: int) -> str:
    return value if len(value) <= chars else value[: max(0, chars - 1)] + ">"


def _clip_width(value: str, width: int) -> str:
    if _text_width(value) <= width:
        return value
    marker = ">"
    marker_width = _text_width(marker)
    result = ""
    for char in value:
        if _text_width(result + char) > width - marker_width:
            break
        result += char
    return result + marker


def _decode_window(
    messages: list[Any],
    snapshot: Snapshot,
    rows: int = 4,
    own_callsign: str | None = None,
) -> list[Any]:
    values = [message for message in messages if _entry_message(message)]
    if len(values) <= rows:
        return values
    # Advance one row every two seconds so crowded FT8 slots remain readable.
    updated_at = snapshot.get("updatedAt")
    tick = int(updated_at / 2000) if isinstance(updated_at, (int, float)) else 0
    start = tick % len(values)
    rotated = values[start:] + values[:start]
    own = (own_callsign or "").strip().upper()
    if not own:
        return rotated[:rows]
    priority = [message for message in values if own in _entry_message(message).upper()]
    filler = [message for message in rotated if message not in priority]
    return (priority + filler)[:rows]


def _decode_entries(ft8: dict[str, Any]) -> list[Any]:
    frames = ft8.get("recentFrames")
    if isinstance(frames, list) and frames:
        return frames
    return list(ft8.get("recentDecodeRawMessages") or [])


def _entry_message(entry: Any) -> str:
    if isinstance(entry, dict):
        message = entry.get("message")
        return message if isinstance(message, str) else ""
    return str(entry) if entry is not None else ""


def _country_label(entry: Any, language: str) -> str:
    if not isinstance(entry, dict):
        return ""
    if language.lower().startswith("zh"):
        value = entry.get("countryZh") or entry.get("country") or entry.get("countryEn")
    else:
        value = entry.get("countryEn") or entry.get("country") or entry.get("countryZh")
    return value if isinstance(value, str) else ""


def _cycle_message_count(ft8: dict[str, Any]) -> int:
    frames = ft8.get("recentFrames")
    if isinstance(frames, list) and frames:
        return len(frames)
    messages = ft8.get("recentDecodeRawMessages")
    return len(messages) if isinstance(messages, list) else 0


def _cycle_utc_compact(ft8: dict[str, Any]) -> str:
    utc_seconds = ft8.get("utc")
    if isinstance(utc_seconds, (int, float)):
        return _format_utc_compact(utc_seconds)
    slot = ft8.get("slot")
    if isinstance(slot, dict) and isinstance(slot.get("utcSeconds"), (int, float)):
        return _format_utc_compact(slot["utcSeconds"])
    return "------"


def _format_utc_compact(utc_seconds: float) -> str:
    total_seconds = int(utc_seconds) % 86_400
    return f"{total_seconds // 3600:02d}{(total_seconds // 60) % 60:02d}{total_seconds % 60:02d}"


def _inverse_text(frame: RenderFrame, x: int, y: int, text: str) -> None:
    width = min(126 - x, max(4, _text_width(text)))
    frame.filled_rect(x - 1, y, x + width, min(52, y + 8), fill=1)
    frame.text(x, y, text, fill=0)


def _right_text(frame: RenderFrame, right_x: int, y: int, text: str, fill: int = 1) -> None:
    frame.text(max(0, right_x - _text_width(text)), y, text, fill=fill)


def _text_width(text: str) -> int:
    return sum(8 if ord(char) > 127 else 4 for char in text)


def _station_callsign(snapshot: Snapshot) -> str | None:
    station = snapshot.get("station") or {}
    callsign = station.get("callsign") if isinstance(station, dict) else None
    return callsign.strip().upper() if isinstance(callsign, str) and callsign.strip() else None
