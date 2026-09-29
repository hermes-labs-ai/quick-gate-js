from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import AdapterSpec
from .execution import run_argv
from .gate_result import validate_gate_result
from .gitstate import git_dir

_MINIMUMS = {
    "pygate": (0, 2, 0),
    "quick-gate": (0, 2, 3),
}
_SNAPSHOT_SKIP_DIRS = {".git", ".quick-gate", ".pygate", "__pycache__", ".venv", "venv", "node_modules"}


@dataclass(frozen=True)
class ResolvedAdapter:
    name: str
    argv: tuple[str, ...]
    version: str


def resolve_adapter(
    spec: AdapterSpec, root: Path, *, timeout_seconds: float = 5
) -> tuple[ResolvedAdapter | None, str]:
    if not spec.enabled:
        return None, "native repository commands"
    floor = _MINIMUMS.get(spec.name)
    if floor is None:
        return None, f"unsupported adapter: {spec.name}"
    if not spec.argv:
        return None, f"{spec.name} adapter argv is empty"
    executable = spec.argv[0]
    executable_path = Path(executable)
    if not executable_path.is_absolute():
        executable_path = root / executable_path
    if shutil.which(executable) is None and not (
        executable_path.is_file() and os.access(executable_path, os.X_OK)
    ):
        return None, f"{spec.name} adapter executable is unavailable"
    version_run = run_argv(
        [*spec.argv, "--version"],
        cwd=root,
        timeout_seconds=max(timeout_seconds, 0.001),
    )
    if version_run.unavailable:
        return None, f"{spec.name} adapter executable is unavailable"
    if version_run.timed_out:
        return None, f"{spec.name} adapter version probe timed out"
    version_text = (version_run.stdout or version_run.stderr).strip().splitlines()
    version = version_text[0] if version_text else ""
    parsed = _version_tuple(version)
    configured = _version_tuple(spec.minimum_version) if spec.minimum_version else floor
    if configured is None:
        return None, f"{spec.name} adapter minimum_version is invalid: {spec.minimum_version}"
    minimum = max(floor, configured)
    if parsed is None or parsed < minimum:
        required = ".".join(str(item) for item in minimum)
        return None, f"{spec.name} {required}+ required; found {version or 'unknown'}"
    return ResolvedAdapter(spec.name, spec.argv, version), ""


def run_adapter(
    spec: AdapterSpec,
    *,
    root: Path,
    mode: str,
    checked_paths: list[str],
    timeout_seconds: float,
) -> dict[str, Any]:
    started = time.monotonic()
    root = root.resolve()
    for raw in checked_paths:
        if not Path(os.path.abspath(root / raw)).is_relative_to(root):
            return {"status": "ERROR", "reason": "adapter input is outside the repository",
                    "checks": [], "command_versions": {}}
    adapter, reason = resolve_adapter(spec, root, timeout_seconds=timeout_seconds)
    if adapter is None:
        return {"status": "ERROR", "reason": reason, "checks": [], "command_versions": {}}
    remaining = timeout_seconds - (time.monotonic() - started)
    if remaining <= 0:
        return {
            "status": "ERROR",
            "reason": f"{adapter.name} adapter budget exhausted during version probe",
            "checks": [],
            "command_versions": {adapter.name: adapter.version},
        }
    state_dir = git_dir(root) / "hermes-gate" / "adapters" / adapter.name / mode
    state_dir.mkdir(parents=True, exist_ok=True)
    snapshot_paths = list(checked_paths)
    if adapter.name == "quick-gate":
        # The JS evaluator also binds its manifest and optional configuration.
        snapshot_paths.append("package.json")
        if (root / "quick-gate.config.json").is_file():
            snapshot_paths.append("quick-gate.config.json")
    js_snapshot = adapter.name == "quick-gate"
    expected_digest, expected_paths = canonical_snapshot_digest(
        root, snapshot_paths, javascript=js_snapshot
    )
    changed_file = state_dir / "changed-files.txt"
    changed_file.write_text(json.dumps(checked_paths), encoding="utf-8")
    primitive_mode = "canary" if adapter.name == "pygate" and mode == "fast" else mode
    if adapter.name == "quick-gate" and mode == "fast":
        primitive_mode = "quick"
    argv = [
        *adapter.argv,
        "run",
        "--mode",
        primitive_mode,
        "--changed-files",
        str(changed_file),
        "--output-dir",
        str(state_dir),
    ]
    result_path = state_dir / "gate-result.json"
    result_path.unlink(missing_ok=True)
    execution = run_argv(argv, cwd=root, timeout_seconds=remaining)
    if execution.unavailable or execution.timed_out:
        detail = "executable unavailable" if execution.unavailable else "timed out"
        return {
            "status": "ERROR",
            "reason": f"{adapter.name} adapter {detail}",
            "checks": [],
            "command_versions": {adapter.name: adapter.version},
        }
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        return {
            "status": "ERROR",
            "reason": f"{adapter.name} did not produce a readable gate-result/v1: {exc}",
            "checks": [],
            "command_versions": {adapter.name: adapter.version},
        }
    errors = validate_gate_result(payload)
    if errors:
        return {
            "status": "ERROR",
            "reason": f"{adapter.name} emitted invalid gate-result/v1: {'; '.join(errors)}",
            "checks": [],
            "command_versions": {adapter.name: adapter.version},
        }
    missing_paths = sorted(set(expected_paths) - set(payload["checked_paths"]))
    if missing_paths:
        return {
            "status": "ERROR",
            "reason": f"{adapter.name} omitted checked paths: {', '.join(missing_paths)}",
            "checks": [],
            "command_versions": {adapter.name: adapter.version},
        }
    current_digest, _ = canonical_snapshot_digest(root, snapshot_paths, javascript=js_snapshot)
    if current_digest != expected_digest:
        return {
            "status": "ERROR",
            "reason": f"{adapter.name} checked inputs changed during execution",
            "checks": [],
            "command_versions": {adapter.name: adapter.version},
        }
    if payload["snapshot_digest"] != expected_digest:
        return {
            "status": "ERROR",
            "reason": f"{adapter.name} snapshot digest does not match checked inputs",
            "checks": [],
            "command_versions": {adapter.name: adapter.version},
        }
    if payload["status"] == "pass" and execution.returncode != 0:
        return {
            "status": "ERROR",
            "reason": f"{adapter.name} emitted pass but exited with {execution.returncode}",
            "checks": [],
            "command_versions": {adapter.name: adapter.version},
        }
    blocking_checks = [
        str(check.get("name", "unknown"))
        for check in payload["checks"]
        if check.get("status") not in {"pass", "skipped"}
    ]
    if payload["status"] == "pass" and (
        blocking_checks or payload.get("errors") or payload.get("findings")
    ):
        detail = ", ".join(blocking_checks) if blocking_checks else "errors or findings"
        return {
            "status": "ERROR",
            "reason": f"{adapter.name} emitted pass with blocking evidence: {detail}",
            "checks": list(payload["checks"]),
            "command_versions": {adapter.name: adapter.version},
        }
    if payload["status"] == "pass" and not any(
        check.get("status") == "pass" for check in payload["checks"]
    ):
        return {
            "status": "ERROR", "reason": f"{adapter.name} executed no checks",
            "checks": list(payload["checks"]),
            "command_versions": {adapter.name: adapter.version},
        }
    status = "PASS" if payload["status"] == "pass" else "FAIL"
    if payload["status"] == "error":
        status = "ERROR"
    reason = "" if status == "PASS" else f"{adapter.name} returned {payload['status']}"
    versions = {adapter.name: adapter.version}
    for name, value in payload.get("command_versions", {}).items():
        versions[str(name)] = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    return {
        "status": status,
        "reason": reason,
        "checks": list(payload["checks"]),
        "command_versions": versions,
        "adapter": adapter.name,
        "adapter_exit_code": execution.returncode,
        "gate_result": payload,
    }


def _version_tuple(value: str) -> tuple[int, int, int] | None:
    match = re.search(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?!\d)", value)
    if not match:
        return None
    return tuple(int(item) for item in match.groups())


def canonical_snapshot_digest(
    root: Path, checked_paths: list[str], *, javascript: bool = False
) -> tuple[str, list[str]]:
    root = root.resolve()
    records: list[dict[str, Any]] = []
    normalized: set[str] = set()
    for raw_path in checked_paths:
        path = Path(raw_path)
        if not path.is_absolute():
            path = root / path
        files = _files_for_snapshot(path)
        if not files and not path.is_dir():
            files = [path]
        for file_path in files:
            relative = _relative_snapshot_path(file_path, root)
            if relative in normalized:
                continue
            normalized.add(relative)
            if file_path.is_symlink():
                record: dict[str, Any] = {
                    "path": relative,
                    "exists": True,
                    "symlink": os.readlink(file_path),
                }
                try:
                    target_stat = file_path.stat()
                except FileNotFoundError:
                    record["target_type"] = "missing"
                except OSError:
                    record["target_type"] = "unreadable"
                else:
                    record["target_type"] = (
                        "file"
                        if stat.S_ISREG(target_stat.st_mode)
                        else "directory"
                        if stat.S_ISDIR(target_stat.st_mode)
                        else "other"
                    )
                if record.get("target_type") == "file":
                    try:
                        content = file_path.read_bytes()
                    except OSError:
                        record["target_type"] = "unreadable"
                    else:
                        record.update(
                            {"size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
                        )
                records.append(record)
                continue
            if not file_path.exists() or not file_path.is_file():
                records.append({"path": relative, "exists": False})
                continue
            try:
                data = file_path.read_bytes()
            except OSError as exc:
                records.append({"path": relative, "exists": False, "error": type(exc).__name__})
                continue
            records.append(
                {
                    "path": relative,
                    "exists": True,
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
    # JS Array.sort uses UTF-16 code units; JSON.stringify emits Unicode directly.
    records.sort(key=lambda record: record["path"].encode("utf-16-be", "surrogatepass")
                 if javascript else record["path"])
    encoded = json.dumps(
        records, sort_keys=True, separators=(",", ":"), ensure_ascii=not javascript
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), [str(record["path"]) for record in records]


def _files_for_snapshot(path: Path) -> list[Path]:
    if path.is_file() or path.is_symlink():
        return [path]
    if not path.is_dir():
        return [path]
    files: list[Path] = []
    for current, directories, names in os.walk(path, followlinks=False):
        directories[:] = sorted(
            item
            for item in directories
            if item not in _SNAPSHOT_SKIP_DIRS and not item.startswith(".")
        )
        files.extend(Path(current) / name for name in sorted(names))
    return files


def _relative_snapshot_path(path: Path, root: Path) -> str:
    try:
        return Path(os.path.abspath(path)).relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.absolute().as_posix()
