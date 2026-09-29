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


@pytest.mark.parametrize("relative", [
    ".hermes/gate.toml",
    ".hermes/hermes_gate_runner.py",
    ".github/workflows/hermes-quality.yml",
])
def test_init_force_refuses_external_integration_symlink(tmp_path: Path, relative: str) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    external = tmp_path / "outside"
    external.write_bytes(b"owner bytes\n")
    target.symlink_to(external)

    outcome = initialize(root, force=True)

    assert outcome["status"] == "PARKED"
    assert target.is_symlink()
    assert external.read_bytes() == b"owner bytes\n"
    assert not (git_dir(root) / "hermes-gate" / "install.json").exists()


@pytest.mark.parametrize("relative", [
    ".hermes/gate.toml",
    ".hermes/hermes_gate_runner.py",
    ".github/workflows/hermes-quality.yml",
])
def test_uninstall_refuses_external_integration_symlink(tmp_path: Path, relative: str) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"owner bytes\n")
    assert initialize(root, force=True)["status"] == "PASS"
    generated = target.read_bytes()
    external = tmp_path / "outside"
    external.write_bytes(generated)
    target.unlink()
    target.symlink_to(external)

    outcome = uninstall(root)

    assert outcome["status"] == "PARKED"
    assert target.is_symlink()
    assert external.read_bytes() == generated
    assert (git_dir(root) / "hermes-gate" / "install.json").exists()


def test_uninstall_refuses_external_integration_parent(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    profile = root / ".hermes" / "gate.toml"
    profile.parent.mkdir()
    profile.write_bytes(b"owner profile\n")
    assert initialize(root, force=True)["status"] == "PASS"
    outside = tmp_path / "outside-hermes"
    profile.parent.rename(outside)
    profile.parent.symlink_to(outside, target_is_directory=True)
    generated = (outside / "gate.toml").read_bytes()

    outcome = uninstall(root)

    assert outcome["status"] == "PARKED"
    assert (outside / "gate.toml").read_bytes() == generated
    assert (outside / "hermes_gate_runner.py").exists()
    assert (git_dir(root) / "hermes-gate" / "install.json").exists()


def test_init_force_refuses_external_backup_destination(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    profile = root / ".hermes" / "gate.toml"
    profile.parent.mkdir()
    profile.write_bytes(b"owner profile\n")
    backup = git_dir(root) / "hermes-gate" / "install-backup" / ".hermes" / "gate.toml"
    backup.parent.mkdir(parents=True)
    external = tmp_path / "outside-backup"
    external.write_bytes(b"outside sentinel\n")
    backup.symlink_to(external)

    outcome = initialize(root, force=True)

    assert outcome["status"] == "PARKED"
    assert external.read_bytes() == b"outside sentinel\n"
    assert profile.read_bytes() == b"owner profile\n"
    assert not (git_dir(root) / "hermes-gate" / "install.json").exists()


def test_uninstall_refuses_symlinked_backup_source(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    profile = root / ".hermes" / "gate.toml"
    profile.parent.mkdir()
    profile.write_bytes(b"owner profile\n")
    assert initialize(root, force=True)["status"] == "PASS"
    generated = profile.read_bytes()
    backup = git_dir(root) / "hermes-gate" / "install-backup" / ".hermes" / "gate.toml"
    external = tmp_path / "outside-backup"
    external.write_bytes(backup.read_bytes())
    backup.unlink()
    backup.symlink_to(external)

    outcome = uninstall(root)

    assert outcome["status"] == "PARKED"
    assert profile.read_bytes() == generated
    assert (git_dir(root) / "hermes-gate" / "install.json").exists()


def test_init_refuses_external_integration_parent(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    outside = tmp_path / "outside-hermes"
    outside.mkdir()
    (root / ".hermes").symlink_to(outside, target_is_directory=True)

    outcome = initialize(root)

    assert outcome["status"] == "PARKED"
    assert not (outside / "gate.toml").exists()
    assert not (git_dir(root) / "hermes-gate" / "install.json").exists()


def test_init_refuses_metadata_state_alias_outside_git_dir(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    state = git_dir(root) / "hermes-gate"
    outside = tmp_path / "outside-state"
    outside.mkdir()
    state.symlink_to(outside, target_is_directory=True)

    outcome = initialize(root)

    assert outcome["status"] == "PARKED"
    assert not (outside / "baseline.json").exists()
    assert not (outside / "install.json").exists()
    assert not (root / ".hermes" / "gate.toml").exists()


def test_verify_and_uninstall_refuse_aliased_metadata_state(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    assert initialize(root)["status"] == "PASS"
    state = git_dir(root) / "hermes-gate"
    outside = tmp_path / "outside-state"
    state.rename(outside)
    state.symlink_to(outside, target_is_directory=True)

    valid, _reason = verify_runner(root)
    outcome = uninstall(root)

    assert not valid
    assert outcome["status"] == "PARKED"
    assert (outside / "install.json").exists()
    assert (root / ".hermes" / "gate.toml").exists()


def test_init_refuses_aliased_baseline_state_file(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    state = git_dir(root) / "hermes-gate"
    state.mkdir()
    external = tmp_path / "outside-baseline"
    external.write_bytes(b"owner baseline\n")
    (state / "baseline.json").symlink_to(external)

    outcome = initialize(root)

    assert outcome["status"] == "PARKED"
    assert external.read_bytes() == b"owner baseline\n"
    assert not (state / "install.json").exists()
    assert not (root / ".hermes" / "gate.toml").exists()


def test_init_refuses_aliased_backup_directory_without_existing_targets(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    state = git_dir(root) / "hermes-gate"
    state.mkdir()
    outside = tmp_path / "outside-backups"
    outside.mkdir()
    (state / "install-backup").symlink_to(outside, target_is_directory=True)

    outcome = initialize(root)

    assert outcome["status"] == "PARKED"
    assert not (state / "install.json").exists()
    assert not (root / ".hermes" / "gate.toml").exists()


@pytest.mark.parametrize("tamper", ["missing", "changed"])
def test_uninstall_refuses_missing_or_altered_recorded_backup(
    tmp_path: Path, tamper: str,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    profile = root / ".hermes" / "gate.toml"
    profile.parent.mkdir()
    profile.write_bytes(b"owner profile\n")
    assert initialize(root, force=True)["status"] == "PASS"
    generated = profile.read_bytes()
    backup = git_dir(root) / "hermes-gate" / "install-backup" / ".hermes" / "gate.toml"
    if tamper == "missing":
        backup.unlink()
    else:
        backup.write_bytes(b"altered backup\n")

    outcome = uninstall(root)

    assert outcome["status"] == "PARKED"
    assert profile.read_bytes() == generated
    assert (git_dir(root) / "hermes-gate" / "install.json").exists()


def test_uninstall_refuses_unrecorded_backup(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    assert initialize(root)["status"] == "PASS"
    profile = root / ".hermes" / "gate.toml"
    generated = profile.read_bytes()
    backup = git_dir(root) / "hermes-gate" / "install-backup" / ".hermes" / "gate.toml"
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_bytes(b"unrecorded backup\n")

    outcome = uninstall(root)

    assert outcome["status"] == "PARKED"
    assert profile.read_bytes() == generated
    assert (git_dir(root) / "hermes-gate" / "install.json").exists()


def test_uninstall_rejects_manifest_traversal_before_removing_files(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    assert initialize(root)["status"] == "PASS"
    external = tmp_path / "outside"
    external.write_bytes(b"outside sentinel\n")
    manifest_path = git_dir(root) / "hermes-gate" / "install.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"] = {"../outside": hashlib.sha256(external.read_bytes()).hexdigest()}
    manifest_path.write_text(json.dumps(manifest))

    outcome = uninstall(root)

    assert outcome["status"] == "NOT_CONFIGURED"
    assert external.read_bytes() == b"outside sentinel\n"
    assert manifest_path.exists()


def test_uninstall_rejects_truncated_v1_manifest_without_partial_removal(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    assert initialize(root)["status"] == "PASS"
    manifest_path = git_dir(root) / "hermes-gate" / "install.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["files"][".hermes/hermes_gate_runner.py"]
    manifest_path.write_text(json.dumps(manifest))

    outcome = uninstall(root)

    assert outcome["status"] == "NOT_CONFIGURED"
    assert manifest_path.exists()
    assert (root / ".hermes" / "gate.toml").exists()
    assert (root / ".hermes" / "hermes_gate_runner.py").exists()
    assert (root / ".github" / "workflows" / "hermes-quality.yml").exists()


def test_repeat_force_init_preserves_original_backup_and_witness(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    profile = root / ".hermes" / "gate.toml"
    profile.parent.mkdir()
    profile.write_bytes(b"owner profile\n")
    assert initialize(root, force=True)["status"] == "PASS"
    state = git_dir(root) / "hermes-gate"
    backup = state / "install-backup" / ".hermes" / "gate.toml"
    original_manifest = (state / "install.json").read_bytes()
    generated = profile.read_bytes()

    repeated = initialize(root, force=True)

    assert repeated["status"] == "PARKED"
    assert backup.read_bytes() == b"owner profile\n"
    assert (state / "install.json").read_bytes() == original_manifest
    assert profile.read_bytes() == generated
    assert uninstall(root)["status"] == "PASS"
    assert profile.read_bytes() == b"owner profile\n"


def test_uninstall_then_fresh_init_remains_reversible(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    profile = root / ".hermes" / "gate.toml"
    profile.parent.mkdir()
    profile.write_bytes(b"owner profile\n")
    assert initialize(root, force=True)["status"] == "PASS"
    backup = git_dir(root) / "hermes-gate" / "install-backup" / ".hermes" / "gate.toml"
    assert uninstall(root)["status"] == "PASS"
    assert profile.read_bytes() == b"owner profile\n"
    assert not backup.exists()

    profile.unlink()
    assert initialize(root)["status"] == "PASS"
    assert uninstall(root)["status"] == "PASS"
    assert not profile.exists()


def test_init_parks_on_stale_backup_without_an_existing_target(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    backup = git_dir(root) / "hermes-gate" / "install-backup" / ".hermes" / "gate.toml"
    backup.parent.mkdir(parents=True)
    backup.write_bytes(b"owner bytes from an older installation\n")

    outcome = initialize(root)

    assert outcome["status"] == "PARKED"
    assert backup.read_bytes() == b"owner bytes from an older installation\n"
    assert not (git_dir(root) / "hermes-gate" / "install.json").exists()
    assert not (root / ".hermes" / "gate.toml").exists()


def test_force_init_reuses_only_a_matching_owner_backup(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    profile = root / ".hermes" / "gate.toml"
    profile.parent.mkdir()
    profile.write_bytes(b"owner profile\n")
    backup = git_dir(root) / "hermes-gate" / "install-backup" / ".hermes" / "gate.toml"
    backup.parent.mkdir(parents=True)
    backup.write_bytes(b"different older owner\n")

    assert initialize(root, force=True)["status"] == "PARKED"
    assert profile.read_bytes() == b"owner profile\n"
    assert backup.read_bytes() == b"different older owner\n"
    assert not (git_dir(root) / "hermes-gate" / "install.json").exists()

    backup.write_bytes(b"owner profile\n")
    assert initialize(root, force=True)["status"] == "PASS"
    assert uninstall(root)["status"] == "PASS"
    assert profile.read_bytes() == b"owner profile\n"
    assert not backup.exists()


def test_uninstall_refuses_external_legacy_manifest_parent(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    assert initialize(root)["status"] == "PASS"
    current = git_dir(root) / "hermes-gate" / "install.json"
    outside = tmp_path / "outside-hermes"
    (root / ".hermes").rename(outside)
    (outside / "install.json").write_bytes(current.read_bytes())
    current.unlink()
    (root / ".hermes").symlink_to(outside, target_is_directory=True)

    outcome = uninstall(root)

    assert outcome["status"] == "PARKED"
    assert (outside / "install.json").exists()
    assert (outside / "hermes_gate_runner.py").exists()


def test_init_and_uninstall_linked_worktree_keep_git_metadata_placement(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    (root / "README.md").write_text("fixture\n")
    git(root, "add", "README.md")
    git(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "-c", "core.hooksPath=/dev/null", "commit", "-qm", "fixture")
    linked = tmp_path / "linked"
    git(root, "worktree", "add", "--detach", str(linked))
    assert (linked / ".git").is_file()

    assert initialize(linked)["status"] == "PASS"
    assert (git_dir(linked) / "hermes-gate" / "install.json").exists()
    assert uninstall(linked)["status"] == "PASS"
