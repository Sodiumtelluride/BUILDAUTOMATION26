"""D5: every design decision records the source behind it."""

from __future__ import annotations

from typing import Any, Callable, Dict, List

import pytest

from pipeline.design_spec import (
    Decision,
    DesignSpec,
    Invalid,
    Valid,
    current_decisions,
    decisions_for,
    from_intake,
    from_rule,
    record_decision,
    spec_targets,
    validate_design_spec,
)

MakeSpec = Callable[[], Dict[str, Any]]


def codes(data: Dict[str, Any], previous: DesignSpec | None = None) -> List[str]:
    result = validate_design_spec(data, previous=previous)
    return [i.code for i in result.issues] if isinstance(result, Invalid) else []


def decision(n: int, **overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "id": f"dec-{n}",
        "kind": "section",
        "targets": ["section:hero-1"],
        "sources": [{"type": "intake", "ref": "visual_style"}],
        "method": "llm",
        "revision": 1,
    }
    return {**base, **overrides}


# --- Coverage: every part of the spec has a current decision -----------------


def test_fixture_covers_every_target(make_spec: MakeSpec) -> None:
    result = validate_design_spec(make_spec())
    assert isinstance(result, Valid)
    covered = {t for d in current_decisions(result.spec) for t in d.targets}
    assert set(spec_targets(result.spec)) <= covered


def test_rejects_a_section_with_no_decision(make_spec: MakeSpec) -> None:
    s = make_spec()
    s["decisions"] = [d for d in s["decisions"] if d["targets"] != ["section:programs-grid-1"]]
    result = validate_design_spec(s)
    assert isinstance(result, Invalid)
    assert any(i.code == "decision_missing" and "section:programs-grid-1" in i.message for i in result.issues)


def test_rejects_a_token_with_no_decision(make_spec: MakeSpec) -> None:
    s = make_spec()
    s["tokens"]["colors"]["ring"] = "#1A3C6E"
    assert "decision_missing" in codes(s)


def test_rejects_a_flag_with_no_decision(make_spec: MakeSpec) -> None:
    s = make_spec()
    s["flags"].append({"code": "tone_style_conflict", "tones": ["playful"]})
    assert "decision_missing" in codes(s)


def test_contrast_adjustment_needs_a_contrast_fix_decision(make_spec: MakeSpec) -> None:
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
    assert "contrast_fix_unrecorded" in codes(s)


# --- The log itself is well formed -------------------------------------------


def test_rejects_a_decision_about_something_not_in_the_spec(make_spec: MakeSpec) -> None:
    s = make_spec()
    s["decisions"].append(decision(16, targets=["section:team-grid-1"]))
    assert "decision_target_missing" in codes(s)


def test_rejects_duplicate_decision_ids(make_spec: MakeSpec) -> None:
    s = make_spec()
    s["decisions"].append(decision(1))
    assert "duplicate_decision_id" in codes(s)


def test_rejects_links_to_decisions_that_do_not_exist(make_spec: MakeSpec) -> None:
    s = make_spec()
    s["decisions"].append(decision(16, derived_from=["dec-99"]))
    s["decisions"].append(decision(17, supersedes="dec-98"))
    assert codes(s).count("decision_reference_missing") == 2


def test_rejects_superseding_one_decision_twice(make_spec: MakeSpec) -> None:
    s = make_spec()
    s["decisions"].append(decision(16, supersedes="dec-7"))
    s["decisions"].append(decision(17, supersedes="dec-7"))
    assert "decision_superseded_twice" in codes(s)


def test_rejects_sources_outside_the_fixed_vocabularies(make_spec: MakeSpec) -> None:
    s = make_spec()
    s["decisions"][0]["sources"] = [{"type": "vibes", "ref": "the client seemed nice"}]
    assert "schema" in codes(s)


def test_rejects_a_kind_pointing_at_the_wrong_kind_of_target(make_spec: MakeSpec) -> None:
    s = make_spec()
    s["decisions"].append(decision(16, kind="token", targets=["section:hero-1"]))
    assert "schema" in codes(s)


def test_assumptions_need_a_summary_for_the_reviewer(make_spec: MakeSpec) -> None:
    s = make_spec()
    del s["decisions"][-1]["summary"]
    assert "schema" in codes(s)


def test_assumptions_may_be_about_the_whole_site(make_spec: MakeSpec) -> None:
    s = make_spec()
    s["decisions"].append(
        decision(16, kind="assumption", targets=["spec"], sources=[{"type": "intake", "ref": "target_audience"}],
                 summary="Audience read as local families, not donors.")
    )
    assert isinstance(validate_design_spec(s), Valid)


# --- Reruns: the log is append-only ------------------------------------------


def test_rerun_can_supersede_a_decision(make_spec: MakeSpec) -> None:
    prev = DesignSpec.model_validate(make_spec())
    nxt = make_spec()
    nxt["tokens"]["colors"]["primary"] = "#7A3B1E"
    nxt["decisions"].append(
        decision(16, kind="token", targets=["tokens.colors.primary", "tokens.colors.secondary"],
                 sources=[{"type": "reviewer_note", "ref": "rej-1"}], revision=2, supersedes="dec-1")
    )
    result = validate_design_spec(nxt, previous=prev)
    assert isinstance(result, Valid)
    assert [d.id for d in decisions_for(result.spec, "tokens.colors.primary")] == ["dec-16"]


def test_rerun_may_not_delete_old_decisions(make_spec: MakeSpec) -> None:
    prev = DesignSpec.model_validate(make_spec())
    nxt = make_spec()
    nxt["decisions"].append(decision(16, revision=2, supersedes="dec-7"))
    del nxt["decisions"][6]  # dec-7
    assert "decision_history_changed" in codes(nxt, previous=prev)


def test_rerun_may_not_edit_old_decisions(make_spec: MakeSpec) -> None:
    prev = DesignSpec.model_validate(make_spec())
    nxt = make_spec()
    nxt["decisions"][6]["sources"] = [{"type": "intake", "ref": "tone"}]
    assert "decision_history_changed" in codes(nxt, previous=prev)


def test_removed_section_leaves_its_decision_as_history(make_spec: MakeSpec) -> None:
    prev = DesignSpec.model_validate(make_spec())
    nxt = make_spec()
    del nxt["pages"][0]["sections"][1]  # programs-grid-1; dec-8 stays in the log
    result = validate_design_spec(nxt, previous=prev)
    assert isinstance(result, Valid)
    assert "dec-8" not in [d.id for d in current_decisions(result.spec)]


# --- record_decision helper ----------------------------------------------------


def test_record_decision_appends_with_the_next_id(make_spec: MakeSpec) -> None:
    spec = DesignSpec.model_validate(make_spec())
    log = record_decision(
        spec.decisions, kind="contrast_fix", targets=["tokens.colors.muted_foreground"],
        sources=from_rule("wcag_aa"), method="code", revision=1, derived_from=["dec-2"],
    )
    assert len(log) == len(spec.decisions) + 1
    assert log[-1].id == "dec-16"
    assert len(spec.decisions) == 15  # the original log is untouched


def test_record_decision_starts_an_empty_log_at_dec_1() -> None:
    log: List[Decision] = []
    log = record_decision(log, kind="page", targets=["page:/"], sources=from_intake("pages"), method="code", revision=1)
    assert [d.id for d in log] == ["dec-1"]


def test_record_decision_rejects_node_bugs(make_spec: MakeSpec) -> None:
    log = DesignSpec.model_validate(make_spec()).decisions
    with pytest.raises(ValueError, match="not in the log"):
        record_decision(log, kind="page", targets=["page:/"], sources=from_intake("pages"), method="code",
                        revision=2, supersedes="dec-99")
    log = record_decision(log, kind="page", targets=["page:/"], sources=from_intake("pages"), method="code",
                          revision=2, supersedes="dec-6")
    with pytest.raises(ValueError, match="already superseded"):
        record_decision(log, kind="page", targets=["page:/"], sources=from_intake("pages"), method="code",
                        revision=2, supersedes="dec-6")
    with pytest.raises(ValueError):
        record_decision(log, kind="page", targets=["section:hero-1"], sources=from_intake("pages"), method="code",
                        revision=2)
