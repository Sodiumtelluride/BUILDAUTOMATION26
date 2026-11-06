"""Intake form answers (PR #8 stored blob) -> structured DesignIntake + notes."""

from __future__ import annotations

import copy
import json
import pathlib
from typing import Any, Dict

import pytest

from pipeline.template_spec.intake_mapping import map_intake_answers

FIX = pathlib.Path(__file__).parent / "fixtures"
RAW: Dict[str, Any] = json.loads((FIX / "intake_answers_complete.json").read_text())

LOGO_URL = "supabase://intake-uploads/intake/a1b2c3d4-e5f6-7890-abcd-ef1234567890/logo/0f1e2d3c.svg"
PDF_URL = "supabase://intake-uploads/intake/a1b2c3d4-e5f6-7890-abcd-ef1234567890/content/9a8b7c6d.pdf"


def _raw() -> Dict[str, Any]:
    return copy.deepcopy(RAW)


def test_complete_answers_map_to_the_structured_intake() -> None:
    intake, notes = map_intake_answers(RAW["answers"], RAW["attachments"])
    assert intake.model_dump() == {
        "organization_name": "Pioneer Valley Food Bank",
        "organization_type": "nonprofit",
        "primary_goal": "accept_donations",
        "organization_description": RAW["answers"]["organizationDescription"],
        "target_audience": RAW["answers"]["targetAudience"],
        "pages": ["home", "about", "team", "donate", "contact", "faq"],
        "features": ["contact_form", "donation_button", "newsletter_signup"],
        "tone": ["friendly", "inspiring", "professional"],
        "visual_style": RAW["answers"]["visualStyle"],
        "brand_colors": ["#2E7D32", "#FFA000"],
        "brand_fonts": ["Source Serif 4", "Inter"],
        "logo": LOGO_URL,
        "brand_assets": [PDF_URL],
        "reference_sites": ["https://feedingamerica.org", "https://foodbankwma.org"],
        "integrations": ["stripe", "google_analytics", "mailchimp"],
        "content_exclusions": "Never mention political parties or make promises of guaranteed aid.",
    }
    assert notes.brand_colors_text == "#2E7D32 and #FFA000 (forest green and warm amber)"
    assert notes.dropped == []


def test_join_apply_and_other_page() -> None:
    raw = _raw()
    raw["answers"]["pages"] = ["Home", "Join/Apply", "Other"]
    intake, notes = map_intake_answers(raw["answers"], raw["attachments"])
    assert intake.pages == ["home", "join_apply"]
    assert notes.dropped == ['pages: "Other" was requested but has no route']


def test_other_feature_and_integration_go_to_notes() -> None:
    raw = _raw()
    raw["answers"].update(
        features=["Other"], featureDetails="A volunteer sign-up sheet", integrations=["Other"], integrationDetails="Givebutter"
    )
    intake, notes = map_intake_answers(raw["answers"], raw["attachments"])
    assert intake.features == [] and intake.integrations == []
    assert notes.feature_details == "A volunteer sign-up sheet" and notes.integration_details == "Givebutter"
    assert notes.dropped == [
        'features: "Other" has no section; see feature_details',
        'integrations: "Other" is not supported; see integration_details',
    ]


def test_no_hex_in_brand_colors_keeps_text_only() -> None:
    raw = _raw()
    raw["answers"]["brandColors"] = "forest green and gold"
    intake, notes = map_intake_answers(raw["answers"], raw["attachments"])
    assert intake.brand_colors == [] and notes.brand_colors_text == "forest green and gold"


def test_hex_is_expanded_uppercased_and_deduplicated() -> None:
    raw = _raw()
    raw["answers"]["brandColors"] = "#2e7d32, #2E7D32, #fa0 and #ffa000"
    intake, _ = map_intake_answers(raw["answers"], raw["attachments"])
    assert intake.brand_colors == ["#2E7D32", "#FFAA00", "#FFA000"]


def test_no_logo_when_not_uploading() -> None:
    raw = _raw()
    raw["answers"]["hasLogo"] = "No — please create a simple text-based logo"
    intake, _ = map_intake_answers(raw["answers"], raw["attachments"])
    assert intake.logo is None


def test_unknown_label_raises_naming_the_field() -> None:
    raw = _raw()
    raw["answers"]["hasLogo"] = "Yes - I will upload it"
    with pytest.raises(ValueError, match="hasLogo"):
        map_intake_answers(raw["answers"], raw["attachments"])


def test_empty_restrictions_become_none() -> None:
    raw = _raw()
    raw["answers"]["contentRestrictions"] = ""
    intake, _ = map_intake_answers(raw["answers"], raw["attachments"])
    assert intake.content_exclusions is None
