"""The optional Claude adapter must send only the selected local patch."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from hermes_gate.claude_review import _fixture_diff, _selected_diff, main
from hermes_gate.gitstate import scope_paths


def test_selected_diff_includes_untracked_and_excludes_other_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    (tmp_path / "tracked.py").write_text("value = 1\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "base"], check=True)
    (tmp_path / "tracked.py").write_text("value = 2\n")
    (tmp_path / "new.py").write_text("fresh = True\n")
    (tmp_path / "other.py").write_text("secret = 'outside scope'\n")
    monkeypatch.chdir(tmp_path)
    diff = _selected_diff(["tracked.py", "new.py"])
    assert "+value = 2" in diff
    assert "+fresh = True" in diff
    assert "outside scope" not in diff


def test_saved_diff_rejects_non_patch_payload(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps([{"filename": "x.py", "diff": "patch"}]))
    assert _fixture_diff(fixture) == "patch"
    fixture.write_text(json.dumps([{"filename": "x.py", "diff": 12}]))
    with pytest.raises(ValueError, match="fixture"):
        _fixture_diff(fixture)


def test_public_console_rejects_saved_diff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = tmp_path / "old.json"
    fixture.write_text(json.dumps([{"diff": "+stale"}]))
    monkeypatch.setattr(sys, "argv", ["hermes-gate-claude-review", "--diff-file", str(fixture)])
    assert main() == 2
    output = capsys.readouterr()
    assert "usage: hermes-gate-claude-review" in output.err
    assert '"type": "complete"' not in output.out


def test_committed_diff_uses_same_no_upstream_base_as_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    (tmp_path / "first.py").write_text("first = 1\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "first"], check=True)
    (tmp_path / "first.py").write_text("first = 2\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "second"], check=True)
    (tmp_path / "second.py").write_text("second = 3\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "third"], check=True)
    monkeypatch.chdir(tmp_path)
    selected = scope_paths(tmp_path)
    assert selected == ["second.py"]
    diff = _selected_diff(selected)
    assert "+second = 3" in diff
    assert "first = 2" not in diff
