"""BUI-66: every section gets catalog-defined content blocks with stable IDs."""

from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, List

from pipeline.design_spec import (
    DesignSpec,
    LayoutPlan,
    assemble_design_spec,
    content_block_index,
    get_section_def,
    parse_design_intake,
    requested_slugs,
    validate_design_spec,
)
from pipeline.design_spec.validate import Invalid, Valid

MakeIntake = Callable[[], Dict[str, Any]]
MakePlan = Callable[[], Dict[str, Any]]
MakeSpec = Callable[[], Dict[str, Any]]

JOB_ID = uuid.uuid4()


def _valid_spec(make_intake: MakeIntake, make_plan: MakePlan, **kwargs: Any) -> DesignSpec:
    intake = parse_design_intake(make_intake())
    spec_dict = assemble_design_spec(JOB_ID, intake, LayoutPlan.model_validate(make_plan()), **kwargs)
    result = validate_design_spec(
        spec_dict,
        kwargs.get("previous"),
        expected_job_id=JOB_ID,
        required_slugs=requested_slugs(intake),
    )
    assert isinstance(result, Valid), getattr(result, "issues", None)
    return result.spec


def _codes(result: object) -> List[str]:
    assert isinstance(result, Invalid)
    return [issue.code for issue in result.issues]


# -- Blocks are defined by the catalog ----------------------------------------


def test_every_section_has_every_catalog_slot_as_a_block(
    make_intake: MakeIntake, make_plan: MakePlan
) -> None:
    spec = _valid_spec(make_intake, make_plan)
    for page in spec.pages:
        for section in page.sections:
            sdef = get_section_def(section.type)
            assert sdef is not None
            by_slot = {block.id.rsplit(".", 1)[-1]: block for block in section.content_blocks}
            assert set(by_slot) == {slot.name for slot in sdef.slots}
            for slot in sdef.slots:
                block = by_slot[slot.name]
                assert block.kind == slot.kind
                assert block.max_chars == slot.max_chars
                assert block.id.startswith(f"{'home' if page.slug == '/' else page.slug.strip('/')}.")


def test_repeated_section_types_get_unique_ids_and_block_ids(
    make_intake: MakeIntake, make_plan: MakePlan
) -> None:
    # The plan uses cta-band on both the home and donate pages.
    spec = _valid_spec(make_intake, make_plan)
    cta_sections = [s for page in spec.pages for s in page.sections if s.type == "cta-band"]
    assert [s.id for s in cta_sections] == ["cta-band-1", "cta-band-2"]

    all_block_ids = [b.id for page in spec.pages for s in page.sections for b in s.content_blocks]
    assert len(all_block_ids) == len(set(all_block_ids))  # globally unique


def test_stage_4_can_address_every_block_by_id(make_intake: MakeIntake, make_plan: MakePlan) -> None:
    spec = _valid_spec(make_intake, make_plan)
    index = content_block_index(spec)
    assert len(index) == sum(len(s.content_blocks) for p in spec.pages for s in p.sections)
    headline = index["home.hero-centered-1.headline"]
    assert headline.kind == "headline"
    assert headline.max_chars == 80


# -- IDs are stable across revisions ------------------------------------------


def test_block_ids_survive_a_revision(make_intake: MakeIntake, make_plan: MakePlan) -> None:
    previous = _valid_spec(make_intake, make_plan)

    def plan_with_extra_section() -> Dict[str, Any]:
        plan = make_plan()
        for page in plan["pages"]:
            if page["page"] == "about":
                page["sections"].append({"type": "mission-statement", "sources": ["primary_goal"]})
        return plan

    spec = _valid_spec(make_intake, plan_with_extra_section, previous=previous, revision=2)

    old_ids = set(content_block_index(previous))
    new_ids = set(content_block_index(spec))
    assert old_ids <= new_ids  # every previous block is still addressable by the same ID
    added = new_ids - old_ids
    assert added == {"about.mission-statement-1.heading", "about.mission-statement-1.body"}

    old_sections = {s.id for p in previous.pages for s in p.sections}
    new_sections = {s.id for p in spec.pages for s in p.sections}
    assert old_sections <= new_sections


# -- Catalog mismatches are rejected ------------------------------------------


def test_max_chars_above_the_slot_limit_is_rejected(make_spec: MakeSpec) -> None:
    spec = make_spec()
    hero = spec["pages"][0]["sections"][0]
    hero["content_blocks"][0]["max_chars"] = 10_000
    assert "content_block_catalog_mismatch" in _codes(validate_design_spec(spec))


def test_wrong_kind_for_a_slot_is_rejected(make_spec: MakeSpec) -> None:
    spec = make_spec()
    hero = spec["pages"][0]["sections"][0]
    hero["content_blocks"][0]["kind"] = "body"
    assert "content_block_catalog_mismatch" in _codes(validate_design_spec(spec))


def test_block_for_a_nonexistent_slot_is_rejected(make_spec: MakeSpec) -> None:
    spec = make_spec()
    hero = spec["pages"][0]["sections"][0]
    hero["content_blocks"][0]["id"] = hero["content_blocks"][0]["id"].rsplit(".", 1)[0] + ".sidebar"
    codes = _codes(validate_design_spec(spec))
    assert "content_block_catalog_mismatch" in codes


def test_missing_required_block_is_rejected(make_spec: MakeSpec) -> None:
    spec = make_spec()
    hero = spec["pages"][0]["sections"][0]
    hero["content_blocks"] = [b for b in hero["content_blocks"] if not b["id"].endswith(".headline")]
    assert "missing_required_content_block" in _codes(validate_design_spec(spec))
