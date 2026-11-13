"""The source log: every value in the spec has a row saying where it came from."""

from __future__ import annotations

import copy
import json
import pathlib
from typing import Any, Dict, List, Tuple

from pipeline.template_spec.intake import DesignIntake
from pipeline.template_spec.intake_mapping import map_intake_answers
from pipeline.template_spec.sources import AssumptionLink, build_source_log, source_issues, split_assumptions, to_reply_shape

FIX = pathlib.Path(__file__).parent / "fixtures"
RAW: Dict[str, Any] = json.loads((FIX / "intake_answers_complete.json").read_text())
REPLY: Dict[str, Any] = json.loads((FIX / "template_design_reply_valid.json").read_text())
SPEC: Dict[str, Any] = json.loads((FIX / "template_design_spec_valid.json").read_text())


def _intake(**update: Any) -> DesignIntake:
    intake, _ = map_intake_answers(RAW["answers"], RAW["attachments"])
    return intake.model_copy(update=update)


def _final() -> Tuple[Dict[str, Any], List[AssumptionLink]]:
    spec = copy.deepcopy(REPLY)
    links, issues = split_assumptions(spec)
    assert issues == []
    return spec, links


def _row(log: List[Dict[str, Any]], target: str) -> Dict[str, Any]:
    return [row for row in log if row["target"] == target][-1]


def test_reply_fixture_flattens_to_the_spec_fixture() -> None:
    spec, links = _final()
    assert spec == SPEC, "the two fixtures must differ only in the shape of assumptions"
    assert [link.field for link in links] == ["tone", "brand_colors", "pages", "features"]


def test_assumptions_must_link_to_a_real_intake_field() -> None:
    spec = copy.deepcopy(REPLY)
    spec["assumptions"] = ["a plain sentence", {"text": "a guess", "field": "favourite_animal"}]
    _, issues = split_assumptions(spec)
    assert len(issues) == 2 and "assumptions[0]" in issues[0] and "'favourite_animal' is not an intake field" in issues[1]
    assert isinstance(spec["assumptions"][1], dict), "nothing is flattened when there are issues"


def test_plain_string_assumptions_are_accepted_only_when_links_are_not_required() -> None:
    spec = copy.deepcopy(SPEC)
    links, issues = split_assumptions(spec, require_links=False)
    assert issues == [] and all(link.field is None for link in links) and spec == SPEC


def test_section_source_fields_must_be_intake_fields() -> None:
    spec, _ = _final()
    spec["pages"][0]["sections"][0]["source_fields"] = []
    spec["pages"][0]["sections"][1]["source_fields"] = ["vibes"]
    issues = source_issues(spec)
    assert issues == [
        "pages[0].sections[0].source_fields: name at least one intake field",
        "pages[0].sections[1].source_fields: 'vibes' is not an intake field",
    ]


def test_contrast_adjustments_must_match_the_tokens() -> None:
    spec, _ = _final()
    spec["tokens"]["contrast_adjustments"] = [
        "darkened it",
        {"role": "brand", "from": "#FFA000", "to": "#B36B00"},
        {"role": "secondary", "from": "#FFA000", "to": "#000000"},
    ]
    issues = source_issues(spec)
    assert len(issues) == 3
    assert "tokens.contrast_adjustments[0]: must be" in issues[0]
    assert "'brand' is not a color role" in issues[1]
    assert "must equal tokens.colors.secondary (#FFA000)" in issues[2]


def test_every_value_has_exactly_one_row_on_the_first_revision() -> None:
    spec, links = _final()
    log = build_source_log(spec, _intake(), links, brand_colors_source="intake", revision=1)
    targets = [row["target"] for row in log]
    assert len(targets) == len(set(targets)) and all(row["revision"] == 1 for row in log)
    expected = (
        {f"tokens.colors.{role}" for role in spec["tokens"]["colors"]}
        | {"tokens.fonts.heading", "tokens.fonts.body", "tokens.radius", "features", "integrations", "data_requirements"}
        | {f"pages.{p['slug']}" for p in spec["pages"]}
        | {f"sections.{s['id']}" for p in spec["pages"] for s in p["sections"]}
        | {f"assumptions.{link.field}: {link.text}" for link in links}
        | {"flags.font_substituted[0]"}
    )
    assert set(targets) == expected


def test_brand_colors_are_sourced_to_the_intake_and_the_rest_to_claude() -> None:
    spec, links = _final()
    log = build_source_log(spec, _intake(), links, brand_colors_source="intake", revision=1)
    primary = _row(log, "tokens.colors.primary")
    assert (primary["source"], primary["fields"], primary["note"]) == ("intake", ["brand_colors"], "")
    muted = _row(log, "tokens.colors.muted")
    assert muted["source"] == "claude" and muted["fields"] == []
    assert muted["assumptions"] == [links[1].text], "the guess that cites brand_colors is shown beside it"


def test_brand_color_match_ignores_hex_case() -> None:
    spec, links = _final()
    spec["tokens"]["colors"]["primary"] = spec["tokens"]["colors"]["primary"].lower()
    log = build_source_log(spec, _intake(), links, brand_colors_source="intake", revision=1)
    assert _row(log, "tokens.colors.primary")["source"] == "intake"


def test_a_contrast_adjusted_brand_color_keeps_its_source() -> None:
    spec, links = _final()
    spec["tokens"]["colors"]["secondary"] = "#B36B00"
    spec["tokens"]["contrast_adjustments"] = [{"role": "secondary", "from": "#ffa000", "to": "#B36B00"}]
    assert source_issues(spec) == []
    row = _row(build_source_log(spec, _intake(), links, brand_colors_source="intake", revision=1), "tokens.colors.secondary")
    assert (row["source"], row["fields"], row["note"]) == ("intake", ["brand_colors"], "adjusted for contrast from #FFA000")


def test_logo_derived_colors_are_sourced_to_the_logo() -> None:
    spec, links = _final()
    row = _row(build_source_log(spec, _intake(), links, brand_colors_source="logo", revision=1), "tokens.colors.primary")
    assert (row["source"], row["fields"]) == ("logo", ["logo"])


def test_fonts_sections_and_flags_have_sources() -> None:
    spec, links = _final()
    log = build_source_log(spec, _intake(), links, brand_colors_source="intake", revision=1)
    heading = _row(log, "tokens.fonts.heading")
    assert heading["source"] == "rule" and heading["fields"] == ["brand_fonts"] and "Source Serif 4" in heading["note"]
    assert _row(log, "tokens.fonts.body")["source"] == "rule"
    hero = _row(log, "sections.hero-1")
    assert hero["source"] == "claude" and hero["fields"] == spec["pages"][0]["sections"][0]["source_fields"]
    donate = _row(log, "sections.donate-1")
    assert donate["source"] == "rule" and "donation_button" in donate["note"]
    assert _row(log, "flags.font_substituted[0]")["fields"] == ["brand_fonts"]


def test_a_rerun_appends_only_what_changed_and_marks_removals() -> None:
    spec, links = _final()
    first = build_source_log(spec, _intake(), links, brand_colors_source="intake", revision=1)
    second_spec = copy.deepcopy(spec)
    second_spec["tokens"]["radius"] = "0.5rem"
    second_spec["pages"][0]["sections"] = [s for s in second_spec["pages"][0]["sections"] if s["id"] != "stats-1"]
    second = build_source_log(second_spec, _intake(), links, brand_colors_source="intake", revision=2, previous_log=first)
    assert second[: len(first)] == first, "earlier rows are never rewritten"
    added = second[len(first) :]
    assert {row["target"] for row in added} == {"tokens.radius", "sections.stats-1"} and all(row["revision"] == 2 for row in added)
    assert _row(second, "tokens.radius")["value"] == "0.5rem"
    removed = _row(second, "sections.stats-1")
    assert removed["source"] == "removed" and removed["value"] is None

    third = build_source_log(second_spec, _intake(), links, brand_colors_source="intake", revision=3, previous_log=second)
    assert third == second, "an unchanged rerun adds nothing"


def test_to_reply_shape_is_the_inverse_of_split_assumptions() -> None:
    spec, links = _final()
    assert to_reply_shape(spec, links) == REPLY


def test_dropping_one_assumption_touches_only_its_own_row() -> None:
    spec, links = _final()
    first = build_source_log(spec, _intake(), links, brand_colors_source="intake", revision=1)
    second_spec = copy.deepcopy(spec)
    dropped, kept = links[2], [link for i, link in enumerate(links) if i != 2]  # the guess about pages, shown beside no token
    second_spec["assumptions"] = [link.text for link in kept]
    second = build_source_log(second_spec, _intake(), kept, brand_colors_source="intake", revision=2, previous_log=first)
    added = second[len(first) :]
    assert [(row["target"], row["source"]) for row in added] == [(f"assumptions.{dropped.field}: {dropped.text}", "removed")]

    reordered = build_source_log(second_spec, _intake(), kept[::-1], brand_colors_source="intake", revision=3, previous_log=second)
    assert reordered == second, "order alone changes nothing"


def test_identical_assumptions_share_one_row() -> None:
    spec, links = _final()
    log = build_source_log(spec, _intake(), [*links, links[0]], brand_colors_source="intake", revision=1)
    assert len([row for row in log if row["target"].startswith("assumptions.")]) == len(links)
