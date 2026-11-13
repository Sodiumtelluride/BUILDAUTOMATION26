"""
Stable section ids across revisions.

When DESIGN reruns for a job (a reviewer rejected the site), later stages'
work is keyed by section id, so a section that survives must keep its id.
Content block ids are the catalog's own (``hero.headline``), fixed by the
section type, so only section ids can drift.

The new spec is compared against the previous spec's ``id -> (type, page)``:

  - Same id, same type, same page: the section survived. Nothing to do.
  - Same id, different type or page: an issue. An id never changes meaning.
  - New id, and exactly one removed id of the same type on the same page (and
    no other new section competing for it): the model regenerated the id of a
    surviving section. The old id is written back; no retry is spent on it.
  - New id, with several candidates on either side: an issue. Code does not
    guess which section continues which.
  - New id, nothing removed of that type on that page: a genuine addition.

Ids are rewritten only when the whole spec has no issues.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Tuple

Key = Tuple[str, str]  # (section type, page slug)


@dataclass(frozen=True)
class RevisionDiff:
    kept: List[str] = field(default_factory=list)
    added: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    remapped: Dict[str, str] = field(default_factory=dict)
    """id the model wrote -> previous id that was written back."""


def _section_keys(spec: Mapping[str, Any]) -> Dict[str, Key]:
    return {s["id"]: (s["type"], p["slug"]) for p in spec["pages"] for s in p["sections"]}


def stabilize_section_ids(spec: Dict[str, Any], previous: Mapping[str, Any]) -> Tuple[RevisionDiff, List[str]]:
    """Make ``spec`` keep the previous spec's section ids. Returns (diff, issues).

    Both specs must already be schema-valid. ``spec`` is edited in place, and
    only when there are no issues.
    """
    old = _section_keys(previous)
    issues: List[str] = []
    kept: List[str] = []
    new_by_key: Dict[Key, List[Dict[str, Any]]] = {}

    for p, page in enumerate(spec["pages"]):
        for s, section in enumerate(page["sections"]):
            key: Key = (section["type"], page["slug"])
            before = old.get(section["id"])
            if before is None:
                new_by_key.setdefault(key, []).append(section)
            elif before == key:
                kept.append(section["id"])
            else:
                issues.append(
                    f"pages[{p}].sections[{s}].id: {section['id']} was a {before[0]} on {before[1]} in the previous spec; "
                    "an id keeps its type and page, so give this section a new id"
                )

    old_by_key: Dict[Key, List[str]] = {}
    for old_id, key in old.items():
        if old_id not in kept:
            old_by_key.setdefault(key, []).append(old_id)

    pairs: List[Tuple[Dict[str, Any], str]] = []
    added: List[str] = []
    for key, sections in new_by_key.items():
        candidates = old_by_key.get(key, [])
        if not candidates:
            added += [section["id"] for section in sections]
        elif len(candidates) == 1 and len(sections) == 1:
            pairs.append((sections[0], candidates[0]))
        else:
            new_ids = ", ".join(section["id"] for section in sections)
            issues.append(
                f"pages: new {key[0]} section(s) {new_ids} on {key[1]} replace previous id(s) {', '.join(candidates)}; "
                "reuse the previous id for each section that continues an old one"
            )

    if issues:
        return RevisionDiff(), issues

    remapped: Dict[str, str] = {}
    for section, old_id in pairs:
        remapped[section["id"]] = old_id
        section["id"] = old_id
    survivors = set(kept) | set(remapped.values())
    removed = [old_id for old_id in old if old_id not in survivors]
    return RevisionDiff(kept=kept, added=added, removed=removed, remapped=remapped), []
