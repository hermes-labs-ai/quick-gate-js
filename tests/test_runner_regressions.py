from __future__ import annotations

import json
import subprocess
import sys
import tracemalloc
from pathlib import Path

import pytest

from hermes_gate.init_repo import ACTION_VERSIONS, initialize
from hermes_gate.init_repo import _workflow as init_repo_workflow
from hermes_gate.repo_runner import _execute, run


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
@pytest.mark.parametrize("size", [32768, 32769, 40001])
def test_runner_reports_each_stream_truncation(tmp_path: Path, stream: str, size: int) -> None:
    result = _execute(
        [sys.executable, "-c", f"import sys; sys.{stream}.write('x' * {size})"],
        tmp_path, 5, "output-probe",
    )
    assert result["status"] == "PASS"
    assert len(result[stream]) == min(size, 32768)
    assert result["output_truncated"] is (size > 32768)


@pytest.mark.parametrize("mode", ["fast", "full"])
@pytest.mark.parametrize("state", ["unstaged", "staged", "untracked", "staged_then_cleaned"])
@pytest.mark.parametrize("bad", [False, True])
def test_generated_whitespace_check_covers_git_states(
    tmp_path: Path, mode: str, state: str, bad: bool
) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.com")
    path = tmp_path / "notes with spaces.txt"
    path.write_text("baseline\n")
    git("add", ".")
    git("commit", "-qm", "baseline")
    assert initialize(tmp_path)["status"] == "PASS"
    if state == "untracked":
        path = tmp_path / "new notes.txt"
    path.write_text("changed" + (" " if bad else "") + "\n")
    if state in {"staged", "staged_then_cleaned"}:
        git("add", "--", path.name)
    if state == "staged_then_cleaned":
        path.write_text("clean working copy\n")
    proc = subprocess.run(
        [sys.executable, str(tmp_path / ".hermes/hermes_gate_runner.py"), mode],
        cwd=tmp_path, capture_output=True, text=True, check=False,
    )
    result = json.loads(proc.stdout)
    assert result["status"] == ("FAIL" if bad else "PASS"), result
    if bad:
        assert "trailing whitespace" in result["checks"][-1]["stdout"]


def test_fast_skips_deleted_paths_before_file_checks(tmp_path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.com")
    hermes = tmp_path / ".hermes"
    hermes.mkdir()
    (hermes / "gate.toml").write_text(
        """version = 1
[gate]
exclusions = [".git/**"]

[[fast]]
name = "python-parse"
argv = ["python3", "-c", "import pathlib,sys; [pathlib.Path(path).read_text() for path in sys.argv[1:]]", "{files}"]
timeout_seconds = 2.0
globs = ["**/*.py"]
""",
        encoding="utf-8",
    )
    source = tmp_path / "deleted.py"
    source.write_text("value = 1\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "baseline")
    source.unlink()

    result = run("fast", root=tmp_path)

    assert result["status"] == "NOT_APPLICABLE"
    assert result["reason"] == "no changed files"


def test_fast_keeps_dangling_symlink_paths(tmp_path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-q")
    hermes = tmp_path / ".hermes"
    hermes.mkdir()
    (hermes / "gate.toml").write_text(
        """version = 1
[gate]
exclusions = [".git/**"]

[[fast]]
name = "path-observer"
argv = ["python3", "-c", "import sys; raise SystemExit(0 if sys.argv[1:] == ['link.py'] else 1)", "{files}"]
timeout_seconds = 2.0
globs = ["**/*.py"]
""",
        encoding="utf-8",
    )
    (tmp_path / "link.py").symlink_to("missing.py")

    result = run("fast", root=tmp_path)

    assert result["status"] == "PASS"


def test_unsupported_runner_runtime_has_actionable_error(tmp_path: Path) -> None:
    runner = Path(__file__).parents[1] / "src/hermes_gate/repo_runner.py"
    proc = subprocess.run(
        [sys.executable, "-c", "import runpy,sys; sys.version_info=(3,10,0); runpy.run_path(sys.argv[1])", str(runner)],
        cwd=tmp_path, capture_output=True, text=True, check=False,
    )
    assert proc.returncode != 0
    assert "Python 3.11 or newer" in proc.stderr
    assert "Traceback" not in proc.stderr
def test_runner_capture_memory_is_bounded_for_large_streams(tmp_path: Path) -> None:
    tracemalloc.start()
    try:
        result = _execute(
            [sys.executable, "-c", "import sys; sys.stdout.write('x' * 8_000_000); sys.stderr.write('y' * 8_000_000)"],
            tmp_path, 5, "bounded-output",
        )
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result["status"] == "PASS"
    assert result["output_truncated"] is True
    assert len(result["stdout"]) == len(result["stderr"]) == 32768
    assert peak < 4_000_000, f"Capture retained memory proportional to emitted output: {peak} bytes"


# --- Review range: a hosted checkout must not report a pass over zero bytes -------------
#
# Ported from the released Agent Trash Guard v0.1.2 rail (commit 9364625), where the
# defect was observed live: `actions/checkout` produces a pristine tree, the worktree
# scope selects nothing, and a file-driven `full` stage reported PASS having read no
# bytes at all.


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    )


def _range_fixture(root: Path) -> str:
    """A repository whose committed bytes carry a whitespace error; worktree is pristine."""
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Fixture")
    _git(root, "config", "user.email", "fixture@example.com")
    hermes = root / ".hermes"
    hermes.mkdir()
    (hermes / "gate.toml").write_text(
        """version = 1
[gate]
exclusions = [".git/**"]

[[full]]
name = "diff-check"
argv = ["python3", ".hermes/hermes_gate_runner.py", "diff-check", "{files}"]
timeout_seconds = 10.0
globs = ["**/*"]
""",
        encoding="utf-8",
    )
    runner = Path(__file__).parents[1] / "src/hermes_gate/repo_runner.py"
    (hermes / "hermes_gate_runner.py").write_bytes(runner.read_bytes())
    (root / "clean.txt").write_text("baseline\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "baseline")
    base = _git(root, "rev-parse", "HEAD").stdout.strip()
    (root / "offending.txt").write_text("committed trailing space \n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "introduce trailing whitespace")
    return base


def _run_runner(root: Path, *args: str, env: dict[str, str] | None = None):
    import os

    proc = subprocess.run(
        [sys.executable, str(root / ".hermes/hermes_gate_runner.py"), *args],
        cwd=root, capture_output=True, text=True, env={**os.environ, **(env or {})}, check=False,
    )
    return proc, json.loads(proc.stdout)


def test_clean_checkout_reports_no_applicable_stage_instead_of_a_vacuous_pass(
    tmp_path: Path,
) -> None:
    _range_fixture(tmp_path)
    proc, result = _run_runner(tmp_path, "full")
    assert result["status"] == "NOT_APPLICABLE", result
    assert proc.returncode == 0
    assert not [check for check in result["checks"] if check["status"] == "PASS"], result


def test_base_range_reviews_the_committed_bytes(tmp_path: Path) -> None:
    base = _range_fixture(tmp_path)
    proc, result = _run_runner(tmp_path, "full", "--base", base)
    assert result["status"] == "FAIL", result
    assert proc.returncode == 1
    assert result["range"] == f"{base}...HEAD"
    assert "offending.txt" in result["checks"][-1]["stdout"]


def test_base_environment_variable_selects_the_same_range(tmp_path: Path) -> None:
    base = _range_fixture(tmp_path)
    _, from_flag = _run_runner(tmp_path, "full", "--base", base)
    _, from_env = _run_runner(tmp_path, "full", env={"HERMES_GATE_BASE": base})
    assert from_env["range"] == from_flag["range"] == f"{base}...HEAD"
    assert from_env["status"] == from_flag["status"] == "FAIL"


@pytest.mark.parametrize(
    ("args", "env", "source"),
    [
        (("--base", ""), None, "--base"),
        (("--base=",), None, "--base"),
        ((), {"HERMES_GATE_BASE": ""}, "HERMES_GATE_BASE"),
        ((), {"HERMES_GATE_BASE": "   "}, "HERMES_GATE_BASE"),
    ],
    ids=["flag-separate", "flag-equals", "env-empty", "env-blank"],
)
def test_empty_base_is_an_error_not_the_local_scope(
    tmp_path: Path, args: tuple[str, ...], env: dict[str, str] | None, source: str
) -> None:
    """An explicitly empty base used to fall through to the worktree scope and, on a
    pristine hosted checkout, report NOT_APPLICABLE over nothing instead of failing."""
    _range_fixture(tmp_path)
    proc, result = _run_runner(tmp_path, "full", *args, env=env)
    assert result["status"] == "ERROR", result
    assert proc.returncode == 2
    assert result["reason"] == (
        f"{source} is set but empty; omit it for the local worktree scope or name a revision"
    )
    assert result.get("checks", []) == []


def test_omitted_base_still_selects_the_local_scope(tmp_path: Path) -> None:
    _range_fixture(tmp_path)
    _, result = _run_runner(tmp_path, "full")
    assert result["range"] == ""
    assert result["status"] == "NOT_APPLICABLE", result


def test_explicit_base_flag_still_overrides_an_empty_environment(tmp_path: Path) -> None:
    base = _range_fixture(tmp_path)
    proc, result = _run_runner(tmp_path, "full", "--base", base, env={"HERMES_GATE_BASE": ""})
    assert result["status"] == "FAIL", result
    assert proc.returncode == 1
    assert result["range"] == f"{base}...HEAD"


def test_run_entry_point_distinguishes_absent_from_empty_base(tmp_path: Path) -> None:
    """The engine-facing run() must not treat an empty base as an omitted one either."""
    base = _range_fixture(tmp_path)
    absent = run("full", root=tmp_path)
    assert absent["status"] == "NOT_APPLICABLE" and absent["range"] == "", absent
    for empty in ("", "   "):
        result = run("full", root=tmp_path, base=empty)
        assert result["status"] == "ERROR", result
        assert "base revision is empty" in result["reason"]
        assert result["checks"] == []
    valid = run("full", root=tmp_path, base=base)
    assert valid["status"] == "FAIL" and valid["range"] == f"{base}...HEAD", valid


def test_unresolvable_base_is_an_error_not_an_empty_change_set(tmp_path: Path) -> None:
    _range_fixture(tmp_path)
    proc, result = _run_runner(tmp_path, "full", "--base", "0" * 40)
    assert result["status"] == "ERROR", result
    assert proc.returncode == 1
    assert "not present in this checkout" in result["reason"]
    assert "fetch-depth" in result["reason"]


def test_all_reviews_every_committed_byte(tmp_path: Path) -> None:
    _range_fixture(tmp_path)
    _, result = _run_runner(tmp_path, "full", "--all")
    assert result["status"] == "FAIL", result
    assert result["range"].endswith("..HEAD")
    assert "offending.txt" in result["checks"][-1]["stdout"]


def test_all_and_base_are_mutually_exclusive(tmp_path: Path) -> None:
    base = _range_fixture(tmp_path)
    proc, result = _run_runner(tmp_path, "full", "--all", "--base", base)
    assert result["status"] == "ERROR"
    assert proc.returncode == 2
    assert result["reason"] == "--all and --base are exclusive"


def test_unknown_option_is_rejected_with_usage(tmp_path: Path) -> None:
    _range_fixture(tmp_path)
    proc, result = _run_runner(tmp_path, "full", "--since", "HEAD~1")
    assert result["status"] == "ERROR"
    assert proc.returncode == 2
    assert "unknown option" in result["reason"]


@pytest.mark.parametrize("mode", ["fast", "full"])
def test_local_worktree_scope_is_unchanged_without_a_base(tmp_path: Path, mode: str) -> None:
    _range_fixture(tmp_path)
    (tmp_path / "clean.txt").write_text("local trailing space \n", encoding="utf-8")
    (tmp_path / ".hermes" / "gate.toml").write_text(
        (tmp_path / ".hermes" / "gate.toml").read_text(encoding="utf-8").replace(
            "[[full]]", "[[fast]]\nname = \"diff-check\"\nargv = "
            "[\"python3\", \".hermes/hermes_gate_runner.py\", \"diff-check\", \"{files}\"]\n"
            "timeout_seconds = 10.0\nglobs = [\"**/*\"]\n\n[[full]]",
        ),
        encoding="utf-8",
    )
    _, result = _run_runner(tmp_path, mode)
    assert result["range"] == ""
    assert result["status"] == "FAIL", result


# --- Every declared full stage owes the caller a result ---------------------------------


def _stage(name: str, argv: str) -> str:
    return (
        f'\n[[full]]\nname = "{name}"\nargv = {argv}\ntimeout_seconds = 10.0\n'
        'globs = ["**/*"]\n'
    )


def _staged_fixture(root: Path, stages: str, mode_table: str = "full") -> None:
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Fixture")
    _git(root, "config", "user.email", "fixture@example.com")
    hermes = root / ".hermes"
    hermes.mkdir()
    (hermes / "gate.toml").write_text(
        'version = 1\n[gate]\nexclusions = [".git/**"]\n' + stages, encoding="utf-8"
    )
    runner = Path(__file__).parents[1] / "src/hermes_gate/repo_runner.py"
    (hermes / "hermes_gate_runner.py").write_bytes(runner.read_bytes())
    (root / "touched.txt").write_text("content\n", encoding="utf-8")


def test_full_runs_every_declared_stage_past_a_failure(tmp_path: Path) -> None:
    _staged_fixture(
        tmp_path,
        _stage("first-fails", '["python3", "-c", "raise SystemExit(1)"]')
        + _stage("sentinel-still-runs", '["python3", "-c", "print(\'sentinel\')"]'),
    )
    _, result = _run_runner(tmp_path, "full")
    names = [check["name"] for check in result["checks"]]
    assert names == ["first-fails", "sentinel-still-runs"], result
    assert result["status"] == "FAIL"
    assert result["reason"] == "failed stages: first-fails"
    assert result["checks"][-1]["status"] == "PASS"


def test_fast_still_stops_at_the_first_failing_stage(tmp_path: Path) -> None:
    _staged_fixture(
        tmp_path,
        _stage("first-fails", '["python3", "-c", "raise SystemExit(1)"]').replace(
            "[[full]]", "[[fast]]"
        )
        + _stage("must-not-run", '["python3", "-c", "print(\'nope\')"]').replace(
            "[[full]]", "[[fast]]"
        ),
    )
    _, result = _run_runner(tmp_path, "fast")
    assert [check["name"] for check in result["checks"]] == ["first-fails"], result
    assert result["status"] == "FAIL"


def test_stage_launch_errors_do_not_abort_the_remaining_stages(tmp_path: Path) -> None:
    _staged_fixture(
        tmp_path,
        _stage("not-executable", '[".hermes/gate.toml"]')
        + _stage("missing-binary", '["hermes-gate-no-such-command-xyz"]')
        + _stage("sentinel-still-runs", '["python3", "-c", "print(\'sentinel\')"]'),
    )
    _, result = _run_runner(tmp_path, "full")
    names = [check["name"] for check in result["checks"]]
    assert names == ["not-executable", "missing-binary", "sentinel-still-runs"], result
    assert result["checks"][0]["status"] == "FAIL"
    assert result["checks"][1]["reason"] == "executable unavailable"
    assert result["checks"][-1]["status"] == "PASS"
    assert result["status"] == "FAIL"


def test_unusable_declarations_surface_as_an_error_naming_every_stage(tmp_path: Path) -> None:
    _staged_fixture(
        tmp_path,
        _stage("empty-argv", "[]")
        + _stage("non-string-argv", "[1]")
        + _stage("sentinel-still-runs", '["python3", "-c", "print(\'sentinel\')"]'),
    )
    proc, result = _run_runner(tmp_path, "full")
    assert result["status"] == "ERROR", result
    assert proc.returncode == 1
    assert "empty-argv" in result["reason"] and "non-string-argv" in result["reason"]
    assert result["checks"][-1]["status"] == "PASS"


def test_file_driven_stage_with_no_selection_is_not_applicable_not_a_pass(
    tmp_path: Path,
) -> None:
    _staged_fixture(
        tmp_path,
        _stage("file-driven", '["python3", "-c", "raise SystemExit(0)", "{files}"]'),
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "baseline")
    _, result = _run_runner(tmp_path, "full")
    assert [check["status"] for check in result["checks"]] == ["NOT_APPLICABLE"], result
    # The stage records why it read nothing; the run records that nothing executed.
    assert result["checks"][0]["reason"] == "no selected files for this stage"
    assert result["status"] == "NOT_APPLICABLE"
    assert result["reason"] == "no commands matched changed files"


def test_file_less_stage_still_runs_on_a_clean_tree(tmp_path: Path) -> None:
    _staged_fixture(
        tmp_path, _stage("file-less", '["python3", "-c", "print(\'ran\')"]')
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "baseline")
    _, result = _run_runner(tmp_path, "full")
    assert result["status"] == "PASS", result
    assert result["checks"][0]["status"] == "PASS"


# --- The generated integration must not regenerate a vacuous rail -----------------------


def test_generated_workflow_reviews_the_pull_request_range(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    (tmp_path / "module.py").write_text("value = 1\n", encoding="utf-8")
    assert initialize(tmp_path)["status"] == "PASS"
    workflow = (tmp_path / ".github/workflows/hermes-quality.yml").read_text(encoding="utf-8")
    assert "fetch-depth: 0" in workflow
    assert "HERMES_GATE_BASE: ${{ github.event.pull_request.base.sha }}" in workflow
    assert 'kwik-gate run --mode full --output "$RUNNER_TEMP/kwik-gate-receipt.json"' in workflow
    assert "name: Preserve the receipt" in workflow
    assert "if: github.event_name == 'pull_request'" in workflow
    assert "  push:\n    branches: [main]\n" in workflow


def test_generated_workflow_checkout_does_not_persist_credentials(tmp_path: Path) -> None:
    """actions/checkout leaves the workflow token in .git/config unless told not to; the
    gate only reads the checkout, so every generated rail must opt out."""
    _git(tmp_path, "init", "-q")
    (tmp_path / "module.py").write_text("value = 1\n", encoding="utf-8")
    assert initialize(tmp_path)["status"] == "PASS"
    workflow = (tmp_path / ".github/workflows/hermes-quality.yml").read_text(encoding="utf-8")
    checkout = workflow.index(f"uses: actions/checkout@{ACTION_VERSIONS['checkout']}")
    next_step = workflow.index(f"- uses: actions/setup-python@{ACTION_VERSIONS['setup-python']}")
    assert "persist-credentials: false" in workflow[checkout:next_step], workflow
    assert workflow.count("persist-credentials") == 1


def test_tracked_workflow_matches_the_generator() -> None:
    """The repository's own quality rail is a generated artifact and must not drift."""
    root = Path(__file__).parents[1]
    tracked = (root / ".github/workflows/hermes-quality.yml").read_text(encoding="utf-8")
    assert tracked == init_repo_workflow(root)


def test_generated_runner_carries_the_review_range_interface(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    (tmp_path / "module.py").write_text("value = 1\n", encoding="utf-8")
    assert initialize(tmp_path)["status"] == "PASS"
    copied = (tmp_path / ".hermes/hermes_gate_runner.py").read_bytes()
    source = (Path(__file__).parents[1] / "src/hermes_gate/repo_runner.py").read_bytes()
    assert copied == source, "init must copy the runner byte-for-byte"
    assert b"HERMES_GATE_BASE" in copied and b"--all" in copied


# --- Corrections from the independent review of the port --------------------------------


def test_fast_skips_a_file_less_stage_whose_globs_match_nothing(tmp_path: Path) -> None:
    """Fast's original selection guard must survive the full-mode NOT_APPLICABLE change."""
    _staged_fixture(
        tmp_path,
        _stage("rust-only", '["python3", "-c", "raise SystemExit(1)"]')
        .replace("[[full]]", "[[fast]]")
        .replace('globs = ["**/*"]', 'globs = ["**/*.rs"]'),
    )
    # Nothing changed matches the stage's globs (the fixture writes no .rs file), and the
    # stage carries no {files} - exactly the case the port stopped skipping.
    (tmp_path / "touched.txt").write_text("prose\n", encoding="utf-8")
    _, result = _run_runner(tmp_path, "fast")
    assert result["checks"] == [], result
    assert result["status"] == "NOT_APPLICABLE"


def test_scalar_argv_is_a_stage_error_rather_than_a_crash(tmp_path: Path) -> None:
    """A non-list argv must not raise out of the loop and deny the caller a receipt."""
    _staged_fixture(
        tmp_path,
        _stage("scalar-argv", "1")
        + _stage("sentinel-still-runs", '["python3", "-c", "print(\'sentinel\')"]'),
    )
    proc, result = _run_runner(tmp_path, "full")
    assert proc.returncode == 1
    assert result["status"] == "ERROR", result
    assert "scalar-argv" in result["reason"]
    assert result["checks"][0]["status"] == "ERROR"
    assert result["checks"][-1]["name"] == "sentinel-still-runs"
    assert result["checks"][-1]["status"] == "PASS"


def test_scalar_argv_in_fast_reports_an_error_receipt(tmp_path: Path) -> None:
    _staged_fixture(tmp_path, _stage("scalar-argv", "1").replace("[[full]]", "[[fast]]"))
    proc, result = _run_runner(tmp_path, "fast")
    assert proc.returncode == 1
    assert result["status"] == "ERROR", result
    assert result["reason"] == "argv must be a non-empty string array"


def test_fixture_repositories_do_not_inherit_the_enclosing_gate_range(
    tmp_path: Path,
) -> None:
    """pytest runs as a gate stage, so the ambient range must not leak into fixtures."""
    import os

    from hermes_gate.repo_runner import BASE_ENV, RANGE_ENV

    assert BASE_ENV not in os.environ and RANGE_ENV not in os.environ
    _range_fixture(tmp_path)
    _, result = _run_runner(tmp_path, "full")
    assert result["range"] == ""
    assert result["status"] == "NOT_APPLICABLE", result


def test_runner_tests_survive_an_enclosing_pull_request_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulate CI: an unrelated base in the environment must not reach the fixture."""
    from hermes_gate.repo_runner import BASE_ENV

    monkeypatch.setenv(BASE_ENV, "f" * 40)
    base = _range_fixture(tmp_path)
    # The helper passes an explicit override, which must win over the ambient value.
    _, result = _run_runner(tmp_path, "full", env={BASE_ENV: base})
    assert result["range"] == f"{base}...HEAD"
    assert result["status"] == "FAIL", result
