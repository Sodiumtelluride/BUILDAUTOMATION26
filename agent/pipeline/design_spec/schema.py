"""
design_spec schema: the contract the DESIGN node writes and CODE_GENERATION,
CONTENT and SEO read.

Source: Design Agent PRD v1 draft, §3 "Design Spec Contract".

Contract rules this module enforces:
  - Strict schema: every model rejects unknown keys (extra="forbid") and
    values are not silently coerced (e.g. "80" is not accepted as 80).
  - No free text a downstream stage must interpret: anything a later stage
    reads is a fixed word (Literal), a pattern-checked ID, or a number.
    The only free string is ``Decision.summary``, which only reviewers read.
    Font names are plain strings for now; the approved-font list is D6.
  - Every flag carries a code from a closed set. Instead of a prose
    ``detail``, each code has typed fields (e.g. which section it is about).
  - D5: every design decision is recorded in ``decisions`` with the source
    that caused it (an intake field, a rule, a default, ...). Assumptions are
    decisions with ``kind="assumption"``. See decisions.py.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Dict, List, Literal, Optional, Tuple, TypeVar, Union

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictInt, StringConstraints, model_validator

# ---------------------------------------------------------------------------
# Fixed vocabularies (the only words downstream stages will ever see)
# NOTE: these must match the frozen Stage 1 output schema; confirm in review.
# ---------------------------------------------------------------------------

# Stage 1 fields a design decision can cite (D5).
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
    "brand_assets",  # "Additional brand assets" upload; D12 needs it for the hero photo
    "reference_sites",
    "integrations",  # "Third-party integrations"; the spec's integrations list comes from it
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
# Decision log (D5): what was decided, and the source behind it
# ---------------------------------------------------------------------------

DECISION_ID_PATTERN = r"^dec-[1-9][0-9]*$"  # e.g. "dec-12"

# What a decision is about, addressed by stable ID (never by list index, which
# shifts between revisions):
#   tokens.colors.<role> | tokens.fonts.heading | tokens.fonts.body | tokens.radius
#   page:<slug> | section:<section id> | flag:<code> | flag:<code>:<section id>
#   feature:<name> | data_requirement:<recipe> | integration:<name>
#   spec  (assumptions about the whole site only)
TARGET_PATTERN = (
    r"^(tokens\.colors\.[a-z_]+|tokens\.fonts\.(heading|body)|tokens\.radius"
    r"|page:/[a-z0-9/-]*|section:[a-z0-9-]+|flag:[a-z_]+(:[a-z0-9-]+)?"
    r"|feature:[a-z_]+|data_requirement:[a-z_]+|integration:[a-z_]+|spec)$"
)

DecisionId = Annotated[str, StringConstraints(pattern=DECISION_ID_PATTERN)]
Target = Annotated[str, StringConstraints(pattern=TARGET_PATTERN)]
# ID of a record outside the spec: a pgvector row, a reviewer note, a change request.
RecordId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")]

DecisionKind = Literal[
    "token",
    "page",
    "section",
    "flag",
    "contrast_fix",
    "feature",
    "data_requirement",
    "integration",
    "assumption",
]

# Which targets each kind may point at. Assumptions may be about anything.
KIND_TARGET_PREFIXES: Dict[str, Tuple[str, ...]] = {
    "token": ("tokens.",),
    "page": ("page:",),
    "section": ("section:",),
    "flag": ("flag:",),
    "contrast_fix": ("tokens.colors.",),
    "feature": ("feature:",),
    "data_requirement": ("data_requirement:",),
    "integration": ("integration:",),
}

RuleRef = Literal[
    "wcag_aa",  # D9 contrast check
    "feature_data_recipe",  # D4: a feature that needs storage
]
DefaultRef = Literal[
    "build_tokens",  # BUILD default token values
    "default_design_track",  # D10
    "hero_gradient",  # D12
]
ConfigRef = Literal["figma_generation"]  # rollout feature flags (PRD §5)


class IntakeSource(_Strict):
    type: Literal["intake"]
    ref: IntakeField


class RetrievalSource(_Strict):
    """D13/D18: a pgvector record (past run, template, component pattern)."""

    type: Literal["retrieval"]
    ref: RecordId


class RuleSource(_Strict):
    type: Literal["rule"]
    ref: RuleRef


class DefaultSource(_Strict):
    type: Literal["default"]
    ref: DefaultRef


class ConfigSource(_Strict):
    type: Literal["config"]
    ref: ConfigRef


class ReviewerNoteSource(_Strict):
    """D17: a Stage 6 rejection note routed back to DESIGN."""

    type: Literal["reviewer_note"]
    ref: RecordId


class ChangeRequestSource(_Strict):
    """D19: a spec_change_request from CODE_GENERATION."""

    type: Literal["change_request"]
    ref: RecordId


Source = Annotated[
    Union[
        IntakeSource,
        RetrievalSource,
        RuleSource,
        DefaultSource,
        ConfigSource,
        ReviewerNoteSource,
        ChangeRequestSource,
    ],
    Field(discriminator="type"),
]


class Decision(_Strict):
    id: DecisionId
    kind: DecisionKind
    targets: NonEmptyUniqueList[Target]
    sources: NonEmptyUniqueList[Source]
    method: Literal["code", "llm"]
    """code = set by deterministic code (provenance is computed).
    llm = chosen by the model, which also cited the sources (provenance is claimed)."""
    revision: StrictInt = Field(ge=1)
    """Which DESIGN run made this decision. 1 = first run; each rerun adds 1."""
    derived_from: UniqueList[DecisionId] = Field(default_factory=list)
    """Earlier decisions this one builds on, e.g. a contrast fix on a brand color."""
    supersedes: Optional[DecisionId] = None
    """On a rerun: the decision this one replaces. The old one stays in the log."""
    summary: Optional[Annotated[str, StringConstraints(min_length=1, max_length=300)]] = None
    """Reviewer-facing note. Required for assumptions. Never parsed downstream."""

    @model_validator(mode="after")
    def _kind_matches_targets(self) -> "Decision":
        if self.kind == "assumption":
            if self.summary is None:
                raise ValueError("an assumption needs a summary for the reviewer")
            return self
        allowed = KIND_TARGET_PREFIXES[self.kind]
        wrong = [t for t in self.targets if not t.startswith(allowed)]
        if wrong:
            raise ValueError(f"a {self.kind} decision cannot target {wrong}; allowed: {list(allowed)}")
        return self


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
    decisions: List[Decision] = Field(min_length=1)
    figma_url: Optional[FigmaUrl] = None
