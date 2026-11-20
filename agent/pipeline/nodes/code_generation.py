"""
CODE_GENERATION node: design spec -> the same site built and running in every
theme family of the template.

Local, one-laptop flow (no deploy yet). Inside the job folder:

    design-spec.json          the spec DESIGN produced (in the family the model chose)
    specs/<family>.json       that spec moved into each family (template_spec.variants)
    template/                 a fresh clone of the template's committed HEAD, with npm ci run once
    sites/<family>/           one clone per family, node_modules copied from template/, built from its spec
    build.log                 output of clone, npm ci, and scripts/build_site_from_spec.sh for every family
    server-<family>.log       output of that family's `next start`
    server.pid                one "<pid> <start time>" line per demo server, so a rerun can stop them

Steps: stop this job's previous servers, re-clone, record the template commit,
`npm ci` once, then per family: clone the local checkout, copy node_modules
(copy-on-write where the file system allows; Turbopack rejects a node_modules
that resolves outside the project), build from the family's spec, start
`next start` on a free port in its own session (so it never holds the caller's
pipes open), and wait until it answers.

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
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from pipeline.contracts import validate_state_for_stage
from pipeline.state import CodeGenerationOutput, PipelineState, StageEnum
from pipeline.template_spec.catalog import load_catalog
from pipeline.template_spec.variants import family_of, specs_in_every_family

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


def stop_previous_servers(job_dir: Path) -> None:
    """Stop the servers this job started last time (one line of server.pid each), but
    only those whose pid is still the same process (same start time). Next renames its
    process to `next-server`, so the command line cannot identify it."""
    pid_file = job_dir / "server.pid"
    try:
        lines = pid_file.read_text().splitlines()
    except OSError:
        return
    for line in lines:
        try:
            pid_text, recorded_start = line.strip().split(" ", 1)
            pid = int(pid_text)
        except ValueError:
            continue
        if started_at(pid) == recorded_start:
            try:
                os.killpg(pid, signal.SIGTERM)  # the server is its own session leader
            except ProcessLookupError:
                pass
    pid_file.unlink(missing_ok=True)


def copy_tree_command(source: Path, target: Path) -> List[str]:
    """`cp -R` with copy-on-write where the platform offers it (APFS clonefile on macOS,
    reflinks on Linux), so five copies of node_modules cost seconds and little disk."""
    flags = "-Rc" if sys.platform == "darwin" else "-R"
    argv = ["cp", flags]
    if sys.platform != "darwin":
        argv.append("--reflink=auto")
    return [*argv, str(source), str(target)]


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
    """Returns {"code_generation_output": ...} with one demo URL per family. Raises BuildError on any failed step."""
    validate_state_for_stage(StageEnum.CODE_GENERATION, state)
    assert state.design_output is not None and state.design_output.design_spec is not None
    spec = state.design_output.design_spec
    catalog = load_catalog()
    chosen = family_of(spec, catalog) or next(iter(catalog.themes))
    variants = specs_in_every_family(spec, catalog)

    job_dir.mkdir(parents=True, exist_ok=True)
    template = job_dir / "template"
    sites = job_dir / "sites"
    specs = job_dir / "specs"
    log = job_dir / "build.log"
    log.write_text("")
    env = site_env()

    stop_previous_servers(job_dir)
    for stale in (template, sites, specs, job_dir / "site"):  # site/ is the single-family layout of earlier runs
        shutil.rmtree(stale, ignore_errors=True)
    (job_dir / "design-spec.json").write_text(json.dumps(spec, indent=2) + "\n")
    specs.mkdir()
    for family, variant in variants.items():
        (specs / f"{family}.json").write_text(json.dumps(variant, indent=2) + "\n")

    run(["git", "clone", "--quiet", template_source, str(template)], job_dir, env, log)
    commit = commit_of(template)
    run(["npm", "ci", "--no-audit", "--no-fund"], template, env, log)

    urls: Dict[str, str] = {}
    pid_lines: List[str] = []
    pid_file = job_dir / "server.pid"
    for family in variants:
        site = sites / family
        try:
            run(["git", "clone", "--quiet", str(template), str(site)], job_dir, env, log)
            run(copy_tree_command(template / "node_modules", site / "node_modules"), job_dir, env, log)
            run(["bash", str(BUILD_SCRIPT), str(specs / f"{family}.json"), str(site)], site, env, log)
            port = free_port()
            pid = serve(site, port, env, job_dir / f"server-{family}.log")
            pid_lines.append(f"{pid} {started_at(pid) or ''}")
            pid_file.write_text("".join(f"{line}\n" for line in pid_lines))  # written as we go: a later failure still leaves these stoppable
            url = f"http://localhost:{port}"
            wait(url, pid)
        except BuildError as exc:
            raise BuildError(f"{family} family: {exc}") from exc
        urls[family] = url

    return {
        "code_generation_output": CodeGenerationOutput(
            repo_url=str(sites / chosen),
            preview_url=urls[chosen],
            preview_variants=urls,
            template_commit=commit,
            test_results={"build": "passed", "families": list(urls)},
        )
    }


__all__: Sequence[str] = ("BuildError", "run_code_generation", "site_env", "stop_previous_servers")
