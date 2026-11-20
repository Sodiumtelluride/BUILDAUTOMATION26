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
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .catalog import TemplateCatalog
from .intake import PAGE_SLUGS, DesignIntake
from .intake_mapping import IntakeNotes
from .validate import FEATURE_SECTIONS, MEMBER_FORM_TYPE

FLAG_FONT_SUBSTITUTED = "font_substituted"
FLAG_UNSUPPORTED_FEATURE = "unsupported_feature"
FLAG_LOGO_UNREADABLE = "logo_unreadable"  # added by the DESIGN node, never by the model

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
        {"text": "The bold theme family (the default) fits the friendly, energetic tone and the visual style asked for.", "field": "tone"},
        {
            "text": "primary is the client's forest green #2E7D32 and secondary the warm amber #FFA000; the other roles are a light palette with WCAG AA body contrast.",
            "field": "brand_colors",
        },
    ],
}

EXAMPLE_SPEC: str = json.dumps(_EXAMPLE, indent=2)


def _catalog_lines(catalog: TemplateCatalog) -> List[str]:
    lines: List[str] = []
    for type_id, blocks in catalog.types.items():
        theme = catalog.theme_of(type_id)
        if theme:
            label = f"{type_id} [{theme}]"
        elif type_id == MEMBER_FORM_TYPE:
            label = f"{type_id} [any family; only with the member_application_form feature]"
        else:
            label = f"{type_id} [any family]"
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
        "- tokens.radius: one CSS length such as 0.5rem or 0.75rem.",
        "- tokens.contrast_adjustments: one {role, from, to} for each brand color you changed to meet contrast",
        "  (from = the client's hex, to = the value you put in tokens.colors[role]); [] when you changed none.",
        "- pages: one entry per requested page: {slug, sections}. slug is \"/\" or \"/lowercase-path\".",
        "- sections: {id, type, components, content_blocks, source_fields}. type is a catalog type id (section 2).",
        "  content_blocks are that type's catalog blocks, ids copied exactly: {id, kind, max_chars?}.",
        "  components: the shadcn primitives the section uses, lowercase (button, card, badge, input, label, textarea).",
        "  source_fields: the intake field names (snake_case, as given in the message) that motivated the section.",
        "- features: the intake's feature names as given. integrations: the intake's integrations as given.",
        "- data_requirements: [] unless the site has a member-application-form section; then [{\"recipe\": \"form_submissions\"}].",
        "- flags: [{code, detail}] for anything the reviewer must look at.",
        "- assumptions: one {text, field} per guess you made. text is one plain sentence; field is the single intake",
        "  field name (snake_case, as given in the message) the guess is about.",
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
        "type-led and story-driven), and say why in assumptions. Use only that family's type ids for the themed",
        "roles. Sections marked [any family] are base sections with one look everywhere; use them with any family.",
        "",
        "4. Pages: produce exactly the requested pages, no others, with these slugs:",
        *slug_lines,
        "The home page starts with a hero and has at least three sections.",
        "Every other page starts with that family's page-header, never a hero.",
        "Section ids are <role>-<n> (hero-1, page-header-1, programs-2, ...) and unique across the whole site.",
        "",
        "5. Colors: tokens.colors.primary is the first brand color given; secondary the second, or a complement if only",
        "one was given; resolve plain-language color names (for example \"warm gold\") to hex and say so in assumptions.",
        "With no brand colors and a logo, choose a palette the logo's colors would sit well on and say so. With no",
        "branding at all, use a calm palette suited to the organization type and say so. The site is light-only:",
        "background is white or near-white, every foreground on its background meets WCAG AA (4.5:1 for body text).",
        "If a brand color fails that, darken or lighten it just enough and record it in tokens.contrast_adjustments.",
        "",
        f"6. Fonts: if the intake names fonts outside [{fonts}], use the closest allowed pair (serif-looking headings ->",
        f"Instrument Serif, otherwise Inter) and add a flag with code \"{FLAG_FONT_SUBSTITUTED}\" naming the requested fonts.",
        "",
        "7. A requested feature with a section in the catalog MUST get that section, and that section appears only",
        "when its feature was requested:",
        *[f"- {feature} -> {type_id}" for feature, type_id in FEATURE_SECTIONS.items()],
        f"Any other feature gets a flag with code \"{FLAG_UNSUPPORTED_FEATURE}\" naming the feature and what you did",
        "instead (for example a cta that links out). Never invent a section type for them.",
        "",
        "8. The client's content exclusions are a hard constraint on every choice. Reference sites are inspiration",
        "only; never copy their structure or content.",
        "",
        "9. Fill source_fields on every section (at least one intake field name) and put every guess in assumptions.",
        "",
        "10. Revisions: when the message includes a previous spec, change only what the reviewer's notes ask for.",
        "Every section that stays keeps its id, type and page. Never reuse an old id for a different section.",
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
    previous_spec: Optional[Mapping[str, Any]] = None,
    reviewer_notes: Optional[str] = None,
) -> str:
    """The per-job message: intake, notes, job id, the reviewer's notes when there are any; on a rerun
    the previous spec; on a retry the previous reply with its problems.

    ``previous_spec`` must be in the reply's shape (``sources.to_reply_shape``), so a model that copies
    it unchanged returns a valid reply."""
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
    if previous_spec is not None:
        lines += ["", "This is a revision. The previous spec for this job:", json.dumps(previous_spec, indent=2)]
    if reviewer_notes and reviewer_notes.strip():
        lines += ["", "Reviewer notes:", reviewer_notes.strip()]
    if previous_issues:
        lines += ["", "Your previous spec had these problems. Return the corrected complete spec:", *[f"- {i}" for i in previous_issues]]
        if previous_reply:
            lines += ["", "Your previous reply was:", previous_reply]
    return "\n".join(lines)
