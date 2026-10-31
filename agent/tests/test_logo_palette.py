"""BUI-71 (D8): palette extraction from logo bytes. No network, no files."""

from __future__ import annotations

import io
from typing import Optional, Sequence, Tuple

import pytest
from PIL import Image

from pipeline.design_spec import logo_palette
from pipeline.design_spec.logo_palette import LogoPalette, extract_logo_palette, logo_palette_for, pick_brand_colors

RGB = Tuple[int, int, int]
GREEN: RGB = (0x2E, 0x7D, 0x32)
ORANGE: RGB = (0xFF, 0xA0, 0x00)
BLUE: RGB = (0x1A, 0x3C, 0x6E)
RED: RGB = (0xD3, 0x2F, 0x2F)


def _png(stripes: Sequence[Tuple[RGB, int]], *, size: int = 100, alpha_bg: bool = False, mode: str = "RGB") -> bytes:
    """Horizontal stripes; each (rgb, width-in-columns). Remaining columns are white or transparent."""
    img = Image.new("RGBA" if alpha_bg else mode, (size, size), (0, 0, 0, 0) if alpha_bg else (255, 255, 255))
    x = 0
    for rgb, width in stripes:
        img.paste(rgb + ((255,) if img.mode == "RGBA" else ()), (x, 0, x + width, size))
        x += width
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_two_color_png_gives_primary_and_secondary_by_area() -> None:
    palette = extract_logo_palette(_png([(GREEN, 70), (ORANGE, 30)]), "image/png")
    assert palette.primary == "#2E7D32"
    assert palette.secondary == "#FFA000"
    assert palette.failure is None


def test_transparent_background_is_ignored() -> None:
    palette = extract_logo_palette(_png([(BLUE, 20)], alpha_bg=True), "image/png")
    assert palette.primary == "#1A3C6E"
    assert palette.secondary is None


def test_white_background_and_black_text_are_ignored() -> None:
    palette = extract_logo_palette(_png([(RED, 20), ((0, 0, 0), 30)]), "image/png")
    assert palette.primary == "#D32F2F"
    assert palette.secondary is None


def test_single_color_logo_has_no_secondary() -> None:
    palette = extract_logo_palette(_png([(GREEN, 100)]), "image/png")
    assert (palette.primary, palette.secondary) == ("#2E7D32", None)


def test_similar_hues_do_not_count_as_a_second_color() -> None:
    palette = extract_logo_palette(_png([(GREEN, 60), ((0x3E, 0x8D, 0x42), 40)]), "image/png")
    assert palette.primary == "#2E7D32"
    assert palette.secondary is None  # hue within 30 degrees of primary


def test_black_and_white_logo_yields_nothing() -> None:
    palette = extract_logo_palette(_png([((0, 0, 0), 50)]), "image/png")
    assert palette == LogoPalette.failed("no_usable_colors")


def test_grayscale_logo_yields_nothing() -> None:
    palette = extract_logo_palette(_png([((120, 120, 124), 50), ((80, 80, 82), 30)]), "image/png")
    assert palette.failure == "no_usable_colors"


def test_gradient_logo_still_yields_a_primary() -> None:
    img = Image.new("RGB", (100, 100))
    for x in range(100):
        img.paste((255 - x, 60, x * 2), (x, 0, x + 1, 100))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    palette = extract_logo_palette(buf.getvalue(), "image/png")
    assert palette.primary is not None
    assert palette.failure is None


def test_large_image_is_downscaled_and_still_extracts() -> None:
    palette = extract_logo_palette(_png([(GREEN, 2100), (ORANGE, 900)], size=3000), "image/png")
    assert (palette.primary, palette.secondary) == ("#2E7D32", "#FFA000")


def test_non_image_bytes_are_unreadable() -> None:
    assert extract_logo_palette(b"<html><body>Not Found</body></html>", "text/html") == LogoPalette.failed("unreadable")


def test_jpeg_is_supported() -> None:
    img = Image.new("RGB", (64, 64), GREEN)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    palette = extract_logo_palette(buf.getvalue(), "image/jpeg")
    assert palette.primary is not None
    assert palette.failure is None


def test_extraction_is_deterministic() -> None:
    data = _png([(GREEN, 55), (ORANGE, 25), (BLUE, 20)])
    assert extract_logo_palette(data, "image/png") == extract_logo_palette(data, "image/png")


def test_hex_output_is_uppercase_six_digits() -> None:
    palette = extract_logo_palette(_png([((0x0A, 0x0B, 0xFC), 100)]), "image/png")
    assert palette.primary == "#0A0BFC"


def test_pick_brand_colors_skips_low_saturation_then_picks_distinct_hue() -> None:
    primary, secondary = pick_brand_colors([(128, 128, 130), GREEN, (0x3E, 0x8D, 0x42), ORANGE])
    assert (primary, secondary) == ("#2E7D32", "#FFA000")


# -- SVG logos: explicit colors in attributes and inline styles --------------

SVG_HEADER = '<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'


def test_svg_fill_stroke_and_stop_colors_are_ranked_by_count() -> None:
    svg = SVG_HEADER + (
        '<rect fill="#2E7D32"/><rect fill="#2E7D32"/><circle style="fill:#2e7d32;stroke:none"/>'
        '<path stroke="#FFA000"/><stop stop-color="#FFA000"/>'
        '<path fill="none"/><path fill="currentColor"/><path fill="url(#grad)"/>'
        "</svg>"
    )
    palette = extract_logo_palette(svg.encode(), "image/svg+xml")
    assert (palette.primary, palette.secondary) == ("#2E7D32", "#FFA000")


def test_svg_named_and_short_hex_colors_resolve() -> None:
    svg = SVG_HEADER + '<rect fill="rebeccapurple"/><rect fill="rebeccapurple"/><rect fill="#fa0"/></svg>'
    palette = extract_logo_palette(svg.encode(), "image/svg+xml")
    assert (palette.primary, palette.secondary) == ("#663399", "#FFAA00")


def test_svg_without_explicit_colors_yields_nothing() -> None:
    svg = SVG_HEADER + '<path fill="currentColor" d="M0 0h10v10z"/></svg>'
    assert extract_logo_palette(svg.encode(), "image/svg+xml") == LogoPalette.failed("no_usable_colors")


def test_svg_black_and_white_yields_nothing() -> None:
    svg = SVG_HEADER + '<rect fill="#000"/><rect fill="white"/></svg>'
    assert extract_logo_palette(svg.encode(), "image/svg+xml") == LogoPalette.failed("no_usable_colors")


def test_svg_is_detected_without_content_type() -> None:
    svg = SVG_HEADER + '<rect fill="#1A3C6E"/></svg>'
    assert extract_logo_palette(svg.encode(), None).primary == "#1A3C6E"


def test_svg_sniff_skips_doctype_and_comments() -> None:
    svg = '\n<!-- exported -->\n<!DOCTYPE svg>\n' + SVG_HEADER + '<rect fill="#1A3C6E"/></svg>'
    assert extract_logo_palette(svg.encode(), None).primary == "#1A3C6E"


# -- Untrusted bytes at the boundary: declared types, sniffing, decoders, size --

HTML_WITH_ICON = (
    "<!doctype html><html><head><title>Error</title></head><body>"
    '<svg xmlns="http://www.w3.org/2000/svg"><path fill="#E53935" d="M0 0h1v1z"/></svg>'
    "<h1>Storage error</h1></body></html>"
).encode()


def test_html_declared_content_type_is_unreadable_even_with_an_inline_svg() -> None:
    assert extract_logo_palette(HTML_WITH_ICON, "text/html; charset=utf-8") == LogoPalette.failed("unreadable")


def test_sniffing_requires_svg_as_the_root_element() -> None:
    assert extract_logo_palette(HTML_WITH_ICON, None) == LogoPalette.failed("unreadable")


def test_non_image_declared_types_are_unreadable() -> None:
    assert extract_logo_palette(b'{"error":"not found"}', "application/json") == LogoPalette.failed("unreadable")


def test_octet_stream_counts_as_undeclared_and_is_sniffed() -> None:
    # Object stores often serve uploads as application/octet-stream; the bytes decide.
    assert extract_logo_palette(_png([(GREEN, 100)]), "application/octet-stream").primary == "#2E7D32"
    svg = SVG_HEADER + '<rect fill="#1A3C6E"/></svg>'
    assert extract_logo_palette(svg.encode(), "application/octet-stream").primary == "#1A3C6E"


def test_unlisted_image_formats_are_unreadable() -> None:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), GREEN).save(buf, format="BMP")
    assert extract_logo_palette(buf.getvalue(), "image/bmp") == LogoPalette.failed("unreadable")


def test_images_over_the_pixel_budget_are_unreadable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logo_palette, "MAX_LOGO_PIXELS", 1_000)
    assert extract_logo_palette(_png([(GREEN, 100)]), "image/png") == LogoPalette.failed("unreadable")


async def test_logo_palette_for_survives_extraction_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(data: bytes, content_type: Optional[str] = None) -> LogoPalette:
        raise MemoryError("decoder blew up")

    monkeypatch.setattr(logo_palette, "extract_logo_palette", boom)

    async def fetcher(url: str) -> Tuple[bytes, Optional[str]]:
        return b"whatever", "image/png"

    assert await logo_palette_for("https://example.org/logo.png", fetcher) == LogoPalette.failed("unreadable")
