from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from hermes_gate import gitstate
from hermes_gate.workflow import run


def test_git_queries_disable_optional_monitor_and_bound_expected_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timed_out(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        assert argv[:5] == ["git", "-C", str(tmp_path), "-c", "core.fsmonitor=false"]
        assert kwargs["timeout"] == gitstate.GIT_TIMEOUT_SECONDS
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(gitstate.subprocess, "run", timed_out)
    with pytest.raises(gitstate.GitError, match="timed out"):
        gitstate.git(tmp_path, "rev-parse", "HEAD", check=False)


def test_hanging_git_discovery_still_issues_a_failure_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = tmp_path / "tools"
    tools.mkdir()
    fake_git = tools / "git"
    fake_git.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(30)\n")
    fake_git.chmod(0o755)
    monkeypatch.setenv("PATH", str(tools) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(gitstate, "GIT_TIMEOUT_SECONDS", 0.05)
    started = time.monotonic()
    result = run(tmp_path)
    assert time.monotonic() - started < 2
    assert result["status"] == "FAIL"
    assert "timed out" in result["reason"]
    saved = Path(result["receipt_path"])
    assert saved.is_file()
    assert json.loads(saved.read_text()) == result["receipt"]
