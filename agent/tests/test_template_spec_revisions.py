"""Stable section ids across DESIGN reruns (converted from the design_spec revision tests)."""

from __future__ import annotations

import copy
import json
import pathlib
from typing import Any, Dict

from pipeline.template_spec.revisions import stabilize_section_ids

FIX = pathlib.Path(__file__).parent / "fixtures"
PREVIOUS: Dict[str, Any] = json.loads((FIX / "template_design_spec_valid.json").read_text())


def _spec() -> Dict[str, Any]:
    return copy.deepcopy(PREVIOUS)


def _section(spec: Dict[str, Any], section_id: str) -> Dict[str, Any]:
    return next(s for p in spec["pages"] for s in p["sections"] if s["id"] == section_id)


def test_unchanged_rerun_keeps_every_id() -> None:
    spec = _spec()
    diff, issues = stabilize_section_ids(spec, PREVIOUS)
    assert issues == [] and spec == PREVIOUS
    assert diff.added == [] and diff.removed == [] and diff.remapped == {}
    assert "hero-1" in diff.kept


def test_adding_a_section_is_allowed_and_reported() -> None:
    spec = _spec()
    extra = copy.deepcopy(_section(spec, "cta-1"))
    extra["id"] = "cta-9"
    spec["pages"][1]["sections"].append(extra)  # /about had no cta-bold before
    diff, issues = stabilize_section_ids(spec, PREVIOUS)
    assert issues == [] and diff.added == ["cta-9"] and diff.removed == []


def test_removing_a_section_is_allowed_and_reported() -> None:
    spec = _spec()
    spec["pages"][0]["sections"] = [s for s in spec["pages"][0]["sections"] if s["id"] != "stats-1"]
    diff, issues = stabilize_section_ids(spec, PREVIOUS)
    assert issues == [] and diff.removed == ["stats-1"] and diff.added == []


def test_a_regenerated_section_id_is_written_back() -> None:
    spec = _spec()
    _section(spec, "stats-1")["id"] = "stats-7"  # same type, same page, new id
    diff, issues = stabilize_section_ids(spec, PREVIOUS)
    assert issues == []
    assert diff.remapped == {"stats-7": "stats-1"} and diff.added == [] and diff.removed == []
    assert spec == PREVIOUS, "the old id is restored in place"


def test_rejects_reusing_an_id_for_a_different_section_type() -> None:
    spec = _spec()
    _section(spec, "stats-1")["type"] = "cta-bold"
    _, issues = stabilize_section_ids(spec, PREVIOUS)
    assert len(issues) == 1 and "stats-1 was a stats-bold on /" in issues[0]


def test_rejects_moving_an_id_to_another_page() -> None:
    spec = _spec()
    moved = _section(spec, "stats-1")
    spec["pages"][0]["sections"].remove(moved)
    spec["pages"][1]["sections"].append(moved)
    _, issues = stabilize_section_ids(spec, PREVIOUS)
    assert len(issues) == 1 and "an id keeps its type and page" in issues[0]


def test_ambiguous_regenerated_ids_are_an_issue_not_a_guess() -> None:
    previous = _spec()
    second = copy.deepcopy(_section(previous, "cta-1"))
    second["id"] = "cta-2"
    previous["pages"][0]["sections"].append(second)  # two cta-bold sections on /
    spec = copy.deepcopy(previous)
    _section(spec, "cta-1")["id"] = "cta-8"
    _section(spec, "cta-2")["id"] = "cta-9"
    before = copy.deepcopy(spec)
    _, issues = stabilize_section_ids(spec, previous)
    assert len(issues) == 1 and "cta-8, cta-9" in issues[0] and "cta-1, cta-2" in issues[0]
    assert spec == before, "nothing is rewritten when there are issues"


def test_one_new_section_with_two_removed_candidates_is_an_issue() -> None:
    previous = _spec()
    second = copy.deepcopy(_section(previous, "cta-1"))
    second["id"] = "cta-2"
    previous["pages"][0]["sections"].append(second)
    spec = copy.deepcopy(previous)
    spec["pages"][0]["sections"] = [s for s in spec["pages"][0]["sections"] if s["id"] != "cta-2"]
    _section(spec, "cta-1")["id"] = "cta-8"
    _, issues = stabilize_section_ids(spec, previous)
    assert len(issues) == 1 and "reuse the previous id" in issues[0]
