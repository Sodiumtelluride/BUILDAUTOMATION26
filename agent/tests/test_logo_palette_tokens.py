"""BUI-71 (D8): derived logo colors become tokens with provenance; D10 never fires with a logo."""

from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, List

from pipeline.design_spec import (
    DesignSpec,
    LayoutPlan,
    LogoPalette,
    assemble_design_spec,
    current_decisions,
    parse_design_intake,
    requested_slugs,
    validate_design_spec,
)
from pipeline.design_spec.generation import DEFAULT_COLORS
from pipeline.design_spec.schema import Decision, DefaultDesignTrackFlag, IntakeSource
from pipeline.design_spec.validate import Valid

MakeIntake = Callable[[], Dict[str, Any]]
MakePlan = Callable[[], Dict[str, Any]]
JOB_ID = uuid.uuid4()
DERIVED = LogoPalette(primary="#2E7D32", secondary="#FFA000", candidates=("#2E7D32", "#FFA000"), failure=None)


def _assemble(
    intake_dict: Dict[str, Any],
    plan_dict: Dict[str, Any],
    palette: LogoPalette | None,
    previous: DesignSpec | None = None,
    revision: int = 1,
) -> DesignSpec:
    intake = parse_design_intake(intake_dict)
    spec_dict = assemble_design_spec(
        JOB_ID, intake, LayoutPlan.model_validate(plan_dict), previous=previous, revision=revision, logo_palette=palette
    )
    result = validate_design_spec(spec_dict, expected_job_id=JOB_ID, required_slugs=requested_slugs(intake))
    assert isinstance(result, Valid), getattr(result, "issues", None)
    return result.spec


def _cites_logo(d: Decision) -> bool:
    return any(isinstance(s, IntakeSource) and s.ref == "logo" for s in d.sources)


def _assumptions_citing_logo(spec: DesignSpec) -> List[Decision]:
    return [d for d in current_decisions(spec) if d.kind == "assumption" and _cites_logo(d)]


def test_logo_palette_fills_primary_and_secondary_when_colors_missing(make_intake: MakeIntake, make_plan: MakePlan) -> None:
    intake_dict = make_intake()
    intake_dict["brand_colors"] = []
    spec = _assemble(intake_dict, make_plan(), DERIVED)
    assert spec.tokens.colors["primary"] == "#2E7D32"
    assert spec.tokens.colors["secondary"] == "#FFA000"
    token_decisions = [d for d in current_decisions(spec) if d.kind == "token" and "tokens.colors.primary" in d.targets]
    assert token_decisions and all(_cites_logo(d) for d in token_decisions)
    assert len(_assumptions_citing_logo(spec)) == 1
    assert "derived from the uploaded logo" in (_assumptions_citing_logo(spec)[0].summary or "")
    assert not [f for f in spec.flags if f.code == "default_design_track"]


def test_single_color_palette_keeps_default_secondary(make_intake: MakeIntake, make_plan: MakePlan) -> None:
    intake_dict = make_intake()
    intake_dict["brand_colors"] = []
    spec = _assemble(intake_dict, make_plan(), LogoPalette("#2E7D32", None, ("#2E7D32",), None))
    assert spec.tokens.colors["primary"] == "#2E7D32"
    assert spec.tokens.colors["secondary"] == DEFAULT_COLORS["secondary"]
    secondary_decisions = [
        d for d in current_decisions(spec) if "tokens.colors.secondary" in d.targets and d.kind == "token"
    ]
    assert secondary_decisions and not any(_cites_logo(d) for d in secondary_decisions)


def test_failed_palette_keeps_defaults_and_records_why(make_intake: MakeIntake, make_plan: MakePlan) -> None:
    intake_dict = make_intake()
    intake_dict["brand_colors"] = []
    spec = _assemble(intake_dict, make_plan(), LogoPalette.failed("fetch_failed"))
    assert spec.tokens.colors["primary"] == DEFAULT_COLORS["primary"]
    notes = _assumptions_citing_logo(spec)
    assert len(notes) == 1
    assert "fetch_failed" in (notes[0].summary or "")
    assert not [f for f in spec.flags if f.code == "default_design_track"]


def test_missing_palette_with_logo_and_no_colors_counts_as_not_attempted(
    make_intake: MakeIntake, make_plan: MakePlan
) -> None:
    intake_dict = make_intake()
    intake_dict["brand_colors"] = []
    spec = _assemble(intake_dict, make_plan(), None)
    assert spec.tokens.colors["primary"] == DEFAULT_COLORS["primary"]
    assert "not_attempted" in (_assumptions_citing_logo(spec)[0].summary or "")


def test_given_brand_colors_win_over_logo_palette(make_intake: MakeIntake, make_plan: MakePlan) -> None:
    intake_dict = make_intake()  # has brand_colors
    spec = _assemble(intake_dict, make_plan(), LogoPalette("#123456", "#654321", ("#123456", "#654321"), None))
    assert spec.tokens.colors["primary"] == intake_dict["brand_colors"][0]
    assert not _assumptions_citing_logo(spec)


def test_default_track_never_fires_when_a_logo_exists(make_intake: MakeIntake, make_plan: MakePlan) -> None:
    intake_dict = make_intake()
    intake_dict["brand_colors"] = []
    intake_dict["brand_fonts"] = []
    spec = _assemble(intake_dict, make_plan(), LogoPalette.failed("unreadable"))
    assert not [f for f in spec.flags if f.code == "default_design_track"]


def test_default_track_still_fires_without_a_logo(make_intake: MakeIntake, make_plan: MakePlan) -> None:
    intake_dict = make_intake()
    intake_dict["logo"] = None
    intake_dict["brand_colors"] = []
    spec = _assemble(intake_dict, make_plan(), None)
    flags = [f for f in spec.flags if isinstance(f, DefaultDesignTrackFlag)]
    assert flags and flags[0].missing == ["logo", "brand_colors"]
    assert not _assumptions_citing_logo(spec)


def test_rerun_does_not_duplicate_logo_decisions(make_intake: MakeIntake, make_plan: MakePlan) -> None:
    intake_dict = make_intake()
    intake_dict["brand_colors"] = []
    first = _assemble(intake_dict, make_plan(), DERIVED)
    second = _assemble(intake_dict, make_plan(), DERIVED, previous=first, revision=2)
    assert len(_assumptions_citing_logo(second)) == 1
    assert len([d for d in second.decisions if d.kind == "token" and _cites_logo(d)]) == 1
