"""BUI-64: Stage 2 generation uses every Stage 1 intake field."""

from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, Mapping, get_args

import pytest

from pipeline.design_spec import (
    DesignSpec,
    LayoutPlan,
    assemble_design_spec,
    build_generation_input,
    missing_branding,
    parse_design_intake,
    render_plan_prompt,
    requested_slugs,
    validate_design_spec,
)
from pipeline.design_spec.generation import DEFAULT_COLORS, DEFAULT_FONTS
from pipeline.design_spec.schema import IntakeField, IntakeSource
from pipeline.design_spec.validate import Valid
from pipeline.nodes.design import run_design
from pipeline.state import IntakeOutput, PipelineState

MakeIntake = Callable[[], Dict[str, Any]]
MakePlan = Callable[[], Dict[str, Any]]

JOB_ID = uuid.uuid4()


def _assemble(intake_dict: Dict[str, Any], plan_dict: Dict[str, Any]) -> DesignSpec:
    intake = parse_design_intake(intake_dict)
    spec_dict = assemble_design_spec(JOB_ID, intake, LayoutPlan.model_validate(plan_dict))
    result = validate_design_spec(spec_dict, expected_job_id=JOB_ID, required_slugs=requested_slugs(intake))
    assert isinstance(result, Valid), getattr(result, "issues", None)
    return result.spec


# -- Every intake field reaches generation -----------------------------------


def test_generation_input_covers_every_frozen_intake_field(make_intake: MakeIntake) -> None:
    gen_input = build_generation_input(parse_design_intake(make_intake()))
    assert set(gen_input) == set(get_args(IntakeField))


def test_prompt_mentions_every_scalar_intake_answer(make_intake: MakeIntake) -> None:
    intake_dict = make_intake()
    prompt = render_plan_prompt(build_generation_input(parse_design_intake(intake_dict)))
    for value in (
        intake_dict["organization_name"],
        intake_dict["organization_type"],
        intake_dict["primary_goal"],
        intake_dict["organization_description"],
        intake_dict["target_audience"],
        intake_dict["visual_style"],
        *intake_dict["tone"],
        *intake_dict["brand_colors"],
        *intake_dict["integrations"],
    ):
        assert value in prompt


# -- Frozen-schema strictness: no invented defaults ---------------------------


def test_missing_required_field_is_rejected(make_intake: MakeIntake) -> None:
    broken = make_intake()
    del broken["organization_description"]
    with pytest.raises(ValueError, match="organization_description"):
        parse_design_intake(broken)


def test_tone_is_capped_at_three(make_intake: MakeIntake) -> None:
    intake_dict = make_intake()
    assert parse_design_intake(intake_dict).tone == intake_dict["tone"]  # 3 tones OK
    intake_dict["tone"] = ["friendly", "inspiring", "professional", "playful"]
    with pytest.raises(ValueError, match="tone"):
        parse_design_intake(intake_dict)


def test_unknown_intake_key_is_rejected(make_intake: MakeIntake) -> None:
    broken = make_intake()
    broken["free_text_notes"] = "anything"
    with pytest.raises(ValueError, match="free_text_notes"):
        parse_design_intake(broken)


# -- Reference sites: inspiration only; exclusions: hard constraint ----------


def test_reference_sites_are_marked_inspiration_only(make_intake: MakeIntake) -> None:
    gen_input = build_generation_input(parse_design_intake(make_intake()))
    assert gen_input["reference_sites"]["role"] == "inspiration_only"
    prompt = render_plan_prompt(gen_input)
    assert "inspiration only" in prompt
    assert "do not copy" in prompt


def test_content_exclusions_are_a_hard_constraint(make_intake: MakeIntake) -> None:
    intake_dict = make_intake()
    gen_input = build_generation_input(parse_design_intake(intake_dict))
    assert gen_input["content_exclusions"] == {
        "text": intake_dict["content_exclusions"],
        "role": "hard_constraint",
    }
    prompt = render_plan_prompt(gen_input)
    assert "Hard constraint" in prompt
    assert intake_dict["content_exclusions"] in prompt


def test_content_exclusions_recorded_as_decision(
    make_intake: MakeIntake, make_plan: MakePlan
) -> None:
    spec = _assemble(make_intake(), make_plan())
    cited = [
        d
        for d in spec.decisions
        if any(isinstance(s, IntakeSource) and s.ref == "content_exclusions" for s in d.sources)
    ]
    assert len(cited) == 1 and cited[0].kind == "assumption"


# -- Branding: brand inputs drive tokens, with cited sources (D5) ------------


def test_brand_colors_and_fonts_drive_tokens(make_intake: MakeIntake, make_plan: MakePlan) -> None:
    intake_dict = make_intake()
    spec = _assemble(intake_dict, make_plan())
    assert spec.tokens.colors["primary"] == intake_dict["brand_colors"][0]
    assert spec.tokens.colors["secondary"] == intake_dict["brand_colors"][1]
    assert spec.tokens.fonts.heading == intake_dict["brand_fonts"][0]
    assert spec.tokens.fonts.body == intake_dict["brand_fonts"][1]

    def cites(target: str, field: str) -> bool:
        return any(
            target in d.targets
            and any(isinstance(s, IntakeSource) and s.ref == field for s in d.sources)
            for d in spec.decisions
        )

    assert cites("tokens.colors.primary", "brand_colors")
    assert cites("tokens.fonts.heading", "brand_fonts")
    assert cites("tokens.radius", "visual_style")


def test_missing_branding_falls_back_to_default_track(
    make_intake: MakeIntake, make_plan: MakePlan
) -> None:
    intake_dict = make_intake()
    del intake_dict["logo"], intake_dict["brand_colors"], intake_dict["brand_fonts"]
    intake = parse_design_intake(intake_dict)
    assert missing_branding(intake) == ["logo", "brand_colors", "brand_fonts"]

    spec = _assemble(intake_dict, make_plan())
    assert spec.tokens.colors["primary"] == DEFAULT_COLORS["primary"]
    assert (spec.tokens.fonts.heading, spec.tokens.fonts.body) == DEFAULT_FONTS
    flags = [f for f in spec.flags if f.code == "default_design_track"]
    assert len(flags) == 1
    assert set(flags[0].missing) == {"logo", "brand_colors", "brand_fonts"}


# -- The DESIGN node end to end -----------------------------------------------


async def test_run_design_writes_validated_spec(make_intake: MakeIntake, make_plan: MakePlan) -> None:
    intake_dict = make_intake()
    state = PipelineState(org_id=uuid.uuid4(), intake_output=IntakeOutput(project_spec=intake_dict))

    async def plan_generator(attempt: object, gen_input: Mapping[str, Any]) -> object:
        assert set(gen_input) == set(get_args(IntakeField))
        return make_plan()

    result = await run_design(state, generate_plan=plan_generator)
    assert set(result) == {"design_output"}
    output = result["design_output"]
    assert set(output.page_map) == set(requested_slugs(parse_design_intake(intake_dict)))

    revalidated = validate_design_spec(output.design_spec, expected_job_id=state.job_id)
    assert isinstance(revalidated, Valid)
