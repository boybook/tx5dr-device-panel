from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tx5dr_device_panel.models import DISPLAY_HEIGHT, DISPLAY_WIDTH, RenderFrame, Snapshot
from tx5dr_device_panel.ui.status_bar import format_frequency, render_status_bar


FT8_TEXT_X = 2
FT8_COUNTRY_RIGHT_X = 126
FT8_COUNTRY_WIDTH = 44
FT8_COUNTRY_GAP = 4
FT8_FOOTER_Y = 55
VOICE_FREQ_FONT_SIZE = 16
ACCESS_TITLE_FONT_SIZE = 12
ACCESS_CAROUSEL_MS = 3000
ACCESS_PARTICLE_STEP_MS = 250
ACCESS_PARTICLES = (
    ("dot", 7, 16, 1, 1),
    ("bubble", 19, 53, 2, -1),
    ("x", 34, 18, 1, 2),
    ("dot", 48, 59, 3, -1),
    ("bubble", 79, 15, 2, 2),
    ("x", 93, 51, 1, -1),
    ("dot", 112, 21, 3, 2),
    ("bubble", 121, 58, 1, -1),
)

ACCESS_TEXT = {
    "zh": {
        "no_network": "设备未联网",
        "server_down": "后端离线",
        "engine_stopped": "引擎未启动",
        "connect_network": "连接网线/WiFi",
        "join_ssid": "连接{ssid}",
        "check_server": "检查TX-5DR服务",
        "console": "登录控制台诊断",
        "doctor": "控制台运行 tx5dr doctor",
        "open_web": "打开后台启动",
        "ip": "IP {ip}",
        "ssid": "SSID {ssid}",
        "no_ip": "IP --",
        "url_wait": "后台不可用",
    },
    "en": {
        "no_network": "NO NETWORK",
        "server_down": "SERVER OFF",
        "engine_stopped": "ENGINE STOPPED",
        "connect_network": "JOIN LAN/WIFI",
        "join_ssid": "JOIN {ssid}",
        "check_server": "CHECK TX-5DR SVC",
        "console": "LOGIN CONSOLE",
        "doctor": "RUN tx5dr doctor",
        "open_web": "OPEN WEB UI",
        "ip": "IP {ip}",
        "ssid": "SSID {ssid}",
        "no_ip": "IP --",
        "url_wait": "WEB UI UNAVAILABLE",
    },
}


@dataclass(frozen=True)
class AccessView:
    title: str
    messages: list[str]
    endpoint: str
    alert: bool = False


def render_snapshot(snapshot: Snapshot, language: str = "zh") -> RenderFrame:
    frame = RenderFrame(DISPLAY_WIDTH, DISPLAY_HEIGHT)
    page = _select_page(snapshot)
    render_status_bar(frame, snapshot, page=page, ptt_active=_is_ptt_active(snapshot))
    if page == "access":
        _render_access(frame, snapshot, language=language)
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


def _render_access(frame: RenderFrame, snapshot: Snapshot, language: str) -> None:
    view = _access_view(snapshot, language)
    _access_particles(frame, snapshot)
    _access_title(frame, view.title)
    _center_text(frame, 43, _clip_width(_access_carousel_message(view.messages, snapshot), 116))
    _center_text(frame, 55, _clip_width(view.endpoint, 124))


def _access_title(frame: RenderFrame, title: str) -> None:
    text = _clip_width(title, 116, font_size=ACCESS_TITLE_FONT_SIZE)
    text_width = _text_width(text, font_size=ACCESS_TITLE_FONT_SIZE)
    x = max(2, (DISPLAY_WIDTH - text_width) // 2)
    frame.filled_rect(max(0, x - 3), 18, min(127, x + text_width + 2), 31, fill=1)
    frame.text(x, 19, text, fill=0, font_size=ACCESS_TITLE_FONT_SIZE)


def _access_particles(frame: RenderFrame, snapshot: Snapshot) -> None:
    updated_at = snapshot.get("updatedAt")
    tick = int(updated_at / ACCESS_PARTICLE_STEP_MS) if isinstance(updated_at, (int, float)) else 0
    for index, (kind, base_x, base_y, speed_x, speed_y) in enumerate(ACCESS_PARTICLES):
        x = 3 + ((base_x + tick * speed_x + index * 11) % 121)
        y = 12 + ((base_y + tick * speed_y + index * 7) % 48)
        _access_particle(frame, kind, x, y, pulse=(index + tick) % 4 == 0)


def _access_particle(frame: RenderFrame, kind: str, x: int, y: int, pulse: bool) -> None:
    if kind == "bubble":
        radius = 2 if pulse else 1
        frame.rect(max(1, x - radius), max(11, y - radius), min(126, x + radius), min(62, y + radius))
        return
    if kind == "x":
        frame.line(max(1, x - 1), max(11, y - 1), min(126, x + 1), min(62, y + 1))
        frame.line(min(126, x + 1), max(11, y - 1), max(1, x - 1), min(62, y + 1))
        return
    if pulse and x > 1:
        frame.line(x - 1, y, x, y)
    else:
        frame.filled_rect(x, y, x, y)


def _access_carousel_message(messages: list[str], snapshot: Snapshot) -> str:
    values = [message for message in messages if message]
    if not values:
        return ""
    updated_at = snapshot.get("updatedAt")
    tick = int(updated_at / ACCESS_CAROUSEL_MS) if isinstance(updated_at, (int, float)) else 0
    return values[tick % len(values)]


def _access_view(snapshot: Snapshot, language: str) -> AccessView:
    text = _access_text(language)
    network = snapshot.get("network") if isinstance(snapshot.get("network"), dict) else {}
    access = snapshot.get("access") if isinstance(snapshot.get("access"), dict) else {}
    engine = snapshot.get("engine") if isinstance(snapshot.get("engine"), dict) else {}
    ip = network.get("ip")
    ssid = network.get("ssid")
    has_network = bool(network.get("connected") and ip)
    last_error = access.get("lastError")

    if not has_network:
        network_line = text["ssid"].format(ssid=ssid) if ssid else text["no_ip"]
        return AccessView(
            title=text["no_network"],
            messages=[_network_hint(text, network), network_line],
            endpoint=network_line,
            alert=True,
        )

    network_line = text["ssid"].format(ssid=ssid) if ssid else text["ip"].format(ip=ip)
    url = _access_url(access, snapshot)
    if last_error:
        return AccessView(
            title=text["server_down"],
            messages=[text["console"]],
            endpoint=text["doctor"],
            alert=True,
        )
    if not engine.get("running"):
        return AccessView(
            title=text["engine_stopped"],
            messages=[_access_next_step(text, network), network_line],
            endpoint=url or text["url_wait"],
        )
    return AccessView(
        title=text["open_web"],
        messages=[_access_next_step(text, network), network_line],
        endpoint=url or text["url_wait"],
    )


def _access_text(language: str) -> dict[str, str]:
    return ACCESS_TEXT["zh"] if language.lower().startswith("zh") else ACCESS_TEXT["en"]


def _access_next_step(text: dict[str, str], network: dict[str, Any]) -> str:
    if network.get("hotspot") and network.get("ssid"):
        return text["join_ssid"].format(ssid=network["ssid"])
    return text["open_web"]


def _network_hint(text: dict[str, str], network: dict[str, Any]) -> str:
    if network.get("hotspot") and network.get("ssid"):
        return text["join_ssid"].format(ssid=network["ssid"])
    return text["connect_network"]


def _access_url(access: dict[str, Any], snapshot: Snapshot) -> str:
    urls = access.get("localUrls")
    if isinstance(urls, list):
        normalized = [_normalize_access_url(url) for url in urls]
        normalized = [url for url in normalized if url]
        if normalized:
            return _access_carousel_message(normalized, snapshot)
    return _normalize_access_url(access.get("localUrl"))


def _normalize_access_url(url: Any) -> str:
    if not isinstance(url, str) or not url.strip():
        return ""
    return url.strip().replace("http://", "").replace("https://", "").rstrip("/")


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
    frequency = _clip_width(
        format_frequency(radio.get("frequency")),
        96,
        font_size=VOICE_FREQ_FONT_SIZE,
    )
    _center_text(frame, 20, frequency, font_size=VOICE_FREQ_FONT_SIZE)
    mode = voice.get("radioMode") or radio.get("radioMode") or "--"
    _center_text(frame, 42, _clip_width(f"MODE {mode}", 96))
    ptt = "PTT LOCK" if voice.get("pttLocked") else "PTT FREE"
    keyer = "KEYER" if voice.get("keyerActive") else "LIVE"
    _center_text(frame, 52, _clip_width(f"{ptt} {keyer}", 120))


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


def _clip_width(value: str, width: int, font_size: int = 8) -> str:
    if _text_width(value, font_size=font_size) <= width:
        return value
    marker = ">"
    marker_width = _text_width(marker, font_size=font_size)
    result = ""
    for char in value:
        if _text_width(result + char, font_size=font_size) > width - marker_width:
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


def _center_text(frame: RenderFrame, y: int, text: str, fill: int = 1, font_size: int = 8) -> None:
    x = max(0, (DISPLAY_WIDTH - _text_width(text, font_size=font_size)) // 2)
    frame.text(x, y, text, fill=fill, font_size=font_size)


def _text_width(text: str, font_size: int = 8) -> int:
    scale = font_size / 8
    return int(sum(8 if ord(char) > 127 else 4 for char in text) * scale)


def _station_callsign(snapshot: Snapshot) -> str | None:
    station = snapshot.get("station") or {}
    callsign = station.get("callsign") if isinstance(station, dict) else None
    return callsign.strip().upper() if isinstance(callsign, str) and callsign.strip() else None
