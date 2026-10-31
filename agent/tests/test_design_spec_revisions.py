"""§3 rule: stable IDs across revisions (DESIGN reruns)."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple

from pipeline.design_spec import DesignSpec, Invalid, Valid, ValidateResult, validate_design_spec

MakeSpec = Callable[[], Dict[str, Any]]


def revision_pair(make_spec: MakeSpec) -> Tuple[DesignSpec, Dict[str, Any]]:
    return DesignSpec.model_validate(make_spec()), make_spec()


def issue_codes(result: ValidateResult) -> List[str]:
    return [i.code for i in result.issues] if isinstance(result, Invalid) else []


def test_unchanged_rerun_passes(make_spec: MakeSpec) -> None:
    prev, nxt = revision_pair(make_spec)
    assert isinstance(validate_design_spec(nxt, previous=prev), Valid)


def test_adding_a_section_is_allowed_and_reported(make_spec: MakeSpec) -> None:
    prev, nxt = revision_pair(make_spec)
    nxt["pages"][0]["sections"].append(
        {
            "id": "stats-bar-1",
            "type": "stats-bar",
            "components": [],
            "content_blocks": [
                {"id": "home.stats.stat-1", "kind": "list_item", "max_chars": 60},
                {"id": "home.stats.stat-2", "kind": "list_item", "max_chars": 60},
                {"id": "home.stats.stat-3", "kind": "list_item", "max_chars": 60},
            ],
        }
    )
    nxt["decisions"].append(
        {
            "id": "dec-16",
            "kind": "section",
            "targets": ["section:stats-bar-1"],
            "sources": [{"type": "reviewer_note", "ref": "rej-1"}],
            "method": "llm",
            "revision": 2,
        }
    )
    result = validate_design_spec(nxt, previous=prev)
    assert isinstance(result, Valid)
    assert result.diff is not None
    assert result.diff.sections_added == ("stats-bar-1",)
    assert result.diff.content_blocks_added == (
        "home.stats.stat-1",
        "home.stats.stat-2",
        "home.stats.stat-3",
    )


def test_removing_a_section_is_allowed_and_reported(make_spec: MakeSpec) -> None:
    prev, nxt = revision_pair(make_spec)
    del nxt["pages"][0]["sections"][1]
    result = validate_design_spec(nxt, previous=prev)
    assert isinstance(result, Valid)
    assert result.diff is not None and result.diff.sections_removed == ("programs-grid-1",)


def test_rejects_changed_job_id(make_spec: MakeSpec) -> None:
    prev, nxt = revision_pair(make_spec)
    nxt["job_id"] = "00000000-0000-4000-8000-000000000000"
    assert "job_id_changed" in issue_codes(validate_design_spec(nxt, previous=prev))


def test_rejects_regenerated_section_id(make_spec: MakeSpec) -> None:
    prev, nxt = revision_pair(make_spec)
    nxt["pages"][0]["sections"][0]["id"] = "hero-2"
    nxt["flags"][0] = {"code": "hero_image_fallback", "section_id": "hero-2"}
    result = validate_design_spec(nxt, previous=prev)
    assert isinstance(result, Invalid)
    regen = [i for i in result.issues if i.code == "section_id_regenerated"]
    assert regen and 'keep the id "hero-1"' in regen[0].message


def test_rejects_reusing_an_id_for_a_different_section_type(make_spec: MakeSpec) -> None:
    prev, nxt = revision_pair(make_spec)
    nxt["pages"][0]["sections"][1]["type"] = "team-grid"
    assert "section_identity_changed" in issue_codes(validate_design_spec(nxt, previous=prev))


def test_rejects_regenerated_content_block_id(make_spec: MakeSpec) -> None:
    prev, nxt = revision_pair(make_spec)
    nxt["pages"][0]["sections"][0]["content_blocks"][0]["id"] = "home.hero.title"
    assert "content_block_id_regenerated" in issue_codes(validate_design_spec(nxt, previous=prev))


def test_rejects_moving_a_content_block_to_another_section(make_spec: MakeSpec) -> None:
    prev, nxt = revision_pair(make_spec)
    block = nxt["pages"][0]["sections"][1]["content_blocks"].pop()
    nxt["pages"][0]["sections"][1]["content_blocks"].append({"id": "home.programs.intro", "kind": "body", "max_chars": 200})
    nxt["pages"][1]["sections"][0]["content_blocks"].append(block)
    assert "content_block_identity_changed" in issue_codes(validate_design_spec(nxt, previous=prev))
