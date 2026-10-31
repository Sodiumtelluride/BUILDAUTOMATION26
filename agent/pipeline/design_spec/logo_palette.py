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

How an SVG logo is read: no rasterizer. Every ``fill``, ``stroke`` and
``stop-color`` value in attributes or inline ``style`` is resolved with
``PIL.ImageColor`` (hex, short hex, CSS names), ``none``/``currentColor``/
``url(...)`` are skipped, and the same white/black filter and count ranking
apply. An SVG that only uses ``currentColor`` therefore yields nothing.

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
import re
from collections import Counter
from dataclasses import dataclass
from typing import Awaitable, Callable, List, Literal, Optional, Sequence, Tuple

from PIL import Image, ImageColor, UnidentifiedImageError

RGB = Tuple[int, int, int]

# Fetches an asset URL -> (body, content type). The DESIGN node supplies the
# real one; tests inject a fake, so nothing here touches the network.
FetchAsset = Callable[[str], Awaitable[Tuple[bytes, Optional[str]]]]

_SVG_COLOR_RE = re.compile(r"(?:fill|stroke|stop-color)\s*[:=]\s*[\"']?\s*([^\"';)\s>]+)", re.IGNORECASE)
_SVG_SKIP_VALUES = frozenset({"none", "currentcolor", "inherit", "transparent"})

NEAR_WHITE_MIN = 235
NEAR_BLACK_MAX = 25
ALPHA_MIN = 128
SATURATION_MIN = 0.15
HUE_SEPARATION_DEG = 30.0
THUMBNAIL_PX = 128
QUANTIZE_COLORS = 8
# Only the formats the intake form accepts (plus WebP) are decoded; anything
# else is "unreadable" rather than a trip through every Pillow plugin.
RASTER_FORMATS: Tuple[str, ...] = ("PNG", "JPEG", "WEBP")
# A flat 12000 x 12000 PNG is a few hundred KB on the wire but ~550 MB as RGBA.
# No real logo comes near this; above it we do not decode at all.
MAX_LOGO_PIXELS = 40_000_000

_SVG_PROLOGUE_RE = re.compile(
    r"^﻿?\s*(?:<\?xml[^>]*\?>\s*|<!DOCTYPE[^>]*>\s*|<!--.*?-->\s*)*", re.IGNORECASE | re.DOTALL
)
_SVG_ROOT_RE = re.compile(r"^<svg[\s>]", re.IGNORECASE)

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
        with Image.open(io.BytesIO(data), formats=RASTER_FORMATS) as opened:
            if opened.width * opened.height > MAX_LOGO_PIXELS:
                return None
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


def _mime(content_type: Optional[str]) -> Optional[str]:
    """``"image/svg+xml; charset=utf-8"`` -> ``"image/svg+xml"``. The generic
    ``application/octet-stream`` that object stores often serve counts as undeclared."""
    if content_type is None:
        return None
    mime = content_type.split(";", 1)[0].strip().lower()
    return None if mime in ("", "application/octet-stream") else mime


def _is_svg(data: bytes, content_type: Optional[str]) -> bool:
    """A declared type decides. Without one, ``<svg`` must be the root element,
    so an HTML error page with an inline icon is not mistaken for a logo."""
    mime = _mime(content_type)
    if mime is not None:
        return mime.startswith("image/svg")
    head = data[:512].decode("utf-8", errors="ignore")
    return _SVG_ROOT_RE.match(_SVG_PROLOGUE_RE.sub("", head, count=1)) is not None


def _svg_candidates(text: str) -> List[RGB]:
    """Ranked usable colors named in an SVG's fill, stroke and stop-color values."""
    counts: Counter[RGB] = Counter()
    for value in _SVG_COLOR_RE.findall(text):
        lowered = value.lower()
        if lowered in _SVG_SKIP_VALUES or lowered.startswith("url("):
            continue
        try:
            resolved = ImageColor.getrgb(value)
        except ValueError:
            continue
        rgb: RGB = (resolved[0], resolved[1], resolved[2])
        if is_usable(rgb):
            counts[rgb] += 1
    return [rgb for rgb, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def extract_logo_palette(data: bytes, content_type: Optional[str] = None) -> LogoPalette:
    """Derive the brand palette from logo bytes. Never raises for bad input."""
    mime = _mime(content_type)
    if mime is not None and not mime.startswith("image/"):
        return LogoPalette.failed("unreadable")  # e.g. a storage error page served as text/html
    candidates: Optional[List[RGB]]
    if _is_svg(data, content_type):
        candidates = _svg_candidates(data.decode("utf-8", errors="ignore"))
    else:
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


async def logo_palette_for(url: str, fetch_asset: FetchAsset) -> LogoPalette:
    """Fetch the logo and derive its palette. A failed fetch is a result, never an exception."""
    try:
        data, content_type = await fetch_asset(url)
    except Exception:  # any fetch problem (scheme, network, size, status) reads the same to the reviewer
        return LogoPalette.failed("fetch_failed")
    try:
        return extract_logo_palette(data, content_type)
    except Exception:  # a decoder surprise (even MemoryError) must not fail the job
        return LogoPalette.failed("unreadable")
