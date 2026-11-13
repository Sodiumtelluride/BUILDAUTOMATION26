"""
One unattended run: stored intake blob on stdin -> a running demo site.

    python -m pipeline.run --job-dir <dir> [--provider ollama|anthropic|mock (default: $AGENT_PROVIDER or ollama)] [--template <git source>] < notes.json

stdin is the JSON the intake API stores in intake_submissions.notes. The run
always ends by writing ``<job-dir>/result.json`` (atomically), whatever
happens, and prints the same JSON as one line:

    {"status": "succeeded", "url": "http://localhost:PORT", "template_commit": "...", "flags": [...], "finished_at": "..."}
    {"status": "failed", "error": "...", "finished_at": "..."}

The admin console reads result.json to finish the intake row, so it does not
need to stay attached to this process. ``state.json`` keeps the final
pipeline state (spec, source log) for debugging.

Exit codes: 0 succeeded, 1 failed, 2 usage.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import traceback
import uuid
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from pipeline.graph import build_graph
from pipeline.nodes.code_generation import BuildError, run_code_generation
from pipeline.state import PipelineState
from pipeline.template_spec.provider import provider_named

DEFAULT_TEMPLATE = Path(__file__).resolve().parents[3] / "BUILD_TEMPLATE_REPO"


def write_result(job_dir: Path, result: Dict[str, Any]) -> None:
    result = {**result, "finished_at": datetime.now(timezone.utc).isoformat()}
    tmp = job_dir / "result.json.tmp"
    tmp.write_text(json.dumps(result, indent=2) + "\n")
    os.replace(tmp, job_dir / "result.json")
    print(json.dumps(result), flush=True)


def outcome(state: PipelineState) -> Dict[str, Any]:
    """result.json fields for a graph run that finished without raising."""
    if state.review_flag is not None:
        return {"status": "failed", "error": state.review_flag.reviewer_notes or state.review_flag.reason.value}
    built = state.code_generation_output
    if built is None or built.preview_url is None:
        return {"status": "failed", "error": "the run ended without a demo URL"}
    spec = state.design_output.design_spec if state.design_output is not None else None
    return {
        "status": "succeeded",
        "url": built.preview_url,
        "template_commit": built.template_commit,
        "flags": list((spec or {}).get("flags", [])),
    }


async def run(blob: Dict[str, Any], job_dir: Path, provider_name: str, template: str) -> Dict[str, Any]:
    state = PipelineState(
        job_id=uuid.UUID(blob["jobId"]) if blob.get("jobId") else uuid.uuid4(),
        org_id=uuid.UUID(blob["organizationId"]) if blob.get("organizationId") else uuid.uuid4(),
        raw_form_payload=blob,
    )
    graph = build_graph(provider_named(provider_name), partial(run_code_generation, job_dir=job_dir, template_source=template))
    final = PipelineState.model_validate(await graph.ainvoke(state))
    (job_dir / "state.json").write_text(final.model_dump_json(indent=2) + "\n")
    return outcome(final)


def main(argv: Sequence[str], stdin_text: Optional[str] = None) -> int:
    p = argparse.ArgumentParser(prog="python -m pipeline.run", description=__doc__.split("\n\n")[0] if __doc__ else None)
    p.add_argument("--job-dir", required=True, type=Path)
    p.add_argument("--provider", choices=["ollama", "anthropic", "mock"], default=os.environ.get("AGENT_PROVIDER", "ollama"))
    p.add_argument("--template", default=os.environ.get("BUILD_TEMPLATE_SOURCE", str(DEFAULT_TEMPLATE)))
    args = p.parse_args(argv)

    job_dir: Path = args.job_dir.resolve()
    job_dir.mkdir(parents=True, exist_ok=True)
    try:
        blob = json.loads(stdin_text if stdin_text is not None else sys.stdin.read())
        result = asyncio.run(run(blob, job_dir, args.provider, args.template))
    except BuildError as exc:
        result = {"status": "failed", "error": str(exc)}
    except Exception as exc:  # the run must always leave a result.json behind
        traceback.print_exc()
        result = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    write_result(job_dir, result)
    return 0 if result["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
