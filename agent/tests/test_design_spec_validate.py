"""D20 / §3: output is validated against the design_spec schema."""

from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, List, Sequence

from pipeline.design_spec import DesignSpec, Invalid, Valid, ValidationIssue, validate_design_spec

MakeSpec = Callable[[], Dict[str, Any]]


def expect_issues(data: Dict[str, Any], *expected: str) -> Sequence[ValidationIssue]:
    result = validate_design_spec(data)
    assert isinstance(result, Invalid), "expected the spec to be rejected"
    found: List[str] = [i.code for i in result.issues]
    for code in expected:
        assert code in found, f"missing {code!r} in {found}"
    return result.issues


# --- A valid spec -----------------------------------------------------------


def test_valid_spec_passes_and_returns_typed_model(make_spec: MakeSpec) -> None:
    result = validate_design_spec(make_spec())
    assert isinstance(result, Valid)
    assert isinstance(result.spec, DesignSpec)
    assert result.spec.pages[0].sections[0].id == "hero-1"


def test_round_trips_through_json(make_spec: MakeSpec) -> None:
    result = validate_design_spec(make_spec())
    assert isinstance(result, Valid)
    dumped = result.spec.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert isinstance(validate_design_spec(dumped), Valid)


def test_accepts_a_contrast_adjustment_as_sent_in_json(make_spec: MakeSpec) -> None:
    s = make_spec()
    s["tokens"]["contrast_adjustments"] = [
        {
            "role": "muted_foreground",
            "pair": ["muted_foreground", "muted"],
            "from": "#94A3B8",
            "to": "#475569",
            "ratio_before": 2.6,
            "ratio_after": 7.2,
        }
    ]
    assert isinstance(validate_design_spec(s), Valid)


# --- Strict schema ----------------------------------------------------------


def test_rejects_unknown_keys(make_spec: MakeSpec) -> None:
    s = make_spec()
    s["notes"] = "use a warmer gold"
    assert expect_issues(s, "schema")[0].path == "notes"


def test_rejects_missing_required_fields(make_spec: MakeSpec) -> None:
    s = make_spec()
    del s["pages"]
    assert expect_issues(s, "schema")[0].path == "pages"


def test_reports_precise_paths_for_bad_ids_and_colors(make_spec: MakeSpec) -> None:
    s = make_spec()
    s["pages"][0]["sections"][0]["id"] = "Hero Section"
    s["tokens"]["colors"]["primary"] = "navy"
    paths = [i.path for i in expect_issues(s, "schema")]
    assert "pages[0].sections[0].id" in paths
    assert "tokens.colors.primary" in paths


def test_does_not_coerce_strings_to_numbers(make_spec: MakeSpec) -> None:
    s = make_spec()
    s["pages"][0]["sections"][0]["content_blocks"][0]["max_chars"] = "80"
    expect_issues(s, "schema")


def test_rejects_words_outside_the_fixed_vocabularies(make_spec: MakeSpec) -> None:
    s = make_spec()
    s["features"] = ["a really nice donate page"]
    s["pages"][0]["sections"][0]["source_fields"] = ["vibes"]
    expect_issues(s, "schema")


# --- Coded flags, no free text ----------------------------------------------


def test_rejects_prose_detail_on_a_flag(make_spec: MakeSpec) -> None:
    s = make_spec()
    s["flags"] = [{"code": "tone_style_conflict", "tones": ["playful"], "detail": "Playful vs corporate"}]
    expect_issues(s, "schema")


def test_rejects_flag_codes_outside_the_closed_set(make_spec: MakeSpec) -> None:
    s = make_spec()
    s["flags"].append({"code": "looks_off"})
    expect_issues(s, "schema")


def test_rejects_flags_pointing_at_missing_sections(make_spec: MakeSpec) -> None:
    s = make_spec()
    s["flags"][0] = {"code": "hero_image_fallback", "section_id": "hero-9"}
    expect_issues(s, "flag_reference_missing")


# --- IDs downstream stages address must be unique ---------------------------


def test_content_block_ids_unique_across_whole_spec(make_spec: MakeSpec) -> None:
    s = make_spec()
    s["pages"][1]["sections"][0]["content_blocks"][0]["id"] = "home.hero.headline"
    expect_issues(s, "duplicate_content_block_id")


def test_section_ids_and_slugs_unique(make_spec: MakeSpec) -> None:
    s = make_spec()
    s["pages"][1]["sections"][0]["id"] = "hero-1"
    s["pages"][1]["slug"] = "/"
    expect_issues(s, "duplicate_section_id", "duplicate_slug")


# --- The spec belongs to the job being run ----------------------------------


def test_rejects_a_spec_for_a_different_job(make_spec: MakeSpec) -> None:
    s = make_spec()
    result = validate_design_spec(s, expected_job_id="00000000-0000-4000-8000-000000000000")
    assert isinstance(result, Invalid)
    assert [i.code for i in result.issues] == ["job_id_mismatch"]


def test_accepts_the_matching_job_id_as_string_or_uuid(make_spec: MakeSpec) -> None:
    s = make_spec()
    assert isinstance(validate_design_spec(s, expected_job_id=s["job_id"]), Valid)
    assert isinstance(validate_design_spec(s, expected_job_id=uuid.UUID(s["job_id"])), Valid)


# --- Fields downstream stages read are IDs, not prose -----------------------


def test_rejects_prose_in_section_type_and_components(make_spec: MakeSpec) -> None:
    s = make_spec()
    s["pages"][0]["sections"][0]["type"] = "make it pop somehow"
    s["pages"][0]["sections"][0]["components"] = ["a nice button please"]
    paths = [i.path for i in expect_issues(s, "schema")]
    assert "pages[0].sections[0].type" in paths
    assert any(p.startswith("pages[0].sections[0].components") for p in paths)


def test_figma_url_must_be_a_figma_link(make_spec: MakeSpec) -> None:
    s = make_spec()
    s["flags"] = [f for f in s["flags"] if f["code"] != "no_figma"]
    s["figma_url"] = "see figma lol"
    assert expect_issues(s, "schema")[0].path == "figma_url"
    s["figma_url"] = "https://www.figma.com/design/AbC123/job-6f1c"
    assert isinstance(validate_design_spec(s), Valid)


# --- figma_url and the no_figma flag agree (D16) ----------------------------


def test_figma_url_and_no_figma_flag_cannot_both_be_set(make_spec: MakeSpec) -> None:
    s = make_spec()  # fixture already has a no_figma flag
    s["figma_url"] = "https://www.figma.com/design/AbC123/job-6f1c"
    expect_issues(s, "figma_state_conflict")


def test_spec_needs_a_figma_url_or_a_no_figma_flag(make_spec: MakeSpec) -> None:
    s = make_spec()
    s["flags"] = [f for f in s["flags"] if f["code"] != "no_figma"]
    expect_issues(s, "figma_state_conflict")
