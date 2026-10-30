"""
D5: record the source behind every design decision.

The decision log lives in ``DesignSpec.decisions``. Downstream stages ignore
it; it exists for the reviewer panel ("Assumptions, each citing its source
field", PRD §4) and for engineers debugging a bad output (PRD §2).

How it works:
  - Every value the DESIGN node sets goes through ``record_decision``. Code
    that sets a value records ``method="code"``; when the model chose it, the
    model's cited sources are recorded with ``method="llm"``.
  - The log is append-only (Pipeline DoD: stages append, never overwrite).
    A rerun adds new decisions that ``supersedes`` old ones; the old ones stay
    as history.
  - A decision is *current* when nothing supersedes it and every one of its
    targets still exists in the spec. Validation (validate.py) requires every
    part of the spec to have at least one current decision.

Example, inside the DESIGN node::

    log = record_decision(
        log, kind="token", targets=["tokens.colors.primary"],
        sources=from_intake("brand_colors"), method="code", revision=1,
    )
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional, Sequence, Set

from .schema import (
    ConfigRef,
    ConfigSource,
    Decision,
    DecisionKind,
    DefaultRef,
    DefaultSource,
    DesignSpec,
    Flag,
    HeroImageFallbackFlag,
    IntakeField,
    IntakeSource,
    RuleRef,
    RuleSource,
    Source,
)

# ---------------------------------------------------------------------------
# Building sources (short helpers so node code stays readable)
# ---------------------------------------------------------------------------


def from_intake(*fields: IntakeField) -> List[Source]:
    return [IntakeSource(type="intake", ref=f) for f in fields]


def from_rule(ref: RuleRef) -> List[Source]:
    return [RuleSource(type="rule", ref=ref)]


def from_default(ref: DefaultRef) -> List[Source]:
    return [DefaultSource(type="default", ref=ref)]


def from_config(ref: ConfigRef) -> List[Source]:
    return [ConfigSource(type="config", ref=ref)]


# ---------------------------------------------------------------------------
# Targets: every part of the spec that needs a decision
# ---------------------------------------------------------------------------


def flag_target(flag: Flag) -> str:
    """Flags have no ID, so their target is the code (plus the section, if any)."""
    if isinstance(flag, HeroImageFallbackFlag):
        return f"flag:{flag.code}:{flag.section_id}"
    return f"flag:{flag.code}"


def spec_targets(spec: DesignSpec) -> List[str]:
    """
    Every target that must have a current decision, in spec order.

    Content blocks are covered by their section's decision, not listed here.
    """
    out: List[str] = [f"tokens.colors.{role}" for role in spec.tokens.colors]
    out += ["tokens.fonts.heading", "tokens.fonts.body", "tokens.radius"]
    for page in spec.pages:
        out.append(f"page:{page.slug}")
        out += [f"section:{s.id}" for s in page.sections]
    out += [f"feature:{f}" for f in spec.features]
    out += [f"data_requirement:{d.recipe}" for d in spec.data_requirements]
    out += [f"integration:{i}" for i in spec.integrations]
    out += [flag_target(f) for f in spec.flags]
    return list(dict.fromkeys(out))  # drop repeats, keep order


def addressable_targets(spec: DesignSpec) -> Set[str]:
    """What a decision may point at: the spec's targets, plus "spec" itself."""
    return set(spec_targets(spec)) | {"spec"}


# ---------------------------------------------------------------------------
# Reading the log
# ---------------------------------------------------------------------------


def superseded_ids(log: Sequence[Decision]) -> Set[str]:
    return {d.supersedes for d in log if d.supersedes is not None}


def current_decisions(spec: DesignSpec) -> List[Decision]:
    """Decisions that still apply: not superseded, and all targets still exist.

    This is what the reviewer panel should show.
    """
    gone = superseded_ids(spec.decisions)
    exists = addressable_targets(spec)
    return [d for d in spec.decisions if d.id not in gone and all(t in exists for t in d.targets)]


def decisions_for(spec: DesignSpec, target: str) -> List[Decision]:
    """Current decisions about one target, e.g. "section:hero-1" (for debugging)."""
    return [d for d in current_decisions(spec) if target in d.targets]


# ---------------------------------------------------------------------------
# Writing the log
# ---------------------------------------------------------------------------


def record_decision(
    log: Sequence[Decision],
    *,
    kind: DecisionKind,
    targets: Sequence[str],
    sources: Sequence[Source],
    method: Literal["code", "llm"],
    revision: int,
    derived_from: Sequence[str] = (),
    supersedes: Optional[str] = None,
    summary: Optional[str] = None,
) -> List[Decision]:
    """
    Return a new log with one decision appended. ``log`` is not changed.

    Assigns the next ``dec-N`` ID. Raises ``ValueError`` for mistakes in node
    code (unknown decision IDs, superseding twice, a bad target or source),
    because those are bugs, not model output to retry.
    """
    by_id: Dict[str, Decision] = {d.id: d for d in log}
    for ref in [*derived_from, *([supersedes] if supersedes else [])]:
        if ref not in by_id:
            raise ValueError(f'decision "{ref}" is not in the log')
    if supersedes is not None and supersedes in superseded_ids(log):
        raise ValueError(f'decision "{supersedes}" is already superseded')

    next_n = max((int(d.id.split("-")[1]) for d in log), default=0) + 1
    decision = Decision.model_validate(
        {
            "id": f"dec-{next_n}",
            "kind": kind,
            "targets": list(targets),
            "sources": [s.model_dump() for s in sources],
            "method": method,
            "revision": revision,
            "derived_from": list(derived_from),
            "supersedes": supersedes,
            "summary": summary,
        }
    )
    return [*log, decision]
