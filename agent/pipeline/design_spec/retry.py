"""
D20: "On failure, retry this node alone (maximum two attempts), then flag the
job for human review."

generate -> validate -> (retry with the errors) -> accepted, or needs review.

Framework-agnostic so it can be unit tested without LangGraph. The DESIGN node
calls this and returns ``spec`` to state only on a ``SpecAccepted`` result.

  - Invalid output (bad JSON, wrong schema, unstable IDs) counts as a failed
    attempt. The next attempt receives the issues so the prompt can ask for a
    targeted fix.
  - An exception raised by ``generate`` (network, provider outage) is NOT
    caught. That is an infrastructure failure for the queue's retry and
    dead-letter path, not this loop.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional, Sequence, Union

from ..config import get_node_config
from .issues import ValidationIssue
from .revisions import RevisionDiff
from .schema import DesignSpec
from .validate import Invalid, ValidateResult, validate_design_spec


@dataclass(frozen=True)
class GenerateAttempt:
    attempt: int
    """1-based attempt number."""
    previous_issues: Sequence[ValidationIssue]
    """Issues from the previous attempt; empty on the first attempt."""


@dataclass(frozen=True)
class SpecAccepted:
    spec: DesignSpec
    attempts: int
    diff: Optional[RevisionDiff] = None
    status: str = field(default="valid", init=False)


@dataclass(frozen=True)
class NeedsHumanReview:
    issues: Sequence[ValidationIssue]
    """Issues from the final attempt."""
    attempts: int
    status: str = field(default="needs_human_review", init=False)


RunResult = Union[SpecAccepted, NeedsHumanReview]
Generate = Callable[[GenerateAttempt], Awaitable[object]]
OnAttempt = Callable[[int, Sequence[ValidationIssue]], None]


async def generate_validated_spec(
    generate: Generate,
    previous: Optional[DesignSpec] = None,
    max_retries: Optional[int] = None,
    on_attempt: Optional[OnAttempt] = None,
    *,
    job_id: Union[uuid.UUID, str],
    required_slugs: Optional[Sequence[str]] = None,
) -> RunResult:
    """
    Call ``generate`` until it returns a valid spec or the retry limit is hit.

    Args:
        generate: Produces the raw model output: a JSON string or a parsed dict.
        job_id: The job being run. A spec with any other job_id is rejected,
            so output is never written to the wrong job's state.
        previous: The last valid spec for this job, if this is a rerun.
        max_retries: Retries after the first attempt. Defaults to the DESIGN
            node's ``max_retries`` in ``pipeline/config.py`` (overridable with
            the ``AGENT_DESIGN_MAX_RETRIES`` env var).
        on_attempt: Called after every attempt with (attempt, issues), for logging.
        required_slugs: Slugs of the pages intake requested; a spec that drops
            one is rejected.
    """
    retries = get_node_config("DESIGN").max_retries if max_retries is None else max_retries
    if retries < 0:
        raise ValueError(f"max_retries must be >= 0, got {retries}")
    total_attempts = retries + 1

    previous_issues: Sequence[ValidationIssue] = ()

    for attempt in range(1, total_attempts + 1):
        raw = await generate(GenerateAttempt(attempt, previous_issues))
        result = _parse_and_validate(raw, previous, job_id, required_slugs)

        issues: Sequence[ValidationIssue] = result.issues if isinstance(result, Invalid) else ()
        if on_attempt is not None:
            on_attempt(attempt, issues)

        if not isinstance(result, Invalid):
            return SpecAccepted(spec=result.spec, attempts=attempt, diff=result.diff)
        previous_issues = result.issues

    return NeedsHumanReview(issues=previous_issues, attempts=total_attempts)


def _parse_and_validate(
    raw: object,
    previous: Optional[DesignSpec],
    job_id: Union[uuid.UUID, str],
    required_slugs: Optional[Sequence[str]] = None,
) -> ValidateResult:
    if isinstance(raw, (str, bytes)):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            return Invalid([ValidationIssue("invalid_json", "", f"output is not valid JSON: {exc}")])
    return validate_design_spec(raw, previous, expected_job_id=job_id, required_slugs=required_slugs)
