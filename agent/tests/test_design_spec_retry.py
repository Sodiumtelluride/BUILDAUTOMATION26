"""D20: on failure, retry this node alone, then flag for human review."""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Sequence

import pytest

from pipeline.design_spec import (
    DesignSpec,
    GenerateAttempt,
    NeedsHumanReview,
    SpecAccepted,
    ValidationIssue,
    generate_validated_spec,
)

MakeSpec = Callable[[], Dict[str, Any]]


async def test_returns_spec_on_first_valid_attempt(make_spec: MakeSpec) -> None:
    calls: List[GenerateAttempt] = []

    async def generate(a: GenerateAttempt) -> object:
        calls.append(a)
        return json.dumps(make_spec())

    result = await generate_validated_spec(generate, max_retries=2)
    assert isinstance(result, SpecAccepted)
    assert result.attempts == 1
    assert len(calls) == 1


async def test_retries_with_previous_issues_then_succeeds(make_spec: MakeSpec) -> None:
    seen: List[GenerateAttempt] = []

    async def generate(a: GenerateAttempt) -> object:
        seen.append(a)
        return "{ not json" if a.attempt == 1 else make_spec()

    result = await generate_validated_spec(generate, max_retries=2)
    assert isinstance(result, SpecAccepted)
    assert result.attempts == 2
    assert list(seen[0].previous_issues) == []
    assert [i.code for i in seen[1].previous_issues] == ["invalid_json"]


async def test_flags_for_human_review_after_the_limit(make_spec: MakeSpec) -> None:
    bad = make_spec()
    bad["notes"] = "free text"
    logged: List[int] = []

    async def generate(a: GenerateAttempt) -> object:
        return bad

    def on_attempt(attempt: int, issues: Sequence[ValidationIssue]) -> None:
        logged.append(attempt)

    result = await generate_validated_spec(generate, max_retries=2, on_attempt=on_attempt)
    assert isinstance(result, NeedsHumanReview)
    assert result.attempts == 3
    assert logged == [1, 2, 3]
    assert [i.code for i in result.issues] == ["schema"]
    assert not hasattr(result, "spec")  # an invalid spec is never handed back to be written


async def test_retry_limit_comes_from_design_node_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_DESIGN_MAX_RETRIES", "1")

    async def generate(a: GenerateAttempt) -> object:
        return "nope"

    result = await generate_validated_spec(generate)
    assert result.attempts == 2


async def test_infrastructure_errors_are_not_retried_here() -> None:
    calls = 0

    async def generate(a: GenerateAttempt) -> object:
        nonlocal calls
        calls += 1
        raise RuntimeError("provider 529")

    with pytest.raises(RuntimeError, match="provider 529"):
        await generate_validated_spec(generate, max_retries=2)
    assert calls == 1


async def test_rerun_with_unstable_ids_is_retried_then_flagged(make_spec: MakeSpec) -> None:
    previous = DesignSpec.model_validate(make_spec())
    regenerated = make_spec()
    regenerated["pages"][0]["sections"][1]["id"] = "programs-grid-2"

    async def generate(a: GenerateAttempt) -> object:
        return regenerated

    result = await generate_validated_spec(generate, previous=previous, max_retries=0)
    assert isinstance(result, NeedsHumanReview)
    assert "section_id_regenerated" in [i.code for i in result.issues]
