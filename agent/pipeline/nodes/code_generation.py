"""
CODE_GENERATION node: design spec -> a built, running demo of the site template.

Local, one-laptop flow (no deploy yet). Inside the job folder:

    design-spec.json   the spec DESIGN produced
    site/              a fresh clone of the template's committed HEAD
    build.log          output of clone, npm ci, and scripts/build_site_from_spec.sh
    server.log         output of `next start`
    server.pid         "<pid> <start time>" of the demo server, so a rerun can stop it

Steps: stop this job's previous server, re-clone, record the template commit,
`npm ci`, build from the spec, start `next start` on a free port in its own
session (so it never holds the caller's pipes open), and wait until it answers.

npm and Next run with a minimal environment: the caller's environment can hold
the platform's DATABASE_URL, and a demo must never write to that database.

Any failed step raises BuildError with the tail of build.log.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from pipeline.contracts import validate_state_for_stage
from pipeline.state import CodeGenerationOutput, PipelineState, StageEnum

BUILD_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build_site_from_spec.sh"
SERVER_READY_TIMEOUT_SECONDS = 60.0

# (argv, cwd, env, log) -> None; raises BuildError on a non-zero exit.
Runner = Callable[[Sequence[str], Path, Mapping[str, str], Path], None]
# (site_dir, port, env, log) -> pid of the started server.
Server = Callable[[Path, int, Mapping[str, str], Path], int]


class BuildError(RuntimeError):
    pass


def site_env() -> Dict[str, str]:
    """Only what npm and Next need. Never the caller's DATABASE_URL or secrets."""
    env = {key: os.environ[key] for key in ("PATH", "HOME") if key in os.environ}
    env["NEXT_TELEMETRY_DISABLED"] = "1"
    return env


def _tail(log: Path, lines: int = 30) -> str:
    try:
        return "\n".join(log.read_text(errors="replace").splitlines()[-lines:])
    except OSError:
        return ""


def run_command(argv: Sequence[str], cwd: Path, env: Mapping[str, str], log: Path) -> None:
    with log.open("a") as out:
        out.write(f"\n$ {' '.join(argv)}\n")
        out.flush()
        code = subprocess.run(list(argv), cwd=cwd, env=dict(env), stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT).returncode
    if code != 0:
        raise BuildError(f"`{' '.join(argv)}` exited {code}. Last lines of {log}:\n{_tail(log)}")


def start_server(site: Path, port: int, env: Mapping[str, str], log: Path) -> int:
    """`next start` detached: own session, no inherited pipes, output to a file."""
    with log.open("a") as out:
        process = subprocess.Popen(
            [str(site / "node_modules" / ".bin" / "next"), "start", "-p", str(port)],
            cwd=site,
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return process.pid


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def started_at(pid: int) -> Optional[str]:
    """The process's start time as `ps` prints it, or None when no such process is running.
    pid plus start time identifies a process; a pid alone can be reused after a reboot."""
    result = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def stop_previous_server(job_dir: Path) -> None:
    """Stop the server this job started last time, but only if that pid is still
    the same process (same start time). Next renames its process to `next-server`,
    so the command line cannot identify it."""
    pid_file = job_dir / "server.pid"
    try:
        pid_text, recorded_start = pid_file.read_text().strip().split(" ", 1)
        pid = int(pid_text)
    except (OSError, ValueError):
        pid_file.unlink(missing_ok=True)
        return
    if started_at(pid) == recorded_start:
        try:
            os.killpg(pid, signal.SIGTERM)  # the server is its own session leader
        except ProcessLookupError:
            pass
    pid_file.unlink(missing_ok=True)


def wait_until_up(url: str, pid: int, timeout: float = SERVER_READY_TIMEOUT_SECONDS) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if started_at(pid) is None:
            raise BuildError(f"the demo server exited before answering on {url}")
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except urllib.error.HTTPError:
            return  # it answered; a 404 or 500 page is still a running server
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    raise BuildError(f"the demo server did not answer on {url} within {timeout:.0f}s")


def template_commit(site: Path) -> str:
    return subprocess.run(["git", "-C", str(site), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()


def run_code_generation(
    state: PipelineState,
    job_dir: Path,
    template_source: str,
    run: Runner = run_command,
    serve: Server = start_server,
    wait: Callable[[str, int], None] = wait_until_up,
    commit_of: Callable[[Path], str] = template_commit,
) -> Dict[str, Any]:
    """Returns {"code_generation_output": ...} with the demo's URL. Raises BuildError on any failed step."""
    validate_state_for_stage(StageEnum.CODE_GENERATION, state)
    assert state.design_output is not None and state.design_output.design_spec is not None

    job_dir.mkdir(parents=True, exist_ok=True)
    site = job_dir / "site"
    log = job_dir / "build.log"
    log.write_text("")
    env = site_env()

    stop_previous_server(job_dir)
    shutil.rmtree(site, ignore_errors=True)
    spec_path = job_dir / "design-spec.json"
    spec_path.write_text(json.dumps(state.design_output.design_spec, indent=2) + "\n")

    run(["git", "clone", "--quiet", template_source, str(site)], job_dir, env, log)
    commit = commit_of(site)
    run(["npm", "ci", "--no-audit", "--no-fund"], site, env, log)
    run(["bash", str(BUILD_SCRIPT), str(spec_path), str(site)], site, env, log)

    port = free_port()
    pid = serve(site, port, env, job_dir / "server.log")
    (job_dir / "server.pid").write_text(f"{pid} {started_at(pid) or ''}\n")
    url = f"http://localhost:{port}"
    wait(url, pid)

    return {
        "code_generation_output": CodeGenerationOutput(
            repo_url=str(site), preview_url=url, template_commit=commit, test_results={"build": "passed"}
        )
    }


__all__: Sequence[str] = ("BuildError", "run_code_generation", "site_env", "stop_previous_server")
