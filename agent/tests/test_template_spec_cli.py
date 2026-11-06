"""The intake-to-spec CLI: mock run, prompt export, validate-only, and clean failures."""

from __future__ import annotations

import json
import pathlib

import pytest

from pipeline.template_spec.cli import main

FIX = pathlib.Path(__file__).parent / "fixtures"
ANSWERS = str(FIX / "intake_answers_complete.json")


def test_mock_run_writes_a_valid_spec(tmp_path: pathlib.Path) -> None:
    out = tmp_path / "design-spec.json"
    assert main(["--answers", ANSWERS, "--out", str(out)]) == 0
    assert json.loads(out.read_text())["pages"][0]["slug"] == "/"


def test_print_prompt_writes_two_files_and_no_spec(tmp_path: pathlib.Path) -> None:
    out = tmp_path / "design-spec.json"
    assert main(["--answers", ANSWERS, "--out", str(out), "--print-prompt", str(tmp_path / "p")]) == 0
    assert (tmp_path / "p" / "system.md").exists()
    assert (tmp_path / "p" / "user.md").exists()
    assert not out.exists()


def test_validate_reports_issues_and_exits_1(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = json.loads((FIX / "template_design_spec_valid.json").read_text())
    bad["tokens"]["fonts"]["body"] = "Instrument Serif"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad))
    assert main(["--answers", ANSWERS, "--validate", str(path)]) == 1
    assert "tokens.fonts.body: must be Inter" in capsys.readouterr().out


def test_validate_valid_file_exits_0(tmp_path: pathlib.Path) -> None:
    assert main(["--answers", ANSWERS, "--validate", str(FIX / "template_design_spec_valid.json")]) == 0


def test_validate_ignores_the_reply_job_id(tmp_path: pathlib.Path) -> None:
    spec = json.loads((FIX / "template_design_spec_valid.json").read_text())
    spec["job_id"] = "00000000-0000-0000-0000-000000000000"
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    assert main(["--answers", ANSWERS, "--validate", str(path)]) == 0


def test_validate_accepts_a_fenced_reply_saved_from_claude(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "reply.md"
    path.write_text("Here is the spec:\n```json\n" + (FIX / "template_design_spec_valid.json").read_text() + "```\n")
    assert main(["--answers", ANSWERS, "--validate", str(path)]) == 0


def test_invalid_mock_spec_writes_nothing(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "bad.json"
    path.write_text("not json")
    out = tmp_path / "design-spec.json"
    assert main(["--answers", ANSWERS, "--out", str(out), "--mock-spec", str(path)]) == 1
    assert not out.exists()
    assert "not a JSON object" in capsys.readouterr().out


def test_missing_out_directory_is_a_clean_error(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "nope" / "design-spec.json"
    assert main(["--answers", ANSWERS, "--out", str(out)]) == 1
    assert "nope" in capsys.readouterr().err
