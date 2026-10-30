"""
Stable IDs across revisions (PRD §3 rules, D17, D19).

When DESIGN reruns for a job (reviewer rejection routed to design, or a
CODE_GENERATION spec_change_request), the new spec must keep the IDs of
anything that still exists. CODE_GENERATION components and CONTENT copy are
keyed by these IDs, so a silently renamed ID orphans that work.

Rules:
  - job_id never changes.
  - An ID that survives keeps its identity: a section keeps its type and page;
    a content block keeps its kind and section.
  - An ID may not be regenerated: if a section disappears and a new one of the
    same type appears on the same page, the old ID must be reused. Same for a
    content block of the same kind inside a surviving section.

  - The decision log is append-only (D5, Pipeline DoD): every decision from
    the previous spec is still there, unchanged. A rerun records changes as
    new decisions that supersede old ones.

Removals and genuine additions are allowed and reported in the diff, so the
pipeline knows which downstream work to invalidate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .issues import ValidationIssue
from .schema import DesignSpec


@dataclass(frozen=True)
class RevisionDiff:
    sections_added: Tuple[str, ...]
    sections_removed: Tuple[str, ...]
    content_blocks_added: Tuple[str, ...]
    content_blocks_removed: Tuple[str, ...]


@dataclass(frozen=True)
class _SectionInfo:
    page: str
    type: str
    path: str


@dataclass(frozen=True)
class _BlockInfo:
    section: str
    kind: str
    path: str


def _index(spec: DesignSpec) -> Tuple[Dict[str, _SectionInfo], Dict[str, _BlockInfo]]:
    sections: Dict[str, _SectionInfo] = {}
    blocks: Dict[str, _BlockInfo] = {}
    for p, page in enumerate(spec.pages):
        for s, section in enumerate(page.sections):
            s_path = f"pages[{p}].sections[{s}]"
            sections[section.id] = _SectionInfo(page.slug, section.type, s_path)
            for b, block in enumerate(section.content_blocks):
                blocks[block.id] = _BlockInfo(section.id, block.kind, f"{s_path}.content_blocks[{b}]")
    return sections, blocks


def compare_revisions(prev: DesignSpec, nxt: DesignSpec) -> Tuple[List[ValidationIssue], RevisionDiff]:
    out: List[ValidationIssue] = []

    if nxt.job_id != prev.job_id:
        out.append(ValidationIssue("job_id_changed", "job_id", f"job_id changed from {prev.job_id} to {nxt.job_id}"))
    a_sections, a_blocks = _index(prev)
    b_sections, b_blocks = _index(nxt)

    # Surviving IDs must keep their identity.
    for sid, now in b_sections.items():
        was = a_sections.get(sid)
        if was is not None and (was.type != now.type or was.page != now.page):
            out.append(
                ValidationIssue(
                    "section_identity_changed",
                    f"{now.path}.id",
                    f'section "{sid}" was {was.type} on {was.page} and is now {now.type} on {now.page}; '
                    "give a different section a new id instead of reusing this one",
                )
            )
    for bid, now_b in b_blocks.items():
        was_b = a_blocks.get(bid)
        if was_b is not None and (was_b.kind != now_b.kind or was_b.section != now_b.section):
            out.append(
                ValidationIssue(
                    "content_block_identity_changed",
                    f"{now_b.path}.id",
                    f'content block "{bid}" was a {was_b.kind} in "{was_b.section}" '
                    f'and is now a {now_b.kind} in "{now_b.section}"',
                )
            )

    sections_removed = [i for i in a_sections if i not in b_sections]
    sections_added = [i for i in b_sections if i not in a_sections]
    blocks_removed = [i for i in a_blocks if i not in b_blocks]
    blocks_added = [i for i in b_blocks if i not in a_blocks]

    # Regenerated section IDs: a removed and an added section in the same slot.
    unmatched = list(sections_removed)
    for added in sections_added:
        now = b_sections[added]
        match = next(
            (r for r in unmatched if a_sections[r].page == now.page and a_sections[r].type == now.type),
            None,
        )
        if match is not None:
            unmatched.remove(match)
            out.append(
                ValidationIssue(
                    "section_id_regenerated",
                    f"{now.path}.id",
                    f'"{added}" replaces "{match}" (same {now.type} on {now.page}); keep the id "{match}"',
                )
            )

    # Regenerated content block IDs: inside a surviving section, same kind.
    unmatched_blocks = list(blocks_removed)
    for added in blocks_added:
        now_b = b_blocks[added]
        if now_b.section not in a_sections:
            continue
        match = next(
            (
                r
                for r in unmatched_blocks
                if a_blocks[r].section == now_b.section and a_blocks[r].kind == now_b.kind
            ),
            None,
        )
        if match is not None:
            unmatched_blocks.remove(match)
            out.append(
                ValidationIssue(
                    "content_block_id_regenerated",
                    f"{now_b.path}.id",
                    f'"{added}" replaces "{match}" (same {now_b.kind} in "{now_b.section}"); keep the id "{match}"',
                )
            )

    new_log = {d.id: d for d in nxt.decisions}
    for old in prev.decisions:
        kept = new_log.get(old.id)
        if kept is None:
            out.append(
                ValidationIssue(
                    "decision_history_changed",
                    "decisions",
                    f'decision "{old.id}" was removed; keep it and supersede it with a new decision instead',
                )
            )
        elif kept != old:
            out.append(
                ValidationIssue(
                    "decision_history_changed",
                    "decisions",
                    f'decision "{old.id}" was edited; keep it unchanged and supersede it with a new decision instead',
                )
            )

    diff = RevisionDiff(
        sections_added=tuple(sections_added),
        sections_removed=tuple(sections_removed),
        content_blocks_added=tuple(blocks_added),
        content_blocks_removed=tuple(blocks_removed),
    )
    return out, diff
