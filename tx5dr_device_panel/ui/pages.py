from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from tx5dr_device_panel.ft8_display import (
    FT8_VISIBLE_ROWS,
    entry_message as _ft8_entry_message,
    ft8_display_entries,
    is_own_entry,
    is_cycle_header,
    scroll_start_index,
)
from tx5dr_device_panel.models import DISPLAY_HEIGHT, DISPLAY_WIDTH, RenderFrame, Snapshot
from tx5dr_device_panel.ui.status_bar import format_frequency, render_status_bar
from tx5dr_device_panel.ui.text_metrics import DEFAULT_TEXT_METRICS, TextMetrics


FT8_TEXT_X = 2
FT8_COUNTRY_RIGHT_X = 126
FT8_COUNTRY_WIDTH = 44
FT8_COUNTRY_GAP = 4
FT8_FOOTER_Y = 55
CW_TEXT_X = 2
CW_ROWS = 4
CW_ROW_Y = (13, 23, 33, 43)
CW_DECODER_OFF_STATES = {"disabled", "stopped", "stopping", "idle", "off", "unavailable"}
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
        "open_ui": "打开用户界面",
        "connect_radio": "连接电台启动",
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
        "open_ui": "OPEN UI",
        "connect_radio": "CONNECT RADIO",
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


def render_snapshot(snapshot: Snapshot, language: str = "zh", metrics: TextMetrics | None = None) -> RenderFrame:
    metrics = metrics or DEFAULT_TEXT_METRICS
    frame = RenderFrame(DISPLAY_WIDTH, DISPLAY_HEIGHT)
    page = _select_page(snapshot)
    render_status_bar(frame, snapshot, page=page, ptt_active=_is_ptt_active(snapshot), metrics=metrics)
    if page == "access":
        _render_access(frame, snapshot, language=language, metrics=metrics)
    elif page == "voice":
        _render_voice(frame, snapshot, metrics=metrics)
    elif page == "cw":
        _render_cw(frame, snapshot, language=language, metrics=metrics)
    else:
        _render_ft8(frame, snapshot, language=language, metrics=metrics)
    _ptt_overlay(frame, snapshot)
    return frame


def _select_page(snapshot: Snapshot) -> str:
    engine = snapshot.get("engine") or {}
    if not engine.get("running"):
        return "access"
    mode_name = _mode_name(snapshot).upper()
    if engine.get("mode") == "voice" or mode_name in {"VOICE", "SSB", "AM", "FM"}:
        return "voice"
    if engine.get("mode") == "cw" or mode_name == "CW":
        return "cw"
    return "ft8"


def _render_access(frame: RenderFrame, snapshot: Snapshot, language: str, metrics: TextMetrics) -> None:
    view = _access_view(snapshot, language)
    _access_particles(frame, snapshot)
    _access_title(frame, view.title, metrics)
    _center_text(
        frame,
        43,
        _clip_width(_access_carousel_message(view.messages, snapshot), 116, metrics=metrics),
        metrics=metrics,
    )
    _center_text(frame, 55, _clip_width(view.endpoint, 124, metrics=metrics), metrics=metrics)


def _access_title(frame: RenderFrame, title: str, metrics: TextMetrics) -> None:
    text = _clip_width(title, 116, font_size=ACCESS_TITLE_FONT_SIZE, metrics=metrics)
    text_width = _text_width(text, font_size=ACCESS_TITLE_FONT_SIZE, metrics=metrics)
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
        title=text["open_ui"],
        messages=[_access_next_step(text, network), network_line],
        endpoint=url or text["url_wait"],
    )


def _access_text(language: str) -> dict[str, str]:
    return ACCESS_TEXT["zh"] if language.lower().startswith("zh") else ACCESS_TEXT["en"]


def _access_next_step(text: dict[str, str], network: dict[str, Any]) -> str:
    if network.get("hotspot") and network.get("ssid"):
        return text["join_ssid"].format(ssid=network["ssid"])
    return text["connect_radio"]


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


def _render_ft8(frame: RenderFrame, snapshot: Snapshot, language: str, metrics: TextMetrics) -> None:
    ft8 = snapshot.get("ft8") or {}
    own = _station_callsigns(snapshot)
    decodes = _decode_window(_decode_entries(snapshot), snapshot, own_callsigns=own)
    for idx, entry in enumerate(decodes):
        y = 12 + idx * 10
        if is_cycle_header(entry):
            _inverse_row(frame, y, _clip_width(_entry_message(entry), 124, metrics=metrics))
            continue
        message = _entry_message(entry)
        country = _country_label(entry, language)
        country_text = _clip_width(country, FT8_COUNTRY_WIDTH, metrics=metrics) if country else ""
        country_width = _text_width(country_text, metrics=metrics)
        country_left = FT8_COUNTRY_RIGHT_X - country_width
        text_width = (
            DISPLAY_WIDTH - FT8_TEXT_X - 1
            if not country_text
            else max(8, country_left - FT8_COUNTRY_GAP - FT8_TEXT_X)
        )
        text = _clip_width(message, text_width, metrics=metrics)
        if is_own_entry(entry, own):
            _inverse_text(frame, FT8_TEXT_X, y, text, metrics)
        else:
            frame.text(FT8_TEXT_X, y, text)
        if country_text:
            _right_text(frame, FT8_COUNTRY_RIGHT_X, y, country_text, metrics=metrics)
    tx = ft8.get("currentTx") or {}
    tx_text = tx.get("lastMessage") or (tx.get("messages") or [None])[-1] or "RX MONITOR"
    frame.line(0, 53, 127, 53)
    count = _cycle_message_count(ft8)
    period_label, period_highlight = _cycle_period_label(snapshot, language)
    count_label = f"{period_label}×{count}"
    _render_tx_footer(
        frame,
        tx_text=str(tx_text),
        tx_armed=_is_tx_armed(snapshot),
        ptt_active=_is_ptt_active(snapshot),
        right_label=count_label,
        metrics=metrics,
    )
    _render_footer_right_label(frame, 126, 55, count_label, highlighted=period_highlight, metrics=metrics)


def _render_cw(frame: RenderFrame, snapshot: Snapshot, language: str, metrics: TextMetrics) -> None:
    cw = snapshot.get("cw") if isinstance(snapshot.get("cw"), dict) else {}
    decoder = cw.get("decoder") if isinstance(cw.get("decoder"), dict) else {}
    committed = _string_value(decoder.get("committedText"))
    pending = _string_value(decoder.get("pendingText"))
    if not _cw_decoder_enabled(decoder):
        _render_cw_no_decoder(frame, cw, language, metrics)
        return
    if committed or pending:
        _render_cw_transcript(frame, committed, pending, metrics)
    else:
        frame.text(CW_TEXT_X, CW_ROW_Y[0], _clip_width(_cw_waiting_decode_text(language), 124, metrics=metrics))

    frame.line(0, 53, 127, 53)
    _render_tx_footer(
        frame,
        tx_text=_cw_footer_text(cw),
        tx_armed=bool((cw.get("currentTx") or {}).get("active")),
        ptt_active=_is_ptt_active(snapshot),
        right_label="",
        metrics=metrics,
    )


def _render_cw_no_decoder(frame: RenderFrame, cw: dict[str, Any], language: str, metrics: TextMetrics) -> None:
    text = _cw_sent_text(cw)
    lines = _wrap_center_lines(text, 116, max_lines=3, metrics=metrics) if text else _cw_empty_lines(language)
    total_height = len(lines) * 10 - 2
    y = max(13, 36 - total_height // 2)
    for index, line in enumerate(lines):
        _center_text(frame, y + index * 10, line, metrics=metrics)


def _cw_decoder_enabled(decoder: dict[str, Any]) -> bool:
    state = _string_value(decoder.get("state")).lower()
    if state in CW_DECODER_OFF_STATES:
        return False
    return bool(decoder.get("enabled"))


def _render_cw_transcript(frame: RenderFrame, committed: str, pending: str, metrics: TextMetrics) -> None:
    row, x = _draw_cw_flow(frame, _normalize_cw_text(committed), row=0, x=CW_TEXT_X, metrics=metrics)
    pending = _normalize_cw_text(pending)
    if not pending or row >= CW_ROWS:
        return

    if x > CW_TEXT_X:
        x += _text_width(" ", metrics=metrics)
        if x > 126:
            row += 1
            x = CW_TEXT_X
    _draw_cw_pending_flow(frame, pending, row=row, x=x, metrics=metrics)


def _draw_cw_flow(frame: RenderFrame, text: str, row: int, x: int, metrics: TextMetrics) -> tuple[int, int]:
    while text and row < CW_ROWS:
        available = 126 - x
        chunk, text = _take_width(text, available, metrics=metrics)
        if not chunk:
            row += 1
            x = CW_TEXT_X
            continue
        frame.text(x, CW_ROW_Y[row], chunk)
        x += _text_width(chunk, metrics=metrics)
        if text:
            row += 1
            x = CW_TEXT_X
    return row, x


def _draw_cw_pending_flow(frame: RenderFrame, text: str, row: int, x: int, metrics: TextMetrics) -> tuple[int, int]:
    while text and row < CW_ROWS:
        available = 126 - x
        chunk, text = _take_width(text, available, metrics=metrics)
        if not chunk:
            row += 1
            x = CW_TEXT_X
            continue
        width = max(4, _text_width(chunk, metrics=metrics))
        y = CW_ROW_Y[row]
        frame.filled_rect(max(0, x - 1), y, min(127, x + width), min(52, y + 8), fill=1)
        frame.text(x, y, chunk, fill=0)
        x += width
        if text:
            row += 1
            x = CW_TEXT_X
    return row, x


def _take_width(text: str, width: int, metrics: TextMetrics) -> tuple[str, str]:
    if width <= 0:
        return "", text
    result = ""
    for char in text:
        if _text_width(result + char, metrics=metrics) > width:
            break
        result += char
    return result, text[len(result):]


def _normalize_cw_text(value: str) -> str:
    return " ".join(value.split())


def _cw_footer_text(cw: dict[str, Any]) -> str:
    return _cw_sent_text(cw) or "CW MONITOR"


def _cw_sent_text(cw: dict[str, Any]) -> str:
    current_tx = cw.get("currentTx") if isinstance(cw.get("currentTx"), dict) else {}
    keyer = cw.get("keyer") if isinstance(cw.get("keyer"), dict) else {}
    return (
        _string_value(current_tx.get("lastMessage"))
        or _string_value(keyer.get("currentText"))
        or _string_value(keyer.get("lastText"))
    )


def _cw_empty_lines(language: str) -> list[str]:
    if language.lower().startswith("zh"):
        return ["还未发报", "网页操作发报"]
    return ["NO TX YET", "SEND FROM WEB"]


def _cw_waiting_decode_text(language: str) -> str:
    return "等待解码结果..." if language.lower().startswith("zh") else "WAITING DECODES..."


def _wrap_center_lines(text: str, width: int, max_lines: int, metrics: TextMetrics) -> list[str]:
    remaining = _normalize_cw_text(text)
    lines: list[str] = []
    while remaining and len(lines) < max_lines:
        chunk, remaining = _take_width(remaining, width, metrics=metrics)
        if not chunk:
            break
        if remaining and len(lines) == max_lines - 1:
            chunk = _clip_width(chunk + remaining, width, metrics=metrics)
            remaining = ""
        lines.append(chunk)
    return lines or [""]


def _render_voice(frame: RenderFrame, snapshot: Snapshot, metrics: TextMetrics) -> None:
    radio = snapshot.get("radio") or {}
    voice = snapshot.get("voice") or {}
    frequency = _clip_width(
        format_frequency(radio.get("frequency")),
        96,
        font_size=VOICE_FREQ_FONT_SIZE,
        metrics=metrics,
    )
    _center_text(frame, 20, frequency, font_size=VOICE_FREQ_FONT_SIZE, metrics=metrics)
    mode = voice.get("radioMode") or radio.get("radioMode") or "--"
    _center_text(frame, 42, _clip_width(f"MODE {mode}", 96, metrics=metrics), metrics=metrics)
    ptt = "PTT LOCK" if voice.get("pttLocked") else "PTT FREE"
    keyer = "KEYER" if voice.get("keyerActive") else "LIVE"
    _center_text(frame, 52, _clip_width(f"{ptt} {keyer}", 120, metrics=metrics), metrics=metrics)


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


def _render_tx_footer(
    frame: RenderFrame,
    tx_text: str,
    tx_armed: bool,
    ptt_active: bool,
    right_label: str,
    metrics: TextMetrics,
) -> None:
    right_width = _text_width(right_label, metrics=metrics) if right_label else 0
    content_right = 126 - right_width - (2 if right_label else 0)
    tx_indicator_active = tx_armed or ptt_active
    if not tx_indicator_active:
        frame.text(2, FT8_FOOTER_Y, _clip_width(tx_text, content_right - 2, metrics=metrics))
        return

    label = "TX"
    label_width = _text_width(label, metrics=metrics)
    frame.filled_rect(1, FT8_FOOTER_Y, 2 + label_width, 63, fill=1)
    frame.text(2, FT8_FOOTER_Y, label, fill=0)
    message_x = 2 + label_width + 4
    frame.text(message_x, FT8_FOOTER_Y, _clip_width(tx_text, max(8, content_right - message_x), metrics=metrics))


def _render_footer_right_label(
    frame: RenderFrame,
    right_x: int,
    y: int,
    text: str,
    highlighted: bool,
    metrics: TextMetrics,
) -> None:
    if not highlighted:
        _right_text(frame, right_x, y, text, metrics=metrics)
        return
    x = metrics.right_x(right_x, text)
    frame.filled_rect(max(0, x - 1), y, 127, 63, fill=1)
    frame.text(x, y, text, fill=0)


def _mode_name(snapshot: Snapshot) -> str:
    engine = snapshot.get("engine") or {}
    current = engine.get("currentMode") or {}
    if isinstance(current, dict) and current.get("name"):
        return str(current["name"])
    return str(engine.get("mode") or "")


def _string_value(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _clip(value: str, chars: int) -> str:
    return value if len(value) <= chars else value[: max(0, chars - 1)] + ">"


def _clip_width(
    value: str,
    width: int,
    font_size: int = 8,
    metrics: TextMetrics = DEFAULT_TEXT_METRICS,
) -> str:
    return metrics.clip_width(value, width, font_size=font_size)


def _decode_window(
    messages: list[Any],
    snapshot: Snapshot,
    rows: int = FT8_VISIBLE_ROWS,
    own_callsigns: str | Sequence[str] | None = None,
) -> list[Any]:
    values = [message for message in messages if _entry_message(message)]
    header_entries = [message for message in values if is_cycle_header(message)]
    body_entries = [message for message in values if not is_cycle_header(message)]
    own_entries = [message for message in body_entries if is_own_entry(message, own_callsigns)]
    other_entries = [message for message in body_entries if not is_own_entry(message, own_callsigns)]

    if header_entries and own_entries:
        remaining_rows = rows - 1
        if remaining_rows <= 0:
            return header_entries[:rows]
        if len(own_entries) >= remaining_rows:
            start = scroll_start_index(snapshot, len(own_entries), remaining_rows)
            return [header_entries[0], *own_entries[start:start + remaining_rows]]
        return [
            header_entries[0],
            *own_entries,
            *_scrolling_slice(other_entries, snapshot, remaining_rows - len(own_entries)),
        ]

    if len(own_entries) >= rows:
        start = scroll_start_index(snapshot, len(own_entries), rows)
        return own_entries[start:start + rows]

    if own_entries:
        remaining_rows = rows - len(own_entries)
        return own_entries + _scrolling_slice(other_entries, snapshot, remaining_rows)

    if len(values) <= rows:
        return values

    return _scrolling_slice(values, snapshot, rows)


def _scrolling_slice(values: list[Any], snapshot: Snapshot, rows: int) -> list[Any]:
    if rows <= 0:
        return []
    if len(values) <= rows:
        return values[:rows]
    start = scroll_start_index(snapshot, len(values), rows)
    return values[start:start + rows]


def _decode_entries(snapshot: Snapshot) -> list[Any]:
    return [entry for entry in ft8_display_entries(snapshot) if entry]


def _entry_message(entry: Any) -> str:
    return _ft8_entry_message(entry)


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


def _cycle_period_label(snapshot: Snapshot, language: str) -> tuple[str, bool]:
    ft8 = snapshot.get("ft8") if isinstance(snapshot.get("ft8"), dict) else {}
    if _display_mode_is_ft4(snapshot):
        cycle_number = _display_cycle_number(ft8)
        if cycle_number is None:
            cycle_number = _derived_display_cycle_number(ft8)
        is_even = cycle_number is None or cycle_number % 2 == 0
        if language.lower().startswith("zh"):
            return ("偶数" if is_even else "奇数", not is_even)
        return ("EVEN" if is_even else "ODD", not is_even)

    second = _display_slot_second(ft8)
    if second is None:
        return "--", False
    is_primary = second % 30 == 0
    return ("00/30" if is_primary else "15/45", not is_primary)


def _display_mode_is_ft4(snapshot: Snapshot) -> bool:
    ft8 = snapshot.get("ft8") if isinstance(snapshot.get("ft8"), dict) else {}
    display = ft8.get("_display") if isinstance(ft8.get("_display"), dict) else {}
    slot = ft8.get("slot") if isinstance(ft8.get("slot"), dict) else {}
    engine = snapshot.get("engine") if isinstance(snapshot.get("engine"), dict) else {}
    current = engine.get("currentMode") if isinstance(engine.get("currentMode"), dict) else {}
    mode = str(display.get("mode") or slot.get("mode") or current.get("name") or engine.get("mode") or "").upper()
    period = display.get("periodMs") or ft8.get("periodMs") or current.get("slotMs")
    return "FT4" in mode or (isinstance(period, (int, float)) and 0 < period <= 8_000)


def _display_cycle_number(ft8: dict[str, Any]) -> int | None:
    display = ft8.get("_display") if isinstance(ft8.get("_display"), dict) else {}
    value = display.get("cycleNumber")
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _derived_display_cycle_number(ft8: dict[str, Any]) -> int | None:
    start_ms = _display_slot_start_ms(ft8)
    display = ft8.get("_display") if isinstance(ft8.get("_display"), dict) else {}
    period_ms = display.get("periodMs") or ft8.get("periodMs")
    if not isinstance(start_ms, (int, float)) or not isinstance(period_ms, (int, float)) or period_ms <= 0:
        return None
    return int(start_ms // period_ms)


def _display_slot_second(ft8: dict[str, Any]) -> int | None:
    start_ms = _display_slot_start_ms(ft8)
    if isinstance(start_ms, (int, float)):
        return int(start_ms / 1000) % 60
    display = ft8.get("_display") if isinstance(ft8.get("_display"), dict) else {}
    entries = display.get("entries")
    if isinstance(entries, list) and entries:
        first = entries[0]
        if isinstance(first, dict) and isinstance(first.get("slotStartMs"), (int, float)):
            return int(first["slotStartMs"] / 1000) % 60
    return None


def _display_slot_start_ms(ft8: dict[str, Any]) -> int | float | None:
    display = ft8.get("_display") if isinstance(ft8.get("_display"), dict) else {}
    value = display.get("slotStartMs")
    if isinstance(value, (int, float)):
        return value
    value = ft8.get("recentFramesSlotStartMs")
    if isinstance(value, (int, float)):
        return value
    frames = ft8.get("recentFrames")
    if isinstance(frames, list) and frames:
        first = frames[0]
        if isinstance(first, dict) and isinstance(first.get("slotStartMs"), (int, float)):
            return first["slotStartMs"]
    slot = ft8.get("slot") if isinstance(ft8.get("slot"), dict) else {}
    value = slot.get("startMs")
    return value if isinstance(value, (int, float)) else None


def _inverse_text(frame: RenderFrame, x: int, y: int, text: str, metrics: TextMetrics) -> None:
    width = min(126 - x, max(4, _text_width(text, metrics=metrics)))
    frame.filled_rect(x - 1, y, x + width, min(52, y + 8), fill=1)
    frame.text(x, y, text, fill=0)


def _inverse_row(frame: RenderFrame, y: int, text: str) -> None:
    frame.filled_rect(0, y, 127, min(52, y + 8), fill=1)
    frame.text(2, y, text, fill=0)


def _right_text(
    frame: RenderFrame,
    right_x: int,
    y: int,
    text: str,
    fill: int = 1,
    metrics: TextMetrics = DEFAULT_TEXT_METRICS,
) -> None:
    frame.text(metrics.right_x(right_x, text), y, text, fill=fill)


def _center_text(
    frame: RenderFrame,
    y: int,
    text: str,
    fill: int = 1,
    font_size: int = 8,
    metrics: TextMetrics = DEFAULT_TEXT_METRICS,
) -> None:
    x = metrics.center_x(text, font_size=font_size)
    frame.text(x, y, text, fill=fill, font_size=font_size)


def _text_width(text: str, font_size: int = 8, metrics: TextMetrics = DEFAULT_TEXT_METRICS) -> int:
    return metrics.text_width(text, font_size=font_size)


def _station_callsigns(snapshot: Snapshot) -> list[str]:
    station = snapshot.get("station") or {}
    if not isinstance(station, dict):
        return []
    callsigns = station.get("callsigns")
    values = callsigns if isinstance(callsigns, list) else []
    normalized: list[str] = []
    for value in [*values, station.get("callsign")]:
        if not isinstance(value, str) or not value.strip():
            continue
        callsign = value.strip().upper()
        if callsign not in normalized:
            normalized.append(callsign)
    return normalized
