"""The INTAKE node: stored blob -> project_spec, and a review flag naming the field when it cannot map."""

from __future__ import annotations

import copy
import json
import pathlib
import uuid
from typing import Any, Dict

from pipeline.nodes.intake import run_intake
from pipeline.state import PipelineState, StageEnum
from pipeline.template_spec.intake_mapping import from_project_spec

FIX = pathlib.Path(__file__).parent / "fixtures"
RAW: Dict[str, Any] = json.loads((FIX / "intake_answers_complete.json").read_text())


def _state(payload: Dict[str, Any]) -> PipelineState:
    return PipelineState(org_id=uuid.uuid4(), raw_form_payload=payload)


def test_stored_blob_becomes_a_project_spec_design_can_read() -> None:
    result = run_intake(_state(RAW))
    assert set(result) == {"intake_output"}
    intake, _ = from_project_spec(result["intake_output"].project_spec)
    assert intake.organization_name == RAW["answers"]["organizationName"]


def test_unknown_label_flags_the_job_and_names_the_field() -> None:
    payload = copy.deepcopy(RAW)
    payload["answers"]["primaryGoal"] = "World domination"
    result = run_intake(_state(payload))
    assert set(result) == {"review_flag"}
    flag = result["review_flag"]
    assert flag.flagged_by_stage == StageEnum.INTAKE and "primaryGoal" in (flag.reviewer_notes or "")


def test_missing_answer_flags_the_job() -> None:
    payload = copy.deepcopy(RAW)
    del payload["answers"]["pages"]
    result = run_intake(_state(payload))
    assert "pages" in (result["review_flag"].reviewer_notes or "")
