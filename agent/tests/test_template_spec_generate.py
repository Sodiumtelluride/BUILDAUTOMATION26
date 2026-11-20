"""Provider + the generate / validate / repair loop."""

from __future__ import annotations

import json
import pathlib
import uuid
from typing import Any, Dict, List, Tuple

import pytest

from pipeline.template_spec.generate import generate_design_spec, parse_spec_text
from pipeline.template_spec.intake import DesignIntake
from pipeline.template_spec.intake_mapping import IntakeNotes, map_intake_answers
from pipeline.template_spec.provider import DEFAULT_MOCK_SPEC, mock_provider

FIX = pathlib.Path(__file__).parent / "fixtures"
RAW: Dict[str, Any] = json.loads((FIX / "intake_answers_complete.json").read_text())
VALID = DEFAULT_MOCK_SPEC.read_text()
JOB = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def _intake() -> Tuple[DesignIntake, IntakeNotes]:
    return map_intake_answers(RAW["answers"], RAW["attachments"])


def test_parse_strips_fence_and_prose() -> None:
    assert parse_spec_text('Here it is:\n```json\n{"a": 1}\n```\n')["a"] == 1


def test_parse_rejects_non_json() -> None:
    with pytest.raises(ValueError, match="not a JSON object"):
        parse_spec_text("no braces here")


async def test_mock_provider_yields_valid_spec_first_try() -> None:
    intake, notes = _intake()
    result = await generate_design_spec(intake, notes, JOB, mock_provider())
    assert result.spec is not None and result.issues == [] and result.attempts == 1
    assert result.spec["job_id"] == str(JOB)


async def test_repair_round_includes_previous_issues() -> None:
    intake, notes = _intake()
    bad = json.loads(VALID)
    bad["tokens"]["fonts"]["body"] = "Instrument Serif"
    seen: List[str] = []

    async def provider(system: str, user: str) -> str:
        seen.append(user)
        return json.dumps(bad) if len(seen) == 1 else VALID

    result = await generate_design_spec(intake, notes, JOB, provider)
    assert result.spec is not None and result.attempts == 2
    assert "tokens.fonts.body: must be Inter" in seen[1] and "must be Inter" not in seen[0]
    assert json.dumps(bad) in seen[1], "the repair message must carry the previous reply"


async def test_gives_up_after_max_attempts() -> None:
    intake, notes = _intake()

    async def provider(system: str, user: str) -> str:
        return "not json"

    result = await generate_design_spec(intake, notes, JOB, provider, max_attempts=2)
    assert result.spec is None and result.attempts == 2
    assert result.issues == ["model reply is not a JSON object"]


async def test_job_id_is_overwritten_from_the_job() -> None:
    intake, notes = _intake()
    other = uuid.uuid4()
    result = await generate_design_spec(intake, notes, other, mock_provider(), max_attempts=1)
    assert result.spec is not None and result.attempts == 1
    assert result.spec["job_id"] == str(other)


async def test_missing_flags_are_added_from_the_intake() -> None:
    raw = json.loads(json.dumps(RAW))
    raw["answers"]["features"].append("Social media feed")
    intake, notes = map_intake_answers(raw["answers"], raw["attachments"])
    unflagged = json.loads(VALID)
    unflagged["flags"] = []
    unflagged["features"].append("social_media_feed")

    async def provider(system: str, user: str) -> str:
        return json.dumps(unflagged)

    result = await generate_design_spec(intake, notes, JOB, provider)
    assert result.spec is not None
    flags = {(f["code"], f["detail"]) for f in result.spec["flags"]}
    assert any(code == "unsupported_feature" and "social_media_feed" in detail for code, detail in flags)
    assert not any("contact_form" in detail for _, detail in flags), "contact_form has a section now"
    assert any(code == "font_substituted" and "Source Serif 4" in detail for code, detail in flags)


async def test_every_mapped_feature_requires_its_section() -> None:
    raw = json.loads(json.dumps(RAW))
    raw["answers"]["features"] = ["Event calendar"]
    intake, notes = map_intake_answers(raw["answers"], raw["attachments"])
    result = await generate_design_spec(intake, notes, JOB, mock_provider(), max_attempts=1)
    assert result.spec is None
    assert "features: event_calendar requires a event-list section" in result.issues
    assert "pages: a contact-block section was added but contact_form was not requested" in result.issues


async def test_existing_flags_are_not_duplicated() -> None:
    intake, notes = _intake()
    result = await generate_design_spec(intake, notes, JOB, mock_provider())
    assert result.spec is not None
    assert len(result.spec["flags"]) == len(json.loads(VALID)["flags"])


async def test_member_form_feature_requires_the_form_section() -> None:
    raw = json.loads(json.dumps(RAW))
    raw["answers"]["features"] = ["Member application form"]
    intake, notes = map_intake_answers(raw["answers"], raw["attachments"])
    result = await generate_design_spec(intake, notes, JOB, mock_provider(), max_attempts=1)
    assert result.spec is None
    assert "features: member_application_form requires a member-application-form section" in result.issues


async def test_plain_string_assumptions_are_sent_back_for_repair() -> None:
    intake, notes = _intake()
    unlinked = json.loads(VALID)
    unlinked["assumptions"] = [a["text"] for a in unlinked["assumptions"]]
    seen: List[str] = []

    async def provider(system: str, user: str) -> str:
        seen.append(user)
        return json.dumps(unlinked) if len(seen) == 1 else VALID

    result = await generate_design_spec(intake, notes, JOB, provider)
    assert result.spec is not None and result.attempts == 2
    assert "assumptions[0]: must be" in seen[1]
    assert all(isinstance(a, str) for a in result.spec["assumptions"]), "the saved spec keeps the template's plain strings"
    assert [link.field for link in result.assumptions] == ["tone", "brand_colors", "pages", "features"]
