"""The demo-site graph and entrypoint with a fake model and a fake build: success, review flags, advisory flags, crashes."""

from __future__ import annotations

import copy
import json
import os
import pathlib
import subprocess
import sys
import uuid
from typing import Any, Dict, List, Mapping, Sequence

import pytest

from pipeline import run as run_module
from pipeline.nodes import code_generation
from pipeline.nodes.code_generation import BuildError, run_code_generation, site_env, started_at, stop_previous_server
from pipeline.state import CodeGenerationOutput, PipelineState
from pipeline.template_spec.prompt import FLAG_LOGO_UNREADABLE

FIX = pathlib.Path(__file__).parent / "fixtures"
RAW: Dict[str, Any] = json.loads((FIX / "intake_answers_complete.json").read_text())
REPLY: Dict[str, Any] = json.loads((FIX / "template_design_reply_valid.json").read_text())


def _blob() -> Dict[str, Any]:
    return {**copy.deepcopy(RAW), "jobId": str(uuid.uuid4()), "organizationId": str(uuid.uuid4())}


def _fake_build(state: PipelineState) -> Dict[str, Any]:
    return {"code_generation_output": CodeGenerationOutput(repo_url="/tmp/site", preview_url="http://localhost:4321", template_commit="abc123")}


def _patch(monkeypatch: pytest.MonkeyPatch, reply: Dict[str, Any], build: Any = _fake_build) -> None:
    async def provide(system: str, user: str) -> str:
        return json.dumps(reply)

    monkeypatch.setattr(run_module, "provider_named", lambda name: provide)
    monkeypatch.setattr(run_module, "run_code_generation", lambda state, job_dir, template_source: build(state))


def _result(job_dir: pathlib.Path) -> Dict[str, Any]:
    result: Dict[str, Any] = json.loads((job_dir / "result.json").read_text())
    return result


def test_success_writes_the_url_and_the_template_commit(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, REPLY)
    assert run_module.main(["--job-dir", str(tmp_path)], json.dumps(_blob())) == 0
    result = _result(tmp_path)
    assert result["status"] == "succeeded" and result["url"] == "http://localhost:4321" and result["template_commit"] == "abc123"
    assert (tmp_path / "state.json").exists() and not (tmp_path / "result.json.tmp").exists()


def test_advisory_spec_flags_do_not_stop_the_build(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An uploaded logo is a supabase:// path the fetcher refuses, so real runs carry logo_unreadable; they must still build."""
    built: List[PipelineState] = []

    def build(state: PipelineState) -> Dict[str, Any]:
        built.append(state)
        return _fake_build(state)

    _patch(monkeypatch, REPLY, build)
    blob = _blob()
    blob["answers"]["brandColors"] = ""
    blob["attachments"] = [{"category": "logo", "bucket": "intake", "path": "x/logo.png", "originalName": "logo.png"}]
    blob["answers"]["hasLogo"] = "Yes — I will upload it"
    assert run_module.main(["--job-dir", str(tmp_path)], json.dumps(blob)) == 0
    assert len(built) == 1
    assert FLAG_LOGO_UNREADABLE in [f["code"] for f in _result(tmp_path)["flags"]]


def test_no_valid_spec_ends_before_the_build(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bad = copy.deepcopy(REPLY)
    bad["tokens"]["fonts"]["body"] = "Instrument Serif"

    def build(state: PipelineState) -> Dict[str, Any]:
        raise AssertionError("must not build without a valid spec")

    _patch(monkeypatch, bad, build)
    assert run_module.main(["--job-dir", str(tmp_path)], json.dumps(_blob())) == 1
    result = _result(tmp_path)
    assert result["status"] == "failed" and "no valid design spec" in result["error"]


def test_unmappable_intake_ends_before_design(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, REPLY)
    blob = _blob()
    blob["answers"]["primaryGoal"] = "World domination"
    assert run_module.main(["--job-dir", str(tmp_path)], json.dumps(blob)) == 1
    assert "primaryGoal" in _result(tmp_path)["error"]


@pytest.mark.parametrize("stdin", ["not json", json.dumps({"answers": {}})])
def test_a_crash_still_leaves_a_result(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, stdin: str) -> None:
    _patch(monkeypatch, REPLY)
    assert run_module.main(["--job-dir", str(tmp_path)], stdin) == 1
    assert _result(tmp_path)["status"] == "failed"


def test_build_error_message_reaches_the_result(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def build(state: PipelineState) -> Dict[str, Any]:
        raise BuildError("`npm ci` exited 1")

    _patch(monkeypatch, REPLY, build)
    assert run_module.main(["--job-dir", str(tmp_path)], json.dumps(_blob())) == 1
    assert _result(tmp_path)["error"] == "`npm ci` exited 1"


# -- CODE_GENERATION node with its commands faked -------------------------------------------


def _designed_state(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> PipelineState:
    """Run the real graph up to the build and capture the state the build node receives."""
    seen: List[PipelineState] = []

    def build(state: PipelineState) -> Dict[str, Any]:
        seen.append(state)
        return _fake_build(state)

    _patch(monkeypatch, REPLY, build)
    run_module.main(["--job-dir", str(tmp_path / "first")], json.dumps(_blob()))
    return seen[0]


def test_build_node_runs_clone_install_build_then_serves(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = _designed_state(tmp_path, monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgresql://platform-db")
    calls: List[Sequence[str]] = []
    envs: List[Mapping[str, str]] = []

    def run(argv: Sequence[str], cwd: pathlib.Path, env: Mapping[str, str], log: pathlib.Path) -> None:
        calls.append(argv)
        envs.append(env)

    job = tmp_path / "job"
    out = run_code_generation(
        state, job, "/src/template", run=run, serve=lambda site, port, env, log: 99999, wait=lambda url, pid: None, commit_of=lambda site: "c0ffee"
    )["code_generation_output"]
    assert [c[0:2] for c in calls] == [["git", "clone"], ["npm", "ci"], ["bash", str(code_generation.BUILD_SCRIPT)]]
    assert out.preview_url.startswith("http://localhost:") and out.template_commit == "c0ffee"
    assert json.loads((job / "design-spec.json").read_text()) == state.design_output.design_spec  # type: ignore[union-attr]
    assert (job / "server.pid").read_text().split()[0] == "99999"
    assert all("DATABASE_URL" not in env for env in envs) and "DATABASE_URL" not in site_env()


def test_build_node_failure_propagates(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = _designed_state(tmp_path, monkeypatch)

    def run(argv: Sequence[str], cwd: pathlib.Path, env: Mapping[str, str], log: pathlib.Path) -> None:
        if argv[0] == "npm":
            raise BuildError("npm ci exited 1")

    with pytest.raises(BuildError):
        run_code_generation(state, tmp_path / "job", "/src", run=run, serve=lambda *a: 1, wait=lambda u, p: None, commit_of=lambda s: "x")


def test_stale_pid_belonging_to_another_process_is_left_alone(tmp_path: pathlib.Path) -> None:
    """Same pid, different start time: after a reboot the pid was reused by something else."""
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    try:
        (tmp_path / "server.pid").write_text(f"{other.pid} Thu Jan  1 00:00:00 1970\n")
        stop_previous_server(tmp_path)
        assert other.poll() is None and not (tmp_path / "server.pid").exists()
    finally:
        other.kill()
        other.wait()


def test_previous_server_for_this_site_is_stopped(tmp_path: pathlib.Path) -> None:
    server = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    try:
        (tmp_path / "server.pid").write_text(f"{server.pid} {started_at(server.pid)}\n")
        stop_previous_server(tmp_path)
        assert server.wait(timeout=5) != 0
    finally:
        if server.poll() is None:
            server.kill()
            server.wait()


def test_run_command_failure_reports_the_log_tail(tmp_path: pathlib.Path) -> None:
    log = tmp_path / "build.log"
    with pytest.raises(BuildError, match="boom"):
        code_generation.run_command(["sh", "-c", "echo boom; exit 3"], tmp_path, {"PATH": os.environ["PATH"]}, log)
