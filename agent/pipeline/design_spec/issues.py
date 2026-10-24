"""
Structured validation issues: logged as JSON (Pipeline DoD: errors as
structured JSON, not free text) and fed back to the model on retry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

IssueCode = Literal[
    # The output isn't the right shape
    "invalid_json",
    "schema",
    # IDs that downstream stages address must be unique and must exist
    "duplicate_slug",
    "duplicate_section_id",
    "duplicate_content_block_id",
    "flag_reference_missing",
    # Stable IDs across revisions
    "job_id_changed",
    "section_identity_changed",
    "content_block_identity_changed",
    "section_id_regenerated",
    "content_block_id_regenerated",
]


@dataclass(frozen=True)
class ValidationIssue:
    code: IssueCode
    path: str
    """Where in the spec, e.g. "pages[0].sections[1].type". "" = top level."""
    message: str


def format_issues_for_repair(issues: Iterable[ValidationIssue]) -> str:
    """Turn issues into a short list the model can act on during a retry."""
    return "\n".join(f"- [{i.code}] {i.path or '(root)'}: {i.message}" for i in issues)
