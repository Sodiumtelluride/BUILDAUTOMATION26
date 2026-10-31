"""
The frozen Stage 1 intake, as the DESIGN stage consumes it.

Stage 1 (the Next.js intake form, ``src/lib/intake/contract.ts``) collects
answers in camelCase. The INTAKE node normalizes them into
``IntakeOutput.project_spec`` using the snake_case names below — the same
names as ``IntakeField`` in schema.py, so every design decision can cite the
field it came from (D5 source-field traceability).

Mapping from the frozen form contract:

    organizationName         -> organization_name
    organizationType         -> organization_type   (snake_cased option)
    primaryGoal              -> primary_goal        (snake_cased option)
    organizationDescription  -> organization_description
    targetAudience           -> target_audience
    pages                    -> pages               (snake_cased options)
    features                 -> features            (snake_cased options)
    toneAndVoice             -> tone                (max 3, like the form)
    visualStyle              -> visual_style
    brandColors              -> brand_colors        (parsed to hex values)
    brandFonts               -> brand_fonts         (parsed to font names)
    logoFile upload          -> logo                (asset URL, never bytes)
    content uploads          -> brand_assets        (asset URLs)
    referenceWebsites        -> reference_sites     (max 3)
    integrations             -> integrations        (snake_cased options)
    contentRestrictions      -> content_exclusions  ("never say or do")

Uploaded assets are referenced by URL only; file contents and secrets never
enter prompts or specs.

Note: a "pages: Other" answer has no slug of its own; the INTAKE node must
resolve it to one of the known pages (or drop it) before DESIGN runs.
"""

from __future__ import annotations

from typing import Annotated, Any, List, Literal, Mapping, Optional

from pydantic import Field, StringConstraints, ValidationError

from .schema import (
    Feature,
    Hex,
    Integration,
    NonEmptyStr,
    NonEmptyUniqueList,
    Tone,
    UniqueList,
    _Strict,
)

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

# Route for each requested page. Keys here are the full frozen page vocabulary.
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

BrandingField = Literal["logo", "brand_colors", "brand_fonts"]


class DesignIntake(_Strict):
    """Stage 1 answers the DESIGN node reads. Field names match IntakeField."""

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


def parse_design_intake(project_spec: Mapping[str, Any]) -> DesignIntake:
    """
    Parse ``IntakeOutput.project_spec`` into the typed intake.

    Raises ``ValueError`` listing what is wrong; DESIGN must not run on an
    intake it cannot fully read (the contract does not define fallbacks for
    missing fields).
    """
    try:
        return DesignIntake.model_validate(dict(project_spec))
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(str(s) for s in e['loc'])}: {e['msg']}" for e in exc.errors())
        raise ValueError(f"intake_output.project_spec does not match the frozen Stage 1 schema: {problems}") from exc


def missing_branding(intake: DesignIntake) -> List[BrandingField]:
    """Branding inputs that were not provided (drives the default_design_track flag, D10)."""
    out: List[BrandingField] = []
    if intake.logo is None:
        out.append("logo")
    if not intake.brand_colors:
        out.append("brand_colors")
    if not intake.brand_fonts:
        out.append("brand_fonts")
    return out
