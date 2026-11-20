"""
DESIGN node: Stage 1 intake -> validated design-spec.json for the site template.

Flow:
  1. Check the stage contract (intake_output present).
  2. Read the intake and its notes from ``intake_output.project_spec``
     (written with ``template_spec.intake_mapping.to_project_spec``). Any
     other shape flags the job for human review.
  3. BUI-71: if the intake has a logo but no brand colors, fill brand_colors
     from the logo. The colors are fetched once per logo URL and reused on
     reruns; a logo that cannot be read adds a ``logo_unreadable`` flag.
  4. Ask the model for the whole spec and validate it against the template's
     contract, with one repair round (``template_spec.generate``). Reviewer
     notes always go into the prompt. On a rerun the previous spec does too,
     and the new spec keeps the previous section ids.
  5. Write the spec and its source log to state. After the retry budget is
     exhausted the job is flagged for human review instead.

The model call is injectable (``provider``) so tests run without a network.
The default uses the DESIGN node config from pipeline/config.py.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

from pipeline.config import get_node_config
from pipeline.contracts import validate_state_for_stage
from pipeline.state import DesignOutput, PipelineState, ReviewFlag, ReviewReason, StageEnum
from pipeline.template_spec.generate import generate_design_spec
from pipeline.template_spec.intake_mapping import from_project_spec
from pipeline.template_spec.logo_palette import FetchAsset, logo_palette_for
from pipeline.template_spec.prompt import FLAG_LOGO_UNREADABLE
from pipeline.template_spec.provider import SpecProvider, anthropic_provider
from pipeline.template_spec.sources import AssumptionLink, build_source_log

MAX_LOGO_BYTES = 10 * 1024 * 1024  # the intake form's upload limit
LOGO_FETCH_TIMEOUT_SECONDS = 10.0


async def fetch_https_asset(
    url: str, *, transport: Optional[httpx.AsyncBaseTransport] = None
) -> Tuple[bytes, Optional[str]]:
    """Default asset fetcher: a direct https URL only, no redirects (so the
    scheme rule holds past the first hop), one total deadline, and a 10 MB cap
    enforced while streaming. Private-bucket access (supabase://) is BUI-93."""
    if not url.lower().startswith("https://"):
        raise ValueError(f"asset URL must use https: {url}")
    chunks: List[bytes] = []
    received = 0
    async with asyncio.timeout(LOGO_FETCH_TIMEOUT_SECONDS):
        async with httpx.AsyncClient(
            timeout=LOGO_FETCH_TIMEOUT_SECONDS, follow_redirects=False, transport=transport
        ) as client:
            async with client.stream("GET", url) as response:
                if not 200 <= response.status_code < 300:
                    raise ValueError(f"asset fetch returned HTTP {response.status_code}: {url}")
                declared = response.headers.get("content-length")
                if declared is not None and int(declared) > MAX_LOGO_BYTES:
                    raise ValueError(f"asset declares {declared} bytes, over the {MAX_LOGO_BYTES} byte cap: {url}")
                async for chunk in response.aiter_bytes():
                    received += len(chunk)
                    if received > MAX_LOGO_BYTES:
                        raise ValueError(f"asset exceeds {MAX_LOGO_BYTES} bytes: {url}")
                    chunks.append(chunk)
                content_type = response.headers.get("content-type")
    return b"".join(chunks), content_type


def _review_flag(notes: str) -> Dict[str, Any]:
    return {
        "review_flag": ReviewFlag(
            reason=ReviewReason.STAGE_ERROR_THRESHOLD, flagged_by_stage=StageEnum.DESIGN, reviewer_notes=notes
        )
    }


async def run_design(
    state: PipelineState,
    provider: Optional[SpecProvider] = None,
    fetch_asset: Optional[FetchAsset] = None,
) -> Dict[str, Any]:
    """Returns {"design_output": ...} on success, {"review_flag": ...} when the
    intake cannot be read or the retry budget is exhausted (append-only state contract)."""
    validate_state_for_stage(StageEnum.DESIGN, state)
    assert state.intake_output is not None  # guaranteed by the contract
    try:
        intake, notes = from_project_spec(state.intake_output.project_spec)
    except ValueError as exc:  # includes pydantic's ValidationError
        return _review_flag(f"DESIGN could not read intake_output.project_spec (expected {{intake, notes}}):\n{exc}")

    before = state.design_output if state.design_output is not None and state.design_output.design_spec is not None else None
    revision = before.revision + 1 if before is not None else 1

    brand_colors_source: Optional[str] = "intake" if intake.brand_colors else None
    logo_colors: Optional[Dict[str, Any]] = None
    logo_failure: Optional[str] = None
    if intake.logo is not None and not intake.brand_colors:
        if before is not None and before.logo_colors is not None and before.logo_colors["url"] == intake.logo:
            logo_colors = before.logo_colors  # same logo as last revision: same colors, no second fetch
        else:
            palette = await logo_palette_for(intake.logo, fetch_asset if fetch_asset is not None else fetch_https_asset)
            if palette.primary is not None:
                colors = [palette.primary] + ([palette.secondary] if palette.secondary is not None else [])
                logo_colors = {"url": intake.logo, "colors": colors}
            else:
                logo_failure = palette.failure
        if logo_colors is not None:
            intake = intake.model_copy(update={"brand_colors": list(logo_colors["colors"])})
            brand_colors_source = "logo"

    config = get_node_config(StageEnum.DESIGN.value)
    result = await generate_design_spec(
        intake,
        notes,
        state.job_id,
        provider if provider is not None else anthropic_provider(),
        max_attempts=int(config.max_retries) + 1,
        previous=before.design_spec if before is not None else None,
        previous_assumptions=[AssumptionLink(text=str(a["text"]), field=a["field"]) for a in before.assumptions] if before is not None else (),
        reviewer_notes=state.reviewer_notes,
    )

    if result.spec is None:
        return _review_flag(
            f"DESIGN produced no valid design spec in {result.attempts} attempts:\n"
            + "\n".join(f"- {issue}" for issue in result.issues)
        )

    spec = result.spec
    if logo_failure is not None:
        spec["flags"].append(
            {"code": FLAG_LOGO_UNREADABLE, "detail": f"the logo could not be used to pick brand colors ({logo_failure}); the palette was chosen without it"}
        )
    return {
        "design_output": DesignOutput(
            page_map={
                page["slug"]: [{"id": section["id"], "type": section["type"]} for section in page["sections"]]
                for page in spec["pages"]
            },
            component_patterns=sorted({section["type"] for page in spec["pages"] for section in page["sections"]}),
            design_spec=spec,
            revision=revision,
            brand_colors_source=brand_colors_source,
            logo_colors=logo_colors,
            assumptions=[{"text": link.text, "field": link.field} for link in result.assumptions],
            source_log=build_source_log(
                spec,
                intake,
                result.assumptions,
                brand_colors_source=brand_colors_source,
                revision=revision,
                previous_log=before.source_log if before is not None else (),
            ),
        )
    }


__all__: Sequence[str] = ("FetchAsset", "MAX_LOGO_BYTES", "SpecProvider", "fetch_https_asset", "run_design")
