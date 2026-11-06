"""
Intake form answers -> DesignIntake.

Input is the blob the intake API stores in intake_submissions.notes
(app/api/intake/route.ts): ``answers`` uses the form's exact option labels
(src/lib/intake/contract.ts) and ``attachments`` lists the uploaded files.
Every label is matched exactly; an unknown label is an error, never a guess.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from .intake import DesignIntake

LOGO_UPLOAD = "Yes — I will upload it"

ORGANIZATION_TYPES: Dict[str, str] = {
    "Student Organization": "student_organization",
    "Campus Department": "campus_department",
    "Small Business": "small_business",
    "Nonprofit": "nonprofit",
    "Personal / Portfolio": "personal_portfolio",
    "Other": "other",
}

PRIMARY_GOALS: Dict[str, str] = {
    "Attract new members": "attract_members",
    "Sell products or services": "sell_products_or_services",
    "Share information or resources": "share_information",
    "Accept donations": "accept_donations",
    "Build a professional presence": "build_professional_presence",
    "Promote events": "promote_events",
    "Other": "other",
}

PAGES: Dict[str, str] = {
    "Home": "home",
    "About": "about",
    "Team": "team",
    "Services": "services",
    "Events": "events",
    "Blog": "blog",
    "Contact": "contact",
    "Gallery": "gallery",
    "Donate": "donate",
    "Join/Apply": "join_apply",
    "FAQ": "faq",
    "Other": "",  # no route of its own; dropped and noted
}

FEATURES: Dict[str, str] = {
    "Contact form": "contact_form",
    "Event calendar": "event_calendar",
    "Photo gallery": "photo_gallery",
    "Newsletter signup": "newsletter_signup",
    "Social media feed": "social_media_feed",
    "Member application form": "member_application_form",
    "Donation button": "donation_button",
    "Password-protected page": "password_protected_page",
    "Other": "",
}

LOGO_OPTIONS = (LOGO_UPLOAD, "No — please create a simple text-based logo", "No — I will provide one later")

TONES: Dict[str, str] = {
    t: t.lower() for t in ("Professional", "Friendly", "Casual", "Inspiring", "Authoritative", "Playful", "Minimalist")
}

INTEGRATIONS: Dict[str, str] = {
    "Google Analytics": "google_analytics",
    "Mailchimp": "mailchimp",
    "HubSpot": "hubspot",
    "Stripe": "stripe",
    "PayPal": "paypal",
    "Calendly": "calendly",
    "Instagram feed": "instagram_feed",
    "Facebook page": "facebook_page",
    "LinkedIn": "linkedin",
    "Other": "",
}

_HEX_RE = re.compile(r"#(?:[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b")


class IntakeNotes(BaseModel):
    """Free text DesignIntake has no field for. Rendered into the prompt, never parsed."""

    model_config = ConfigDict(extra="forbid")

    brand_colors_text: str = ""
    feature_details: str = ""
    integration_details: str = ""
    additional_info: str = ""
    dropped: List[str] = Field(default_factory=list)


def asset_url(attachment: Mapping[str, Any]) -> str:
    return f"supabase://{attachment['bucket']}/{attachment['path']}"


def _lookup(field: str, label: str, table: Mapping[str, str]) -> str:
    if label not in table:
        raise ValueError(f"{field}: unknown option {label!r}")
    return table[label]


def _lookup_many(field: str, labels: Sequence[str], table: Mapping[str, str]) -> List[str]:
    values = [_lookup(field, label, table) for label in labels]
    return [v for v in values if v]


def _hex_colors(text: str) -> List[str]:
    out: List[str] = []
    for match in _HEX_RE.findall(text):
        digits = match[1:]
        if len(digits) == 3:
            digits = "".join(d * 2 for d in digits)
        value = f"#{digits.upper()}"
        if value not in out:
            out.append(value)
    return out


def _font_names(text: str) -> List[str]:
    names = [part.strip() for part in re.split(r",|/|\band\b", text)]
    out: List[str] = []
    for name in names:
        if name and name not in out:
            out.append(name)
    return out


def map_intake_answers(
    answers: Mapping[str, Any], attachments: Sequence[Mapping[str, Any]]
) -> Tuple[DesignIntake, IntakeNotes]:
    """Map the stored form answers to the structured intake plus reviewer notes.

    Raises ValueError on an unknown option label (naming the field) and
    pydantic's ValidationError when the mapped values break the intake rules.
    """
    dropped: List[str] = []

    pages = _lookup_many("pages", answers["pages"], PAGES)
    if "Other" in answers["pages"]:
        dropped.append('pages: "Other" was requested but has no route')

    features = _lookup_many("features", answers["features"], FEATURES)
    if "Other" in answers["features"]:
        dropped.append('features: "Other" has no section; see feature_details')

    integrations = _lookup_many("integrations", answers["integrations"], INTEGRATIONS)
    if "Other" in answers["integrations"]:
        dropped.append('integrations: "Other" is not supported; see integration_details')

    has_logo = answers["hasLogo"]
    if has_logo not in LOGO_OPTIONS:
        raise ValueError(f"hasLogo: unknown option {has_logo!r}")
    logo = next((asset_url(a) for a in attachments if a.get("category") == "logo"), None) if has_logo == LOGO_UPLOAD else None
    brand_assets = [asset_url(a) for a in attachments if a.get("category") == "content"]

    exclusions = answers["contentRestrictions"].strip()

    intake = DesignIntake.model_validate(
        {
            "organization_name": answers["organizationName"],
            "organization_type": _lookup("organizationType", answers["organizationType"], ORGANIZATION_TYPES),
            "primary_goal": _lookup("primaryGoal", answers["primaryGoal"], PRIMARY_GOALS),
            "organization_description": answers["organizationDescription"],
            "target_audience": answers["targetAudience"],
            "pages": pages,
            "features": features,
            "tone": _lookup_many("toneAndVoice", answers["toneAndVoice"], TONES),
            "visual_style": answers["visualStyle"],
            "brand_colors": _hex_colors(answers["brandColors"]),
            "brand_fonts": _font_names(answers["brandFonts"]),
            "logo": logo,
            "brand_assets": brand_assets,
            "reference_sites": [u for u in answers["referenceWebsites"] if u.strip()],
            "integrations": integrations,
            "content_exclusions": exclusions or None,
        }
    )
    notes = IntakeNotes(
        brand_colors_text=answers["brandColors"].strip(),
        feature_details=answers["featureDetails"].strip(),
        integration_details=answers["integrationDetails"].strip(),
        additional_info=answers["additionalInfo"].strip(),
        dropped=dropped,
    )
    return intake, notes
