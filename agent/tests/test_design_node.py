"""The DESIGN node end to end with a fake model: first run, logo colors, rerun, and the human-review flag."""

from __future__ import annotations

import asyncio
import copy
import io
import json
import pathlib
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import httpx
import pytest
from PIL import Image

from pipeline.nodes import design
from pipeline.nodes.design import MAX_LOGO_BYTES, fetch_https_asset, run_design
from pipeline.state import IntakeOutput, PipelineState, ReviewReason, StageEnum
from pipeline.template_spec.generate import parse_spec_text
from pipeline.template_spec.intake_mapping import from_project_spec, map_intake_answers, to_project_spec
from pipeline.template_spec.validate import validate_template_spec

FIX = pathlib.Path(__file__).parent / "fixtures"
RAW: Dict[str, Any] = json.loads((FIX / "intake_answers_complete.json").read_text())
REPLY: Dict[str, Any] = json.loads((FIX / "template_design_reply_valid.json").read_text())
LOGO_URL = "https://assets.build-umass.org/jobs/a1b2c3d4/logo_green.png"


def _state(**intake_update: Any) -> PipelineState:
    intake, notes = map_intake_answers(RAW["answers"], RAW["attachments"])
    intake = intake.model_copy(update=intake_update)
    return PipelineState(org_id=uuid.uuid4(), intake_output=IntakeOutput(project_spec=to_project_spec(intake, notes)))


def _provider(*replies: Dict[str, Any]) -> Tuple[Any, List[str]]:
    """A fake model that returns the given replies in order (the last one repeats) and records the user messages."""
    seen: List[str] = []

    async def provide(system: str, user: str) -> str:
        seen.append(user)
        return json.dumps(replies[min(len(seen), len(replies)) - 1])

    return provide, seen


def _row(log: List[Dict[str, Any]], target: str) -> Dict[str, Any]:
    return [row for row in log if row["target"] == target][-1]


async def test_first_run_writes_a_template_valid_spec_and_its_source_log() -> None:
    state = _state()
    provider, _ = _provider(REPLY)
    result = await run_design(state, provider)
    assert set(result) == {"design_output"}
    out = result["design_output"]
    assert validate_template_spec(out.design_spec) == [] and out.design_spec["job_id"] == str(state.job_id)
    assert out.revision == 1 and out.brand_colors_source == "intake"
    assert out.page_map["/"][0] == {"id": "hero-1", "type": "hero-bold"}
    assert "hero-bold" in out.component_patterns
    assert _row(out.source_log, "tokens.colors.primary")["source"] == "intake"


async def test_exhausted_retries_flag_the_job_for_human_review() -> None:
    bad = copy.deepcopy(REPLY)
    bad["tokens"]["fonts"]["body"] = "Instrument Serif"
    provider, seen = _provider(bad)
    result = await run_design(_state(), provider)
    assert set(result) == {"review_flag"} and len(seen) == 2
    flag = result["review_flag"]
    assert flag.reason == ReviewReason.STAGE_ERROR_THRESHOLD and flag.flagged_by_stage == StageEnum.DESIGN
    assert "2 attempts" in flag.reviewer_notes and "tokens.fonts.body: must be Inter" in flag.reviewer_notes


async def test_rerun_sends_the_previous_spec_and_notes_and_keeps_section_ids() -> None:
    state = _state()
    provider, _ = _provider(REPLY)
    first = (await run_design(state, provider))["design_output"]

    revised = copy.deepcopy(REPLY)
    revised["tokens"]["radius"] = "0.5rem"
    stats = next(s for s in revised["pages"][0]["sections"] if s["id"] == "stats-1")
    stats["id"] = "stats-99"  # the model regenerated an id it should have kept
    provider, seen = _provider(revised)
    rerun_state = state.model_copy(update={"design_output": first, "reviewer_notes": "Make the corners less round."})
    second = (await run_design(rerun_state, provider))["design_output"]

    assert "This is a revision" in seen[0] and "Make the corners less round." in seen[0] and '"stats-1"' in seen[0]
    assert '"field": "brand_colors"' in seen[0], "the previous spec is shown in the shape the reply must have"
    assert len(seen) == 1, "an unambiguous id is fixed in code, not with a retry"
    assert second.revision == 2
    assert [s["id"] for s in second.design_spec["pages"][0]["sections"]] == [s["id"] for s in first.design_spec["pages"][0]["sections"]]
    assert second.source_log[: len(first.source_log)] == first.source_log
    assert [(row["target"], row["revision"]) for row in second.source_log[len(first.source_log) :]] == [("tokens.radius", 2)]


async def test_rerun_with_an_id_reused_for_another_type_is_flagged() -> None:
    state = _state()
    provider, _ = _provider(REPLY)
    first = (await run_design(state, provider))["design_output"]
    revised = copy.deepcopy(REPLY)
    home = revised["pages"][0]["sections"]
    stats = next(s for s in home if s["id"] == "stats-1")
    cta = next(s for s in home if s["id"] == "cta-1")
    stats["id"], cta["id"] = "cta-1", "stats-1"  # ids swapped between two different section types
    provider, seen = _provider(revised)
    result = await run_design(state.model_copy(update={"design_output": first}), provider)
    assert set(result) == {"review_flag"} and len(seen) == 2
    assert "an id keeps its type and page" in seen[1], "the retry message names the problem"


def _green_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (0x2E, 0x7D, 0x32)).save(buf, format="PNG")
    return buf.getvalue()


async def test_logo_fills_brand_colors_only_when_none_were_given() -> None:
    fetched: List[str] = []

    async def fetch(url: str) -> Tuple[bytes, Optional[str]]:
        fetched.append(url)
        return _green_png(), "image/png"

    provider, seen = _provider(REPLY)
    out = (await run_design(_state(brand_colors=[], logo=LOGO_URL), provider, fetch))["design_output"]
    assert fetched == [LOGO_URL] and out.brand_colors_source == "logo"
    assert '"#2E7D32"' in seen[0], "the logo color reaches the prompt as a brand color"
    primary = _row(out.source_log, "tokens.colors.primary")
    assert (primary["source"], primary["fields"]) == ("logo", ["logo"])

    fetched.clear()
    out = (await run_design(_state(logo=LOGO_URL), provider, fetch))["design_output"]
    assert fetched == [] and out.brand_colors_source == "intake"


async def test_a_failed_logo_fetch_leaves_the_colors_to_the_model() -> None:
    async def fetch(url: str) -> Tuple[bytes, Optional[str]]:
        raise ValueError("boom")

    provider, _ = _provider(REPLY)
    out = (await run_design(_state(brand_colors=[], logo=LOGO_URL), provider, fetch))["design_output"]
    assert out.brand_colors_source is None and out.logo_colors is None
    assert _row(out.source_log, "tokens.colors.primary")["source"] == "claude"
    flags = [f for f in out.design_spec["flags"] if f["code"] == "logo_unreadable"]
    assert len(flags) == 1 and "fetch_failed" in flags[0]["detail"], "the reviewer is told the logo was not read"
    assert validate_template_spec(out.design_spec) == []
    assert _row(out.source_log, "flags.logo_unreadable[0]")["fields"] == ["logo"]


async def test_an_uploaded_supabase_logo_is_flagged_by_the_default_fetcher() -> None:
    provider, _ = _provider(REPLY)
    out = (await run_design(_state(brand_colors=[], logo="supabase://intake-private/job/logo.png"), provider))["design_output"]
    assert [f["code"] for f in out.design_spec["flags"]].count("logo_unreadable") == 1


async def test_rerun_reuses_logo_colors_until_the_logo_changes() -> None:
    fetched: List[str] = []

    async def fetch(url: str) -> Tuple[bytes, Optional[str]]:
        fetched.append(url)
        if len(fetched) > 1:
            raise ValueError("storage is down")
        return _green_png(), "image/png"

    provider, _ = _provider(REPLY)
    state = _state(brand_colors=[], logo=LOGO_URL)
    first = (await run_design(state, provider, fetch))["design_output"]
    assert first.logo_colors == {"url": LOGO_URL, "colors": ["#2E7D32"]}

    second = (await run_design(state.model_copy(update={"design_output": first}), provider, fetch))["design_output"]
    assert fetched == [LOGO_URL], "same logo: no second fetch, so a storage outage cannot change the colors"
    assert second.brand_colors_source == "logo" and second.source_log == first.source_log

    new_logo = LOGO_URL.replace("logo_green", "logo_v2")
    changed = _state(brand_colors=[], logo=new_logo).model_copy(update={"design_output": second})
    third = (await run_design(changed, provider, fetch))["design_output"]
    assert fetched == [LOGO_URL, new_logo], "a new logo is fetched again"
    assert third.logo_colors is None and third.brand_colors_source is None


async def test_a_model_that_copies_the_previous_spec_unchanged_passes_first_try() -> None:
    """Guards the prompt against drifting from the reply contract (the previous spec is pasted in reply shape)."""
    state = _state()
    provider, _ = _provider(REPLY)
    first = (await run_design(state, provider))["design_output"]
    seen: List[str] = []

    async def echo(system: str, user: str) -> str:
        seen.append(user)
        tail = user.split("The previous spec for this job:\n", 1)[1]
        return json.dumps(json.JSONDecoder().raw_decode(tail)[0])

    second = (await run_design(state.model_copy(update={"design_output": first}), echo))["design_output"]
    assert len(seen) == 1 and second.design_spec == first.design_spec and second.source_log == first.source_log
    assert parse_spec_text(seen[0].split("The previous spec for this job:\n", 1)[1].split("\n\nReviewer notes:")[0])["assumptions"] == REPLY["assumptions"]


async def test_reviewer_notes_reach_the_prompt_even_without_a_previous_spec() -> None:
    provider, seen = _provider(REPLY)
    state = _state().model_copy(update={"reviewer_notes": "Use the serif heading font."})
    out = (await run_design(state, provider))["design_output"]
    assert out.revision == 1 and "Reviewer notes:\nUse the serif heading font." in seen[0] and "This is a revision" not in seen[0]


async def test_an_unreadable_project_spec_flags_the_job_instead_of_crashing() -> None:
    old_shape = {"site_title": "Pioneer Valley Food Bank", "pages": ["home"], "brand": {"primary_color": "#2E7D32"}}
    state = PipelineState(org_id=uuid.uuid4(), intake_output=IntakeOutput(project_spec=old_shape))
    result = await run_design(state, _provider(REPLY)[0])
    assert set(result) == {"review_flag"}
    assert "could not read intake_output.project_spec" in result["review_flag"].reviewer_notes


async def test_the_intake_complete_fixture_is_design_ready() -> None:
    state = PipelineState.model_validate_json((FIX / "intake_complete.json").read_text())
    assert state.intake_output is not None
    from_project_spec(state.intake_output.project_spec)  # raises if the fixture drifts from the shape DESIGN reads
    assert set(await run_design(state, _provider(REPLY)[0])) == {"design_output"}


async def test_https_fetcher_returns_body_and_content_type() -> None:
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, content=b"png-bytes", headers={"content-type": "image/png"})
    )
    assert await fetch_https_asset(LOGO_URL, transport=transport) == (b"png-bytes", "image/png")


async def test_https_fetcher_rejects_non_https_schemes() -> None:
    for url in ("http://example.org/logo.png", "supabase://bucket/logo.png", "s3://bucket/logo.png", "file:///etc/passwd"):
        with pytest.raises(ValueError):
            await fetch_https_asset(url)


async def test_https_fetcher_rejects_error_status() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(404, content=b"<html>Not Found</html>"))
    with pytest.raises(ValueError):
        await fetch_https_asset(LOGO_URL, transport=transport)


async def test_https_fetcher_rejects_oversized_body() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=b"x" * (MAX_LOGO_BYTES + 1)))
    with pytest.raises(ValueError):
        await fetch_https_asset(LOGO_URL, transport=transport)


async def test_https_fetcher_rejects_a_declared_oversize_before_reading_the_body() -> None:
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, content=b"tiny", headers={"content-length": str(MAX_LOGO_BYTES + 1)})
    )
    with pytest.raises(ValueError):
        await fetch_https_asset(LOGO_URL, transport=transport)


async def test_https_fetcher_does_not_follow_redirects() -> None:
    requested: List[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.scheme == "https":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})
        return httpx.Response(200, content=b"internal")

    with pytest.raises(ValueError):
        await fetch_https_asset(LOGO_URL, transport=httpx.MockTransport(handler))
    assert requested == [LOGO_URL]


class _Trickle(httpx.AsyncByteStream):
    """A body that never finishes: one byte, then a long pause, forever."""

    async def __aiter__(self) -> AsyncIterator[bytes]:
        while True:
            yield b"x"
            await asyncio.sleep(0.2)


async def test_https_fetcher_enforces_a_total_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(design, "LOGO_FETCH_TIMEOUT_SECONDS", 0.05)
    transport = httpx.MockTransport(lambda req: httpx.Response(200, stream=_Trickle()))
    with pytest.raises(TimeoutError):
        await fetch_https_asset(LOGO_URL, transport=transport)
