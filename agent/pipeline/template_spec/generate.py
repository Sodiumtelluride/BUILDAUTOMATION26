"""
Intake -> prompt -> model -> validated design spec, with one repair round.

Only a spec that passes every check in ``finalize_spec`` is returned as
``spec``; otherwise ``issues`` says what was wrong with the last reply.

On a rerun, pass the job's previous spec and its assumption links: the model
sees the spec in the shape it must reply in, and the new spec must keep its
section ids (revisions.py). Reviewer notes go into the prompt on any run.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .catalog import TemplateCatalog, load_catalog
from .intake import PAGE_SLUGS, DesignIntake
from .intake_mapping import IntakeNotes
from .prompt import FLAG_FONT_SUBSTITUTED, FLAG_UNSUPPORTED_FEATURE, render_system_prompt, render_user_message
from .provider import SpecProvider
from .revisions import RevisionDiff, stabilize_section_ids
from .sources import AssumptionLink, source_issues, split_assumptions, to_reply_shape
from .validate import FEATURE_SECTIONS, validate_template_spec


@dataclass
class SpecResult:
    spec: Optional[Dict[str, Any]]
    issues: List[str] = field(default_factory=list)
    attempts: int = 0
    raw: str = ""
    assumptions: List[AssumptionLink] = field(default_factory=list)
    """Each guess with the intake field it is about (the spec keeps only the text)."""
    diff: Optional[RevisionDiff] = None
    """What changed against the previous spec; None on a first run."""


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


def reconcile_flags(spec: Dict[str, Any], intake: DesignIntake, catalog: TemplateCatalog) -> List[str]:
    """Make the owner's "flag, don't drop" rule deterministic.

    Adds the flags the intake alone determines when the model left them out
    (an ``unsupported_feature`` per feature the catalog cannot render, a
    ``font_substituted`` when the brand fonts are not bundled) and returns
    issues for what cannot be patched: the member application form feature
    and its section must agree.
    """
    flags: List[Dict[str, str]] = spec["flags"]

    def has_flag(code: str, needle: str) -> bool:
        return any(f["code"] == code and needle in f["detail"] for f in flags)

    for feature in intake.features:
        if feature not in FEATURE_SECTIONS and not has_flag(FLAG_UNSUPPORTED_FEATURE, feature):
            flags.append({"code": FLAG_UNSUPPORTED_FEATURE, "detail": f"{feature} has no section in the template catalog"})
    unbundled = [font for font in intake.brand_fonts if font not in catalog.fonts]
    if unbundled and not any(f["code"] == FLAG_FONT_SUBSTITUTED for f in flags):
        chosen = spec["tokens"]["fonts"]
        flags.append(
            {
                "code": FLAG_FONT_SUBSTITUTED,
                "detail": f"{', '.join(unbundled)} not bundled; using {chosen['heading']} / {chosen['body']}",
            }
        )

    present = {s["type"] for p in spec["pages"] for s in p["sections"]}
    issues: List[str] = []
    for name, type_id in FEATURE_SECTIONS.items():
        wanted, has = name in intake.features, type_id in present
        if wanted and not has:
            issues.append(f"features: {name} requires a {type_id} section")
        if has and not wanted:
            issues.append(f"pages: a {type_id} section was added but {name} was not requested")
    return issues


def finalize_spec(
    spec: Dict[str, Any],
    intake: DesignIntake,
    job_id: uuid.UUID,
    *,
    previous: Optional[Mapping[str, Any]] = None,
    require_links: bool = True,
) -> Tuple[List[AssumptionLink], Optional[RevisionDiff], List[str]]:
    """Check a parsed model reply and turn it into the final spec, in place.

    Returns (assumption links, revision diff, issues). The spec is final only
    when issues is empty: job id set, assumptions flattened to the template's
    plain strings, intake-determined flags added, previous section ids kept.
    """
    spec["job_id"] = str(job_id)  # ours, not the model's: a clerical slip must not burn the repair round
    links, issues = split_assumptions(spec, require_links=require_links)
    if not issues:
        issues = validate_template_spec(spec, requested_slugs=requested_slugs(intake))
    if not issues:
        issues = source_issues(spec)
    if not issues:
        issues = reconcile_flags(spec, intake, load_catalog())
    diff: Optional[RevisionDiff] = None
    if not issues and previous is not None:
        diff, issues = stabilize_section_ids(spec, previous)
    return links, diff, issues


async def generate_design_spec(
    intake: DesignIntake,
    notes: IntakeNotes,
    job_id: uuid.UUID,
    provider: SpecProvider,
    *,
    max_attempts: int = 2,
    previous: Optional[Mapping[str, Any]] = None,
    previous_assumptions: Sequence[AssumptionLink] = (),
    reviewer_notes: Optional[str] = None,
) -> SpecResult:
    shown = to_reply_shape(previous, previous_assumptions) if previous is not None else None
    system = render_system_prompt(load_catalog())
    issues: Sequence[str] = ()
    raw = ""
    attempts = 0
    for attempts in range(1, max_attempts + 1):
        user = render_user_message(
            intake, notes, job_id, previous_issues=issues, previous_reply=raw, previous_spec=shown, reviewer_notes=reviewer_notes
        )
        raw = await provider(system, user)
        try:
            spec = parse_spec_text(raw)
        except ValueError as exc:
            issues = [str(exc)]
            continue
        links, diff, issues = finalize_spec(spec, intake, job_id, previous=previous)
        if not issues:
            return SpecResult(spec=spec, issues=[], attempts=attempts, raw=raw, assumptions=links, diff=diff)
    return SpecResult(spec=None, issues=list(issues), attempts=attempts, raw=raw)
