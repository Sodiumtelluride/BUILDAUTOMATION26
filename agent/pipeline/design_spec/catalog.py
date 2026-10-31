"""
The approved BUILD section catalog (D2).

This is the single source of truth for which section types the DESIGN node
may select, which shadcn/ui components a section may use, and which content
slots (BUI-66) each section exposes. validate.py rejects any spec that uses
a type, component, slot, kind or character limit not defined here.

Versioning: bump CATALOG_VERSION whenever an entry is added, removed, or an
existing slot's kind/limit changes, so stored specs can be traced to the
catalog they were validated against.

Content slot rules:
  - A content block's slot is the last dot-segment of its ID, e.g.
    "home.hero-1.headline" fills the "headline" slot. Slot names are unique
    within a section type, so Stage 4 (CONTENT) can address every block
    without ambiguity.
  - The slot fixes the block's kind. A block's max_chars may be at most the
    slot's limit (the generator uses the slot limit as-is; a tightened limit
    never breaks downstream).
  - required=True slots must be present on every section of that type.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from .schema import ContentBlockKind, Feature

CATALOG_VERSION = "1"


@dataclass(frozen=True)
class SlotDef:
    """One addressable content slot on a section type."""

    name: str
    kind: ContentBlockKind
    max_chars: int
    required: bool = False


@dataclass(frozen=True)
class SectionDef:
    """One approved section type."""

    type: str
    components: Tuple[str, ...]
    slots: Tuple[SlotDef, ...]

    def slot(self, name: str) -> Optional[SlotDef]:
        return next((s for s in self.slots if s.name == name), None)

    def required_slots(self) -> Tuple[SlotDef, ...]:
        return tuple(s for s in self.slots if s.required)


def _section(type_: str, components: Tuple[str, ...], *slots: SlotDef) -> SectionDef:
    names = [s.name for s in slots]
    if len(set(names)) != len(names):
        raise ValueError(f"catalog entry {type_!r} has duplicate slot names")
    return SectionDef(type=type_, components=components, slots=slots)


SECTION_CATALOG: Dict[str, SectionDef] = {
    d.type: d
    for d in (
        _section(
            "hero-centered",
            ("Button", "Badge"),
            SlotDef("headline", "headline", 80, required=True),
            SlotDef("subheadline", "subheadline", 160),
            SlotDef("cta", "cta_label", 24),
        ),
        _section(
            "hero-split",
            ("Button", "Badge"),
            SlotDef("headline", "headline", 80, required=True),
            SlotDef("subheadline", "subheadline", 160),
            SlotDef("cta", "cta_label", 24),
            SlotDef("image-alt", "image_alt", 125),
        ),
        _section(
            "stats-bar",
            ("Card",),
            SlotDef("heading", "headline", 60),
            SlotDef("stat-1", "list_item", 60, required=True),
            SlotDef("stat-2", "list_item", 60, required=True),
            SlotDef("stat-3", "list_item", 60, required=True),
        ),
        _section(
            "programs-grid",
            ("Card",),
            SlotDef("heading", "headline", 60, required=True),
            SlotDef("intro", "body", 300),
            SlotDef("item-1", "list_item", 160),
            SlotDef("item-2", "list_item", 160),
            SlotDef("item-3", "list_item", 160),
        ),
        _section(
            "services-grid",
            ("Card", "Button"),
            SlotDef("heading", "headline", 60, required=True),
            SlotDef("intro", "body", 300),
            SlotDef("item-1", "list_item", 160),
            SlotDef("item-2", "list_item", 160),
            SlotDef("item-3", "list_item", 160),
        ),
        _section(
            "team-grid",
            ("Card", "Avatar"),
            SlotDef("heading", "headline", 60, required=True),
            SlotDef("intro", "body", 300),
            SlotDef("member-1", "caption", 80),
            SlotDef("member-2", "caption", 80),
            SlotDef("member-3", "caption", 80),
            SlotDef("member-4", "caption", 80),
        ),
        _section(
            "about-story",
            ("Separator",),
            SlotDef("heading", "headline", 60, required=True),
            SlotDef("body", "body", 1200, required=True),
            SlotDef("quote", "quote", 200),
        ),
        _section(
            "mission-statement",
            ("Badge",),
            SlotDef("heading", "headline", 60, required=True),
            SlotDef("body", "body", 600, required=True),
        ),
        _section(
            "cta-band",
            ("Button",),
            SlotDef("headline", "headline", 70, required=True),
            SlotDef("supporting", "body", 160),
            SlotDef("cta", "cta_label", 24, required=True),
        ),
        _section(
            "faq-accordion",
            ("Accordion",),
            SlotDef("heading", "headline", 60, required=True),
            SlotDef("q-1", "label", 120),
            SlotDef("a-1", "body", 500),
            SlotDef("q-2", "label", 120),
            SlotDef("a-2", "body", 500),
            SlotDef("q-3", "label", 120),
            SlotDef("a-3", "body", 500),
        ),
        _section(
            "contact-form",
            ("Input", "Textarea", "Button", "Label"),
            SlotDef("heading", "headline", 60, required=True),
            SlotDef("body", "body", 300),
            SlotDef("cta", "cta_label", 24),
        ),
        _section(
            "event-list",
            ("Card", "Badge"),
            SlotDef("heading", "headline", 60, required=True),
            SlotDef("intro", "body", 300),
            SlotDef("empty-state", "body", 160),
        ),
        _section(
            "gallery-grid",
            ("Card", "AspectRatio"),
            SlotDef("heading", "headline", 60, required=True),
            SlotDef("intro", "body", 300),
            SlotDef("image-alt-1", "image_alt", 125),
            SlotDef("image-alt-2", "image_alt", 125),
            SlotDef("image-alt-3", "image_alt", 125),
        ),
        _section(
            "blog-list",
            ("Card",),
            SlotDef("heading", "headline", 60, required=True),
            SlotDef("intro", "body", 300),
        ),
        _section(
            "donation-cta",
            ("Button", "Card"),
            SlotDef("headline", "headline", 70, required=True),
            SlotDef("body", "body", 400),
            SlotDef("cta", "cta_label", 24, required=True),
        ),
        _section(
            "newsletter-signup",
            ("Input", "Button", "Label"),
            SlotDef("heading", "headline", 60, required=True),
            SlotDef("body", "body", 200),
            SlotDef("cta", "cta_label", 24),
        ),
        _section(
            "application-form",
            ("Input", "Textarea", "Button", "Label", "Checkbox"),
            SlotDef("heading", "headline", 60, required=True),
            SlotDef("body", "body", 400),
            SlotDef("cta", "cta_label", 24),
        ),
        _section(
            "social-feed",
            ("Card",),
            SlotDef("heading", "headline", 60, required=True),
            SlotDef("caption", "caption", 160),
        ),
        _section(
            "quote-spotlight",
            ("Card",),
            SlotDef("quote", "quote", 240, required=True),
            SlotDef("attribution", "caption", 80),
        ),
    )
}

# Which section type renders each intake feature. None = the feature needs no
# section of its own (handled at the page/infrastructure level).
FEATURE_SECTION_TYPES: Dict[Feature, Optional[str]] = {
    "contact_form": "contact-form",
    "event_calendar": "event-list",
    "photo_gallery": "gallery-grid",
    "newsletter_signup": "newsletter-signup",
    "social_media_feed": "social-feed",
    "member_application_form": "application-form",
    "donation_button": "donation-cta",
    "password_protected_page": None,
}


def get_section_def(section_type: str) -> Optional[SectionDef]:
    return SECTION_CATALOG.get(section_type)


def is_approved_type(section_type: str) -> bool:
    return section_type in SECTION_CATALOG
