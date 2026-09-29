from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hermes_gate.cli import main
from hermes_gate.delegate_judge import judge, read_request


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / ".hermes").mkdir()
    return root


def write_profile(
    root: Path, command: list[str] | None = None, *, exclusions: list[str] | None = None
) -> None:
    command = command or [sys.executable, "-c", "raise SystemExit(0)"]
    exclusions = exclusions if exclusions is not None else [".git/**"]
    (root / ".hermes" / "gate.toml").write_text(
        f"""[gate]
fast_budget_seconds = 8.0
full_required_local = false
exclusions = {json.dumps(exclusions)}
[lintlang]
enabled = false
[review]
argv = ["coderabbit", "--agent"]
material_severities = ["critical", "major"]
material_categories = ["correctness"]
fallback_argv = []
[[fast]]
name = "test"
argv = {json.dumps(command)}
timeout_seconds = 2.0
globs = ["**/*"]
""",
        encoding="utf-8",
    )


def request(workspace_path: Path, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "version": 1,
        "goal": "implement the feature",
        "summary": "did the thing",
        "attempt": 1,
        "max_retries": 2,
        "previous_feedback": [],
        "task_index": 0,
        "subagent_id": "agent-1",
        "session_id": None,
        "model": None,
        "api_calls": None,
        "completed": True,
        "workspace": str(workspace_path),
        "workspace_isolated": True,
    }
    base.update(overrides)
    return base


def test_pass_when_fast_gate_passes(repo: Path) -> None:
    write_profile(repo)
    outcome = judge(request(repo))
    assert outcome == {"verdict": "pass", "feedback": ""}


def test_pass_when_all_changed_paths_are_excluded(repo: Path) -> None:
    write_profile(repo, exclusions=[".git/**", "*.md"])
    git(repo, "add", ".hermes/gate.toml")
    git(repo, "commit", "-q", "-m", "init")
    (repo / "notes.md").write_text("scratch\n", encoding="utf-8")
    outcome = judge(request(repo))
    assert outcome == {"verdict": "pass", "feedback": ""}


def test_retry_while_attempt_within_max_retries_then_reject_after(repo: Path) -> None:
    # attempt is one-based (first attempt is 1); max_retries counts allowed
    # correction turns after that first attempt, so attempts 1 and 2 both owe
    # a retry when max_retries=2, and only attempt 3 exhausts the budget.
    write_profile(repo, [sys.executable, "-c", "raise SystemExit(1)"])
    (repo / "source.py").write_text("bad = True\n", encoding="utf-8")
    first = judge(request(repo, attempt=1, max_retries=2))
    assert first["verdict"] == "retry"
    assert "test" in first["feedback"]
    second = judge(request(repo, attempt=2, max_retries=2))
    assert second["verdict"] == "retry"
    third = judge(request(repo, attempt=3, max_retries=2))
    assert third["verdict"] == "reject"


def test_first_attempt_retries_when_one_correction_turn_is_allowed(repo: Path) -> None:
    # Regression: the Hermes Agent's default max_retries=1 means "one allowed
    # correction turn", so the very first (attempt=1) failure must retry, not
    # reject outright.
    write_profile(repo, [sys.executable, "-c", "raise SystemExit(1)"])
    (repo / "source.py").write_text("bad = True\n", encoding="utf-8")
    outcome = judge(request(repo, attempt=1, max_retries=1))
    assert outcome["verdict"] == "retry"


def test_zero_max_retries_rejects_immediately(repo: Path) -> None:
    write_profile(repo, [sys.executable, "-c", "raise SystemExit(1)"])
    (repo / "source.py").write_text("bad = True\n", encoding="utf-8")
    outcome = judge(request(repo, attempt=1, max_retries=0))
    assert outcome["verdict"] == "reject"


def test_missing_check_executable_is_error_not_retry(repo: Path) -> None:
    # Regression: a declared check whose executable cannot even be launched
    # is a gate/environment problem, not something a correction turn can fix,
    # so it must map to "error" rather than "retry" or "reject".
    write_profile(repo, ["hermes-gate-test-nonexistent-tool-xyz"])
    (repo / "source.py").write_text("bad = True\n", encoding="utf-8")
    outcome = judge(request(repo, attempt=1, max_retries=2))
    assert outcome["verdict"] == "error"
    assert "unavailable" in outcome["feedback"]


def test_failure_feedback_omits_raw_stdout(repo: Path) -> None:
    secret_marker = "TOP-SECRET-SOURCE-BYTES"
    write_profile(
        repo,
        [sys.executable, "-c", f"import sys; print({secret_marker!r}); raise SystemExit(1)"],
    )
    (repo / "source.py").write_text("bad = True\n", encoding="utf-8")
    outcome = judge(request(repo, attempt=1, max_retries=1))
    assert outcome["verdict"] == "retry"
    assert secret_marker not in outcome["feedback"]


def test_missing_profile_is_error(repo: Path) -> None:
    outcome = judge(request(repo))
    assert outcome == {"verdict": "error", "feedback": "gate not configured: run hermes-gate init"}


def test_workspace_not_a_repository_is_error(tmp_path: Path) -> None:
    not_a_repo = tmp_path / "plain-dir"
    not_a_repo.mkdir()
    outcome = judge(request(not_a_repo))
    assert outcome == {"verdict": "error", "feedback": "workspace is not a Git repository"}


def test_missing_workspace_directory_is_fixed_error(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist-SECRET-PATH"
    outcome = judge(request(missing))
    assert outcome == {
        "verdict": "error",
        "feedback": "workspace unavailable: path is not a directory",
    }
    assert "SECRET-PATH" not in outcome["feedback"]


def test_null_workspace_is_fixed_error(tmp_path: Path) -> None:
    outcome = judge(request(tmp_path, workspace=None, workspace_isolated=False))
    assert outcome == {
        "verdict": "error",
        "feedback": "workspace unavailable: request has no workspace path",
    }


def test_absent_workspace_key_is_fixed_error(tmp_path: Path) -> None:
    payload = request(tmp_path)
    del payload["workspace"]
    outcome = judge(payload)
    assert outcome["feedback"] == "workspace unavailable: request has no workspace path"


@pytest.mark.parametrize("feedback", [None, "prior note", ["one", "two"]])
def test_previous_feedback_shapes_are_accepted(repo: Path, feedback: object) -> None:
    write_profile(repo)
    outcome = judge(request(repo, previous_feedback=feedback))
    assert outcome == {"verdict": "pass", "feedback": ""}


def test_null_subagent_id_and_absent_workspace_isolated_are_accepted(repo: Path) -> None:
    write_profile(repo)
    payload = request(repo, subagent_id=None)
    del payload["workspace_isolated"]
    assert judge(payload) == {"verdict": "pass", "feedback": ""}


def test_unisolated_workspace_with_a_path_is_still_judged(repo: Path) -> None:
    write_profile(repo, [sys.executable, "-c", "raise SystemExit(1)"])
    (repo / "source.py").write_text("bad = True\n", encoding="utf-8")
    outcome = judge(request(repo, workspace_isolated=False, attempt=1, max_retries=1))
    assert outcome["verdict"] == "retry"


@pytest.mark.parametrize(
    "overrides",
    [
        {"version": 2},
        {"workspace": ""},
        {"attempt": 0},
        {"attempt": -1},
        {"max_retries": -1},
    ],
)
def test_invalid_request_fields_are_rejected(repo: Path, overrides: dict[str, object]) -> None:
    outcome = judge(request(repo, **overrides))
    assert outcome["verdict"] == "error"
    assert outcome["feedback"].startswith("invalid request:")


def test_missing_required_field_is_rejected(repo: Path) -> None:
    payload = request(repo)
    del payload["goal"]
    outcome = judge(payload)
    assert outcome == {
        "verdict": "error",
        "feedback": "invalid request: missing required field: goal",
    }


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"attempt": "0"}, "attempt must be an integer"),
        ({"goal": 1}, "goal must be a string"),
        ({"completed": "yes"}, "completed must be a boolean"),
        ({"api_calls": "3"}, "api_calls must be an integer or null"),
        ({"model": 7}, "model must be a string or null"),
        ({"subagent_id": 5}, "subagent_id must be a string or null"),
        ({"workspace": 5}, "workspace must be a string or null"),
        ({"workspace_isolated": "yes"}, "workspace_isolated must be a boolean"),
        (
            {"previous_feedback": [1]},
            "previous_feedback must be a string, an array of strings, or null",
        ),
        (
            {"previous_feedback": {"text": "x"}},
            "previous_feedback must be a string, an array of strings, or null",
        ),
    ],
)
def test_wrong_type_field_is_rejected(
    repo: Path, overrides: dict[str, object], message: str
) -> None:
    outcome = judge(request(repo, **overrides))
    assert outcome == {"verdict": "error", "feedback": f"invalid request: {message}"}


def test_read_request_rejects_malformed_json() -> None:
    value, error = read_request(io.StringIO("not json"))
    assert value is None
    assert "not valid JSON" in error


def test_read_request_rejects_non_object_json() -> None:
    value, error = read_request(io.StringIO("[1, 2, 3]"))
    assert value is None
    assert error == "request must be a JSON object"


def test_read_request_accepts_valid_object() -> None:
    value, error = read_request(io.StringIO(json.dumps({"a": 1})))
    assert error == ""
    assert value == {"a": 1}


class _UndecodableStream:
    """A stream whose ``read()`` raises, like stdin on bytes invalid for its encoding."""

    def read(self) -> str:
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")


def test_read_request_rejects_undecodable_stdin() -> None:
    # Regression: the seam contract is exactly one JSON object on stdout, so a
    # decoding failure reading stdin must produce a fixed reason instead of
    # raising out of read_request (which the CLI does not wrap in a try/except).
    value, error = read_request(_UndecodableStream())
    assert value is None
    assert error == "stdin is not decodable text"


def test_cli_delegate_judge_pass(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_profile(repo)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(request(repo))))
    exit_code = main(["delegate-judge"])
    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert captured == {"verdict": "pass", "feedback": ""}


def test_cli_delegate_judge_undecodable_stdin_still_exits_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", _UndecodableStream())
    exit_code = main(["delegate-judge"])
    raw = capsys.readouterr().out
    captured = json.loads(raw)
    assert exit_code == 0
    assert raw.count("\n") == 1
    assert captured == {"verdict": "error", "feedback": "stdin is not decodable text"}


def test_cli_delegate_judge_malformed_stdin_still_exits_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"secret": "DO-NOT-ECHO"'))
    exit_code = main(["delegate-judge"])
    raw = capsys.readouterr().out
    captured = json.loads(raw)
    assert exit_code == 0
    assert raw.count("\n") == 1
    assert set(captured) == {"verdict", "feedback"}
    assert captured["verdict"] == "error"
    assert "DO-NOT-ECHO" not in raw


def test_cli_delegate_judge_internal_error_does_not_leak_exception_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    secret_marker = "SUPER-SECRET-TOKEN-VALUE"

    def explode(_request: dict[str, object]) -> dict[str, str]:
        raise RuntimeError(f"credential {secret_marker} rejected")

    monkeypatch.setattr("hermes_gate.cli.delegate_judge", explode)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(request(tmp_path))))
    exit_code = main(["delegate-judge"])
    raw = capsys.readouterr().out
    captured = json.loads(raw)
    assert exit_code == 0
    assert raw.count("\n") == 1
    assert secret_marker not in raw
    assert "RuntimeError" not in raw
    assert captured == {
        "verdict": "error",
        "feedback": "internal error while judging the workspace",
    }


def test_cli_delegate_judge_does_not_require_cwd_to_be_a_repository(
    tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_profile(repo)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(request(repo))))
    exit_code = main(["delegate-judge"])
    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert captured["verdict"] == "pass"


def test_existing_commands_are_unaffected(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_profile(repo)
    original_cwd = Path.cwd()
    os.chdir(repo)
    try:
        exit_code = main(["fast"])
    finally:
        os.chdir(original_cwd)
    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert captured["status"] == "PASS"
