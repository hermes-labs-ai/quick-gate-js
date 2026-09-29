from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from test_workflow import git, profile

from hermes_gate.config import CommandSpec, GateConfig, load_config
from hermes_gate.receipts import receipt_path
from hermes_gate.routing import select
from hermes_gate.workflow import plan, run, verify


def test_routing_selects_only_relevant_fast_checks_without_io(tmp_path, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("routing must not read files or execute commands")

    monkeypatch.setattr(Path, "read_bytes", unexpected)
    monkeypatch.setattr("subprocess.run", unexpected)
    config = GateConfig(root=tmp_path, review_required=False, fast=(
        CommandSpec("python", ("python3",), 1, globs=("**/*.py",)),
        CommandSpec("javascript", ("node",), 1, globs=("**/*.js",)),
        CommandSpec("whitespace", ("git",), 1),
    ))
    route = select(config, ["src/example.py"])
    assert route["mode"] == "fast"
    assert route["selected_stages"] == ["python", "whitespace"]
    assert route["skipped_stages"] == ["javascript"]
    assert not route["review_executed"]


@pytest.mark.parametrize("path", [
    "pyproject.toml", "package-lock.json", "tests/test_example.py",
    ".github/workflows/ci.yml", ".hermes/gate.toml", "src/auth/session.py",
])
def test_structural_and_sensitive_changes_escalate_to_full(tmp_path, path):
    config = GateConfig(root=tmp_path)
    assert select(config, [path])["mode"] == "full"
    assert select(config, [path], requested="fast")["mode"] == "fast"


def test_repository_routing_policy_broadens_and_recommends_review(tmp_path):
    (tmp_path / ".hermes").mkdir()
    (tmp_path / ".hermes/gate.toml").write_text(
        '[routing]\nfull_globs=["core/**"]\nreview_globs=["billing/**"]\n'
    )
    config = load_config(tmp_path)
    assert select(config, ["core/engine.py"])["mode"] == "full"
    route = select(config, ["billing/invoice.py"])
    assert route["review_recommended"]
    assert route["review_paths"] == ["billing/invoice.py"]
    assert not route["review_executed"]


def test_native_initialization_preserves_both_polyglot_contracts(tmp_path):
    from hermes_gate.init_repo import initialize

    git(tmp_path, "init", "-q")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\n")
    (tmp_path / "package.json").write_text(json.dumps({
        "scripts": {"lint": "eslint .", "test": "node --test"}
    }))
    assert initialize(tmp_path)["status"] == "PASS"
    config = load_config(tmp_path)
    assert {"pytest", "test"}.issubset({s.name for s in config.full})
    route = select(config, ["src/example.py"])
    assert "python-parse" in route["selected_stages"]
    assert "lint" in route["skipped_stages"]


def test_auto_run_records_actual_gate_choice_and_verify_uses_latest(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.com")
    profile(root)
    (root / "source.py").write_text("value=1\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    (root / "source.py").write_text("value=2\n")
    preview = plan(root)
    assert preview["status"] == "PLANNED"
    assert not (root / ".git/hermes-gate").exists()
    assert run(root)["receipt"]["routing"]["mode"] == "fast"
    (root / "pyproject.toml").write_text("[project]\nname='fixture'\n")
    result = run(root)
    assert result["status"] == "PASS"
    assert result["receipt"]["kind"] == "full"
    assert result["routing"]["mode"] == "full"
    assert verify(root)["status"] == "PASS"
    profile(root, "raise SystemExit(1)")
    assert run(root)["status"] == "FAIL"
    assert verify(root)["status"] == "FAIL"


def test_latest_verification_rejects_corruption_and_accepts_new_cached_run(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    profile(root)
    (root / "source.py").write_text("value=1\n")
    assert run(root, mode="fast")["status"] == "PASS"
    assert run(root, mode="full")["status"] == "PASS"
    receipt_path(root, "full").write_text("broken json")
    assert verify(root)["status"] == "FAIL"
    result = run(root, mode="fast")
    assert result["cached"] and result["status"] == "PASS"
    assert verify(root)["status"] == "PASS"


def test_scope_change_between_routing_and_execution_cannot_pass(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    profile(root)
    (root / "source.py").write_text("value=1\n")
    # Select only a normal source edit, then introduce a structural change before
    # the engine captures inputs. A fast PASS cannot satisfy the new full decision.
    monkeypatch.setattr("hermes_gate.workflow.scope", lambda *a, **k: (["source.py"], "HEAD"))
    from hermes_gate.engine import fast

    def changed_scope(*args, **kwargs):
        (root / "pyproject.toml").write_text("[project]\nname='fixture'\n")
        return fast(*args, **kwargs)

    monkeypatch.setattr("hermes_gate.workflow.fast", changed_scope)
    result = run(root)
    assert result["status"] == "FAIL"
    assert "decision changed" in result["reason"]


def test_real_pygate_adapter_roundtrip_and_initialization(tmp_path):
    from hermes_gate.adapters import run_adapter
    from hermes_gate.config import AdapterSpec
    from hermes_gate.init_repo import initialize

    executable = os.environ.get("KWIK_PYGATE_CLI")
    if not executable:
        pytest.skip("set KWIK_PYGATE_CLI to an installed pygate; CI runs this integration")
    root = (tmp_path / "python-repo").resolve()
    root.mkdir()
    git(root, "init", "-q")
    commands = {
        "lint": [sys.executable, "-c", "print('[]')"],
        "typecheck": [sys.executable, "-c", 'print(\'{"generalDiagnostics": []}\')'],
    }
    (root / "pyproject.toml").write_text("[project]\nname='fixture'\n")
    def write_commands():
        (root / "pygate.toml").write_text(
            '[commands]\n' + '\n'.join(f'{k}={json.dumps(v)}' for k, v in commands.items())
        )
    write_commands()
    names = ["source.py", "café.py", "🧾.py", "\ue000.py", "line\nbreak.py"]
    for name in names:
        (root / name).write_text("# checked\n")
    spec = AdapterSpec(enabled=True, name="pygate", argv=(executable,))
    result = run_adapter(spec, root=root, mode="fast", checked_paths=names, timeout_seconds=8)
    assert result["status"] == "PASS", result
    assert set(result["gate_result"]["checked_paths"]) == set(names)
    commands["lint"] = [sys.executable, "-c", "raise SystemExit(1)"]
    write_commands()
    assert run_adapter(spec, root=root, mode="fast", checked_paths=names,
                       timeout_seconds=8)["status"] == "FAIL"
    assert initialize(root, adapter="pygate")["status"] == "PASS"
    config = load_config(root)
    assert config.adapter.argv == ("pygate",)
    assert config.adapter.minimum_version == "0.3.2"
