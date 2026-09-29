from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from hermes_gate import init_repo
from hermes_gate.engine import fast
from hermes_gate.gitstate import ContentReadError, git_dir
from hermes_gate.init_repo import initialize, uninstall, verify_runner


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_init_generates_checksum_bound_runner_and_rollback(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    (root / "pyproject.toml").write_text(
        "[project]\nname='fixture'\nversion='0'\n", encoding="utf-8"
    )
    (root / "src").mkdir()
    outcome = initialize(root)
    assert outcome["status"] == "PASS"
    manifest_path = git_dir(root) / "hermes-gate" / "install.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert not (root / ".hermes" / "install.json").exists()
    runner = root / ".hermes" / "hermes_gate_runner.py"
    assert manifest["runner_sha256"] == hashlib.sha256(runner.read_bytes()).hexdigest()
    assert verify_runner(root)[0]
    assert "shell" not in (root / ".hermes" / "gate.toml").read_text(encoding="utf-8")
    assert "compileall" not in (root / ".hermes" / "gate.toml").read_text(encoding="utf-8")
    assert "sys.path.insert(0, 'src')" in (root / ".hermes" / "gate.toml").read_text(
        encoding="utf-8"
    )
    workflow = (root / ".github" / "workflows" / "hermes-quality.yml").read_text(encoding="utf-8")
    assert "python3 -m pip install -e '.'" in workflow
    assert "ruff" in workflow and "pytest" in workflow
    rolled_back = uninstall(root)
    assert rolled_back["status"] == "PASS"
    assert not runner.exists()


def test_init_refuses_overwrite_without_force(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    (root / ".hermes").mkdir()
    (root / ".hermes" / "gate.toml").write_text("owner bytes\n", encoding="utf-8")
    outcome = initialize(root)
    assert outcome["status"] == "PARKED"
    assert (root / ".hermes" / "gate.toml").read_text(encoding="utf-8") == "owner bytes\n"


def test_init_refuses_dangling_integration_symlink_even_when_forced(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    profile = root / ".hermes" / "gate.toml"
    profile.parent.mkdir()
    profile.symlink_to("missing-profile.toml")

    outcome = initialize(root, force=True)

    assert outcome["status"] == "PARKED"
    assert outcome["existing"] == [".hermes/gate.toml"]
    assert profile.is_symlink()
    assert not (profile.parent / "missing-profile.toml").exists()


def test_init_parks_without_manifest_when_post_write_snapshot_is_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    profile = root / ".hermes" / "gate.toml"
    profile.parent.mkdir()
    profile.write_text("owner profile\n", encoding="utf-8")
    original_snapshot = init_repo.snapshot
    calls = 0

    def interrupted_snapshot(*args: object, **kwargs: object) -> dict[str, str]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ContentReadError("short read for generated profile")
        return original_snapshot(*args, **kwargs)

    monkeypatch.setattr(init_repo, "snapshot", interrupted_snapshot)

    outcome = initialize(root, force=True)

    assert outcome["status"] == "PARKED"
    assert "was rolled back" in outcome["reason"]
    assert profile.read_text(encoding="utf-8") == "owner profile\n"
    assert not (root / ".hermes" / "hermes_gate_runner.py").exists()
    assert not (root / ".github" / "workflows" / "hermes-quality.yml").exists()
    assert not (git_dir(root) / "hermes-gate" / "install.json").exists()
    assert not (git_dir(root) / "hermes-gate" / "baseline.json").exists()


def test_uninstall_preflights_all_targets_before_restoring_any(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    profile = root / ".hermes" / "gate.toml"
    profile.parent.mkdir()
    profile.write_text("owner profile\n", encoding="utf-8")
    assert initialize(root, force=True)["status"] == "PASS"

    # Workflow follows the profile in manifest insertion order.  Its edit must
    # prevent restoration of the backed-up profile as well as all later work.
    workflow = root / ".github" / "workflows" / "hermes-quality.yml"
    workflow.write_text(workflow.read_text(encoding="utf-8") + "# local edit\n", encoding="utf-8")
    outcome = uninstall(root)

    assert outcome["status"] == "PARKED"
    assert profile.read_text(encoding="utf-8") != "owner profile\n"
    assert (git_dir(root) / "hermes-gate" / "install.json").exists()


def test_uninstall_accepts_legacy_worktree_manifest(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    assert initialize(root)["status"] == "PASS"
    current = git_dir(root) / "hermes-gate" / "install.json"
    legacy = root / ".hermes" / "install.json"
    legacy.write_bytes(current.read_bytes())
    current.unlink()

    outcome = uninstall(root)

    assert outcome["status"] == "PASS"
    assert not legacy.exists()


def test_generated_runner_and_central_fast_have_status_parity(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    (root / "pyproject.toml").write_text(
        "[project]\nname='fixture'\nversion='0'\n", encoding="utf-8"
    )
    (root / "source.py").write_text("value = 1\n", encoding="utf-8")
    assert initialize(root)["status"] == "PASS"
    central = fast(root)
    proc = subprocess.run(
        [sys.executable, str(root / ".hermes" / "hermes_gate_runner.py"), "fast"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    generated = json.loads(proc.stdout)
    assert central["status"] == generated["status"] == "PASS"


@pytest.mark.parametrize("relative", [
    ".hermes/gate.toml",
    ".hermes/hermes_gate_runner.py",
    ".github/workflows/hermes-quality.yml",
])
@pytest.mark.parametrize("force", [False, True])
def test_init_rolls_back_truncation_before_manifest_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative: str, force: bool
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    target = root / relative
    if force:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"owner bytes\n")
    original_write_text = Path.write_text
    original_write_bytes = Path.write_bytes

    def truncate(path: Path) -> None:
        if path == target:
            with path.open("r+b") as handle:
                handle.truncate(1)

    def write_text(path: Path, *args: object, **kwargs: object) -> int:
        result = original_write_text(path, *args, **kwargs)
        truncate(path)
        return result

    def write_bytes(path: Path, data: bytes) -> int:
        result = original_write_bytes(path, data)
        truncate(path)
        return result

    monkeypatch.setattr(Path, "write_text", write_text)
    monkeypatch.setattr(Path, "write_bytes", write_bytes)

    outcome = initialize(root, force=force)

    assert outcome["status"] == "PARKED"
    assert "was rolled back" in outcome["reason"]
    for generated in (".hermes/gate.toml", ".hermes/hermes_gate_runner.py",
                      ".github/workflows/hermes-quality.yml"):
        path = root / generated
        if force and path == target:
            assert path.read_bytes() == b"owner bytes\n"
        else:
            assert not path.exists()
    state = git_dir(root) / "hermes-gate"
    assert not (state / "install.json").exists()
    assert not (state / "baseline.json").exists()



def test_init_preserves_existing_symlink_identity_when_forced(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    profile = root / ".hermes" / "gate.toml"
    profile.parent.mkdir()
    (profile.parent / "owner.toml").write_bytes(b"owner profile\n")
    profile.symlink_to("./owner.toml")

    assert initialize(root, force=True)["status"] == "PASS"
    assert profile.is_symlink()
    assert uninstall(root)["status"] == "PASS"
    assert profile.read_bytes() == b"owner profile\n"
