"""
design_spec: the DESIGN node's output contract (PRD §3) and its D20 validation.

Typical use inside the DESIGN node::

    from pipeline.design_spec import SpecAccepted, generate_validated_spec

    result = await generate_validated_spec(generate=call_model, previous=previous_spec, job_id=state.job_id)
    if isinstance(result, SpecAccepted):
        ...  # safe to write result.spec to state
    else:
        ...  # result.issues -> review flag; an invalid spec is never written
"""

from .issues import IssueCode, ValidationIssue, format_issues_for_repair
from .retry import GenerateAttempt, NeedsHumanReview, RunResult, SpecAccepted, generate_validated_spec
from .revisions import RevisionDiff, compare_revisions
from .schema import DesignSpec
from .validate import Invalid, Valid, ValidateResult, validate_design_spec

__all__ = [
    "DesignSpec",
    "GenerateAttempt",
    "Invalid",
    "IssueCode",
    "NeedsHumanReview",
    "RevisionDiff",
    "RunResult",
    "SpecAccepted",
    "Valid",
    "ValidateResult",
    "ValidationIssue",
    "compare_revisions",
    "format_issues_for_repair",
    "generate_validated_spec",
    "validate_design_spec",
]
