"""
D20: validate DESIGN output against the design_spec schema before it is
written to pipeline state.

Checks, in order:
  1. Schema: the strict Pydantic contract in schema.py.
  2. Job: the spec's job_id is the job being run, when the caller passes it.
  3. IDs: section, content block and page IDs are unique (so downstream
     stages can address them), and flags only point at IDs that exist.
  4. Catalog (D2): every section type is in the approved BUILD section
     catalog, components are allowed for that type, and content blocks match
     the type's slots: kind fixed by the slot, max_chars at most the slot
     limit, required slots present (catalog.py).
  5. Requested pages: when the caller passes the slugs intake asked for,
     every one of them must appear in the page map.
  6. Consistency: figma_url is set exactly when there is no no_figma flag.
  7. Decisions (D5): the log is well formed and every part of the spec has a
     current decision (decisions.py).
  8. Stable IDs: on a rerun, IDs match the previous spec and earlier
     decisions are kept unchanged (revisions.py).

Pure function: no I/O, no state writes. The caller writes ``spec`` to state
only when the result is ``Valid``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple, Union

from pydantic import ValidationError

from .catalog import CATALOG_VERSION, get_section_def
from .decisions import addressable_targets, spec_targets, superseded_ids
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
    required_slugs: Optional[Sequence[str]] = None,
) -> ValidateResult:
    """
    Validate parsed model output (a dict). Pass ``previous`` on a rerun.

    Pass ``expected_job_id`` (the job being run) whenever the result may be
    written to state, so a spec for the wrong job is never accepted.

    Pass ``required_slugs`` (the slugs of the pages intake requested) so a
    spec that drops a requested page is rejected.
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
    issues.extend(_check_catalog(spec))
    issues.extend(_check_requested_pages(spec, required_slugs))
    issues.extend(_check_figma(spec))
    issues.extend(_check_decisions(spec, previous))

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


def _check_catalog(spec: DesignSpec) -> List[ValidationIssue]:
    """D2: sections, their components and their content blocks must come from
    the approved BUILD section catalog (catalog.py, version CATALOG_VERSION)."""
    out: List[ValidationIssue] = []
    for p, page in enumerate(spec.pages):
        for s, section in enumerate(page.sections):
            s_path = f"pages[{p}].sections[{s}]"
            sdef = get_section_def(section.type)
            if sdef is None:
                out.append(
                    ValidationIssue(
                        "unknown_section_type",
                        f"{s_path}.type",
                        f'"{section.type}" is not in the approved BUILD section catalog (version {CATALOG_VERSION})',
                    )
                )
                continue

            unknown = [c for c in section.components if c not in sdef.components]
            if unknown:
                out.append(
                    ValidationIssue(
                        "section_components_not_in_catalog",
                        f"{s_path}.components",
                        f'{unknown} are not allowed for "{section.type}"; allowed: {list(sdef.components)}',
                    )
                )

            filled: Set[str] = set()
            for b, block in enumerate(section.content_blocks):
                b_path = f"{s_path}.content_blocks[{b}]"
                slot_name = block.id.rsplit(".", 1)[-1]
                slot = sdef.slot(slot_name)
                if slot is None:
                    out.append(
                        ValidationIssue(
                            "content_block_catalog_mismatch",
                            f"{b_path}.id",
                            f'"{section.type}" has no content slot "{slot_name}"; '
                            f"slots: {[sl.name for sl in sdef.slots]}",
                        )
                    )
                    continue
                if slot_name in filled:
                    out.append(
                        ValidationIssue(
                            "content_block_catalog_mismatch",
                            f"{b_path}.id",
                            f'slot "{slot_name}" is already filled on section "{section.id}"',
                        )
                    )
                    continue
                filled.add(slot_name)
                if block.kind != slot.kind:
                    out.append(
                        ValidationIssue(
                            "content_block_catalog_mismatch",
                            f"{b_path}.kind",
                            f'slot "{slot_name}" of "{section.type}" is a {slot.kind}, not a {block.kind}',
                        )
                    )
                if block.max_chars > slot.max_chars:
                    out.append(
                        ValidationIssue(
                            "content_block_catalog_mismatch",
                            f"{b_path}.max_chars",
                            f'slot "{slot_name}" of "{section.type}" allows at most {slot.max_chars} characters, '
                            f"got {block.max_chars}",
                        )
                    )

            missing = [sl.name for sl in sdef.required_slots() if sl.name not in filled]
            if missing:
                out.append(
                    ValidationIssue(
                        "missing_required_content_block",
                        f"{s_path}.content_blocks",
                        f'section "{section.id}" ({section.type}) is missing required slots {missing}',
                    )
                )
    return out


def _check_requested_pages(spec: DesignSpec, required_slugs: Optional[Sequence[str]]) -> List[ValidationIssue]:
    if required_slugs is None:
        return []
    present = {page.slug for page in spec.pages}
    return [
        ValidationIssue("missing_requested_page", "pages", f'requested page "{slug}" is not in the page map')
        for slug in required_slugs
        if slug not in present
    ]


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


def _check_decisions(spec: DesignSpec, previous: Optional[DesignSpec] = None) -> List[ValidationIssue]:
    """D5: every design decision is recorded with its source.

    - Decision IDs are unique; derived_from/supersedes point at real decisions;
      nothing is superseded twice.
    - Decisions made in this run only point at things in the spec. Decisions
      kept from ``previous`` may point at things a rerun removed; that is
      history, and they simply stop being current.
    - Every part of the spec has at least one current decision.
    - Every contrast adjustment (D9) has a contrast_fix decision.
    """
    out: List[ValidationIssue] = []
    log = spec.decisions
    seen: Dict[str, int] = {}
    for i, d in enumerate(log):
        if d.id in seen:
            out.append(
                ValidationIssue(
                    "duplicate_decision_id", f"decisions[{i}].id", f'decision id "{d.id}" is already used at decisions[{seen[d.id]}]'
                )
            )
        seen.setdefault(d.id, i)

    supersede_count: Dict[str, int] = {}
    for i, d in enumerate(log):
        for ref in d.derived_from:
            if ref not in seen:
                out.append(
                    ValidationIssue(
                        "decision_reference_missing", f"decisions[{i}].derived_from", f'decision "{ref}" does not exist'
                    )
                )
        if d.supersedes is not None:
            if d.supersedes not in seen or d.supersedes == d.id:
                out.append(
                    ValidationIssue(
                        "decision_reference_missing",
                        f"decisions[{i}].supersedes",
                        f'decision "{d.supersedes}" does not exist or is this decision',
                    )
                )
            supersede_count[d.supersedes] = supersede_count.get(d.supersedes, 0) + 1
    for ref, n in supersede_count.items():
        if n > 1:
            out.append(
                ValidationIssue(
                    "decision_superseded_twice", "decisions", f'decision "{ref}" is superseded by {n} decisions; only one may replace it'
                )
            )

    exists = addressable_targets(spec)
    earlier = {d.id for d in previous.decisions} if previous is not None else set()
    for i, d in enumerate(log):
        if d.id in earlier:
            continue
        for t in d.targets:
            if t not in exists:
                out.append(
                    ValidationIssue(
                        "decision_target_missing", f"decisions[{i}].targets", f'"{t}" is not part of this spec'
                    )
                )

    gone = superseded_ids(log)
    covered: Set[str] = set()
    fixed_roles: Set[str] = set()
    for d in log:
        if d.id in gone or not all(t in exists for t in d.targets):
            continue
        covered.update(d.targets)
        if d.kind == "contrast_fix":
            fixed_roles.update(t.removeprefix("tokens.colors.") for t in d.targets)
    for t in spec_targets(spec):
        if t not in covered:
            out.append(
                ValidationIssue(
                    "decision_missing", "decisions", f'"{t}" has no decision; record which input or rule set it'
                )
            )
    for a, adj in enumerate(spec.tokens.contrast_adjustments):
        if adj.role not in fixed_roles:
            out.append(
                ValidationIssue(
                    "contrast_fix_unrecorded",
                    f"tokens.contrast_adjustments[{a}]",
                    f'the change to "{adj.role}" needs a contrast_fix decision targeting "tokens.colors.{adj.role}"',
                )
            )
    return out


def _format_loc(loc: Tuple[Union[int, str], ...]) -> str:
    out = ""
    for seg in loc:
        if isinstance(seg, int):
            out += f"[{seg}]"
        else:
            out += seg if out == "" else f".{seg}"
    return out
