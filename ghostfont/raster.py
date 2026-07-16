"""Glyph rasterization: message / decoy strings -> binary canvas masks.

Implements ``RasterizeGlyphs`` from the formal spec (Definition: Letter Mask).
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        # Fall back to any bold-ish face PIL can find, then the bitmap default.
        for alt in (
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial.ttf",
        ):
            try:
                return ImageFont.truetype(alt, size)
            except OSError:
                continue
        return ImageFont.load_default()


def _text_size(font: ImageFont.FreeTypeFont, text: str) -> tuple[int, int]:
    # Pillow >= 8: use getbbox for tight metrics.
    left, top, right, bottom = font.getbbox(text)
    return right - left, bottom - top


def rasterize_glyphs(
    text: str,
    width: int,
    height: int,
    font_path: str,
    target_width_frac: float = 0.86,
    fixed_size: int | None = None,
) -> np.ndarray:
    """Rasterize ``text`` centered on a ``height`` x ``width`` canvas.

    Returns a boolean array ``M`` of shape (height, width) where ``True`` marks
    pixels falling inside a glyph.
    """
    if fixed_size is not None:
        size = fixed_size
    else:
        # Binary-search the largest font size whose rendered width fits.
        target_w = int(width * target_width_frac)
        lo, hi, size = 4, height * 3, height
        while lo <= hi:
            mid = (lo + hi) // 2
            font = _load_font(font_path, mid)
            tw, th = _text_size(font, text)
            if tw <= target_w and th <= int(height * 0.82):
                size = mid
                lo = mid + 1
            else:
                hi = mid - 1

    font = _load_font(font_path, size)
    img = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(img)
    left, top, right, bottom = font.getbbox(text)
    tw, th = right - left, bottom - top
    x = (width - tw) // 2 - left
    y = (height - th) // 2 - top
    draw.text((x, y), text, fill=255, font=font)
    return np.asarray(img) > 127


def rasterize_multiline(
    text: str,
    width: int,
    height: int,
    font_path: str,
    font_size: int,
) -> np.ndarray:
    """Rasterize possibly-wrapping ``text`` centered on the canvas (decoy use)."""
    font = _load_font(font_path, font_size)
    img = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(img)

    # Greedy word wrap to fit width.
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if _text_size(font, trial)[0] <= int(width * 0.94) or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)

    line_h = _text_size(font, "Ag")[1] + 6
    total_h = line_h * len(lines)
    y = (height - total_h) // 2
    for line in lines:
        lw = _text_size(font, line)[0]
        draw.text(((width - lw) // 2, y), line, fill=255, font=font)
        y += line_h
    return np.asarray(img) > 127
