from __future__ import annotations

import os
from pathlib import Path


FUSION_PIXEL_FONT_DIR = (
    Path(__file__).resolve().parent
    / "assets"
    / "fonts"
    / "fusion-pixel-font"
)
DEFAULT_FUSION_PIXEL_FONT_PATH = str(FUSION_PIXEL_FONT_DIR / "fusion-pixel-8px-monospaced-zh_hans.ttf")
DEFAULT_FUSION_PIXEL_12PX_FONT_PATH = str(FUSION_PIXEL_FONT_DIR / "fusion-pixel-12px-monospaced-zh_hans.ttf")
DEFAULT_FUSION_PIXEL_FONT_SIZE = 8
BUNDLED_FUSION_PIXEL_FONT_PATHS = {
    8: DEFAULT_FUSION_PIXEL_FONT_PATH,
    12: DEFAULT_FUSION_PIXEL_12PX_FONT_PATH,
}


def resolve_font_path(font_path: str | None = None) -> str:
    return font_path or os.getenv("TX5DR_PANEL_FONT_PATH") or DEFAULT_FUSION_PIXEL_FONT_PATH


def font_path_for_size(font_path: str, size: int) -> Path:
    path = Path(font_path).expanduser()
    if path == Path(DEFAULT_FUSION_PIXEL_FONT_PATH).expanduser():
        bundled = Path(BUNDLED_FUSION_PIXEL_FONT_PATHS.get(size, font_path)).expanduser()
        if bundled.exists():
            return bundled
    return path
