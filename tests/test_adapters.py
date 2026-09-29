from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from hermes_gate.adapters import canonical_snapshot_digest, run_adapter
from hermes_gate.config import AdapterSpec


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _adapter_script(
    path: Path,
    *,
    name: str,
    version: str,
    root: Path,
    checked_paths: list[str] | None = None,
) -> None:
    paths = list(checked_paths if checked_paths is not None else ["source.txt"])
    if name == "quick-gate":
        paths.append("package.json")
    snapshot_digest, canonical_paths = canonical_snapshot_digest(root, paths)
    payload = {
        "schema": "gate-result/v1",
        "status": "pass",
        "snapshot_digest": snapshot_digest,
        "checked_paths": canonical_paths,
        "checks": [
            {
                "name": "adapter",
                "status": "pass",
                "argv": ["fixture"],
                "elapsed_ms": 1,
                "timed_out": False,
                "output_truncated": False,
            }
        ],
        "findings": [],
        "command_versions": {"fixture": "1.0.0"},
        "elapsed_ms": 1,
        "output_truncated": False,
        "errors": [],
    }
    path.write_text(
        "import json,sys\n"
        "from pathlib import Path\n"
        f"NAME={name!r}\n"
        f"VERSION={version!r}\n"
        f"PAYLOAD={payload!r}\n"
        "if '--version' in sys.argv:\n"
        "    print(f'{NAME} {VERSION}')\n"
        "    raise SystemExit(0)\n"
        "args=sys.argv[1:]\n"
        "out=Path(args[args.index('--output-dir')+1])\n"
        "mode=args[args.index('--mode')+1]\n"
        "value=dict(PAYLOAD)\n"
        "value['checks']=[{'name': mode, 'status': 'pass', 'argv': ['fixture'], "
        "'elapsed_ms': 1, 'timed_out': False, 'output_truncated': False}]\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "(out/'gate-result.json').write_text(json.dumps(value), encoding='utf-8')\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("name", "version", "mode", "expected_mode"),
    [
        ("pygate", "0.2.0", "fast", "canary"),
        ("quick-gate", "0.2.3", "fast", "quick"),
    ],
)
def test_optional_adapter_runs_from_explicit_argv_and_writes_only_git_state(
    tmp_path: Path, name: str, version: str, mode: str, expected_mode: str
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    (root / "source.txt").write_text("ok\n", encoding="utf-8")
    script = tmp_path / f"{name}.py"
    _adapter_script(script, name=name, version=version, root=root)
    result = run_adapter(
        AdapterSpec(
            enabled=True,
            name=name,
            argv=(sys.executable, str(script)),
            minimum_version=version,
        ),
        root=root,
        mode=mode,
        checked_paths=["source.txt"],
        timeout_seconds=5,
    )
    assert result["status"] == "PASS"
    assert result["checks"][0]["name"] == expected_mode
    assert result["command_versions"][name].endswith(version)
    assert not (root / ".pygate").exists()
    assert not (root / ".quick-gate").exists()


def test_adapter_rejects_version_below_supported_floor(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    script = tmp_path / "pygate.py"
    _adapter_script(script, name="pygate", version="0.1.2", root=root, checked_paths=[])
    result = run_adapter(
        AdapterSpec(
            enabled=True,
            name="pygate",
            argv=(sys.executable, str(script)),
            minimum_version="0.2.0",
        ),
        root=root,
        mode="fast",
        checked_paths=[],
        timeout_seconds=5,
    )
    assert result["status"] == "ERROR"
    assert "0.2.0+ required" in result["reason"]


def test_adapter_cannot_reuse_stale_result(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    script = tmp_path / "pygate.py"
    script.write_text(
        "import sys\nif '--version' in sys.argv:\n    print('pygate 0.2.0')\n",
        encoding="utf-8",
    )
    state_dir = root / ".git" / "hermes-gate" / "adapters" / "pygate" / "fast"
    state_dir.mkdir(parents=True)
    (state_dir / "gate-result.json").write_text("{}", encoding="utf-8")
    result = run_adapter(
        AdapterSpec(enabled=True, name="pygate", argv=(sys.executable, str(script))),
        root=root,
        mode="fast",
        checked_paths=[],
        timeout_seconds=5,
    )
    assert result["status"] == "ERROR"
    assert "did not produce" in result["reason"]
    assert not (state_dir / "gate-result.json").exists()


def test_adapter_requires_complete_checked_path_coverage(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    script = tmp_path / "pygate.py"
    _adapter_script(script, name="pygate", version="0.2.0", root=root)
    result = run_adapter(
        AdapterSpec(enabled=True, name="pygate", argv=(sys.executable, str(script))),
        root=root,
        mode="fast",
        checked_paths=["source.txt", "missing.txt"],
        timeout_seconds=5,
    )
    assert result["status"] == "ERROR"
    assert result["reason"].endswith("missing.txt")


def test_adapter_resolves_relative_executable_from_repository_root(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    tools = root / "tools"
    tools.mkdir(parents=True)
    _git(root, "init", "-q")
    script = tools / "pygate"
    empty_digest, _ = canonical_snapshot_digest(root, [])
    script.write_text(
        f"#!{sys.executable}\n"
        "import json,sys\n"
        "from pathlib import Path\n"
        "if '--version' in sys.argv:\n"
        "    print('pygate 0.2.0')\n"
        "    raise SystemExit(0)\n"
        "out=Path(sys.argv[sys.argv.index('--output-dir')+1])\n"
        f"payload={{'schema':'gate-result/v1','status':'pass','snapshot_digest':{empty_digest!r},"
        "'checked_paths':[],'checks':[{'name':'fixture','status':'pass','argv':[],"
        "'elapsed_ms':0,'timed_out':False,'output_truncated':False}],"
        "'findings':[],'command_versions':{},"
        "'elapsed_ms':0,'output_truncated':False,'errors':[]}\n"
        "(out/'gate-result.json').write_text(json.dumps(payload), encoding='utf-8')\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    result = run_adapter(
        AdapterSpec(enabled=True, name="pygate", argv=("./tools/pygate",)),
        root=root,
        mode="fast",
        checked_paths=[],
        timeout_seconds=5,
    )
    assert result["status"] == "PASS"


def test_adapter_rejects_non_executable_relative_path(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    tools = root / "tools"
    tools.mkdir(parents=True)
    _git(root, "init", "-q")
    script = tools / "pygate"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o644)

    result = run_adapter(
        AdapterSpec(enabled=True, name="pygate", argv=("./tools/pygate",)),
        root=root,
        mode="fast",
        checked_paths=[],
        timeout_seconds=5,
    )

    assert result["status"] == "ERROR"
    assert result["reason"] == "pygate adapter executable is unavailable"


def test_canonical_snapshot_preserves_symlink_identity(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "target.txt"
    target.write_text("first\n", encoding="utf-8")
    link = root / "link.txt"
    link.symlink_to("target.txt")

    first_digest, first_paths = canonical_snapshot_digest(root, ["link.txt"])
    target.write_text("second\n", encoding="utf-8")
    second_digest, second_paths = canonical_snapshot_digest(root, ["link.txt"])

    assert first_paths == second_paths == ["link.txt"]
    assert first_digest != second_digest


def test_adapter_rejects_pass_with_blocking_nested_check(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    script = tmp_path / "pygate.py"
    _adapter_script(script, name="pygate", version="0.2.0", root=root, checked_paths=[])
    source = script.read_text(encoding="utf-8")
    script.write_text(
        source.replace(
            "'status': 'pass', 'argv': ['fixture']", "'status': 'fail', 'argv': ['fixture']"
        ),
        encoding="utf-8",
    )

    result = run_adapter(
        AdapterSpec(enabled=True, name="pygate", argv=(sys.executable, str(script))),
        root=root,
        mode="fast",
        checked_paths=[],
        timeout_seconds=5,
    )

    assert result["status"] == "ERROR"
    assert "pass with blocking evidence" in result["reason"]


def test_adapter_version_probe_shares_total_budget(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    script = tmp_path / "pygate.py"
    script.write_text("import time; time.sleep(2)\n", encoding="utf-8")
    started = time.monotonic()
    result = run_adapter(
        AdapterSpec(enabled=True, name="pygate", argv=(sys.executable, str(script))),
        root=root,
        mode="fast",
        checked_paths=[],
        timeout_seconds=0.05,
    )
    assert result["status"] == "ERROR"
    assert "version probe timed out" in result["reason"]
    assert time.monotonic() - started < 1


def test_adapter_rejects_pass_payload_after_nonzero_exit(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    script = tmp_path / "pygate.py"
    _adapter_script(script, name="pygate", version="0.2.0", root=root)
    script.write_text(
        script.read_text(encoding="utf-8") + "raise SystemExit(1)\n", encoding="utf-8"
    )
    result = run_adapter(
        AdapterSpec(enabled=True, name="pygate", argv=(sys.executable, str(script))),
        root=root,
        mode="fast",
        checked_paths=["source.txt"],
        timeout_seconds=5,
    )
    assert result["status"] == "ERROR"
    assert "emitted pass but exited with 1" in result["reason"]


def test_adapter_rejects_malformed_minimum_version(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    script = tmp_path / "pygate.py"
    _adapter_script(script, name="pygate", version="0.2.0", root=root, checked_paths=[])
    result = run_adapter(
        AdapterSpec(
            enabled=True,
            name="pygate",
            argv=(sys.executable, str(script)),
            minimum_version="latest",
        ),
        root=root,
        mode="fast",
        checked_paths=[],
        timeout_seconds=5,
    )
    assert result["status"] == "ERROR"
    assert "minimum_version is invalid" in result["reason"]


def test_adapter_rejects_snapshot_digest_for_different_bytes(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    (root / "source.txt").write_text("current\n", encoding="utf-8")
    script = tmp_path / "pygate.py"
    _adapter_script(script, name="pygate", version="0.2.0", root=root)
    expected, _ = canonical_snapshot_digest(root, ["source.txt"])
    script.write_text(
        script.read_text(encoding="utf-8").replace(expected, "0" * 64),
        encoding="utf-8",
    )
    result = run_adapter(
        AdapterSpec(enabled=True, name="pygate", argv=(sys.executable, str(script))),
        root=root,
        mode="fast",
        checked_paths=["source.txt"],
        timeout_seconds=5,
    )
    assert result["status"] == "ERROR"
    assert "snapshot digest does not match" in result["reason"]
