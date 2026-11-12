# Derive brand colors from an uploaded logo (D8, BUI-71)

**Ticket:** [BUI-71](https://linear.app/build-engineering/issue/BUI-71/derive-brand-colors-from-an-uploaded-logo)
**PRD requirement:** D8. "If no colors are given but a logo exists, derive the palette from the logo."
**Status:** approved in chat on 2026-10-31 (plan review by the reviewer, answers folded in below).

## Intent

Nonprofits often upload a logo but leave brand colors blank. Today the DESIGN node
(PR #11, `feat/bui-64-66-design-node`) falls to BUILD default colors and raises the
`default_design_track` flag. With D8, the node reads the logo, picks its two most
prominent brand colors, and uses them as `tokens.colors.primary` and `secondary`,
recording where they came from so the reviewer can check them.

## Goals

- When `brand_colors` is empty and `logo` is set, `primary` (and `secondary` when a
  distinct second hue exists) come from the logo.
- Every derived token has a D5 decision citing intake field `logo`, plus one
  reviewer-facing assumption saying the colors were derived.
- Extraction is deterministic: the same logo bytes always give the same hex values,
  so reruns keep stable tokens.
- Extraction failure never fails the job. Defaults apply and an assumption says why.
- Tests run with no network and no storage credentials.

## Non-goals

- Contrast fixing (D9, BUI-72). Derived colors flow into it like typed brand colors do.
- Storage access to the private Supabase bucket (BUI-93). Only `https://` is fetched.
- Plain-language color names (D6, BUI-69/70).
- Changing the Stage 1 field names. `logo` is an asset URL, as PR #11 assumes.

## Decisions

| Topic | Decision |
|---|---|
| Base branch | Stack on `origin/feat/bui-64-66-design-node` (PR #11). Note the stack in the PR body like #10 and #11 do. |
| Where the code goes | New `agent/pipeline/design_spec/logo_palette.py` (pure extraction). Small edits to `generation.py` (token assembly, decisions, D10 rule) and `nodes/design.py` (fetch, injectable). |
| Logo file types | PNG, JPG, SVG per the Intake Form PRD (10 MB max). WebP works for free through Pillow. |
| Raster extraction | Pillow: RGBA, thumbnail to 128 px, drop pixels with alpha < 128, near-white (every channel >= 235) and near-black (every channel <= 25); median-cut quantize to 8 colors; rank by pixel count. |
| SVG extraction | Regex over `fill`, `stroke`, `stop-color` in attributes and inline `style`; resolve with `PIL.ImageColor.getrgb`; same filters and ranking as raster. No rasterizer. |
| Picking colors | Primary = most frequent color with HSV saturation >= 0.15. Secondary = next color whose hue differs by >= 30 degrees. No such color means secondary stays the BUILD default. |
| Black-and-white or grayscale logo | Nothing usable. Defaults apply and an assumption records it. |
| D10 flag | `default_design_track` fires only when no logo was uploaded. With a logo it never fires, whether extraction succeeds or fails. PR #11 fires it per missing item; tell the BUI-64/66 owner (achiu). |
| Reviewer visibility | An `assumption` decision, not a new flag code. The PRD's reviewer panel lists a closed set of flag codes. |
| Fetching | `run_design` takes an injectable `fetch_asset`. The default fetches `https://` only, 10 s timeout, 10 MB cap. Anything else is a fetch failure. |
| Fixtures | Test logos are generated in the tests with Pillow (PNG) or inline strings (SVG). No binary files in git. |
| Dependencies | `pillow>=11.3`, `httpx>=0.27` added to `agent/pyproject.toml`. |

## What the reviewer sees

Tokens panel: primary and secondary swatches from the logo. Assumptions panel: one
line, "Brand colors were derived from the uploaded logo because none were provided;
confirm they match the brand." or, on failure, "No brand colors were provided and the
logo could not be used (<reason>). BUILD default colors were applied." No
`default_design_track` flag.
