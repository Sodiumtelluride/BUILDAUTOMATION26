"""
Logo palette extraction (D8, BUI-71).

When a Stage 1 intake has a logo but no brand colors, the DESIGN node derives
``tokens.colors.primary`` and ``secondary`` from the logo. This module is the
pure part: logo bytes in, an ordered palette out. Fetching is the node's job.

How a raster logo (PNG, JPG, WebP) is read:
  1. Convert to RGBA and shrink to at most ``THUMBNAIL_PX`` on a side with
     nearest-neighbour resampling, so flat colors are never blended.
  2. Drop pixels that are transparent (alpha < ``ALPHA_MIN``), near-white
     (every channel >= ``NEAR_WHITE_MIN``) or near-black (every channel
     <= ``NEAR_BLACK_MAX``): backgrounds and text, not brand colors.
  3. Median-cut quantize what is left to ``QUANTIZE_COLORS`` colors and rank
     them by pixel count.

Picking the two brand colors from the ranked candidates:
  - primary   = the most frequent color with HSV saturation >= ``SATURATION_MIN``
  - secondary = the next such color whose hue differs by >= ``HUE_SEPARATION_DEG``
    degrees; none means the caller keeps its default secondary.

Everything here is deterministic: the same bytes always give the same hex
values, so reruns keep stable tokens. This module imports only the standard
library and Pillow; ``generation.py`` imports it, never the other way round.
"""

from __future__ import annotations

import colorsys
import io
from dataclasses import dataclass
from typing import List, Literal, Optional, Sequence, Tuple

from PIL import Image, UnidentifiedImageError

RGB = Tuple[int, int, int]

NEAR_WHITE_MIN = 235
NEAR_BLACK_MAX = 25
ALPHA_MIN = 128
SATURATION_MIN = 0.15
HUE_SEPARATION_DEG = 30.0
THUMBNAIL_PX = 128
QUANTIZE_COLORS = 8

LogoPaletteFailure = Literal["fetch_failed", "unreadable", "no_usable_colors", "not_attempted"]


@dataclass(frozen=True)
class LogoPalette:
    """The outcome of reading one logo. ``failure`` is None exactly when ``primary`` is set."""

    primary: Optional[str]
    secondary: Optional[str]
    candidates: Tuple[str, ...]
    failure: Optional[LogoPaletteFailure]

    @classmethod
    def failed(cls, reason: LogoPaletteFailure) -> "LogoPalette":
        return cls(primary=None, secondary=None, candidates=(), failure=reason)


def to_hex(rgb: RGB) -> str:
    """``(46, 125, 50)`` -> ``"#2E7D32"`` (uppercase, as the design_spec fixtures use)."""
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def is_usable(rgb: RGB) -> bool:
    """False for near-white and near-black: backgrounds and text, not brand colors."""
    if all(channel >= NEAR_WHITE_MIN for channel in rgb):
        return False
    if all(channel <= NEAR_BLACK_MAX for channel in rgb):
        return False
    return True


def _hsv(rgb: RGB) -> Tuple[float, float, float]:
    r, g, b = (channel / 255.0 for channel in rgb)
    return colorsys.rgb_to_hsv(r, g, b)


def _hue_distance_deg(a: RGB, b: RGB) -> float:
    delta = abs(_hsv(a)[0] - _hsv(b)[0]) * 360.0
    return min(delta, 360.0 - delta)


def pick_brand_colors(candidates: Sequence[RGB]) -> Tuple[Optional[str], Optional[str]]:
    """(primary, secondary) as hex from candidates ordered most prominent first."""
    saturated = [rgb for rgb in candidates if _hsv(rgb)[1] >= SATURATION_MIN]
    if not saturated:
        return None, None
    primary = saturated[0]
    secondary = next(
        (rgb for rgb in saturated[1:] if _hue_distance_deg(rgb, primary) >= HUE_SEPARATION_DEG),
        None,
    )
    return to_hex(primary), (to_hex(secondary) if secondary is not None else None)


def _raster_candidates(data: bytes) -> Optional[List[RGB]]:
    """Ranked usable colors of a raster image; None when the bytes are not an image."""
    try:
        with Image.open(io.BytesIO(data)) as opened:
            img = opened.convert("RGBA")
        img.thumbnail((THUMBNAIL_PX, THUMBNAIL_PX), Image.Resampling.NEAREST)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None

    raw = img.tobytes()
    kept: List[RGB] = [
        (r, g, b)
        for r, g, b, a in zip(raw[0::4], raw[1::4], raw[2::4], raw[3::4])
        if a >= ALPHA_MIN and is_usable((r, g, b))
    ]
    if not kept:
        return []

    strip = Image.frombytes("RGB", (len(kept), 1), bytes(channel for rgb in kept for channel in rgb))
    quantized = strip.quantize(colors=QUANTIZE_COLORS, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette() or []
    ranked: List[Tuple[int, RGB]] = []
    for count, index in quantized.getcolors() or []:
        if not isinstance(index, int):
            continue
        rgb: RGB = (palette[index * 3], palette[index * 3 + 1], palette[index * 3 + 2])
        ranked.append((count, rgb))
    ranked.sort(key=lambda item: (-item[0], item[1]))  # most pixels first; ties by value, for determinism
    return [rgb for _, rgb in ranked if is_usable(rgb)]


def extract_logo_palette(data: bytes, content_type: Optional[str] = None) -> LogoPalette:
    """Derive the brand palette from logo bytes. Never raises for bad input."""
    candidates = _raster_candidates(data)
    if candidates is None:
        return LogoPalette.failed("unreadable")
    primary, secondary = pick_brand_colors(candidates)
    if primary is None:
        return LogoPalette.failed("no_usable_colors")
    return LogoPalette(
        primary=primary,
        secondary=secondary,
        candidates=tuple(to_hex(rgb) for rgb in candidates),
        failure=None,
    )
