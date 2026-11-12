"""BUI-65: page map covers every requested page; sections only from the catalog."""

from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, List, Sequence

from pipeline.design_spec import (
    SECTION_CATALOG,
    GenerateAttempt,
    LayoutPlan,
    NeedsHumanReview,
    ValidationIssue,
    assemble_design_spec,
    generate_validated_spec,
    parse_design_intake,
    requested_slugs,
    validate_design_spec,
)
from pipeline.design_spec.validate import Invalid, Valid

MakeIntake = Callable[[], Dict[str, Any]]
MakePlan = Callable[[], Dict[str, Any]]

JOB_ID = uuid.uuid4()


def _codes(result: object) -> List[str]:
    assert isinstance(result, Invalid)
    return [issue.code for issue in result.issues]


def test_page_map_covers_every_requested_page_in_order(
    make_intake: MakeIntake, make_plan: MakePlan
) -> None:
    intake = parse_design_intake(make_intake())
    plan = LayoutPlan.model_validate(make_plan())
    result = validate_design_spec(
        assemble_design_spec(JOB_ID, intake, plan),
        expected_job_id=JOB_ID,
        required_slugs=requested_slugs(intake),
    )
    assert isinstance(result, Valid), result
    spec = result.spec

    assert [p.slug for p in spec.pages] == requested_slugs(intake)

    planned = {p.page: [s.type for s in p.sections] for p in plan.pages}
    by_name = dict(zip(intake.pages, spec.pages))
    for name, page in by_name.items():
        assert [s.type for s in page.sections] == planned[name]  # plan order kept


def test_all_section_types_come_from_the_approved_catalog(
    make_intake: MakeIntake, make_plan: MakePlan
) -> None:
    intake = parse_design_intake(make_intake())
    result = validate_design_spec(
        assemble_design_spec(JOB_ID, intake, LayoutPlan.model_validate(make_plan())),
        expected_job_id=JOB_ID,
    )
    assert isinstance(result, Valid)
    for page in result.spec.pages:
        for section in page.sections:
            assert section.type in SECTION_CATALOG


def test_unknown_section_type_is_never_accepted(make_spec: Callable[[], Dict[str, Any]]) -> None:
    spec = make_spec()
    spec["pages"][0]["sections"][0]["type"] = "hero-rotating-carousel"
    assert "unknown_section_type" in _codes(validate_design_spec(spec))


def test_components_outside_the_catalog_entry_are_rejected(
    make_spec: Callable[[], Dict[str, Any]]
) -> None:
    spec = make_spec()
    spec["pages"][0]["sections"][0]["components"].append("Carousel")
    assert "section_components_not_in_catalog" in _codes(validate_design_spec(spec))


def test_dropping_a_requested_page_is_rejected(make_intake: MakeIntake, make_plan: MakePlan) -> None:
    intake = parse_design_intake(make_intake())
    plan_dict = make_plan()
    plan_dict["pages"] = [p for p in plan_dict["pages"] if p["page"] != "faq"]
    result = validate_design_spec(
        assemble_design_spec(JOB_ID, intake, LayoutPlan.model_validate(plan_dict)),
        expected_job_id=JOB_ID,
        required_slugs=requested_slugs(intake),
    )
    assert isinstance(result, Invalid)
    assert any(issue.code == "missing_requested_page" and "/faq" in issue.message for issue in result.issues)


async def test_persistently_unknown_type_exhausts_retries_with_feedback(
    make_intake: MakeIntake, make_plan: MakePlan
) -> None:
    """The retry loop feeds the catalog issue back; a plan that never fixes it
    ends in NeedsHumanReview, so an unknown type can never reach state."""
    intake = parse_design_intake(make_intake())
    seen_issues: List[Sequence[ValidationIssue]] = []

    async def generate(attempt: GenerateAttempt) -> object:
        seen_issues.append(attempt.previous_issues)
        plan_dict = make_plan()
        plan_dict["pages"][0]["sections"][0]["type"] = "hero-rotating-carousel"
        return assemble_design_spec(JOB_ID, intake, LayoutPlan.model_validate(plan_dict))

    result = await generate_validated_spec(
        generate, job_id=JOB_ID, max_retries=1, required_slugs=requested_slugs(intake)
    )
    assert isinstance(result, NeedsHumanReview)
    assert result.attempts == 2
    assert any(issue.code == "unknown_section_type" for issue in result.issues)
    # The second attempt received the first attempt's issues.
    assert seen_issues[0] == ()
    assert any(issue.code == "unknown_section_type" for issue in seen_issues[1])
