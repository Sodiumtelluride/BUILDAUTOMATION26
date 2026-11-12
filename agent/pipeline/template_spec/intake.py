"""
The structured intake the design prompt reads (Stage 1 output, snake_case).

Field names and vocabularies mirror the frozen intake form
(src/lib/intake/contract.ts); intake_mapping.py turns the form's labels into
these values. Uploaded assets are URLs only; file contents never enter prompts.
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Mapping, Optional, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

OrganizationType = Literal[
    "student_organization",
    "campus_department",
    "small_business",
    "nonprofit",
    "personal_portfolio",
    "other",
]

PrimaryGoal = Literal[
    "attract_members",
    "sell_products_or_services",
    "share_information",
    "accept_donations",
    "build_professional_presence",
    "promote_events",
    "other",
]

PageName = Literal[
    "home",
    "about",
    "team",
    "services",
    "events",
    "blog",
    "contact",
    "gallery",
    "donate",
    "join_apply",
    "faq",
]

# Route for each requested page: the slugs the design spec must use.
PAGE_SLUGS: Mapping[PageName, str] = {
    "home": "/",
    "about": "/about",
    "team": "/team",
    "services": "/services",
    "events": "/events",
    "blog": "/blog",
    "contact": "/contact",
    "gallery": "/gallery",
    "donate": "/donate",
    "join_apply": "/join",
    "faq": "/faq",
}

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
]

Tone = Literal["professional", "friendly", "casual", "inspiring", "authoritative", "playful", "minimalist"]

Hex = Annotated[str, StringConstraints(pattern=r"^#[0-9A-F]{6}$")]
NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]

T = TypeVar("T")


def _no_duplicates(xs: List[T]) -> List[T]:
    if len(set(xs)) != len(xs):
        raise ValueError("must not contain duplicates")
    return xs


UniqueList = Annotated[List[T], AfterValidator(_no_duplicates)]
NonEmptyUniqueList = Annotated[List[T], Field(min_length=1), AfterValidator(_no_duplicates)]


class DesignIntake(BaseModel):
    """Stage 1 answers the design prompt reads."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    organization_name: Annotated[str, StringConstraints(min_length=2, max_length=100)]
    organization_type: OrganizationType
    primary_goal: PrimaryGoal
    organization_description: Annotated[str, StringConstraints(min_length=50, max_length=1000)]
    target_audience: Annotated[str, StringConstraints(min_length=30, max_length=500)]
    pages: NonEmptyUniqueList[PageName]
    features: UniqueList[Feature] = Field(default_factory=list)
    tone: Annotated[NonEmptyUniqueList[Tone], Field(max_length=3)]
    visual_style: Annotated[str, StringConstraints(min_length=30, max_length=500)]
    brand_colors: UniqueList[Hex] = Field(default_factory=list)
    brand_fonts: UniqueList[NonEmptyStr] = Field(default_factory=list)
    logo: Optional[NonEmptyStr] = None
    brand_assets: UniqueList[NonEmptyStr] = Field(default_factory=list)
    reference_sites: Annotated[UniqueList[NonEmptyStr], Field(max_length=3)] = Field(default_factory=list)
    integrations: UniqueList[Integration] = Field(default_factory=list)
    content_exclusions: Optional[Annotated[str, StringConstraints(min_length=1, max_length=500)]] = None
