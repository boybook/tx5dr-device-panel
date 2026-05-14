from __future__ import annotations

from math import ceil

from PIL import ImageFont

from tx5dr_device_panel.fonts import DEFAULT_FUSION_PIXEL_FONT_SIZE, font_path_for_size, resolve_font_path
from tx5dr_device_panel.models import DISPLAY_WIDTH


class TextMetrics:
    def __init__(self, font_path: str | None = None, font_size: int = DEFAULT_FUSION_PIXEL_FONT_SIZE) -> None:
        self.font_path = resolve_font_path(font_path)
        self.font_size = font_size
        self._font_cache: dict[int, ImageFont.FreeTypeFont] = {}

    def text_width(self, text: str, font_size: int | None = None) -> int:
        if not text:
            return 0
        font = self._font(font_size)
        return int(ceil(font.getlength(text)))

    def clip_width(self, value: str, width: int, font_size: int | None = None, marker: str = ">") -> str:
        if self.text_width(value, font_size=font_size) <= width:
            return value
        marker_width = self.text_width(marker, font_size=font_size)
        if width <= marker_width:
            return ""
        result = ""
        for char in value:
            if self.text_width(result + char, font_size=font_size) > width - marker_width:
                break
            result += char
        return result + marker

    def right_x(self, right_x: int, text: str, font_size: int | None = None, min_x: int = 0) -> int:
        return max(min_x, right_x - self.text_width(text, font_size=font_size))

    def center_x(self, text: str, font_size: int | None = None, width: int = DISPLAY_WIDTH) -> int:
        return max(0, (width - self.text_width(text, font_size=font_size)) // 2)

    def _font(self, font_size: int | None) -> ImageFont.FreeTypeFont:
        size = font_size or self.font_size
        if size not in self._font_cache:
            path = font_path_for_size(self.font_path, size)
            self._font_cache[size] = ImageFont.truetype(str(path), size=size)
        return self._font_cache[size]


DEFAULT_TEXT_METRICS = TextMetrics()
