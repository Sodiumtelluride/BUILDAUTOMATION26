"""
INTAKE node: the stored intake blob -> intake_output.project_spec for DESIGN.

``raw_form_payload`` is the JSON the intake API saves in
intake_submissions.notes: ``{version, answers, attachments, ...}``. The
mapping is deterministic (template_spec.intake_mapping); no model call. An
unknown option label or a missing answer flags the job for human review with
the field named, rather than guessing.
"""

from __future__ import annotations

from typing import Any, Dict, Sequence

from pipeline.contracts import validate_state_for_stage
from pipeline.state import IntakeOutput, PipelineState, ReviewFlag, ReviewReason, StageEnum
from pipeline.template_spec.intake_mapping import map_intake_answers, to_project_spec


def run_intake(state: PipelineState) -> Dict[str, Any]:
    """Returns {"intake_output": ...}, or {"review_flag": ...} when the answers cannot be mapped."""
    validate_state_for_stage(StageEnum.INTAKE, state)
    payload = state.raw_form_payload
    try:
        intake, notes = map_intake_answers(payload["answers"], payload.get("attachments", []))
    except KeyError as exc:
        return _review_flag(f"INTAKE: the stored intake has no answer for {exc}")
    except (TypeError, ValueError) as exc:  # ValueError includes pydantic's ValidationError
        return _review_flag(f"INTAKE could not map the stored answers:\n{exc}")
    return {"intake_output": IntakeOutput(project_spec=to_project_spec(intake, notes))}


def _review_flag(notes: str) -> Dict[str, Any]:
    return {
        "review_flag": ReviewFlag(
            reason=ReviewReason.STAGE_ERROR_THRESHOLD, flagged_by_stage=StageEnum.INTAKE, reviewer_notes=notes
        )
    }


__all__: Sequence[str] = ("run_intake",)
