"""
DESIGN node (BUI-64/65/66): Stage 1 intake -> validated design_spec.

Flow:
  1. Check the stage contract (intake_output present).
  2. Parse ``intake_output.project_spec`` against the frozen Stage 1 schema.
  2b. If the intake has a logo but no brand colors, fetch the logo (https
     only) and derive a palette from it, once per run (D8).
  3. Ask the model for a LayoutPlan: catalog section types per requested
     page, each pick citing its intake fields.
  4. Deterministically assemble the full design_spec (tokens, page map,
     content blocks from catalog slots, flags, D5 decision log).
  5. Validate with the D20 retry loop; only an accepted spec is written to
     state. On exhausted retries the job is flagged for human review.

The model call (``generate_plan``) and the asset fetch (``fetch_asset``) are
injectable so tests run without a provider or network. The default uses the DESIGN node config from pipeline/config.py.
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Dict, Mapping, Optional, Sequence, Tuple

import httpx

from pipeline.config import get_node_config
from pipeline.contracts import validate_state_for_stage
from pipeline.design_spec import (
    DesignSpec,
    GenerateAttempt,
    SpecAccepted,
    format_issues_for_repair,
    generate_validated_spec,
)
from pipeline.design_spec.generation import (
    LayoutPlan,
    assemble_design_spec,
    build_generation_input,
    render_plan_prompt,
    requested_slugs,
)
from pipeline.design_spec.intake import parse_design_intake
from pipeline.design_spec.logo_palette import FetchAsset, LogoPalette, logo_palette_for
from pipeline.state import DesignOutput, PipelineState, ReviewFlag, ReviewReason, StageEnum

# Returns the model's raw layout plan: a LayoutPlan, a dict, or a JSON string.
GeneratePlan = Callable[[GenerateAttempt, Mapping[str, Any]], Awaitable[object]]

MAX_LOGO_BYTES = 10 * 1024 * 1024  # the intake form's upload limit
LOGO_FETCH_TIMEOUT_SECONDS = 10.0


async def fetch_https_asset(
    url: str, *, transport: Optional[httpx.AsyncBaseTransport] = None
) -> Tuple[bytes, Optional[str]]:
    """Default asset fetcher: https only (private-bucket access is BUI-93), 10 s, 10 MB."""
    if not url.lower().startswith("https://"):
        raise ValueError(f"asset URL must use https: {url}")
    async with httpx.AsyncClient(
        timeout=LOGO_FETCH_TIMEOUT_SECONDS, follow_redirects=True, transport=transport
    ) as client:
        response = await client.get(url)
    if not 200 <= response.status_code < 300:
        raise ValueError(f"asset fetch returned HTTP {response.status_code}: {url}")
    if len(response.content) > MAX_LOGO_BYTES:
        raise ValueError(f"asset exceeds {MAX_LOGO_BYTES} bytes: {url}")
    return response.content, response.headers.get("content-type")


async def run_design(
    state: PipelineState,
    generate_plan: Optional[GeneratePlan] = None,
    fetch_asset: Optional[FetchAsset] = None,
) -> Dict[str, Any]:
    """Returns {"design_output": ...} on success, {"review_flag": ...} after
    the retry budget is exhausted (append-only state contract)."""
    validate_state_for_stage(StageEnum.DESIGN, state)
    assert state.intake_output is not None  # guaranteed by the contract
    intake = parse_design_intake(state.intake_output.project_spec)

    # D8: no brand colors but a logo -> derive the palette once, before the retry loop.
    logo_palette: Optional[LogoPalette] = None
    if intake.logo is not None and not intake.brand_colors:
        logo_palette = await logo_palette_for(intake.logo, fetch_asset if fetch_asset is not None else fetch_https_asset)

    previous: Optional[DesignSpec] = None
    if state.design_output is not None and state.design_output.design_spec is not None:
        previous = DesignSpec.model_validate(state.design_output.design_spec)
    revision = max((d.revision for d in previous.decisions), default=0) + 1 if previous else 1

    gen_input = build_generation_input(intake)
    plan_generator = generate_plan if generate_plan is not None else _llm_generate_plan()

    async def generate(attempt: GenerateAttempt) -> object:
        raw = await plan_generator(attempt, gen_input)
        plan = _parse_plan(raw)
        if plan is None:
            # Not a plan at all; let spec validation produce the issues that
            # drive the retry prompt.
            return raw
        return assemble_design_spec(
            state.job_id, intake, plan, previous=previous, revision=revision, logo_palette=logo_palette
        )

    result = await generate_validated_spec(
        generate,
        previous=previous,
        job_id=state.job_id,
        required_slugs=requested_slugs(intake),
    )

    if isinstance(result, SpecAccepted):
        spec = result.spec
        page_map = {
            page.slug: [{"id": section.id, "type": section.type} for section in page.sections]
            for page in spec.pages
        }
        component_patterns = sorted({section.type for page in spec.pages for section in page.sections})
        return {
            "design_output": DesignOutput(
                page_map=page_map,
                component_patterns=component_patterns,
                design_spec=spec.model_dump(mode="json", by_alias=True),
            )
        }

    return {
        "review_flag": ReviewFlag(
            reason=ReviewReason.STAGE_ERROR_THRESHOLD,
            flagged_by_stage=StageEnum.DESIGN,
            reviewer_notes=(
                f"DESIGN produced no valid design_spec in {result.attempts} attempts:\n"
                + format_issues_for_repair(result.issues)
            ),
        )
    }


def _parse_plan(raw: object) -> Optional[LayoutPlan]:
    if isinstance(raw, LayoutPlan):
        return raw
    data: object = raw
    if isinstance(data, (str, bytes)):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return None
    try:
        return LayoutPlan.model_validate(data)
    except ValueError:
        return None


def _llm_generate_plan() -> GeneratePlan:
    """The default plan generator: one model call per attempt, with the
    previous attempt's validation issues folded into the prompt."""
    config = get_node_config(StageEnum.DESIGN.value)

    async def generate(attempt: GenerateAttempt, gen_input: Mapping[str, Any]) -> object:
        from langchain_anthropic import ChatAnthropic  # type: ignore[import-not-found]  # deferred: tests never import a provider

        model = ChatAnthropic(model_name=str(config.model_id), timeout=None, stop=None)
        prompt = render_plan_prompt(gen_input, attempt.previous_issues)
        response = await model.ainvoke(prompt)
        return response.content if isinstance(response.content, str) else json.dumps(response.content)

    return generate


__all__: Sequence[str] = ("FetchAsset", "GeneratePlan", "MAX_LOGO_BYTES", "fetch_https_asset", "run_design")
