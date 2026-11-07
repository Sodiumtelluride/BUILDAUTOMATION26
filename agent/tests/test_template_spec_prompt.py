"""The system prompt and user message the design-spec generator sends."""

from __future__ import annotations

import json
import pathlib
import uuid
from typing import Any, Dict

from pipeline.template_spec.catalog import load_catalog
from pipeline.template_spec.intake import PAGE_SLUGS
from pipeline.template_spec.intake_mapping import map_intake_answers
from pipeline.template_spec.prompt import EXAMPLE_SPEC, render_system_prompt, render_user_message

FIX = pathlib.Path(__file__).parent / "fixtures"
RAW: Dict[str, Any] = json.loads((FIX / "intake_answers_complete.json").read_text())


def test_system_prompt_lists_every_type_block_and_theme() -> None:
    cat = load_catalog()
    text = render_system_prompt(cat)
    for type_id, blocks in cat.types.items():
        assert type_id in text
        for block_id in blocks:
            assert block_id in text
    for theme in cat.themes:
        assert theme in text


def test_system_prompt_states_the_hard_rules() -> None:
    text = render_system_prompt(load_catalog())
    for needle in [
        "Inter",
        "Instrument Serif",
        "font_substituted",
        "unsupported_feature",
        "form_submissions",
        "primary-foreground",
        "assumptions",
        "source_fields",
        "JSON only",
        "/join",
    ]:
        assert needle in text


def test_system_prompt_worked_example_is_valid_json() -> None:
    text = render_system_prompt(load_catalog())
    example = text[text.index("{", text.index("Example")) :]
    assert json.loads(example[: example.rindex("}") + 1])["pages"]


def test_user_message_carries_intake_notes_job_id_and_repair() -> None:
    intake, notes = map_intake_answers(RAW["answers"], RAW["attachments"])
    job = uuid.uuid4()
    text = render_user_message(intake, notes, job, previous_issues=["tokens.fonts.body: must be Inter"])
    assert str(job) in text
    assert '"organization_name": "Pioneer Valley Food Bank"' in text
    assert "forest green and warm amber" in text
    assert "tokens.fonts.body: must be Inter" in text and "previous" in text.lower()
    for name in intake.pages:
        assert PAGE_SLUGS[name] in text


def test_system_prompt_defaults_to_the_bold_family() -> None:
    cat = load_catalog()
    text = render_system_prompt(cat)
    assert "Default to bold" in text
    example_types = {s["type"] for p in json.loads(EXAMPLE_SPEC)["pages"] for s in p["sections"]}
    assert example_types and example_types <= set(cat.themes["bold"].values())
