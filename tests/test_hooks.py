from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from hermes_gate import hooks
from hermes_gate.hooks import pre_tool_use, session_start, stop
from hermes_gate.init_repo import initialize


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    return root


def test_non_git_and_read_only_session_exit_immediately(tmp_path: Path) -> None:
    payload = {"cwd": str(tmp_path), "session_id": "s", "source": "startup"}
    assert session_start(payload) == {"continue": True}
    assert stop(payload) == {"continue": True}


def test_stop_is_advisory_and_reuses_receipt(tmp_path: Path, monkeypatch) -> None:
    root = repo(tmp_path)
    (root / ".hermes").mkdir()
    (root / ".hermes" / "gate.toml").write_text(
        f"""[gate]
fast_budget_seconds = 8.0
full_required_local = false
exclusions = [".git/**"]
[lintlang]
enabled = false
argv = ["lintlang", "scan", "{{files}}"]
trigger_globs = []
[review]
argv = ["coderabbit", "--agent"]
material_severities = ["critical", "major"]
material_categories = ["correctness"]
fallback_argv = []
[[fast]]
name = "pass"
argv = {json.dumps([sys.executable, "-c", "raise SystemExit(0)"])}
timeout_seconds = 1.0
globs = ["**/*"]
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    payload = {"cwd": str(root), "session_id": "s", "source": "startup"}
    session_start(payload)
    (root / "source.py").write_text("x = 1\n", encoding="utf-8")
    first = stop({"cwd": str(root), "session_id": "s", "stop_hook_active": False})
    second = stop({"cwd": str(root), "session_id": "s", "stop_hook_active": True})
    assert first == {"continue": True}
    assert second == {"continue": True}
    assert not (root / ".hermes" / "receipt.json").exists()


def test_pretool_blocks_real_commit_but_not_quoted_prose(tmp_path: Path) -> None:
    root = repo(tmp_path)
    assert initialize(root)["status"] == "PASS"
    (root / "source.py").write_text("x = 1\n", encoding="utf-8")
    git(root, "add", "source.py")
    quoted = pre_tool_use(
        {"cwd": str(root), "tool_name": "Bash", "tool_input": {"command": "echo 'git commit -m x'"}}
    )
    blocked = pre_tool_use(
        {"cwd": str(root), "tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}
    )
    assert quoted == {}
    assert blocked["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "matching fast PASS receipt" in blocked["hookSpecificOutput"]["permissionDecisionReason"]


def test_pretool_allows_push_from_never_adopted_repository(tmp_path: Path) -> None:
    """A global hook must not enroll unrelated repositories by blocking their push."""
    root = repo(tmp_path)
    (root / "source.py").write_text("x = 1\n", encoding="utf-8")

    output = pre_tool_use(
        {"cwd": str(root), "tool_name": "Bash", "tool_input": {"command": "git push origin main"}}
    )

    assert output == {}


def test_pretool_keeps_adopted_repository_fail_closed_when_profile_is_missing(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    assert initialize(root)["status"] == "PASS"
    (root / ".hermes" / "gate.toml").unlink()
    (root / "source.py").write_text("x = 1\n", encoding="utf-8")

    output = pre_tool_use(
        {"cwd": str(root), "tool_name": "Bash", "tool_input": {"command": "git push origin main"}}
    )

    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "hermes-gate init" in output["hookSpecificOutput"]["permissionDecisionReason"]


def test_non_code_commit_is_exempt_without_profile(tmp_path: Path) -> None:
    root = repo(tmp_path)
    (root / "README.md").write_text("docs\n", encoding="utf-8")
    git(root, "add", "README.md")
    output = pre_tool_use(
        {"cwd": str(root), "tool_name": "Bash", "tool_input": {"command": "git commit -m docs"}}
    )
    assert output == {}


def test_pretool_blocks_shell_wrapped_commit(tmp_path: Path) -> None:
    root = repo(tmp_path)
    assert initialize(root)["status"] == "PASS"
    (root / "source.py").write_text("x = 1\n", encoding="utf-8")
    git(root, "add", "source.py")
    output = pre_tool_use(
        {
            "cwd": str(root),
            "tool_name": "Bash",
            "tool_input": {"command": "zsh -c 'git commit -m x'"},
        }
    )
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_pretool_validates_repository_selected_by_git_c(tmp_path: Path, monkeypatch) -> None:
    outer = repo(tmp_path)
    selected = tmp_path / "selected"
    selected.mkdir()
    git(selected, "init", "-q")
    captured: dict[str, object] = {}

    def fake_boundary(root: Path, action: str) -> dict[str, object]:
        captured.update(root=root, action=action)
        return {"status": "PASS"}

    monkeypatch.setattr(hooks, "boundary", fake_boundary)
    output = pre_tool_use(
        {
            "cwd": str(outer),
            "tool_name": "Bash",
            "tool_input": {"command": f"git -C {selected} commit -m x"},
        }
    )
    assert output == {}
    assert captured == {"root": selected.resolve(), "action": "commit"}


def test_pretool_safely_denies_unresolvable_git_c_repository(tmp_path: Path) -> None:
    outer = repo(tmp_path)
    output = pre_tool_use(
        {
            "cwd": str(outer),
            "tool_name": "Bash",
            "tool_input": {"command": "git -C does-not-exist push origin main"},
        }
    )
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "selected by git -C" in output["hookSpecificOutput"]["permissionDecisionReason"]
