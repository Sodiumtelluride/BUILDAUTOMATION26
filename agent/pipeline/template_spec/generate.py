"""
Intake -> prompt -> model -> validated design spec, with one repair round.

Only a spec that passes ``validate_template_spec`` is returned as ``spec``;
otherwise ``issues`` says what was wrong with the last reply.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from .catalog import load_catalog
from .intake import PAGE_SLUGS, DesignIntake
from .intake_mapping import IntakeNotes
from .prompt import render_system_prompt, render_user_message
from .provider import SpecProvider
from .validate import validate_template_spec


@dataclass
class SpecResult:
    spec: Optional[Dict[str, Any]]
    issues: List[str] = field(default_factory=list)
    attempts: int = 0
    raw: str = ""


def parse_spec_text(text: str) -> Dict[str, Any]:
    """The JSON object in a model reply, tolerating a code fence or a leading sentence."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("model reply is not a JSON object")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("model reply is not a JSON object") from exc
    if not isinstance(data, dict):
        raise ValueError("model reply is not a JSON object")
    return data


def requested_slugs(intake: DesignIntake) -> List[str]:
    return [PAGE_SLUGS[name] for name in intake.pages]


async def generate_design_spec(
    intake: DesignIntake,
    notes: IntakeNotes,
    job_id: uuid.UUID,
    provider: SpecProvider,
    *,
    max_attempts: int = 2,
) -> SpecResult:
    system = render_system_prompt(load_catalog())
    issues: Sequence[str] = ()
    raw = ""
    attempts = 0
    for attempts in range(1, max_attempts + 1):
        user = render_user_message(intake, notes, job_id, previous_issues=issues)
        raw = await provider(system, user)
        try:
            spec = parse_spec_text(raw)
        except ValueError as exc:
            issues = [str(exc)]
            continue
        if spec.get("job_id") != str(job_id):
            issues = [f"job_id: expected {job_id}, got {spec.get('job_id')!r}"]
            continue
        issues = validate_template_spec(spec, requested_slugs=requested_slugs(intake))
        if not issues:
            return SpecResult(spec=spec, issues=[], attempts=attempts, raw=raw)
    return SpecResult(spec=None, issues=list(issues), attempts=attempts, raw=raw)
