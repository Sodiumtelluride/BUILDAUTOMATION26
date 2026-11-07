"""
The prompt that turns a structured intake into design-spec.json.

``render_system_prompt`` is static per catalog version: the contract, the
section catalog, the theme families and the rules. ``render_user_message`` is
per job: the intake, the reviewer notes, the job id and, on a retry, the
problems the previous reply had. Both are plain strings a person can paste
into Claude Code (see the CLI's --print-prompt).
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Sequence

from .catalog import TemplateCatalog
from .intake import PAGE_SLUGS, DesignIntake
from .intake_mapping import IntakeNotes

FLAG_FONT_SUBSTITUTED = "font_substituted"
FLAG_UNSUPPORTED_FEATURE = "unsupported_feature"

MAX_CHARS: Dict[str, int] = {"headline": 80, "subhead": 160, "body": 400, "label": 40, "items": 60}

_EXAMPLE_COLORS = {
    "background": "#FFFFFF",
    "foreground": "#0F172A",
    "card": "#FFFFFF",
    "card-foreground": "#0F172A",
    "popover": "#FFFFFF",
    "popover-foreground": "#0F172A",
    "primary": "#2E7D32",
    "primary-foreground": "#FFFFFF",
    "secondary": "#FFA000",
    "secondary-foreground": "#1A1A1A",
    "muted": "#F1F5F9",
    "muted-foreground": "#475569",
    "accent": "#E8F5E9",
    "accent-foreground": "#1B5E20",
    "destructive": "#DC2626",
    "destructive-foreground": "#FFFFFF",
    "border": "#E2E8F0",
    "input": "#E2E8F0",
    "ring": "#2E7D32",
}


def _block(block_id: str, kind: str) -> Dict[str, Any]:
    block: Dict[str, Any] = {"id": block_id, "kind": kind}
    if kind in MAX_CHARS:
        block["max_chars"] = MAX_CHARS[kind]
    return block


_EXAMPLE: Dict[str, Any] = {
    "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "tokens": {
        "colors": _EXAMPLE_COLORS,
        "fonts": {"heading": "Instrument Serif", "body": "Inter"},
        "radius": "0.75rem",
        "contrast_adjustments": [],
    },
    "pages": [
        {
            "slug": "/",
            "sections": [
                {
                    "id": "hero-1",
                    "type": "hero-bold",
                    "components": ["button"],
                    "content_blocks": [
                        _block("hero.headline", "headline"),
                        _block("hero.subhead", "subhead"),
                        _block("hero.primary_cta", "cta"),
                        _block("hero.secondary_cta", "cta"),
                        _block("hero.image", "image"),
                    ],
                    "source_fields": ["organization_name", "organization_description", "tone"],
                },
                {
                    "id": "stats-1",
                    "type": "stats-bold",
                    "components": [],
                    "content_blocks": [
                        _block("stats.headline", "headline"),
                        _block("stats.stat_1", "stat"),
                        _block("stats.stat_2", "stat"),
                        _block("stats.stat_3", "stat"),
                    ],
                    "source_fields": ["organization_description"],
                },
                {
                    "id": "cta-1",
                    "type": "cta-bold",
                    "components": ["button"],
                    "content_blocks": [_block("cta.headline", "headline"), _block("cta.body", "body"), _block("cta.button", "cta")],
                    "source_fields": ["primary_goal"],
                },
            ],
        },
        {
            "slug": "/about",
            "sections": [
                {
                    "id": "hero-2",
                    "type": "hero-bold",
                    "components": ["button"],
                    "content_blocks": [
                        _block("hero.headline", "headline"),
                        _block("hero.subhead", "subhead"),
                        _block("hero.primary_cta", "cta"),
                    ],
                    "source_fields": ["organization_description"],
                },
                {
                    "id": "programs-2",
                    "type": "programs-bold",
                    "components": ["card"],
                    "content_blocks": [
                        _block("programs.headline", "headline"),
                        _block("programs.intro", "body"),
                        _block("programs.items", "items"),
                    ],
                    "source_fields": ["organization_description", "target_audience"],
                },
            ],
        },
    ],
    "features": ["contact_form", "donation_button"],
    "data_requirements": [],
    "integrations": ["stripe", "google_analytics"],
    "flags": [
        {"code": FLAG_FONT_SUBSTITUTED, "detail": "Source Serif 4 is not bundled; Instrument Serif used for headings"},
        {"code": FLAG_UNSUPPORTED_FEATURE, "detail": "contact_form has no section in the catalog; the contact page uses a cta-bold"},
        {"code": FLAG_UNSUPPORTED_FEATURE, "detail": "donation_button has no section in the catalog; the donate page uses a cta-bold linking to Stripe"},
    ],
    "assumptions": [
        "The bold theme family (the default) fits the friendly, energetic tone and the visual style asked for.",
        "primary is the client's forest green #2E7D32 and secondary the warm amber #FFA000; the other roles are a light palette with WCAG AA body contrast.",
    ],
}

EXAMPLE_SPEC: str = json.dumps(_EXAMPLE, indent=2)


def _catalog_lines(catalog: TemplateCatalog) -> List[str]:
    lines: List[str] = []
    for type_id, blocks in catalog.types.items():
        theme = catalog.theme_of(type_id)
        label = f"{type_id} [{theme}]" if theme else f"{type_id} [no family; only with the member_application_form feature]"
        parts = [f"{block_id} ({b.kind}{', optional' if b.optional else ''})" for block_id, b in blocks.items()]
        lines.append(f"- {label}: {', '.join(parts)}")
    return lines


def _theme_lines(catalog: TemplateCatalog) -> List[str]:
    return [f"- {theme}: " + ", ".join(f"{role} = {type_id}" for role, type_id in roles.items()) for theme, roles in catalog.themes.items()]


def render_system_prompt(catalog: TemplateCatalog) -> str:
    """The static instructions: contract, catalog, families, rules, example."""
    fonts = ", ".join(catalog.fonts)
    color_roles = ", ".join(_EXAMPLE_COLORS)
    slug_lines = [f"- {name} -> {slug}" for name, slug in PAGE_SLUGS.items()]
    lines = [
        "You are the BUILD UMass design agent. From a client's intake you produce exactly one JSON object: the",
        "design-spec.json that the BUILD site template builds a static multi-page site from.",
        "Reply with JSON only. No prose before or after, no markdown code fence.",
        "",
        "1. Contract (every key is required):",
        "- job_id: the job id given in the message, copied exactly.",
        f"- tokens.colors: an object keyed by these shadcn roles, hyphenated, hex values (#RRGGBB): {color_roles}.",
        f"- tokens.fonts: {{heading, body}}. heading must be one of: {fonts}. body must be Inter.",
        "- tokens.radius: one CSS length such as 0.5rem or 0.75rem. tokens.contrast_adjustments: [].",
        "- pages: one entry per requested page: {slug, sections}. slug is \"/\" or \"/lowercase-path\".",
        "- sections: {id, type, components, content_blocks, source_fields}. type is a catalog type id (section 2).",
        "  content_blocks are that type's catalog blocks, ids copied exactly: {id, kind, max_chars?}.",
        "  components: the shadcn primitives the section uses, lowercase (button, card, badge, input, label, textarea).",
        "  source_fields: the intake field names (snake_case, as given in the message) that motivated the section.",
        "- features: the intake's feature names as given. integrations: the intake's integrations as given.",
        "- data_requirements: [] unless the site has a member-application-form section; then [{\"recipe\": \"form_submissions\"}].",
        "- flags: [{code, detail}] for anything the reviewer must look at. assumptions: one plain sentence per guess you made.",
        "",
        "2. Section catalog (the ONLY allowed type ids and block ids; blocks not marked optional are required):",
        *_catalog_lines(catalog),
        "",
        f"max_chars by kind: headline {MAX_CHARS['headline']}, subhead {MAX_CHARS['subhead']}, body {MAX_CHARS['body']}, "
        f"label {MAX_CHARS['label']}, items {MAX_CHARS['items']} (per item title). cta, image and stat blocks have no max_chars.",
        "",
        "3. Theme families (one visual treatment per role):",
        *_theme_lines(catalog),
        "Use ONE family for the whole site. Default to bold (high-contrast and energetic); pick another only when the",
        "tone and visual style clearly ask for it (classic = balanced, minimal = quiet and spacious, editorial =",
        "type-led and story-driven), and say why in assumptions. Use only that family's type ids.",
        "member-application-form belongs to no family and is used only when",
        "member_application_form is among the features.",
        "",
        "4. Pages: produce exactly the requested pages, no others, with these slugs:",
        *slug_lines,
        "The home page starts with a hero and has at least three sections. Every other page starts with a hero or a",
        "programs section. Section ids are <role>-<n> (hero-1, stats-1, programs-2, ...) and unique across the whole site.",
        "",
        "5. Colors: tokens.colors.primary is the first brand color given; secondary the second, or a complement if only",
        "one was given; resolve plain-language color names (for example \"warm gold\") to hex and say so in assumptions.",
        "With no brand colors and a logo, choose a palette the logo's colors would sit well on and say so. With no",
        "branding at all, use a calm palette suited to the organization type and say so. The site is light-only:",
        "background is white or near-white, every foreground on its background meets WCAG AA (4.5:1 for body text).",
        "",
        f"6. Fonts: if the intake names fonts outside [{fonts}], use the closest allowed pair (serif-looking headings ->",
        f"Instrument Serif, otherwise Inter) and add a flag with code \"{FLAG_FONT_SUBSTITUTED}\" naming the requested fonts.",
        "",
        f"7. Features with no section in the catalog get a flag with code \"{FLAG_UNSUPPORTED_FEATURE}\" naming the feature",
        "and what you did instead (for example a cta-band that links out). Never invent a section type for them.",
        "",
        "8. The client's content exclusions are a hard constraint on every choice. Reference sites are inspiration",
        "only; never copy their structure or content.",
        "",
        "9. Fill source_fields on every section and put every guess in assumptions.",
        "",
        "Example (two pages shown; yours lists every requested page):",
        EXAMPLE_SPEC,
    ]
    return "\n".join(lines)


def render_user_message(
    intake: DesignIntake,
    notes: IntakeNotes,
    job_id: uuid.UUID,
    previous_issues: Sequence[str] = (),
    previous_reply: str = "",
) -> str:
    """The per-job message: intake, notes, job id, and on a retry the previous reply with its problems."""
    lines = [
        f"Job id: {job_id}",
        "",
        "Requested pages and slugs:",
        *[f"- {name} -> {PAGE_SLUGS[name]}" for name in intake.pages],
        "",
        "Intake (structured):",
        json.dumps(intake.model_dump(), indent=2),
    ]
    note_lines: List[str] = []
    if notes.brand_colors_text:
        note_lines.append(f"- Brand colors as written by the client: {notes.brand_colors_text}")
    if notes.feature_details:
        note_lines.append(f"- Feature details: {notes.feature_details}")
    if notes.integration_details:
        note_lines.append(f"- Integration details: {notes.integration_details}")
    if notes.additional_info:
        note_lines.append(f"- Additional information: {notes.additional_info}")
    note_lines += [f"- {dropped}" for dropped in notes.dropped]
    if note_lines:
        lines += ["", "Notes:", *note_lines]
    if previous_issues:
        lines += ["", "Your previous spec had these problems. Return the corrected complete spec:", *[f"- {i}" for i in previous_issues]]
        if previous_reply:
            lines += ["", "Your previous reply was:", previous_reply]
    return "\n".join(lines)
