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

from .catalog import TemplateCatalog, load_catalog
from .intake import PAGE_SLUGS, DesignIntake
from .intake_mapping import IntakeNotes
from .prompt import FLAG_FONT_SUBSTITUTED, FLAG_UNSUPPORTED_FEATURE, render_system_prompt, render_user_message
from .provider import SpecProvider
from .validate import MEMBER_FORM_TYPE, validate_template_spec


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


MEMBER_FORM_FEATURE = "member_application_form"


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

    renderable = {MEMBER_FORM_FEATURE}
    for feature in intake.features:
        if feature not in renderable and not has_flag(FLAG_UNSUPPORTED_FEATURE, feature):
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

    has_form_section = any(s["type"] == MEMBER_FORM_TYPE for p in spec["pages"] for s in p["sections"])
    wants_form = MEMBER_FORM_FEATURE in intake.features
    if wants_form and not has_form_section:
        return [f"features: {MEMBER_FORM_FEATURE} requires a {MEMBER_FORM_TYPE} section"]
    if has_form_section and not wants_form:
        return [f"pages: a {MEMBER_FORM_TYPE} section was added but {MEMBER_FORM_FEATURE} was not requested"]
    return []


async def generate_design_spec(
    intake: DesignIntake,
    notes: IntakeNotes,
    job_id: uuid.UUID,
    provider: SpecProvider,
    *,
    max_attempts: int = 2,
) -> SpecResult:
    catalog = load_catalog()
    system = render_system_prompt(catalog)
    issues: Sequence[str] = ()
    raw = ""
    attempts = 0
    for attempts in range(1, max_attempts + 1):
        user = render_user_message(intake, notes, job_id, previous_issues=issues, previous_reply=raw)
        raw = await provider(system, user)
        try:
            spec = parse_spec_text(raw)
        except ValueError as exc:
            issues = [str(exc)]
            continue
        spec["job_id"] = str(job_id)  # ours, not the model's: a clerical slip must not burn the repair round
        issues = validate_template_spec(spec, requested_slugs=requested_slugs(intake))
        if not issues:
            issues = reconcile_flags(spec, intake, catalog)
        if not issues:
            return SpecResult(spec=spec, issues=[], attempts=attempts, raw=raw)
    return SpecResult(spec=None, issues=list(issues), attempts=attempts, raw=raw)
