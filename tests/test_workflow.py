from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hermes_gate.cli import kwik_main
from hermes_gate.engine import fast, full
from hermes_gate.receipts import receipt_path, valid_receipt
from hermes_gate.workflow import run, verify


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def profile(root: Path, code: str = "pass") -> None:
    (root / ".hermes").mkdir(exist_ok=True)
    command = json.dumps([sys.executable, "-c", code])
    (root / ".hermes/gate.toml").write_text(
        '[gate]\nexclusions=[".git/**", ".hermes/**"]\n'
        f'[[fast]]\nname="check"\nargv={command}\n'
        f'[[full]]\nname="check"\nargv={command}\n'
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.com")
    profile(root)
    (root / "source.py").write_text("value = 1\n")
    (root / "other.py").write_text("value = 2\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    (root / "source.py").write_text("value = 3\n")
    return root


def test_run_pass_receipt_export_and_read_only_verify(repo: Path, tmp_path: Path) -> None:
    output = tmp_path / "receipt.json"
    result = run(repo, mode="fast", output=output)
    assert result["status"] == "PASS"
    assert json.loads(output.read_text()) == result["receipt"]
    assert Path(result["receipt_path"]).is_file()
    assert run(repo, mode="fast")["cached"] is True
    before = sorted(p for p in repo.rglob("*") if p.is_file())
    assert verify(repo, path=output)["status"] == "PASS"
    assert sorted(p for p in repo.rglob("*") if p.is_file()) == before


@pytest.mark.parametrize("code", ["raise SystemExit(1)", "import time; time.sleep(2)"])
def test_failure_and_timeout_always_have_receipts(repo: Path, code: str) -> None:
    profile(repo, code)
    path = repo / ".hermes/gate.toml"
    path.write_text(path.read_text() + "timeout_seconds=0.05\n")
    result = run(repo, mode="full")
    assert result["status"] == "FAIL"
    assert result["receipt"]["status"] == "FAIL"
    assert Path(result["receipt_path"]).is_file()
    assert verify(repo, kind="full")["status"] == "FAIL"


@pytest.mark.parametrize("case", ["missing", "invalid", "scalar", "bad-mode", "bad-base"])
def test_setup_errors_always_have_failure_receipts(repo: Path, case: str) -> None:
    if case == "missing":
        (repo / ".hermes/gate.toml").unlink()
    elif case == "invalid":
        (repo / ".hermes/gate.toml").write_text("[invalid")
    elif case == "scalar":
        (repo / ".hermes/gate.toml").write_text('[gate]\nfast_budget_seconds="no"')
    result = run(repo, mode="invalid" if case == "bad-mode" else "fast",
                 base="missing-base" if case == "bad-base" else None)
    assert result["status"] == "FAIL"
    assert Path(result["receipt_path"]).is_file()
    assert result["receipt"]["reason_code"] != "PASS"


def test_non_git_run_has_a_receipt_in_user_cache(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    result = run(tmp_path)
    assert result["status"] == "FAIL"
    assert Path(result["receipt_path"]).is_file()
    assert result["receipt"]["repository"]["head"] == "NONE"


def test_no_check_execution_cannot_be_pass(repo: Path) -> None:
    (repo / ".hermes/gate.toml").write_text('[gate]\n[[fast]]\nargv=["true"]\nglobs=["*.rs"]')
    result = run(repo, mode="fast")
    assert result["status"] == "FAIL"
    assert Path(result["receipt_path"]).is_file()


def test_excluded_profile_change_invalidates_cache(repo: Path) -> None:
    assert fast(repo, files=["source.py"])["status"] == "PASS"
    profile(repo, "raise SystemExit(1)")
    result = fast(repo, files=["source.py"])
    assert not result.get("cached")
    assert result["status"] == "FAIL"


def test_instruction_scanner_receives_only_declared_trigger_paths(repo: Path) -> None:
    (repo / "AGENTS.md").write_text("Instruction contract for this fixture.\n")
    command = json.dumps([sys.executable, "-c",
        "import sys; assert sys.argv[1:]==['AGENTS.md'], sys.argv[1:]", "{files}"])
    path = repo / ".hermes/gate.toml"
    path.write_text(path.read_text() + f'\n[lintlang]\nenabled=true\nargv={command}\n'
                    'trigger_globs=["**/AGENTS.md"]\n')
    result = fast(repo)
    assert result["status"] == "PASS"
    check = next(c for c in result["receipt"]["checks"] if c["name"] == "lintlang")
    assert check["argv"][-1] == "AGENTS.md"


def test_unchanged_dependency_edit_invalidates_scoped_receipt(repo: Path) -> None:
    first = fast(repo, files=["source.py"])
    (repo / "other.py").write_text("value = 4\n")
    assert valid_receipt(repo, "fast", first["receipt"]["diff_sha256"]) is None
    assert not fast(repo, files=["source.py"]).get("cached")


@pytest.mark.parametrize("mode", ["fast", "full"])
@pytest.mark.parametrize("change", [
    'Path("source.py").write_text("after\\n")',
    'Path("new-input.py").write_text("new\\n")',
    'Path("other.py").unlink()',
])
def test_mutating_check_cannot_issue_pass(repo: Path, mode: str, change: str) -> None:
    profile(repo, f"from pathlib import Path; {change}")
    result = fast(repo) if mode == "fast" else full(repo)
    assert result["status"] == "ERROR"
    assert "changed during execution" in result["reason"]
    assert valid_receipt(repo, mode) is None


def test_changed_tool_bytes_or_execution_bits_invalidate_receipt(repo: Path) -> None:
    tool = repo / "check.sh"
    tool.write_text("#!/bin/sh\nexit 0\n")
    tool.chmod(0o755)
    (repo / ".hermes/gate.toml").write_text('[[fast]]\nargv=["./check.sh"]\n')
    result = run(repo, mode="fast")
    assert result["status"] == "PASS"
    tool.chmod(0o644)
    assert verify(repo)["status"] == "FAIL"
    tool.chmod(0o755)
    tool.write_text("#!/bin/sh\nexit 1\n")
    assert valid_receipt(repo, "fast", result["receipt"]["diff_sha256"]) is None


def test_receipt_without_binding_must_be_regenerated(repo: Path) -> None:
    result = run(repo, mode="fast")
    raw = result["receipt"]
    del raw["binding"]
    receipt_path(repo, "fast").write_text(json.dumps(raw))
    assert verify(repo)["status"] == "FAIL"


def test_export_inside_repository_is_rejected_with_receipt(repo: Path) -> None:
    result = run(repo, mode="fast", output=repo / "receipt.json")
    assert result["status"] == "FAIL"
    assert result["export_path"] is None
    assert not (repo / "receipt.json").exists()
    assert Path(result["receipt_path"]).is_file()


def test_storage_failure_still_emits_failure_receipt(repo: Path, monkeypatch) -> None:
    monkeypatch.setattr("hermes_gate.workflow._atomic_json", lambda *_: (_ for _ in ()).throw(
        OSError("disk unavailable")
    ))
    result = run(repo, mode="fast")
    assert result["status"] == "FAIL"
    assert result["receipt"]["reason_code"] == "RECEIPT_WRITE_ERROR"
    assert result["receipt_path"] is None


def test_canonical_cli_needs_no_reviewer(repo: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(repo)
    monkeypatch.setattr("hermes_gate.engine.review", lambda *_: pytest.fail("review invoked"))
    assert kwik_main(["run"]) == 0
    assert json.loads(capsys.readouterr().out)["receipt"]["status"] == "PASS"
    assert kwik_main(["verify"]) == 0
    capsys.readouterr()
    assert kwik_main(["run", "--mode", "bad"]) == 1
    assert json.loads(capsys.readouterr().out)["receipt"]["status"] == "FAIL"


def test_missing_receipt_verification_creates_no_runtime_state(repo: Path) -> None:
    assert verify(repo)["status"] == "FAIL"
    assert not (repo / ".git/hermes-gate").exists()


def test_missing_git_still_emits_failure_receipt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr("hermes_gate.workflow.repo_root", lambda *_: (_ for _ in ()).throw(
        FileNotFoundError("git unavailable")
    ))
    result = run(tmp_path)
    assert result["status"] == "FAIL"
    assert Path(result["receipt_path"]).is_file()
    assert verify(tmp_path)["status"] == "FAIL"


def test_real_js_adapter_roundtrip(tmp_path: Path) -> None:
    from hermes_gate.adapters import run_adapter
    from hermes_gate.config import AdapterSpec

    cli = os.environ.get("KWIK_QUICK_GATE_CLI")
    if not cli:
        pytest.skip("set KWIK_QUICK_GATE_CLI to a checkout's src/cli.js; CI runs this integration")
    cli = str(Path(cli).resolve())
    root = (tmp_path / "js-repo").resolve()
    root.mkdir()
    git(root, "init", "-q")
    (root / "package.json").write_text(json.dumps({"scripts": {}}))
    (root / "quick-gate.config.json").write_text(json.dumps({
        "gates": {"typecheck": False, "lighthouse": False},
        "commands": {"lint": ["node", "-e", "process.exit(0)"]},
    }))
    names = ["source.js", "café.js", "🧾.js", "\ue000.js", "line\nbreak.js"]
    for name in names:
        (root / name).write_text("// checked\n")
    spec = AdapterSpec(enabled=True, name="quick-gate", argv=("node", cli))
    result = run_adapter(spec, root=root, mode="fast", checked_paths=names, timeout_seconds=8)
    assert result["status"] == "PASS", result
    assert {"package.json", "quick-gate.config.json", *names} == set(
        result["gate_result"]["checked_paths"]
    )
    config = json.loads((root / "quick-gate.config.json").read_text())
    config["commands"]["lint"] = ["node", "-e", "process.exit(1)"]
    (root / "quick-gate.config.json").write_text(json.dumps(config))
    failed = run_adapter(spec, root=root, mode="fast", checked_paths=names, timeout_seconds=8)
    assert failed["status"] == "FAIL"


def test_full_on_clean_checkout_runs_file_driven_stages(repo: Path) -> None:
    (repo / ".hermes/gate.toml").write_text(
        '[[full]]\nname="files"\n'
        f'argv={json.dumps([sys.executable, "-c", "import sys; assert len(sys.argv)>1", "{files}"])}\n'
        'globs=["*.py"]\n'
    )
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "clean")
    result = run(repo, mode="full")
    assert result["status"] == "PASS"
    assert "other.py" in result["receipt"]["execution_paths"]
    assert "other.py" in result["receipt"]["checks"][0]["argv"]


def test_init_adapter_is_explicit_and_keeps_native_commands_portable(repo: Path) -> None:
    from hermes_gate.config import load_config
    from hermes_gate.init_repo import initialize

    (repo / "package.json").write_text(json.dumps({
        "scripts": {"lint": "eslint .", "test": "node --test"}
    }))
    (repo / ".hermes/gate.toml").unlink()
    result = initialize(repo, adapter="quick-gate")
    assert result["status"] == "PASS"
    config = load_config(repo)
    assert config.adapter.enabled
    assert config.adapter.argv == ("npx", "--no-install", "quick-gate")
    assert all("--runInBand" not in spec.argv for spec in config.full)
    assert config.review_required is False


def test_explicit_local_boundary_policy_does_not_require_a_model(repo: Path) -> None:
    from hermes_gate.engine import boundary

    path = repo / ".hermes/gate.toml"
    path.write_text(path.read_text().replace('[gate]', '[gate]\nreview_required=false'))
    assert run(repo, mode="fast")["status"] == "PASS"
    result = boundary(repo, "push")
    assert result["status"] == "PASS"
    assert result["required"] == ["fast"]


def test_commit_boundary_rejects_staged_bytes_that_were_not_checked(repo: Path) -> None:
    from hermes_gate.engine import boundary

    (repo / "source.py").write_text("bad = True\n")
    git(repo, "add", "source.py")
    (repo / "source.py").write_text("fixed = True\n")
    assert run(repo, mode="fast")["status"] == "PASS"
    rejected = boundary(repo, "commit")
    assert rejected["status"] == "FAIL"
    assert "staged bytes differ" in rejected["reason"]
    git(repo, "add", "source.py")
    assert boundary(repo, "commit")["status"] == "PASS"


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_nonfinite_timeout_produces_failure_receipt(repo: Path, value: str) -> None:
    profile_path = repo / ".hermes/gate.toml"
    profile_path.write_text(f'[[fast]]\nargv=["true"]\ntimeout_seconds={value}\n')
    result = run(repo, mode="fast")
    assert result["status"] == "FAIL"
    assert "finite and positive" in result["reason"]
    assert Path(result["receipt_path"]).is_file()


def test_script_interpreter_upgrade_invalidates_receipt(repo: Path, tmp_path: Path, monkeypatch) -> None:
    tools = tmp_path / "bin"
    tools.mkdir()
    interpreter = tools / "node"
    interpreter.write_text("#!/bin/sh\necho node-old\n")
    interpreter.chmod(0o755)
    tool = repo / "check-tool"
    tool.write_text("#!/usr/bin/env node\n")
    tool.chmod(0o755)
    (repo / ".hermes/gate.toml").write_text('[[fast]]\nargv=["./check-tool"]\n')
    monkeypatch.setenv("PATH", str(tools) + os.pathsep + os.environ["PATH"])
    assert run(repo, mode="fast")["status"] == "PASS"
    interpreter.write_text("#!/bin/sh\necho node-new\n")
    assert verify(repo)["status"] == "FAIL"
    result = run(repo, mode="fast")
    assert result["status"] == "PASS" and not result["cached"]


def test_internal_execution_error_still_has_a_receipt(repo: Path, monkeypatch) -> None:
    monkeypatch.setattr("hermes_gate.workflow.fast", lambda *a, **kw: (_ for _ in ()).throw(
        RuntimeError("unexpected internal state")
    ))
    result = run(repo, mode="fast")
    assert result["status"] == "FAIL"
    assert "RuntimeError" in result["reason"]
    assert Path(result["receipt_path"]).is_file()
