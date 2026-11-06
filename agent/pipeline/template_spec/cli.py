"""
Intake answers -> design-spec.json, from the command line.

    python -m pipeline.template_spec.cli --answers <stored intake blob> --out design-spec.json
        [--provider mock|anthropic] [--mock-spec <file>] [--job-id <uuid>]
    python -m pipeline.template_spec.cli --answers <blob> --print-prompt <dir>   # system.md + user.md to paste by hand
    python -m pipeline.template_spec.cli --answers <blob> --validate <spec.json>

Exit codes: 0 valid, 1 invalid spec or bad input, 2 usage.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Sequence

from .catalog import load_catalog
from .generate import generate_design_spec, requested_slugs
from .intake_mapping import map_intake_answers
from .prompt import render_system_prompt, render_user_message
from .provider import DEFAULT_MOCK_SPEC, SpecProvider, anthropic_provider, mock_provider
from .validate import validate_template_spec


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m pipeline.template_spec.cli", description=__doc__.split("\n\n")[0])
    p.add_argument("--answers", required=True, help="the stored intake blob: {version, answers, attachments, jobId}")
    p.add_argument("--out", help="where to write design-spec.json")
    p.add_argument("--provider", choices=["mock", "anthropic"], default="mock")
    p.add_argument("--mock-spec", type=Path, default=DEFAULT_MOCK_SPEC, help="file the mock provider replies with")
    p.add_argument("--job-id", type=uuid.UUID, help="defaults to the blob's jobId, else a new uuid4")
    p.add_argument("--print-prompt", metavar="DIR", help="write system.md and user.md here and exit")
    p.add_argument("--validate", metavar="FILE", help="validate an existing spec against the intake and exit")
    return p


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


def main(argv: Sequence[str]) -> int:
    args = _parser().parse_args(argv)
    try:
        blob: Dict[str, Any] = json.loads(Path(args.answers).read_text())
        intake, notes = map_intake_answers(blob["answers"], blob.get("attachments", []))
    except (OSError, ValueError, KeyError) as exc:
        return _fail(f"cannot read intake answers from {args.answers}: {exc}")

    if args.validate:
        try:
            spec = json.loads(Path(args.validate).read_text())
        except (OSError, ValueError) as exc:
            return _fail(f"cannot read {args.validate}: {exc}")
        issues = validate_template_spec(spec, requested_slugs=requested_slugs(intake))
        for issue in issues:
            print(issue)
        print("valid" if not issues else f"{len(issues)} issue(s)")
        return 1 if issues else 0

    job_id = args.job_id or (uuid.UUID(blob["jobId"]) if blob.get("jobId") else uuid.uuid4())

    if args.print_prompt:
        out_dir = Path(args.print_prompt)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "system.md").write_text(render_system_prompt(load_catalog()) + "\n")
        (out_dir / "user.md").write_text(render_user_message(intake, notes, job_id) + "\n")
        print(f"wrote {out_dir / 'system.md'} and {out_dir / 'user.md'} (job id {job_id})")
        return 0

    if not args.out:
        _parser().print_usage(sys.stderr)
        return _fail("--out is required unless --print-prompt or --validate is given")
    out = Path(args.out)
    if not out.parent.is_dir():
        return _fail(f"output directory does not exist: {out.parent}")

    provider: SpecProvider = mock_provider(args.mock_spec) if args.provider == "mock" else anthropic_provider()
    result = asyncio.run(generate_design_spec(intake, notes, job_id, provider))
    if result.spec is None:
        for issue in result.issues:
            print(issue)
        print(f"no valid spec after {result.attempts} attempt(s)")
        return 1
    out.write_text(json.dumps(result.spec, indent=2) + "\n")
    print(f"wrote {out} (job id {job_id}, {result.attempts} attempt(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
