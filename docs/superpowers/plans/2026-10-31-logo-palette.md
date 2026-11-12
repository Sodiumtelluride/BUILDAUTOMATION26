# Logo Palette (D8, BUI-71) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a Stage 1 intake has a logo but no brand colors, the DESIGN node derives `tokens.colors.primary` and `secondary` from the logo, records the provenance, and never fails the job if it cannot.

**Architecture:** A pure module `logo_palette.py` turns logo bytes into an ordered palette. `assemble_design_spec` (PR #11) takes an optional `LogoPalette` and uses it in place of brand colors, adding D5 decisions and one assumption. `run_design` fetches the logo through an injectable async fetcher before assembly, so tests stay offline and assembly stays pure.

**Tech Stack:** Python 3.11+, Pydantic v2, Pillow (`PIL.Image`, `PIL.ImageColor`), httpx, pytest (asyncio auto mode), mypy strict.

**Spec:** `docs/superpowers/specs/2026-10-31-logo-palette-design.md`

## Global Constraints

- Work on branch `bui-71-derive-brand-colors` rebased onto `origin/feat/bui-64-66-design-node` (PR #11). Do not target `main`.
- All commands run from `/Users/achoi/BUILDAUTOMATION26/agent` using `venv/bin/python`, `venv/bin/pytest`, `venv/bin/mypy`.
- `mypy --strict pipeline/ tests/` must stay clean (repo `pyproject.toml` sets `strict = true`).
- Hex output is uppercase, six digits, `#RRGGBB` (matches `schema.Hex` and existing fixtures).
- Only `https://` URLs are fetched. Timeout 10 s. Body cap 10 MB (`10 * 1024 * 1024` bytes).
- Filters: alpha < 128 dropped; near-white = every channel >= 235; near-black = every channel <= 25; saturation floor 0.15 (HSV, `colorsys`); hue separation for secondary >= 30 degrees; thumbnail bound 128 px; quantize to 8 colors with `Image.Quantize.MEDIANCUT`.
- `Decision.summary` is at most 300 characters.
- No binary fixture files. PNG test logos are generated with Pillow inside tests. SVGs are inline strings.
- No `.pyc` or `__pycache__` committed (`agent/.gitignore` on the base branch already ignores them).
- Verified before planning (2026-10-31, Python 3.14.7): Pillow 13.0.0 installs, ships `py.typed`, resolves `rebeccapurple` and `#fa0`, and median cut returns the exact stripe colors for the 100 px and 3000 px two-color test images. `bui-71-derive-brand-colors` is an ancestor of `origin/feat/bui-64-66-design-node`, so Task 0's rebase is a fast-forward.

## Review Focus

Inputs the spec implies but a casual reading would miss. Each has a test pinned to its owning task.

1. A gradient or photo-like logo (hundreds of colors) must still give a stable primary, not an empty palette. Task 1, `test_gradient_logo_still_yields_a_primary`.
2. A large-dimension image that compresses under 10 MB (for example 3000 x 3000 flat PNG) must finish quickly via the thumbnail step. Task 1, `test_large_image_is_downscaled_and_still_extracts`.
3. A grayscale logo with a faint tint must fall through to defaults rather than pick a muddy gray as primary. Task 1, `test_grayscale_logo_yields_nothing`.
4. A fetch that returns a 200 with an HTML body (storage error page) must be treated as unreadable, not crash assembly. Task 1, `test_non_image_bytes_are_unreadable`; Task 4, `test_run_design_fetch_error_falls_back_to_defaults`.
5. A logo URL on a non-https scheme (`supabase://`, `s3://`, which the current intake route and old fixtures use) must be a clean fetch failure with an assumption, never an exception out of the node. Task 4, `test_https_fetcher_rejects_non_https_schemes` and `test_run_design_fetch_error_falls_back_to_defaults`.

---

### Task 0: Branch onto PR #11 and establish the baseline

**Files:**
- Modify: `agent/pyproject.toml` (dependencies list)

**Interfaces:**
- Produces: a working tree where `from pipeline.design_spec.generation import assemble_design_spec, DEFAULT_COLORS` and `from pipeline.nodes.design import run_design` import, and `PIL` and `httpx` import.

- [ ] **Step 1: Rebase onto the stacked branch**

```bash
cd /Users/achoi/BUILDAUTOMATION26
git fetch origin feat/bui-64-66-design-node
git rebase origin/feat/bui-64-66-design-node bui-71-derive-brand-colors
```
Expected: clean rebase (the branch has no commits of its own yet, so it fast-forwards).

- [ ] **Step 2: Add dependencies to `agent/pyproject.toml`**

In `[project] dependencies`, add `"pillow>=11.3"` and `"httpx>=0.27"` after `"pydantic>=2.0"`.

- [ ] **Step 3: Install and run the baseline**

```bash
cd /Users/achoi/BUILDAUTOMATION26/agent
venv/bin/pip install -e ".[dev]"
venv/bin/pytest -q
venv/bin/mypy --strict pipeline/ tests/
```
Expected: `80 passed` and `Success: no issues found`.

- [ ] **Step 4: Commit**

```bash
git add agent/pyproject.toml
git commit -m "chore(agent): add pillow and httpx for logo palette extraction (BUI-71)"
```

---

### Task 1: Raster palette extraction

**Files:**
- Create: `agent/pipeline/design_spec/logo_palette.py`
- Test: `agent/tests/test_logo_palette.py`

**Interfaces:**
- Produces, in `logo_palette.py`:

```python
LogoPaletteFailure = Literal["fetch_failed", "unreadable", "no_usable_colors", "not_attempted"]

@dataclass(frozen=True)
class LogoPalette:
    primary: Optional[str]            # uppercase "#RRGGBB" or None
    secondary: Optional[str]          # uppercase "#RRGGBB" or None
    candidates: Tuple[str, ...]       # every usable color, most prominent first
    failure: Optional[LogoPaletteFailure]   # None when primary is set

    @classmethod
    def failed(cls, reason: LogoPaletteFailure) -> "LogoPalette": ...

def extract_logo_palette(data: bytes, content_type: Optional[str] = None) -> LogoPalette: ...
def pick_brand_colors(candidates: Sequence[Tuple[int, int, int]]) -> Tuple[Optional[str], Optional[str]]: ...
def is_usable(rgb: Tuple[int, int, int]) -> bool: ...   # not near-white, not near-black
def to_hex(rgb: Tuple[int, int, int]) -> str: ...       # "#2E7D32"
```

- `extract_logo_palette` returns `failure="unreadable"` when Pillow cannot open the bytes, and `failure="no_usable_colors"` when every pixel is filtered out or nothing clears the saturation floor. SVG handling is Task 2; until then SVG bytes are simply unreadable.
- `logo_palette.py` imports only the standard library and `PIL`. It must not import from `pipeline.design_spec` (generation.py will import it, so this avoids a cycle).

- [ ] **Step 1: Write the failing tests**

Create `agent/tests/test_logo_palette.py` with a PNG helper and these tests:

```python
"""BUI-71 (D8): palette extraction from logo bytes. No network, no files."""

from __future__ import annotations

import io
from typing import Sequence, Tuple

from PIL import Image

from pipeline.design_spec.logo_palette import LogoPalette, extract_logo_palette, pick_brand_colors

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
    palette = extract_logo_palette(_png([((0x0a, 0x0b, 0xfc), 100)]), "image/png")
    assert palette.primary == "#0A0BFC"


def test_pick_brand_colors_skips_low_saturation_then_picks_distinct_hue() -> None:
    primary, secondary = pick_brand_colors([(128, 128, 130), GREEN, (0x3E, 0x8D, 0x42), ORANGE])
    assert (primary, secondary) == ("#2E7D32", "#FFA000")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_logo_palette.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'pipeline.design_spec.logo_palette'`.

- [ ] **Step 3: Implement `agent/pipeline/design_spec/logo_palette.py`**

Module docstring: D8, what it reads, the filter thresholds, and that it is pure. Constants at top: `NEAR_WHITE_MIN = 235`, `NEAR_BLACK_MAX = 25`, `ALPHA_MIN = 128`, `SATURATION_MIN = 0.15`, `HUE_SEPARATION_DEG = 30.0`, `THUMBNAIL_PX = 128`, `QUANTIZE_COLORS = 8`.

Raster path, `_raster_candidates(data: bytes) -> Optional[List[Tuple[int, int, int]]]` (None means unreadable):
1. `Image.open(io.BytesIO(data))`, `.convert("RGBA")`, `.thumbnail((THUMBNAIL_PX, THUMBNAIL_PX), Image.Resampling.NEAREST)` (nearest, so flat logos are not blended at edges and results stay exact and deterministic). Catch `(UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError)` and return None.
2. Read pixels with `raw = img.tobytes()` and `zip(raw[0::4], raw[1::4], raw[2::4], raw[3::4])` (not `getdata`, which Pillow 13 deprecates). Keep pixels with alpha >= `ALPHA_MIN` and `is_usable(rgb)`. Empty means return `[]`.
3. Put the kept pixels into a 1-row `RGB` image (`Image.new("RGB", (n, 1))`, `putdata`), `quantize(colors=QUANTIZE_COLORS, method=Image.Quantize.MEDIANCUT)`, then `getcolors()` and `getpalette()` to map each palette index to its RGB and count.
4. Sort by count descending, then by RGB tuple for determinism. Return the RGB list, filtered again with `is_usable` (median cut can blend toward white or black).

`pick_brand_colors`: primary is the first candidate with `colorsys.rgb_to_hsv` saturation >= `SATURATION_MIN`; secondary is the next candidate with saturation >= floor and circular hue distance >= `HUE_SEPARATION_DEG`. Return hex strings via `to_hex`.

`extract_logo_palette`: SVG branch is a placeholder returning `LogoPalette.failed("unreadable")` until Task 2 (`_is_svg` is defined in Task 2). Otherwise call `_raster_candidates`; None gives `failed("unreadable")`; then `pick_brand_colors`; no primary gives `failed("no_usable_colors")`; else `LogoPalette(primary, secondary, tuple(to_hex(c) for c in candidates), None)`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_logo_palette.py -q && venv/bin/mypy --strict pipeline/ tests/`
Expected: `14 passed`, mypy clean. If `test_two_color_png_gives_primary_and_secondary_by_area` fails on an off-by-one channel, the cause is JPEG-style blending in `convert`; PNG with flat stripes must come back exact, so fix the pixel collection, do not loosen the assertion.

- [ ] **Step 5: Commit**

```bash
git add agent/pipeline/design_spec/logo_palette.py agent/tests/test_logo_palette.py
git commit -m "feat(design): extract a brand palette from raster logos (BUI-71)"
```

---

### Task 2: SVG palette extraction

**Files:**
- Modify: `agent/pipeline/design_spec/logo_palette.py`
- Test: `agent/tests/test_logo_palette.py`

**Interfaces:**
- Consumes: `is_usable`, `pick_brand_colors`, `LogoPalette` from Task 1.
- Produces: `_is_svg(data: bytes, content_type: Optional[str]) -> bool` and `_svg_candidates(text: str) -> List[Tuple[int, int, int]]`, wired into `extract_logo_palette`.

- [ ] **Step 1: Write the failing tests**

Append to `agent/tests/test_logo_palette.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_logo_palette.py -q -k svg`
Expected: 5 failures, each with `failure == "unreadable"` where a color or `no_usable_colors` was expected.

- [ ] **Step 3: Implement the SVG path in `logo_palette.py`**

- `_is_svg`: true when `content_type` starts with `image/svg`, or the first 512 bytes decoded as UTF-8 (errors ignored), lowercased, contain `<svg`.
- `_svg_candidates(text)`: one regex, `re.compile(r"(?:fill|stroke|stop-color)\s*[:=]\s*[\"']?\s*([^\"';)\s>]+)", re.IGNORECASE)`. For each match, skip values that lowercase to `none`, `currentcolor`, `inherit`, `transparent`, or start with `url(`. Resolve with `ImageColor.getrgb(value)`; on `ValueError` skip; take the first three channels. Count with `collections.Counter`, keep `is_usable`, order by count descending then RGB tuple.
- In `extract_logo_palette`, when `_is_svg`, decode the bytes as UTF-8 with errors ignored and use `_svg_candidates`, then the same `pick_brand_colors` and failure mapping as the raster path.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv/bin/pytest tests/test_logo_palette.py -q && venv/bin/mypy --strict pipeline/ tests/`
Expected: `19 passed`, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add agent/pipeline/design_spec/logo_palette.py agent/tests/test_logo_palette.py
git commit -m "feat(design): read brand colors from SVG logos (BUI-71)"
```

---

### Task 3: Use the palette in token assembly, decisions, and the D10 rule

**Files:**
- Modify: `agent/pipeline/design_spec/generation.py` (the `# -- Tokens` block, the `# -- Flags` block, `_build_decisions`)
- Modify: `agent/pipeline/design_spec/__init__.py` (exports)
- Test: `agent/tests/test_logo_palette_tokens.py`

**Interfaces:**
- Consumes: `LogoPalette` from Task 1.
- Produces: `assemble_design_spec(job_id, intake, plan, previous=None, revision=1, logo_palette: Optional[LogoPalette] = None) -> Dict[str, Any]`. Also `LOGO_PALETTE_SUMMARY: str` and `LOGO_PALETTE_FAILED_SUMMARY: str` (format string with `{reason}`), both under 300 characters.
- Rule: the palette is used only when `intake.brand_colors` is empty and `intake.logo` is set. In that situation `logo_palette=None` is treated as `LogoPalette.failed("not_attempted")`.
- D10 rule: `default_design_track` fires only when `intake.logo is None` and `missing_branding(intake)` is non-empty.
- Exports added to `pipeline.design_spec`: `LogoPalette`, `extract_logo_palette`.

- [ ] **Step 1: Write the failing tests**

Create `agent/tests/test_logo_palette_tokens.py`:

```python
"""BUI-71 (D8): derived logo colors become tokens with provenance; D10 never fires with a logo."""

from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, List

from pipeline.design_spec import (
    DesignSpec,
    LayoutPlan,
    LogoPalette,
    assemble_design_spec,
    current_decisions,
    parse_design_intake,
    requested_slugs,
    validate_design_spec,
)
from pipeline.design_spec.generation import DEFAULT_COLORS
from pipeline.design_spec.schema import Decision, DefaultDesignTrackFlag, IntakeSource
from pipeline.design_spec.validate import Valid

MakeIntake = Callable[[], Dict[str, Any]]
MakePlan = Callable[[], Dict[str, Any]]
JOB_ID = uuid.uuid4()
DERIVED = LogoPalette(primary="#2E7D32", secondary="#FFA000", candidates=("#2E7D32", "#FFA000"), failure=None)


def _assemble(intake_dict: Dict[str, Any], plan_dict: Dict[str, Any], palette: LogoPalette | None, previous: DesignSpec | None = None, revision: int = 1) -> DesignSpec:
    intake = parse_design_intake(intake_dict)
    spec_dict = assemble_design_spec(JOB_ID, intake, LayoutPlan.model_validate(plan_dict), previous=previous, revision=revision, logo_palette=palette)
    result = validate_design_spec(spec_dict, expected_job_id=JOB_ID, required_slugs=requested_slugs(intake))
    assert isinstance(result, Valid), getattr(result, "issues", None)
    return result.spec


def _cites_logo(d: Decision) -> bool:
    return any(isinstance(s, IntakeSource) and s.ref == "logo" for s in d.sources)


def _assumptions_citing_logo(spec: DesignSpec) -> List[Decision]:
    return [d for d in current_decisions(spec) if d.kind == "assumption" and _cites_logo(d)]


def test_logo_palette_fills_primary_and_secondary_when_colors_missing(make_intake: MakeIntake, make_plan: MakePlan) -> None:
    intake_dict = make_intake()
    intake_dict["brand_colors"] = []
    spec = _assemble(intake_dict, make_plan(), DERIVED)
    assert spec.tokens.colors["primary"] == "#2E7D32"
    assert spec.tokens.colors["secondary"] == "#FFA000"
    token_decisions = [d for d in current_decisions(spec) if d.kind == "token" and "tokens.colors.primary" in d.targets]
    assert token_decisions and all(_cites_logo(d) for d in token_decisions)
    assert len(_assumptions_citing_logo(spec)) == 1
    assert "derived from the uploaded logo" in (_assumptions_citing_logo(spec)[0].summary or "")
    assert not [f for f in spec.flags if f.code == "default_design_track"]


def test_single_color_palette_keeps_default_secondary(make_intake: MakeIntake, make_plan: MakePlan) -> None:
    intake_dict = make_intake()
    intake_dict["brand_colors"] = []
    spec = _assemble(intake_dict, make_plan(), LogoPalette("#2E7D32", None, ("#2E7D32",), None))
    assert spec.tokens.colors["primary"] == "#2E7D32"
    assert spec.tokens.colors["secondary"] == DEFAULT_COLORS["secondary"]
    secondary_decisions = [d for d in current_decisions(spec) if "tokens.colors.secondary" in d.targets and d.kind == "token"]
    assert secondary_decisions and not any(_cites_logo(d) for d in secondary_decisions)


def test_failed_palette_keeps_defaults_and_records_why(make_intake: MakeIntake, make_plan: MakePlan) -> None:
    intake_dict = make_intake()
    intake_dict["brand_colors"] = []
    spec = _assemble(intake_dict, make_plan(), LogoPalette.failed("fetch_failed"))
    assert spec.tokens.colors["primary"] == DEFAULT_COLORS["primary"]
    notes = _assumptions_citing_logo(spec)
    assert len(notes) == 1
    assert "fetch_failed" in (notes[0].summary or "")
    assert not [f for f in spec.flags if f.code == "default_design_track"]


def test_missing_palette_with_logo_and_no_colors_counts_as_not_attempted(make_intake: MakeIntake, make_plan: MakePlan) -> None:
    intake_dict = make_intake()
    intake_dict["brand_colors"] = []
    spec = _assemble(intake_dict, make_plan(), None)
    assert spec.tokens.colors["primary"] == DEFAULT_COLORS["primary"]
    assert "not_attempted" in (_assumptions_citing_logo(spec)[0].summary or "")


def test_given_brand_colors_win_over_logo_palette(make_intake: MakeIntake, make_plan: MakePlan) -> None:
    intake_dict = make_intake()  # has brand_colors
    spec = _assemble(intake_dict, make_plan(), LogoPalette("#123456", "#654321", ("#123456", "#654321"), None))
    assert spec.tokens.colors["primary"] == intake_dict["brand_colors"][0]
    assert not _assumptions_citing_logo(spec)


def test_default_track_never_fires_when_a_logo_exists(make_intake: MakeIntake, make_plan: MakePlan) -> None:
    intake_dict = make_intake()
    intake_dict["brand_colors"] = []
    intake_dict["brand_fonts"] = []
    spec = _assemble(intake_dict, make_plan(), LogoPalette.failed("unreadable"))
    assert not [f for f in spec.flags if f.code == "default_design_track"]


def test_default_track_still_fires_without_a_logo(make_intake: MakeIntake, make_plan: MakePlan) -> None:
    intake_dict = make_intake()
    intake_dict["logo"] = None
    intake_dict["brand_colors"] = []
    spec = _assemble(intake_dict, make_plan(), None)
    flags = [f for f in spec.flags if isinstance(f, DefaultDesignTrackFlag)]
    assert flags and flags[0].missing == ["logo", "brand_colors"]
    assert not _assumptions_citing_logo(spec)


def test_rerun_does_not_duplicate_logo_decisions(make_intake: MakeIntake, make_plan: MakePlan) -> None:
    intake_dict = make_intake()
    intake_dict["brand_colors"] = []
    first = _assemble(intake_dict, make_plan(), DERIVED)
    second = _assemble(intake_dict, make_plan(), DERIVED, previous=first, revision=2)
    assert len(_assumptions_citing_logo(second)) == 1
    assert len([d for d in second.decisions if d.kind == "token" and _cites_logo(d)]) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_logo_palette_tokens.py -q`
Expected: `ImportError: cannot import name 'LogoPalette' from 'pipeline.design_spec'`.

- [ ] **Step 3: Export from `pipeline/design_spec/__init__.py`**

Add `from .logo_palette import LogoPalette, extract_logo_palette` and both names to `__all__`.

- [ ] **Step 4: Implement in `generation.py`**

Add the two summary constants near `DEFAULT_RADIUS`:
- `LOGO_PALETTE_SUMMARY = "Brand colors were derived from the uploaded logo because none were provided; confirm they match the brand."`
- `LOGO_PALETTE_FAILED_SUMMARY = "No brand colors were provided and the logo could not be used ({reason}). BUILD default colors were applied."`

In `assemble_design_spec`, after computing `colors` from `intake.brand_colors`:
- `palette: Optional[LogoPalette] = None`; when `not intake.brand_colors and intake.logo is not None`, set `palette = logo_palette or LogoPalette.failed("not_attempted")`.
- When `palette is not None and palette.primary is not None`: set `colors["primary"]`, append `"primary"` to a new `logo_roles: List[ColorRole]`; same for `secondary` when present. `default_roles` must exclude both `brand_roles` and `logo_roles`.
- Flags: replace `if missing:` with `if intake.logo is None and missing:` for the `DefaultDesignTrackFlag`, and pass `missing=[]` to `_build_decisions` when the flag did not fire, so no flag decision is recorded.
- Pass `logo_roles` and `palette` to `_build_decisions` (new keyword parameters `logo_roles: List[ColorRole]`, `logo_palette: Optional[LogoPalette]`).

In `_build_decisions`:
- After the `brand_roles` cover: `if logo_roles: cover("token", [f"tokens.colors.{r}" for r in logo_roles], from_intake("logo"), "code")`.
- After the content-exclusions block, when `logo_palette is not None`: if no current (not superseded) assumption already cites intake `logo` (same `already` pattern as content exclusions), append one with `record_decision(log, kind="assumption", targets=["tokens.colors.primary", "tokens.colors.secondary"], sources=from_intake("logo") if logo_palette.primary else from_intake("logo") + from_default("build_tokens"), method="code", revision=revision, summary=LOGO_PALETTE_SUMMARY if logo_palette.primary else LOGO_PALETTE_FAILED_SUMMARY.format(reason=logo_palette.failure))`.

- [ ] **Step 5: Run the whole suite**

Run: `venv/bin/pytest -q && venv/bin/mypy --strict pipeline/ tests/`
Expected: `107 passed` (80 + 19 + 8), mypy clean. The existing `test_missing_branding_falls_back_to_default_track` still passes because it removes the logo as well.

- [ ] **Step 6: Commit**

```bash
git add agent/pipeline/design_spec/generation.py agent/pipeline/design_spec/__init__.py agent/tests/test_logo_palette_tokens.py
git commit -m "feat(design): use the logo palette for tokens and stop D10 firing when a logo exists (BUI-71)"
```

---

### Task 4: Fetch the logo in the DESIGN node

**Files:**
- Modify: `agent/pipeline/nodes/design.py`
- Modify: `agent/pipeline/design_spec/logo_palette.py` (add `logo_palette_for`)
- Test: `agent/tests/test_logo_palette_node.py`

**Interfaces:**
- Consumes: `extract_logo_palette`, `LogoPalette` (Task 1), `assemble_design_spec(..., logo_palette=...)` (Task 3).
- Produces, in `logo_palette.py`:

```python
FetchAsset = Callable[[str], Awaitable[Tuple[bytes, Optional[str]]]]   # (body, content type)

async def logo_palette_for(url: str, fetch_asset: FetchAsset) -> LogoPalette: ...
```
  Any exception from `fetch_asset` gives `LogoPalette.failed("fetch_failed")`; otherwise the result of `extract_logo_palette`.

- Produces, in `nodes/design.py`:

```python
MAX_LOGO_BYTES = 10 * 1024 * 1024
LOGO_FETCH_TIMEOUT_SECONDS = 10.0

async def fetch_https_asset(url: str, *, transport: Optional["httpx.AsyncBaseTransport"] = None) -> Tuple[bytes, Optional[str]]: ...
async def run_design(state: PipelineState, generate_plan: Optional[GeneratePlan] = None, fetch_asset: Optional[FetchAsset] = None) -> Dict[str, Any]: ...
```
  `fetch_https_asset` raises `ValueError` for a non-`https://` URL, for a non-2xx status, and for a body over `MAX_LOGO_BYTES`. It uses `httpx.AsyncClient(timeout=LOGO_FETCH_TIMEOUT_SECONDS, follow_redirects=True, transport=transport)` and returns `(response.content, response.headers.get("content-type"))`. `httpx` is imported at module top (it is now a declared dependency).
  `run_design` calls `logo_palette_for` only when `intake.logo is not None and not intake.brand_colors`, once per node run (before the retry loop, not per attempt), and passes the result to every `assemble_design_spec` call.

- [ ] **Step 1: Write the failing tests**

Create `agent/tests/test_logo_palette_node.py`:

```python
"""BUI-71 (D8): the DESIGN node fetches the logo through an injectable fetcher."""

from __future__ import annotations

import io
import uuid
from typing import Any, Dict, List, Mapping, Optional, Tuple

import httpx
import pytest
from PIL import Image

from pipeline.design_spec import DesignSpec, validate_design_spec
from pipeline.design_spec.generation import DEFAULT_COLORS
from pipeline.design_spec.validate import Valid
from pipeline.nodes.design import MAX_LOGO_BYTES, fetch_https_asset, run_design
from pipeline.state import IntakeOutput, PipelineState

LOGO_URL = "https://assets.build-umass.org/jobs/a1b2c3d4/logo_green.svg"


def _green_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (0x2E, 0x7D, 0x32)).save(buf, format="PNG")
    return buf.getvalue()


def _spec(result: Dict[str, Any], state: PipelineState) -> DesignSpec:
    assert set(result) == {"design_output"}
    validated = validate_design_spec(result["design_output"].design_spec, expected_job_id=state.job_id)
    assert isinstance(validated, Valid), getattr(validated, "issues", None)
    return validated.spec


async def test_run_design_fetches_logo_only_when_colors_missing(make_intake: Any, make_plan: Any) -> None:
    calls: List[str] = []

    async def fetcher(url: str) -> Tuple[bytes, Optional[str]]:
        calls.append(url)
        return _green_png(), "image/png"

    async def planner(attempt: object, gen_input: Mapping[str, Any]) -> object:
        return make_plan()

    with_colors = PipelineState(org_id=uuid.uuid4(), intake_output=IntakeOutput(project_spec=make_intake()))
    await run_design(with_colors, generate_plan=planner, fetch_asset=fetcher)
    assert calls == []

    intake_dict = make_intake()
    intake_dict["brand_colors"] = []
    without = PipelineState(org_id=uuid.uuid4(), intake_output=IntakeOutput(project_spec=intake_dict))
    spec = _spec(await run_design(without, generate_plan=planner, fetch_asset=fetcher), without)
    assert calls == [intake_dict["logo"]]
    assert spec.tokens.colors["primary"] == "#2E7D32"


async def test_run_design_fetch_error_falls_back_to_defaults(make_intake: Any, make_plan: Any) -> None:
    async def fetcher(url: str) -> Tuple[bytes, Optional[str]]:
        raise ValueError("unsupported scheme")

    async def planner(attempt: object, gen_input: Mapping[str, Any]) -> object:
        return make_plan()

    intake_dict = make_intake()
    intake_dict["brand_colors"] = []
    intake_dict["logo"] = "supabase://intake-uploads/a1b2c3d4/logo.png"
    state = PipelineState(org_id=uuid.uuid4(), intake_output=IntakeOutput(project_spec=intake_dict))
    spec = _spec(await run_design(state, generate_plan=planner, fetch_asset=fetcher), state)
    assert spec.tokens.colors["primary"] == DEFAULT_COLORS["primary"]
    assert any(d.kind == "assumption" and "fetch_failed" in (d.summary or "") for d in spec.decisions)
    assert not [f for f in spec.flags if f.code == "default_design_track"]


async def test_run_design_fetches_once_across_retry_attempts(make_intake: Any, make_plan: Any) -> None:
    calls: List[str] = []
    attempts: List[int] = []

    async def fetcher(url: str) -> Tuple[bytes, Optional[str]]:
        calls.append(url)
        return _green_png(), "image/png"

    async def planner(attempt: object, gen_input: Mapping[str, Any]) -> object:
        attempts.append(1)
        return {"pages": []} if len(attempts) == 1 else make_plan()  # first attempt is invalid

    intake_dict = make_intake()
    intake_dict["brand_colors"] = []
    state = PipelineState(org_id=uuid.uuid4(), intake_output=IntakeOutput(project_spec=intake_dict))
    _spec(await run_design(state, generate_plan=planner, fetch_asset=fetcher), state)
    assert len(attempts) == 2
    assert len(calls) == 1


async def test_https_fetcher_returns_body_and_content_type() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=b"png-bytes", headers={"content-type": "image/png"}))
    assert await fetch_https_asset(LOGO_URL, transport=transport) == (b"png-bytes", "image/png")


async def test_https_fetcher_rejects_non_https_schemes() -> None:
    for url in ("http://example.org/logo.png", "supabase://bucket/logo.png", "s3://bucket/logo.png", "file:///etc/passwd"):
        with pytest.raises(ValueError):
            await fetch_https_asset(url)


async def test_https_fetcher_rejects_error_status() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(404, content=b"<html>Not Found</html>"))
    with pytest.raises(ValueError):
        await fetch_https_asset(LOGO_URL, transport=transport)


async def test_https_fetcher_rejects_oversized_body() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=b"x" * (MAX_LOGO_BYTES + 1)))
    with pytest.raises(ValueError):
        await fetch_https_asset(LOGO_URL, transport=transport)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv/bin/pytest tests/test_logo_palette_node.py -q`
Expected: `ImportError: cannot import name 'MAX_LOGO_BYTES' from 'pipeline.nodes.design'`.

- [ ] **Step 3: Implement `logo_palette_for` in `logo_palette.py` and the node changes in `nodes/design.py`**

In `run_design`, after `intake = parse_design_intake(...)`:

```python
logo_palette: Optional[LogoPalette] = None
if intake.logo is not None and not intake.brand_colors:
    logo_palette = await logo_palette_for(intake.logo, fetch_asset or fetch_https_asset)
```
and pass `logo_palette=logo_palette` in the `assemble_design_spec` call inside `generate`. Update the module docstring flow list with a step "2b. If there are no brand colors but a logo, fetch it and derive a palette (D8)". Add `fetch_https_asset` and `FetchAsset` to `__all__`.

- [ ] **Step 4: Run the whole suite**

Run: `venv/bin/pytest -q && venv/bin/mypy --strict pipeline/ tests/`
Expected: `114 passed`, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add agent/pipeline/nodes/design.py agent/pipeline/design_spec/logo_palette.py agent/tests/test_logo_palette_node.py
git commit -m "feat(design): fetch the logo over https and derive tokens in the DESIGN node (BUI-71)"
```

---

### Task 5: Docs, final verification, and the pull request

**Files:**
- Modify: `agent/README.md` (directory table, one row)

- [ ] **Step 1: Document the module**

In the `agent/README.md` directory table, add a row: `pipeline/design_spec/logo_palette.py` | D8: derives brand colors from an uploaded logo when none were given.

- [ ] **Step 2: Full verification from a clean state**

```bash
cd /Users/achoi/BUILDAUTOMATION26/agent
find . -name __pycache__ -not -path "./venv/*" -not -path "./.venv/*" -prune -exec rm -rf {} +
venv/bin/pytest -q
venv/bin/mypy --strict pipeline/ tests/
git -C /Users/achoi/BUILDAUTOMATION26 status --porcelain | grep -E "\.pyc|__pycache__" ; echo "exit=$?"
```
Expected: `114 passed`, mypy clean, the grep prints nothing and `exit=1`.

- [ ] **Step 3: Commit and push**

```bash
git add agent/README.md
git commit -m "docs(agent): list the logo palette module (BUI-71)"
git push -u origin bui-71-derive-brand-colors
```

- [ ] **Step 4: Open the PR against `feat/bui-64-66-design-node`**

```bash
gh pr create --base feat/bui-64-66-design-node --title "Derive brand colors from an uploaded logo (D8, BUI-71)" --body-file -
```
Body must include: "Stacked on #11 (BUI-64/65/66)."; a summary of the four behaviors (derived tokens, provenance, failure fallback, https-only fetch); the D10 change with this note for the BUI-64/66 owner: "PR #11 raises `default_design_track` per missing branding item. The PRD (D10) scopes it to no logo, no colors, and no fonts. This PR stops it firing whenever a logo exists. The no-logo cases are left as #11 has them; achiu, please confirm whether D10 should also require colors and fonts to both be missing."; the test commands and counts; and "Closes BUI-71".

- [ ] **Step 5: Report**

Tell the user the PR URL, the test count, and that the D10 note to achiu is in the PR body and still needs a Linear comment on BUI-64 if they want it tracked there.
