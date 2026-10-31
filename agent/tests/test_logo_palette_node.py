"""BUI-71 (D8): the DESIGN node fetches the logo through an injectable fetcher."""

from __future__ import annotations

import asyncio
import io
import uuid
from typing import Any, AsyncIterator, Dict, List, Mapping, Optional, Tuple

import httpx
import pytest
from PIL import Image

from pipeline.design_spec import DesignSpec, validate_design_spec
from pipeline.design_spec.generation import DEFAULT_COLORS
from pipeline.design_spec.validate import Valid
from pipeline.nodes import design
from pipeline.nodes.design import MAX_LOGO_BYTES, fetch_https_asset, run_design
from pipeline.state import IntakeOutput, PipelineState

LOGO_URL = "https://assets.build-umass.org/jobs/a1b2c3d4/logo_green.svg"


def _green_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (0x2E, 0x7D, 0x32)).save(buf, format="PNG")
    return buf.getvalue()


def _spec(result: Dict[str, Any], state: PipelineState) -> DesignSpec:
    assert set(result) == {"design_output"}
    validated = validate_design_spec(result["design_output"].design_spec, expected_job_id=state.job_id)
    assert isinstance(validated, Valid), getattr(validated, "issues", None)
    return validated.spec


async def test_run_design_fetches_logo_only_when_colors_missing(make_intake: Any, make_plan: Any) -> None:
    calls: List[str] = []

    async def fetcher(url: str) -> Tuple[bytes, Optional[str]]:
        calls.append(url)
        return _green_png(), "image/png"

    async def planner(attempt: object, gen_input: Mapping[str, Any]) -> object:
        return make_plan()

    with_colors = PipelineState(org_id=uuid.uuid4(), intake_output=IntakeOutput(project_spec=make_intake()))
    await run_design(with_colors, generate_plan=planner, fetch_asset=fetcher)
    assert calls == []

    intake_dict = make_intake()
    intake_dict["brand_colors"] = []
    without = PipelineState(org_id=uuid.uuid4(), intake_output=IntakeOutput(project_spec=intake_dict))
    spec = _spec(await run_design(without, generate_plan=planner, fetch_asset=fetcher), without)
    assert calls == [intake_dict["logo"]]
    assert spec.tokens.colors["primary"] == "#2E7D32"


async def test_run_design_fetch_error_falls_back_to_defaults(make_intake: Any, make_plan: Any) -> None:
    async def fetcher(url: str) -> Tuple[bytes, Optional[str]]:
        raise ValueError("unsupported scheme")

    async def planner(attempt: object, gen_input: Mapping[str, Any]) -> object:
        return make_plan()

    intake_dict = make_intake()
    intake_dict["brand_colors"] = []
    intake_dict["logo"] = "supabase://intake-uploads/a1b2c3d4/logo.png"
    state = PipelineState(org_id=uuid.uuid4(), intake_output=IntakeOutput(project_spec=intake_dict))
    spec = _spec(await run_design(state, generate_plan=planner, fetch_asset=fetcher), state)
    assert spec.tokens.colors["primary"] == DEFAULT_COLORS["primary"]
    assert any(d.kind == "assumption" and "fetch_failed" in (d.summary or "") for d in spec.decisions)
    assert not [f for f in spec.flags if f.code == "default_design_track"]


async def test_run_design_fetches_once_across_retry_attempts(make_intake: Any, make_plan: Any) -> None:
    calls: List[str] = []
    attempts: List[int] = []

    async def fetcher(url: str) -> Tuple[bytes, Optional[str]]:
        calls.append(url)
        return _green_png(), "image/png"

    async def planner(attempt: object, gen_input: Mapping[str, Any]) -> object:
        attempts.append(1)
        return {"pages": []} if len(attempts) == 1 else make_plan()  # first attempt is invalid

    intake_dict = make_intake()
    intake_dict["brand_colors"] = []
    state = PipelineState(org_id=uuid.uuid4(), intake_output=IntakeOutput(project_spec=intake_dict))
    _spec(await run_design(state, generate_plan=planner, fetch_asset=fetcher), state)
    assert len(attempts) == 2
    assert len(calls) == 1


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
