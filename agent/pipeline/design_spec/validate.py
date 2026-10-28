"""
D20: validate DESIGN output against the design_spec schema before it is
written to pipeline state.

Checks, in order:
  1. Schema: the strict Pydantic contract in schema.py.
  2. Job: the spec's job_id is the job being run, when the caller passes it.
  3. IDs: section, content block and page IDs are unique (so downstream
     stages can address them), and flags only point at IDs that exist.
  4. Consistency: figma_url is set exactly when there is no no_figma flag.
  5. Stable IDs: on a rerun, IDs match the previous spec (revisions.py).

Pure function: no I/O, no state writes. The caller writes ``spec`` to state
only when the result is ``Valid``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple, Union

from pydantic import ValidationError

from .issues import ValidationIssue
from .revisions import RevisionDiff, compare_revisions
from .schema import DesignSpec, HeroImageFallbackFlag, NoFigmaFlag


@dataclass(frozen=True)
class Valid:
    spec: DesignSpec
    diff: Optional[RevisionDiff] = None
    ok: bool = field(default=True, init=False)


@dataclass(frozen=True)
class Invalid:
    issues: Sequence[ValidationIssue]
    ok: bool = field(default=False, init=False)


ValidateResult = Union[Valid, Invalid]


def validate_design_spec(
    data: object,
    previous: Optional[DesignSpec] = None,
    *,
    expected_job_id: Optional[Union[uuid.UUID, str]] = None,
) -> ValidateResult:
    """
    Validate parsed model output (a dict). Pass ``previous`` on a rerun.

    Pass ``expected_job_id`` (the job being run) whenever the result may be
    written to state, so a spec for the wrong job is never accepted.
    """
    try:
        spec = DesignSpec.model_validate(data)
    except ValidationError as exc:
        return Invalid([ValidationIssue("schema", _format_loc(e["loc"]), e["msg"]) for e in exc.errors()])

    issues: List[ValidationIssue] = []
    if expected_job_id is not None:
        try:
            expected = uuid.UUID(str(expected_job_id))
        except ValueError:
            raise ValueError(f"expected_job_id is not a UUID: {expected_job_id!r}") from None
        if spec.job_id != expected:
            issues.append(
                ValidationIssue(
                    "job_id_mismatch", "job_id", f'job_id is "{spec.job_id}" but this run is for job "{expected}"'
                )
            )

    issues.extend(_check_ids(spec))
    issues.extend(_check_figma(spec))

    diff: Optional[RevisionDiff] = None
    if previous is not None:
        revision_issues, diff = compare_revisions(previous, spec)
        issues.extend(revision_issues)

    return Invalid(issues) if issues else Valid(spec, diff)


def _check_ids(spec: DesignSpec) -> List[ValidationIssue]:
    out: List[ValidationIssue] = []
    slugs: Set[str] = set()
    section_ids: Dict[str, str] = {}  # id -> where it was first seen
    block_ids: Dict[str, str] = {}

    for p, page in enumerate(spec.pages):
        if page.slug in slugs:
            out.append(
                ValidationIssue("duplicate_slug", f"pages[{p}].slug", f'slug "{page.slug}" appears on more than one page')
            )
        slugs.add(page.slug)

        for s, section in enumerate(page.sections):
            s_path = f"pages[{p}].sections[{s}]"
            first = section_ids.setdefault(section.id, f"{s_path}.id")
            if first != f"{s_path}.id":
                out.append(
                    ValidationIssue(
                        "duplicate_section_id", f"{s_path}.id", f'section id "{section.id}" is already used at {first}'
                    )
                )

            for b, block in enumerate(section.content_blocks):
                b_path = f"{s_path}.content_blocks[{b}].id"
                first_block = block_ids.setdefault(block.id, b_path)
                if first_block != b_path:
                    out.append(
                        ValidationIssue(
                            "duplicate_content_block_id",
                            b_path,
                            f'content block id "{block.id}" is already used at {first_block}; '
                            "CONTENT fills blocks by id, so ids must be unique across the whole spec",
                        )
                    )

    for i, flag in enumerate(spec.flags):
        if isinstance(flag, HeroImageFallbackFlag) and flag.section_id not in section_ids:
            out.append(
                ValidationIssue(
                    "flag_reference_missing",
                    f"flags[{i}].section_id",
                    f'section "{flag.section_id}" does not exist in the page map',
                )
            )
    return out


def _check_figma(spec: DesignSpec) -> List[ValidationIssue]:
    """D16 + PRD §4: the dashboard hides the Figma link when no_figma is set,
    so a spec must have either a figma_url or a no_figma flag, never both."""
    has_no_figma = any(isinstance(f, NoFigmaFlag) for f in spec.flags)
    if spec.figma_url is not None and has_no_figma:
        return [ValidationIssue("figma_state_conflict", "figma_url", "figma_url is set but a no_figma flag is also set")]
    if spec.figma_url is None and not has_no_figma:
        return [
            ValidationIssue(
                "figma_state_conflict", "figma_url", "figma_url is missing; set it or add a no_figma flag with a reason"
            )
        ]
    return []


def _format_loc(loc: Tuple[Union[int, str], ...]) -> str:
    out = ""
    for seg in loc:
        if isinstance(seg, int):
            out += f"[{seg}]"
        else:
            out += seg if out == "" else f".{seg}"
    return out
