from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github/actions/kwik-e-gate/run.py"


@pytest.mark.parametrize("case", ["pass", "fail", "invalid-mode", "missing-profile"])
def test_pinned_source_action_preserves_failure_receipts(tmp_path: Path, case: str) -> None:
    repo = tmp_path / "consumer"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    # A project-local module must not shadow the Action's reviewed source.
    (repo / "hermes_gate.py").write_text("raise RuntimeError('wrong implementation')\n")
    if case != "missing-profile":
        (repo / ".hermes").mkdir()
        code = "import sys; sys.exit(1)" if case == "fail" else "pass"
        command = json.dumps([sys.executable, "-c", code])
        (repo / ".hermes/gate.toml").write_text(
            f'[[fast]]\nname="check"\nargv={command}\n'
            f'[[full]]\nname="check"\nargv={command}\n'
        )
    output = tmp_path / "outputs"
    env = dict(os.environ, RUNNER_TEMP=str(tmp_path), GITHUB_OUTPUT=str(output),
               KWIK_GATE_DIRECTORY=str(repo), KWIK_GATE_BASE="",
               KWIK_GATE_MODE="invalid" if case == "invalid-mode" else "full")
    env.pop("HERMES_GATE_BASE", None)
    process = subprocess.run(
        [sys.executable, "-I", str(SCRIPT)], cwd=repo, env=env,
        capture_output=True, text=True, timeout=30, check=False,
    )
    result = json.loads(process.stdout)
    expected = "PASS" if case == "pass" else "FAIL"
    assert result["status"] == expected, process.stderr
    assert process.returncode == (0 if case == "pass" else 1)
    assert result["receipt"]["schema"] == "hermes-gate/receipt-v1"
    export = Path(result["export_path"])
    assert export.is_file()
    assert json.loads(export.read_text()) == result["receipt"]
    assert f"status={expected}\n" in output.read_text()
    assert f"receipt-path={export}\n" in output.read_text()


@pytest.mark.parametrize("case", [
    "unsupported-python", "missing-core", "missing-initializer", "unwritable-export",
    "symlink-loop", "missing-directory", "not-a-directory", "directory-symlink",
])
def test_action_bootstrap_failure_is_receipted(tmp_path: Path, case: str) -> None:
    repo = tmp_path / "consumer"
    repo.mkdir()
    script = SCRIPT
    if case in {"missing-core", "missing-initializer"}:
        script = tmp_path / "broken/.github/actions/kwik-e-gate/run.py"
        script.parent.mkdir(parents=True)
        script.write_bytes(SCRIPT.read_bytes())
        if case == "missing-initializer":
            workflow = tmp_path / "broken/src/hermes_gate/workflow.py"
            workflow.parent.mkdir(parents=True)
            workflow.write_text("raise RuntimeError('must not import this stub')\n")
    runner_temp = tmp_path / "missing-temp" if case == "unwritable-export" else tmp_path
    directory = repo
    if case == "symlink-loop":
        directory = tmp_path / "loop"
        directory.symlink_to("loop")
    elif case == "missing-directory":
        directory = tmp_path / "missing-consumer"
    elif case == "not-a-directory":
        directory = tmp_path / "consumer-file"
        directory.write_text("not a checkout\n")
    elif case == "directory-symlink":
        directory = tmp_path / "consumer-alias"
        directory.symlink_to(repo, target_is_directory=True)
    output = tmp_path / "outputs"
    env = dict(os.environ, RUNNER_TEMP=str(runner_temp), GITHUB_OUTPUT=str(output),
               KWIK_GATE_DIRECTORY=str(directory), KWIK_GATE_MODE="full")
    code = "import runpy,sys; "
    if case not in {"missing-core", "missing-initializer"}:
        code += "sys.version_info=(3,10,0); "
    code += "runpy.run_path(sys.argv[1],run_name='__main__')"
    process = subprocess.run(
        [sys.executable, "-I", "-c", code, str(script)], cwd=repo, env=env,
        capture_output=True, text=True, timeout=30, check=False,
    )
    result = json.loads(process.stdout)
    assert process.returncode == 1
    assert result["status"] == result["receipt"]["status"] == "FAIL"
    assert result["receipt"]["reason_code"] == "ACTION_BOOTSTRAP_ERROR"
    assert result["receipt"]["checks"] == []
    assert result["receipt"]["kind"] == "full"
    if case in {"missing-core", "missing-initializer"}:
        assert "pinned core source is missing" in result["reason"]
    assert "status=FAIL\n" in output.read_text()
    if case in {"unwritable-export", "symlink-loop", "missing-directory", "not-a-directory"}:
        assert result["export_path"] is None
        assert "receipt-path=\n" in output.read_text()
        assert "receipt export failed" in result["reason"]
    else:
        export = Path(result["export_path"])
        assert json.loads(export.read_text()) == result["receipt"]
        assert f"receipt-path={export}\n" in output.read_text()
