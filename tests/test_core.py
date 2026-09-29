from __future__ import annotations

import io
import json
import runpy
import subprocess
import sys
import time
from pathlib import Path

import pytest

from hermes_gate.cli import main as cli_main
from hermes_gate.config import ConfigError, load_config
from hermes_gate.engine import (
    _fallback_review,
    _provider_review_argv,
    _review_provider_matches,
    _state_file,
    _tool_version,
    boundary,
    fast,
    repair,
    review,
)
from hermes_gate.execution import Execution, run_argv
from hermes_gate.gitstate import ContentReadError, diff_digest, session_changed_paths, snapshot
from hermes_gate.receipts import read_receipt, valid_receipt
from hermes_gate.repo_runner import _execute
from hermes_gate.status import Status


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
    root: Path, command: list[str] | None = None, *, repair_command: list[str] | None = None
) -> None:
    command = command or [sys.executable, "-c", "raise SystemExit(0)"]
    text = f"""version = 1
[gate]
fast_budget_seconds = 8.0
full_required_local = false
exclusions = [".git/**"]
[lintlang]
enabled = false
argv = ["lintlang", "scan", "{{files}}"]
trigger_globs = []
timeout_seconds = 1.0
blocking_threshold = "MEDIUM"
[review]
provider = "coderabbit"
argv = ["coderabbit", "review", "--agent"]
timeout_seconds = 1.0
material_severities = ["critical", "major"]
material_categories = ["correctness"]
fallback_argv = []
[[fast]]
name = "test"
argv = {json.dumps(command)}
timeout_seconds = 2.0
globs = ["**/*"]
[[full]]
name = "test"
argv = {json.dumps(command)}
timeout_seconds = 2.0
globs = ["**/*"]
"""
    if repair_command:
        text += f"""
[[repair]]
name = "repair"
argv = {json.dumps(repair_command)}
timeout_seconds = 2.0
globs = ["**/*"]
"""
    (root / ".hermes" / "gate.toml").write_text(text, encoding="utf-8")


def test_config_rejects_shell_string_argv(repo: Path) -> None:
    (repo / ".hermes" / "gate.toml").write_text("[[fast]]\nargv = 'pytest -q'\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="array of strings"):
        load_config(repo)


def test_execution_timeout_kills_process_group_and_caps_output(tmp_path: Path) -> None:
    marker = tmp_path / "descendant-survived"
    child_code = (
        "import signal, time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM, lambda *_: None); "
        f"time.sleep(0.8); Path({str(marker)!r}).write_text('bad')"
    )
    parent_code = (
        f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        "time.sleep(10)"
    )
    timeout = run_argv(
        [sys.executable, "-c", parent_code], cwd=tmp_path, timeout_seconds=0.05
    )
    assert timeout.timed_out
    assert timeout.elapsed_ms < 1500
    time.sleep(1)
    assert not marker.exists()
    capped = run_argv(
        [sys.executable, "-c", "print('x'*10000)"], cwd=tmp_path, timeout_seconds=1, output_cap=100
    )
    assert capped.output_truncated
    assert len(capped.stdout.encode()) <= 100


def test_execution_tolerates_process_group_exiting_before_term(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ExitedProcess:
        pid = 43210
        returncode = 0

        def __init__(self) -> None:
            self.calls = 0

        def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired(["probe"], timeout or 0)
            return b"", b""

        def poll(self) -> int:
            return 0

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: ExitedProcess())
    monkeypatch.setattr(
        "hermes_gate.execution.os.killpg",
        lambda *args: (_ for _ in ()).throw(ProcessLookupError()),
    )

    result = run_argv(["probe"], cwd=tmp_path, timeout_seconds=0.01)

    assert result.timed_out
    assert result.returncode is None


def test_fast_refuses_detached_merge_without_upstream_or_base(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_profile(repo)
    base_branch = subprocess.run(
        ["git", "-C", str(repo), "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    (repo / "shared.py").write_text("base = True\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    git(repo, "checkout", "-qb", "feature")
    (repo / "feature.py").write_text("feature = True\n", encoding="utf-8")
    git(repo, "add", "feature.py")
    git(repo, "commit", "-qm", "feature change")
    git(repo, "checkout", base_branch)
    (repo / "base_only.py").write_text("base_only = True\n", encoding="utf-8")
    git(repo, "add", "base_only.py")
    git(repo, "commit", "-qm", "base change")
    base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    git(repo, "checkout", "feature")
    git(repo, "merge", "--no-ff", base_branch, "-m", "sync base")
    git(repo, "checkout", "--detach")

    unresolved = fast(repo)

    assert unresolved["status"] == "ERROR"
    assert unresolved["reason"] == "scope unresolved: HEAD is a merge commit with no upstream or --base"
    assert read_receipt(repo, "fast") is None

    explicit_unresolved = fast(repo, files=["feature.py"])

    assert explicit_unresolved["status"] == "ERROR"
    assert explicit_unresolved["reason"] == unresolved["reason"]
    assert read_receipt(repo, "fast") is None

    resolved = fast(repo, base=base)

    assert resolved["status"] == "PASS"
    assert resolved["receipt"]["checked_paths"] == ["feature.py"]

    (repo / "dirty.py").write_text("dirty = True\n", encoding="utf-8")
    with_dirty = fast(repo, base=base)
    assert with_dirty["status"] == "PASS"
    assert with_dirty["receipt"]["checked_paths"] == ["dirty.py", "feature.py"]

    profile_path = repo / ".hermes" / "gate.toml"
    profile_path.write_text(
        profile_path.read_text(encoding="utf-8").replace(
            'argv = ["coderabbit", "review", "--agent"]',
            'argv = ["coderabbit", "review", "--agent", "--base", "main", "--base-commit", "deadbeef"]',
        ),
        encoding="utf-8",
    )
    provider_argv = _provider_review_argv(load_config(repo), repo, base=base)
    assert provider_argv[-3:] == ("--include-untracked", "--base-commit", base)
    assert "--committed" not in provider_argv
    assert "deadbeef" not in provider_argv

    monkeypatch.chdir(repo)
    assert cli_main(["fast", "--base", base]) == 0
    monkeypatch.setenv("HERMES_GATE_BASE", base)
    assert cli_main(["fast"]) == 0


def test_copied_runner_timeout_kills_process_group(tmp_path: Path) -> None:
    marker = tmp_path / "runner-descendant-survived"
    child_code = (
        "import signal, time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM, lambda *_: None); "
        f"time.sleep(0.8); Path({str(marker)!r}).write_text('bad')"
    )
    parent_code = (
        f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        "time.sleep(10)"
    )

    result = _execute([sys.executable, "-c", parent_code], tmp_path, 0.05, "probe")

    assert result["reason"] == "timeout"
    time.sleep(1)
    assert not marker.exists()


def test_tracked_runner_timeout_kills_process_group(tmp_path: Path) -> None:
    tracked_runner = Path(__file__).parents[1] / ".hermes" / "hermes_gate_runner.py"
    namespace = runpy.run_path(str(tracked_runner))
    assert tracked_runner.read_bytes() == (Path(__file__).parents[1] / "src/hermes_gate/repo_runner.py").read_bytes()

    marker = tmp_path / "tracked-runner-descendant-survived"
    child_code = (
        "import signal, time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM, lambda *_: None); "
        f"time.sleep(0.8); Path({str(marker)!r}).write_text('bad')"
    )
    parent_code = (
        f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        "time.sleep(10)"
    )

    result = namespace["_execute"](
        [sys.executable, "-c", parent_code], tmp_path, 0.05, "tracked-probe"
    )

    assert result["reason"] == "timeout"
    time.sleep(1)
    assert not marker.exists()


def test_copied_runner_tolerates_process_group_exiting_before_term(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ExitedProcess:
        pid = 43210
        returncode = None

        def __init__(self) -> None:
            self.stdout = io.BytesIO()
            self.stderr = io.BytesIO()

        def wait(self, timeout: float | None = None) -> int:
            self.returncode = 0
            return 0

        def poll(self) -> int | None:
            return self.returncode

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: ExitedProcess())
    monkeypatch.setattr(
        "hermes_gate.repo_runner.os.killpg",
        lambda *args: (_ for _ in ()).throw(ProcessLookupError()),
    )

    result = _execute(["probe"], tmp_path, 0.01, "probe")

    assert result == {"name": "probe", "argv": ["probe"], "status": "FAIL", "reason": "timeout"}


def test_preexisting_dirty_bytes_are_not_session_changes_until_edited(repo: Path) -> None:
    path = repo / "source.py"
    path.write_text("before = 1\n", encoding="utf-8")
    baseline = snapshot(repo)
    assert session_changed_paths(repo, baseline) == []
    path.write_text("after = 2\n", encoding="utf-8")
    assert session_changed_paths(repo, baseline) == ["source.py"]


def test_fast_receipt_is_cached_and_invalidated_after_edit(repo: Path) -> None:
    write_profile(repo)
    source = repo / "source.py"
    source.write_text("ok = True\n", encoding="utf-8")
    first = fast(repo)
    second = fast(repo)
    assert first["status"] == "PASS"
    assert second["status"] == "PASS" and second["cached"] is True
    assert first["receipt"]["command_versions"]
    original_digest = first["receipt"]["diff_sha256"]
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "checkpoint")
    assert valid_receipt(repo, "fast", diff_digest(repo)) is None
    after_commit = fast(repo)
    assert after_commit["receipt"]["repository"]["head"] != first["receipt"]["repository"]["head"]
    source.write_text("ok = False\n", encoding="utf-8")
    assert valid_receipt(repo, "fast", diff_digest(repo)) is None
    third = fast(repo)
    assert third["receipt"]["diff_sha256"] != original_digest


def test_fast_receipt_is_not_reused_across_explicit_bases(repo: Path) -> None:
    write_profile(repo)
    source = repo / "source.py"
    source.write_text("value = 'one'\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "first base")
    first_base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    source.write_text("value = 'two'\n", encoding="utf-8")
    git(repo, "commit", "-am", "second base")
    second_base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    source.write_text("value = 'current'\n", encoding="utf-8")
    git(repo, "commit", "-am", "current")

    first = fast(repo, files=["source.py"], base=first_base)
    second = fast(repo, files=["source.py"], base=second_base)

    assert first["status"] == second["status"] == "PASS"
    assert first["receipt"]["scope_base"] == first_base
    assert second["receipt"]["scope_base"] == second_base
    assert first["receipt"]["diff_sha256"] != second["receipt"]["diff_sha256"]
    assert second.get("cached") is None


def test_configured_fallback_receives_resolved_base(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_profile(repo)
    source = repo / "source.py"
    source.write_text("value = 'base'\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    source.write_text("value = 'head'\n", encoding="utf-8")
    git(repo, "commit", "-am", "head")
    profile_path = repo / ".hermes" / "gate.toml"
    profile_path.write_text(
        profile_path.read_text(encoding="utf-8").replace(
            "fallback_argv = []", f"fallback_argv = {json.dumps([sys.executable, '-c', 'pass'])}"
        ),
        encoding="utf-8",
    )
    calls: list[dict[str, object]] = []

    def fallback(argv: tuple[str, ...], **kwargs: object) -> Execution:
        calls.append(kwargs)
        return Execution(argv, 0, 0, '{"type":"complete"}\n', "")

    monkeypatch.setattr("hermes_gate.engine.run_argv", fallback)

    outcome = _fallback_review(load_config(repo), repo, "digest", base=base)

    assert outcome is not None
    assert any(call.get("env") == {"HERMES_GATE_BASE": base} for call in calls)


def test_snapshot_binds_symlink_identity_and_target_bytes(repo: Path) -> None:
    target = repo / "target.py"
    target.write_text("first = True\n", encoding="utf-8")
    link = repo / "link.py"
    link.symlink_to("target.py")
    first = snapshot(repo, ["link.py"])

    target.write_text("second = True\n", encoding="utf-8")
    second = snapshot(repo, ["link.py"])

    assert first["link.py"] != second["link.py"]


def test_snapshot_rejects_a_short_read_of_a_nonempty_file(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = repo / "source.py"
    source.write_bytes(b"declared bytes")
    original_open = Path.open

    def short_read(path: Path, *args: object, **kwargs: object) -> io.BytesIO | object:
        if path == source and (args[:1] == ("rb",) or kwargs.get("mode") == "rb"):
            return io.BytesIO(b"")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", short_read)

    with pytest.raises(ContentReadError, match="short read.*expected 14 bytes, got 0"):
        snapshot(repo, ["source.py"])


def test_snapshot_streams_declared_file_bytes(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = repo / "source.py"
    source.write_bytes(b"declared bytes")
    original_read_bytes = Path.read_bytes

    def no_read_bytes(path: Path) -> bytes:
        if path == source:
            raise AssertionError("snapshot must stream file bytes")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", no_read_bytes)

    assert snapshot(repo, ["source.py"])["source.py"] == "fb97a2ca3f3b9f557e8537aa5199ff34cdfd854e9492a52ba9c63ae1386a239f"


def test_fast_returns_error_without_receipt_for_a_short_read(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_profile(repo)
    source = repo / "source.py"
    source.write_bytes(b"declared bytes")
    original_open = Path.open

    def short_read(path: Path, *args: object, **kwargs: object) -> io.BytesIO | object:
        if path == source and (args[:1] == ("rb",) or kwargs.get("mode") == "rb"):
            return io.BytesIO(b"")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", short_read)

    outcome = fast(repo, files=["source.py"])

    assert outcome["status"] == Status.ERROR
    assert "short read" in outcome["reason"]
    assert "receipt" not in outcome


def test_snapshot_keeps_symlink_identity_when_target_is_unreadable(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = repo / "target.py"
    target.write_text("protected = True\n", encoding="utf-8")
    link = repo / "link.py"
    link.symlink_to("target.py")
    original = Path.open

    def unreadable(path: Path, *args: object, **kwargs: object) -> object:
        if path == link:
            raise PermissionError("fixture")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", unreadable)

    assert snapshot(repo, ["link.py"])["link.py"] == "SYMLINK:target.py:UNREADABLE:PermissionError"


def test_failed_check_maps_to_fail_and_boundary_rejects_stale_receipt(repo: Path) -> None:
    write_profile(repo, [sys.executable, "-c", "raise SystemExit(7)"])
    (repo / "source.py").write_text("bad = True\n", encoding="utf-8")
    assert fast(repo)["status"] == "FAIL"
    git(repo, "add", "source.py")
    outcome = boundary(repo, "commit")
    assert outcome["status"] == "FAIL"
    assert outcome["missing"] == ["fast"]


def test_commit_boundary_rejects_receipt_from_previous_head(repo: Path) -> None:
    write_profile(repo)
    git(repo, "add", ".hermes/gate.toml")
    git(repo, "commit", "-qm", "profile")
    source = repo / "source.py"
    source.write_text("value = 1\n", encoding="utf-8")
    assert fast(repo)["status"] == "PASS"
    notes = repo / "notes.md"
    notes.write_text("checkpoint\n", encoding="utf-8")
    git(repo, "add", "notes.md")
    git(repo, "commit", "-qm", "checkpoint")
    git(repo, "add", "source.py")

    outcome = boundary(repo, "commit")

    assert outcome["status"] == "FAIL"
    assert outcome["missing"] == ["fast"]


def test_repair_allows_one_attempt_for_unchanged_digest(repo: Path) -> None:
    write_profile(repo, repair_command=[sys.executable, "-c", "raise SystemExit(0)"])
    (repo / "source.py").write_text("x = 1\n", encoding="utf-8")
    assert repair(repo)["status"] == "PASS"
    assert repair(repo)["status"] == "PARKED"


def test_fast_global_budget_is_bounded(repo: Path) -> None:
    write_profile(repo, [sys.executable, "-c", "import time; time.sleep(10)"])
    profile = (
        (repo / ".hermes" / "gate.toml")
        .read_text(encoding="utf-8")
        .replace("fast_budget_seconds = 8.0", "fast_budget_seconds = 0.05")
    )
    (repo / ".hermes" / "gate.toml").write_text(profile, encoding="utf-8")
    (repo / "source.py").write_text("x = 1\n", encoding="utf-8")
    started = time.monotonic()
    assert fast(repo)["status"] == "FAIL"
    assert time.monotonic() - started < 1.5


def test_fast_command_version_probe_shares_global_budget(repo: Path) -> None:
    tool = repo / "slow-version-tool"
    tool.write_text(
        f"#!{sys.executable}\nimport sys,time\nif '--version' in sys.argv:\n    time.sleep(2)\n",
        encoding="utf-8",
    )
    tool.chmod(0o755)
    write_profile(repo, [str(tool)])
    profile_path = repo / ".hermes" / "gate.toml"
    profile_path.write_text(
        profile_path.read_text(encoding="utf-8").replace(
            "fast_budget_seconds = 8.0", "fast_budget_seconds = 0.5"
        ),
        encoding="utf-8",
    )
    (repo / "source.py").write_text("x = 1\n", encoding="utf-8")
    started = time.monotonic()
    outcome = fast(repo)
    assert outcome["status"] == "PASS"
    assert time.monotonic() - started < 1


def test_relative_check_command_has_accurate_version_receipt(repo: Path) -> None:
    tool = repo / "version-tool"
    tool.write_text(
        f"#!{sys.executable}\nimport sys\n"
        "print('version-tool 9.8.7' if '--version' in sys.argv else 'ok')\n",
        encoding="utf-8",
    )
    tool.chmod(0o755)
    write_profile(repo, ["./version-tool"])
    (repo / "source.py").write_text("x = 1\n", encoding="utf-8")

    outcome = fast(repo)

    assert outcome["status"] == "PASS"
    assert outcome["receipt"]["command_versions"]["./version-tool"] == "version-tool 9.8.7"


def test_relative_path_entry_version_probe_runs_discovered_executable(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    tool = bin_dir / "version-tool"
    tool.write_text(
        f"#!{sys.executable}\nprint('discovered 4.5.6')\n",
        encoding="utf-8",
    )
    tool.chmod(0o755)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "bin")

    assert _tool_version("version-tool", repo) == "discovered 4.5.6"


def test_conditional_lintlang_runs_once_for_ai_files_and_zero_for_source(repo: Path) -> None:
    counter = repo / ".git" / "lintlang-count.txt"
    lint_command = [
        sys.executable,
        "-c",
        f"from pathlib import Path; p=Path({str(counter)!r}); p.write_text(str(int(p.read_text())+1) if p.exists() else '1')",
    ]
    write_profile(repo)
    profile_path = repo / ".hermes" / "gate.toml"
    profile = profile_path.read_text(encoding="utf-8")
    profile = profile.replace("enabled = false", "enabled = true", 1)
    profile = profile.replace(
        'argv = ["lintlang", "scan", "{files}"]', f"argv = {json.dumps(lint_command)}"
    )
    profile = profile.replace("trigger_globs = []", 'trigger_globs = ["**/AGENTS.md"]')
    profile_path.write_text(profile, encoding="utf-8")
    (repo / "source.py").write_text("x = 1\n", encoding="utf-8")
    assert fast(repo, files=["source.py"])["status"] == "PASS"
    assert not counter.exists()
    (repo / "AGENTS.md").write_text("agent guidance\n", encoding="utf-8")
    assert fast(repo, files=["AGENTS.md"])["status"] == "PASS"
    assert fast(repo, files=["AGENTS.md"])["status"] == "PASS"
    assert counter.read_text(encoding="utf-8") == "1"


def test_lintlang_skips_deleted_trigger_paths(repo: Path) -> None:
    lint_command = [
        sys.executable,
        "-c",
        "from pathlib import Path; import sys; [Path(path).read_text() for path in sys.argv[1:]]",
        "{files}",
    ]
    write_profile(repo)
    profile_path = repo / ".hermes" / "gate.toml"
    profile = profile_path.read_text(encoding="utf-8")
    profile = profile.replace("enabled = false", "enabled = true", 1)
    profile = profile.replace(
        'argv = ["lintlang", "scan", "{files}"]', f"argv = {json.dumps(lint_command)}"
    )
    profile = profile.replace("trigger_globs = []", 'trigger_globs = ["**/AGENTS.md"]')
    profile_path.write_text(profile, encoding="utf-8")
    guidance = repo / "AGENTS.md"
    guidance.write_text("agent guidance\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "baseline")
    guidance.unlink()

    outcome = fast(repo)

    assert outcome["status"] == "NOT_APPLICABLE"


def test_review_nonzero_exit_never_creates_pass_receipt(repo: Path) -> None:
    write_profile(repo)
    profile_path = repo / ".hermes" / "gate.toml"
    provider_argv = [
        sys.executable,
        "-c",
        'print(\'{"type":"complete"}\'); raise SystemExit(7)',
    ]
    profile = profile_path.read_text(encoding="utf-8").replace(
        'argv = ["coderabbit", "review", "--agent"]',
        f"argv = {json.dumps(provider_argv)}",
    )
    profile_path.write_text(profile, encoding="utf-8")
    (repo / "source.py").write_text("ok = True\n", encoding="utf-8")

    assert fast(repo)["status"] == "PASS"
    assert review(repo)["status"] == "REVIEW_UNAVAILABLE"


def test_review_receipt_preserves_unusable_fallback_metadata(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_profile(repo)
    git(repo, "add", ".hermes/gate.toml")
    git(repo, "commit", "-qm", "profile")
    profile_path = repo / ".hermes" / "gate.toml"
    fallback_argv = [sys.executable, "-c", "print('{\"type\":\"error\"}')"]
    profile = profile_path.read_text(encoding="utf-8").replace(
        "fallback_argv = []", f"fallback_argv = {json.dumps(fallback_argv)}"
    )
    profile_path.write_text(profile, encoding="utf-8")
    (repo / "source.py").write_text("ok = True\n", encoding="utf-8")
    assert fast(repo)["status"] == "PASS"
    calls: list[tuple[str, ...]] = []

    def provider(argv: tuple[str, ...], **kwargs: object) -> Execution:
        calls.append(argv)
        return Execution(argv, 0, 0, '{"type":"error"}\n', "")

    monkeypatch.setattr("hermes_gate.engine.run_argv", provider)
    outcome = review(repo)

    assert outcome["status"] == "REVIEW_UNAVAILABLE"
    receipt = outcome["receipt"]
    assert receipt["fallback_attempted"] is True
    assert receipt["fallback_provider"] == sys.executable
    assert receipt["fallback_reason"]
    assert any(argv[0] == sys.executable for argv in calls)


def test_review_skips_automatic_fallback_for_empty_comparison(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_profile(repo)
    (repo / "source.py").write_text("ok = True\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "only commit")
    assert fast(repo)["status"] == "PASS"
    calls: list[tuple[str, ...]] = []

    def provider(argv: tuple[str, ...], **kwargs: object) -> Execution:
        calls.append(argv)
        return Execution(argv, 0, 0, '{"type":"error"}\n', "")

    monkeypatch.setattr("hermes_gate.engine.shutil.which", lambda *a, **kw: "/usr/bin/hermes-pr-review")
    monkeypatch.setattr("hermes_gate.engine._tool_version", lambda *args, **kwargs: "test")
    monkeypatch.setattr("hermes_gate.engine.run_argv", provider)
    outcome = review(repo)

    assert outcome["status"] == "REVIEW_UNAVAILABLE"
    assert not any(argv[0] == "hermes-pr-review" for argv in calls)
    assert calls[-1][0] == "coderabbit"
    assert outcome["receipt"]["fallback_attempted"] is False
    assert outcome["receipt"]["fallback_provider"] == ""
    assert outcome["receipt"]["fallback_reason"] == ""


def test_review_runs_automatic_fallback_for_nonempty_comparison(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_profile(repo)
    source = repo / "source.py"
    source.write_text("value = 'base'\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    base = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    source.write_text("value = 'head'\n", encoding="utf-8")
    git(repo, "commit", "-am", "head")
    assert fast(repo, base=base)["status"] == "PASS"
    calls: list[tuple[str, ...]] = []

    def provider(argv: tuple[str, ...], **kwargs: object) -> Execution:
        calls.append(argv)
        if argv[0] == "hermes-pr-review":
            output_dir = Path(argv[argv.index("--output-dir") + 1])
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "review.json").write_text(
                '{"verdict":"PASS","findings":[]}\n', encoding="utf-8"
            )
            return Execution(argv, 0, 0, "", "")
        return Execution(argv, 0, 0, '{"type":"error"}\n', "")

    monkeypatch.setattr("hermes_gate.engine.shutil.which", lambda *a, **kw: "/usr/bin/hermes-pr-review")
    monkeypatch.setattr("hermes_gate.engine._tool_version", lambda *args, **kwargs: "test")
    monkeypatch.setattr("hermes_gate.engine.run_argv", provider)
    outcome = review(repo, base=base)

    assert outcome["status"] == "PASS"
    fallback_call = next(argv for argv in calls if argv[0] == "hermes-pr-review")
    assert fallback_call[fallback_call.index("--base") + 1] == base
    assert outcome["receipt"]["provider"] == "hermes-pr-review"
    assert outcome["receipt"]["fallback_attempted"] is True
    assert outcome["receipt"]["fallback_provider"] == "hermes-pr-review"
    assert outcome["receipt"]["fallback_reason"] == ""


def test_boundary_rejects_invalid_profile_for_non_code_commit(repo: Path) -> None:
    write_profile(repo)
    profile_path = repo / ".hermes" / "gate.toml"
    profile_path.write_text(
        profile_path.read_text(encoding="utf-8").replace(
            'provider = "coderabbit"', 'provider = "hermes-pr-review"'
        ),
        encoding="utf-8",
    )
    (repo / "README.md").write_text("documentation only\n", encoding="utf-8")
    git(repo, "add", "README.md")

    outcome = boundary(repo, "commit")

    assert outcome["status"] == "ERROR"
    assert outcome["reason"].startswith("invalid profile:")
def test_jsonl_provider_passes_exact_diff_and_writes_receipt(repo: Path) -> None:
    write_profile(repo)
    profile_path = repo / ".hermes" / "gate.toml"
    code = (
        "import json, os; "
        "print(json.dumps({'type':'complete', 'digest':os.environ['HERMES_GATE_DIFF_DIGEST'], "
        "'reviewed_paths':json.loads(os.environ['HERMES_GATE_REVIEWED_PATHS'])}))"
    )
    profile_path.write_text(
        profile_path.read_text(encoding="utf-8")
        .replace('provider = "coderabbit"', 'provider = "jsonl"')
        .replace('argv = ["coderabbit", "review", "--agent"]',
                 f"argv = {json.dumps([sys.executable, '-c', code])}"),
        encoding="utf-8",
    )
    (repo / "source.py").write_text("value = 1\n", encoding="utf-8")
    assert fast(repo)["status"] == "PASS"
    result = review(repo)
    assert result["status"] == "PASS"
    assert result["receipt"]["provider"] == "jsonl"
    assert result["receipt"]["diff_sha256"] == diff_digest(repo)


def test_jsonl_timeout_with_complete_stdout_is_unavailable(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_profile(repo)
    profile_path = repo / ".hermes" / "gate.toml"
    profile_path.write_text(
        profile_path.read_text(encoding="utf-8")
        .replace('provider = "coderabbit"', 'provider = "jsonl"'),
        encoding="utf-8",
    )
    (repo / "source.py").write_text("value = 1\n", encoding="utf-8")
    assert fast(repo)["status"] == "PASS"

    def timed_out(argv: tuple[str, ...], **kwargs: object) -> Execution:
        env = kwargs["env"]
        assert isinstance(env, dict)
        complete = json.dumps(
            {"type": "complete", "digest": env["HERMES_GATE_DIFF_DIGEST"],
             "reviewed_paths": json.loads(env["HERMES_GATE_REVIEWED_PATHS"])}
        )
        return Execution(argv, None, 1, complete, "", timed_out=True)

    monkeypatch.setattr("hermes_gate.engine._tool_version", lambda *args, **kwargs: "test")
    monkeypatch.setattr("hermes_gate.engine.run_argv", timed_out)
    outcome = review(repo)
    assert outcome["status"] == "REVIEW_UNAVAILABLE"
    assert outcome["receipt"]["status"] == "REVIEW_UNAVAILABLE"


def test_review_cannot_reuse_pass_from_another_provider(repo: Path) -> None:
    write_profile(repo)
    source = repo / "source.py"
    source.write_text("value = 1\n", encoding="utf-8")
    assert fast(repo)["status"] == "PASS"
    profile_path = repo / ".hermes" / "gate.toml"
    profile_path.write_text(
        profile_path.read_text(encoding="utf-8")
        .replace('provider = "coderabbit"', 'provider = "jsonl"')
        .replace('argv = ["coderabbit", "review", "--agent"]', 'argv = ["missing-wrapper"]'),
        encoding="utf-8",
    )
    assert fast(repo)["status"] == "PASS"
    digest = diff_digest(repo)
    from hermes_gate.receipts import write_receipt

    write_receipt(repo, "review", status="PASS", digest=digest, elapsed_ms=1,
                  extra={"provider": "coderabbit"})
    assert boundary(repo, "push")["status"] == "FAIL"
    assert review(repo)["status"] == "REVIEW_UNAVAILABLE"


def test_jsonl_provider_has_own_review_attempt_budget(repo: Path) -> None:
    write_profile(repo)
    profile_path = repo / ".hermes" / "gate.toml"
    code = (
        "import json, os; "
        "print(json.dumps({'type':'complete', 'digest':os.environ['HERMES_GATE_DIFF_DIGEST'], "
        "'reviewed_paths':json.loads(os.environ['HERMES_GATE_REVIEWED_PATHS'])}))"
    )
    profile_path.write_text(
        profile_path.read_text(encoding="utf-8")
        .replace('provider = "coderabbit"', 'provider = "jsonl"')
        .replace('argv = ["coderabbit", "review", "--agent"]',
                 f"argv = {json.dumps([sys.executable, '-c', code])}"),
        encoding="utf-8",
    )
    (repo / "source.py").write_text("value = 1\n", encoding="utf-8")
    assert fast(repo)["status"] == "PASS"
    digest = diff_digest(repo)
    _state_file(repo, "review-budget.json").write_text(
        json.dumps({"attempts_by_digest": {digest: 2}}), encoding="utf-8"
    )
    assert review(repo)["status"] == "PASS"


def test_legacy_coderabbit_fallback_receipt_keeps_valid_provider_identity() -> None:
    fallback = {"provider": "hermes-pr-review"}
    assert _review_provider_matches(fallback, "coderabbit")
    assert not _review_provider_matches(fallback, "jsonl")
    assert _review_provider_matches({**fallback, "configured_provider": "coderabbit"}, "coderabbit")


def test_review_unavailable_does_not_consume_semantic_attempt(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_profile(repo)
    (repo / "source.py").write_text("ok = True\n", encoding="utf-8")
    assert fast(repo)["status"] == "PASS"
    calls = 0

    def provider(*args: object, **kwargs: object) -> Execution:
        nonlocal calls
        calls += 1
        output = '{"type":"error"}' if calls <= 2 else '{"type":"complete"}'
        return Execution(("provider",), 0, 0, output, "")

    monkeypatch.setattr("hermes_gate.engine._tool_version", lambda *args, **kwargs: "test")
    monkeypatch.setattr("hermes_gate.engine.run_argv", provider)

    # Two unavailable results would exhaust the budget if either consumed an attempt.
    assert review(repo)["status"] == "REVIEW_UNAVAILABLE"
    assert review(repo)["status"] == "REVIEW_UNAVAILABLE"
    assert review(repo)["status"] == "PASS"


def test_review_budget_is_scoped_to_current_digest(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_profile(repo)
    (repo / "source.py").write_text("ok = True\n", encoding="utf-8")
    assert fast(repo)["status"] == "PASS"
    _state_file(repo, "review-budget.json").write_text(
        json.dumps({"digests": ["stale-digest-a", "stale-digest-b"]}), encoding="utf-8"
    )
    monkeypatch.setattr("hermes_gate.engine._tool_version", lambda *args, **kwargs: "test")
    monkeypatch.setattr(
        "hermes_gate.engine.run_argv",
        lambda *args, **kwargs: Execution(("provider",), 0, 0, '{"type":"complete"}', ""),
    )

    assert review(repo)["status"] == "PASS"


def test_review_parks_after_two_completed_attempts_on_current_digest(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_profile(repo)
    (repo / "source.py").write_text("ok = True\n", encoding="utf-8")
    assert fast(repo)["status"] == "PASS"
    finding = json.dumps(
        {"type": "finding", "severity": "critical", "category": "correctness", "message": "bug"}
    )
    calls = 0

    def provider(*args: object, **kwargs: object) -> Execution:
        nonlocal calls
        calls += 1
        return Execution(("provider",), 0, 0, f'{finding}\n{{"type":"complete"}}', "")

    monkeypatch.setattr("hermes_gate.engine._tool_version", lambda *args, **kwargs: "test")
    monkeypatch.setattr("hermes_gate.engine.run_argv", provider)

    assert review(repo)["status"] == "FAIL"
    assert review(repo)["status"] == "FAIL"
    assert review(repo)["status"] == "PARKED"
    assert calls == 2


def test_coderabbit_argv_binds_dirty_and_committed_boundaries(repo: Path) -> None:
    write_profile(repo)
    source = repo / "source.py"
    source.write_text("value = 1\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    source.write_text("value = 2\n", encoding="utf-8")
    config = load_config(repo)
    branch = subprocess.run(
        ["git", "-C", str(repo), "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    dirty = _provider_review_argv(config, repo)
    assert dirty[-5:] == (
        "--include-untracked",
        "--base",
        branch,
        "--base-commit",
        "HEAD",
    )

    git(repo, "add", "source.py")
    git(repo, "commit", "-qm", "change")
    committed = _provider_review_argv(config, repo)
    assert committed[-2] == "--base-commit"
    assert (
        committed[-1]
        == subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD^"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    assert "--committed" in committed
    assert committed[committed.index("--base") + 1] == branch


def test_coderabbit_argv_preserves_inline_base_configuration(repo: Path) -> None:
    write_profile(repo)
    profile_path = repo / ".hermes" / "gate.toml"
    profile_path.write_text(
        profile_path.read_text(encoding="utf-8").replace(
            'argv = ["coderabbit", "review", "--agent"]',
            'argv = ["coderabbit", "review", "--agent", "--base=main"]',
        ),
        encoding="utf-8",
    )

    argv = _provider_review_argv(load_config(repo), repo)

    assert argv == ("coderabbit", "review", "--agent", "--base=main")


def test_config_rejects_unsupported_review_provider(repo: Path) -> None:
    write_profile(repo)
    profile_path = repo / ".hermes" / "gate.toml"
    profile_path.write_text(
        profile_path.read_text(encoding="utf-8")
        .replace('provider = "coderabbit"', 'provider = "hermes-pr-review"')
        .replace('argv = ["coderabbit", "review", "--agent"]', 'argv = ["hermes-pr-review"]'),
        encoding="utf-8",
    )
    (repo / "source.py").write_text("ok = True\n", encoding="utf-8")

    with pytest.raises(ConfigError, match=r'review\.provider "hermes-pr-review".*supported: coderabbit'):
        load_config(repo)
    for command in (fast, review):
        outcome = command(repo)
        assert outcome["status"] == "ERROR"
        assert outcome["reason"].startswith("invalid profile: review.provider")
    assert read_receipt(repo, "fast") is None


def test_config_accepts_alternate_executable_for_coderabbit_provider(repo: Path) -> None:
    write_profile(repo)
    profile_path = repo / ".hermes" / "gate.toml"
    profile_path.write_text(
        profile_path.read_text(encoding="utf-8").replace(
            'argv = ["coderabbit", "review", "--agent"]', 'argv = ["cr", "review", "--agent"]'
        ),
        encoding="utf-8",
    )

    config = load_config(repo)

    assert config.review.provider == "coderabbit"
    assert config.review.argv[0] == "cr"
