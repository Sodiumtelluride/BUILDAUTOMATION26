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

from .catalog import CATALOG_VERSION, FEATURE_SECTION_TYPES, SECTION_CATALOG, SectionDef, SlotDef, get_section_def
from .decisions import (
    current_decisions,
    decisions_for,
    from_config,
    from_default,
    from_intake,
    from_rule,
    record_decision,
    spec_targets,
)
from .generation import (
    LayoutPlan,
    PlannedPage,
    PlannedSection,
    assemble_design_spec,
    build_generation_input,
    content_block_index,
    render_plan_prompt,
    requested_slugs,
)
from .intake import PAGE_SLUGS, DesignIntake, missing_branding, parse_design_intake
from .issues import IssueCode, ValidationIssue, format_issues_for_repair
from .logo_palette import LogoPalette, extract_logo_palette
from .retry import GenerateAttempt, NeedsHumanReview, RunResult, SpecAccepted, generate_validated_spec
from .revisions import RevisionDiff, compare_revisions
from .schema import Decision, DesignSpec
from .validate import Invalid, Valid, ValidateResult, validate_design_spec

__all__ = [
    "CATALOG_VERSION",
    "Decision",
    "DesignIntake",
    "DesignSpec",
    "FEATURE_SECTION_TYPES",
    "GenerateAttempt",
    "LayoutPlan",
    "LogoPalette",
    "PAGE_SLUGS",
    "PlannedPage",
    "PlannedSection",
    "SECTION_CATALOG",
    "SectionDef",
    "SlotDef",
    "Invalid",
    "IssueCode",
    "NeedsHumanReview",
    "RevisionDiff",
    "RunResult",
    "SpecAccepted",
    "Valid",
    "ValidateResult",
    "ValidationIssue",
    "assemble_design_spec",
    "build_generation_input",
    "compare_revisions",
    "content_block_index",
    "current_decisions",
    "decisions_for",
    "extract_logo_palette",
    "from_config",
    "get_section_def",
    "missing_branding",
    "parse_design_intake",
    "render_plan_prompt",
    "requested_slugs",
    "from_default",
    "from_intake",
    "from_rule",
    "record_decision",
    "spec_targets",
    "format_issues_for_repair",
    "generate_validated_spec",
    "validate_design_spec",
]
