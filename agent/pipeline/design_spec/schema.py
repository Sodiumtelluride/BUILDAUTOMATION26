"""
design_spec schema: the contract the DESIGN node writes and CODE_GENERATION,
CONTENT and SEO read.

Source: Design Agent PRD v1 draft, §3 "Design Spec Contract".

Contract rules this module enforces:
  - Strict schema: every model rejects unknown keys (extra="forbid") and
    values are not silently coerced (e.g. "80" is not accepted as 80).
  - No free text a downstream stage must interpret: anything a later stage
    reads is a fixed word (Literal), a pattern-checked ID, or a number.
    The only free string is ``Assumption.text``, which only reviewers read.
    Font names are plain strings for now; the approved-font list is D6.
  - Every flag carries a code from a closed set. Instead of a prose
    ``detail``, each code has typed fields (e.g. which section it is about).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Dict, List, Literal, Optional, Tuple, TypeVar, Union

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictInt, StringConstraints

# ---------------------------------------------------------------------------
# Fixed vocabularies (the only words downstream stages will ever see)
# NOTE: these must match the frozen Stage 1 output schema; confirm in review.
# ---------------------------------------------------------------------------

# Stage 1 fields a design decision can cite (§3 "source_fields").
IntakeField = Literal[
    "organization_name",
    "organization_type",
    "primary_goal",
    "organization_description",
    "target_audience",
    "pages",
    "features",
    "tone",
    "visual_style",
    "brand_colors",
    "brand_fonts",
    "logo",
    "reference_sites",
    "content_exclusions",
]

Feature = Literal[
    "contact_form",
    "event_calendar",
    "photo_gallery",
    "newsletter_signup",
    "social_media_feed",
    "member_application_form",
    "donation_button",
    "password_protected_page",
]

DataRecipe = Literal["form_submissions", "events"]

Integration = Literal[
    "google_analytics",
    "mailchimp",
    "hubspot",
    "stripe",
    "paypal",
    "calendly",
    "instagram_feed",
    "facebook_page",
    "linkedin",
    "notion",
    "linktree",
    "airtable",
]

Tone = Literal["professional", "friendly", "casual", "inspiring", "authoritative", "playful", "minimalist"]

ContentBlockKind = Literal[
    "headline", "subheadline", "body", "cta_label", "list_item", "image_alt", "caption", "quote", "label"
]

# shadcn/ui color roles. CSS variable = "--" + name with "_" -> "-".
ColorRole = Literal[
    "background",
    "foreground",
    "primary",
    "primary_foreground",
    "secondary",
    "secondary_foreground",
    "muted",
    "muted_foreground",
    "accent",
    "accent_foreground",
    "border",
    "card",
    "card_foreground",
    "popover",
    "popover_foreground",
    "destructive",
    "destructive_foreground",
    "input",
    "ring",
]

# ---------------------------------------------------------------------------
# ID and value formats
# ---------------------------------------------------------------------------

SECTION_ID_PATTERN = r"^[a-z][a-z0-9]*(-[a-z0-9]+)*-[0-9]+$"  # e.g. "hero-1"
CONTENT_BLOCK_ID_PATTERN = r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9_-]*)+$"  # e.g. "home.hero.headline"

Hex = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]
SectionId = Annotated[str, StringConstraints(pattern=SECTION_ID_PATTERN)]
ContentBlockId = Annotated[str, StringConstraints(pattern=CONTENT_BLOCK_ID_PATTERN)]
Slug = Annotated[str, StringConstraints(pattern=r"^/([a-z0-9]+(-[a-z0-9]+)*(/[a-z0-9]+(-[a-z0-9]+)*)*)?$")]
Rem = Annotated[str, StringConstraints(pattern=r"^(0|[0-9]+(\.[0-9]+)?rem)$")]
# Catalog section type ID, e.g. "hero-centered". Membership in the approved
# catalog is D2's check; this only guarantees an ID, not prose.
SectionType = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")]
# shadcn/ui component name, e.g. "Button", "DropdownMenu".
ComponentName = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Za-z0-9]*$")]
FigmaUrl = Annotated[str, StringConstraints(pattern=r"^https://(www\.)?figma\.com/\S+$")]
NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]

T = TypeVar("T")


def _no_duplicates(xs: List[T]) -> List[T]:
    if len(set(xs)) != len(xs):
        raise ValueError("must not contain duplicates")
    return xs


UniqueList = Annotated[List[T], AfterValidator(_no_duplicates)]
NonEmptyUniqueList = Annotated[List[T], Field(min_length=1), AfterValidator(_no_duplicates)]


class _Strict(BaseModel):
    """Base for every contract model: unknown keys rejected, no coercion."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------


class Fonts(_Strict):
    heading: NonEmptyStr
    body: NonEmptyStr


class ContrastAdjustment(_Strict):
    role: ColorRole  # the color that was changed
    pair: Tuple[ColorRole, ColorRole] = Field(strict=False)  # (text, background); JSON sends a list
    from_: Hex = Field(alias="from")
    to: Hex
    ratio_before: float
    ratio_after: float

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, populate_by_name=True)


class Tokens(_Strict):
    colors: Annotated[Dict[ColorRole, Hex], Field(min_length=1)]
    fonts: Fonts
    radius: Rem
    contrast_adjustments: List[ContrastAdjustment]


# ---------------------------------------------------------------------------
# Page map
# ---------------------------------------------------------------------------


class ContentBlock(_Strict):
    id: ContentBlockId
    kind: ContentBlockKind
    max_chars: StrictInt = Field(ge=1)


class Section(_Strict):
    id: SectionId
    type: SectionType
    components: UniqueList[ComponentName]
    content_blocks: List[ContentBlock] = Field(min_length=1)
    source_fields: NonEmptyUniqueList[IntakeField]


class Page(_Strict):
    slug: Slug
    sections: List[Section] = Field(min_length=1)


# ---------------------------------------------------------------------------
# Flags: a code + typed fields, no prose
# ---------------------------------------------------------------------------


class ToneStyleConflictFlag(_Strict):
    code: Literal["tone_style_conflict"]
    tones: NonEmptyUniqueList[Tone]


class DefaultDesignTrackFlag(_Strict):
    code: Literal["default_design_track"]
    missing: NonEmptyUniqueList[Literal["logo", "brand_colors", "brand_fonts"]]


class HeroImageFallbackFlag(_Strict):
    code: Literal["hero_image_fallback"]
    section_id: SectionId


class NoFigmaFlag(_Strict):
    code: Literal["no_figma"]
    reason: Literal["figma_disabled", "figma_unavailable", "figma_error"]


Flag = Annotated[
    Union[ToneStyleConflictFlag, DefaultDesignTrackFlag, HeroImageFallbackFlag, NoFigmaFlag],
    Field(discriminator="code"),
]


# ---------------------------------------------------------------------------
# Assumptions: reviewer-facing only; each cites its source field (PRD §4 UI)
# ---------------------------------------------------------------------------


class Assumption(_Strict):
    source_fields: NonEmptyUniqueList[IntakeField]
    text: Annotated[str, StringConstraints(min_length=1, max_length=300)]  # never parsed downstream


class DataRequirement(_Strict):
    recipe: DataRecipe


# ---------------------------------------------------------------------------
# The spec (§3)
# ---------------------------------------------------------------------------


class DesignSpec(_Strict):
    job_id: uuid.UUID = Field(strict=False)  # accepts the UUID string from JSON
    tokens: Tokens
    pages: List[Page] = Field(min_length=1)
    features: UniqueList[Feature]
    data_requirements: List[DataRequirement]
    integrations: UniqueList[Integration]
    flags: List[Flag]
    assumptions: List[Assumption]
    figma_url: Optional[FigmaUrl] = None
