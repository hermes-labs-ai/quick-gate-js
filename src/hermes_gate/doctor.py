from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from .binding import capture_binding
from .codex_install import installed as codex_installed
from .config import ConfigError, ReviewSpec, load_config
from .execution import run_argv
from .gitstate import ContentReadError, ScopeError, diff_digest, repo_root, scope
from .init_repo import verify_runner
from .receipts import read_receipt
from .status import Status


def _provider_auth_status(returncode: int, output: str) -> str:
    """Interpret CodeRabbit's agent event instead of trusting its status exit code."""
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("authenticated") is True:
            return "AUTHENTICATED"
        if event.get("authenticated") is False:
            return "AUTH_REQUIRED"
        status = str(event.get("status", "")).lower()
        if status in {"not_authenticated", "unauthenticated", "auth_required"}:
            return "AUTH_REQUIRED"
        if status in {"authenticated", "signed_in"}:
            return "AUTHENTICATED"
    return "AUTHENTICATED" if returncode == 0 else "AUTH_REQUIRED"


def _provider_executable(name: str, root: Path | None) -> str | None:
    """Resolve the configured review executable the way `review` will launch it."""
    found = shutil.which(name)
    if found:
        return str(Path(found).resolve())
    if root is not None:
        candidate = root / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _provider_report(spec: ReviewSpec, root: Path | None) -> dict[str, Any]:
    """Probe the executable the profile names, not a fixed binary."""
    executable = spec.argv[0]
    binary = _provider_executable(executable, root)
    report: dict[str, Any] = {"name": spec.provider, "argv0": executable, "binary": binary}
    if binary is None:
        report["status"] = "NOT_CONFIGURED"
        installer_copy = Path.home() / ".local" / "bin" / executable
        if installer_copy.is_file():
            report["detail"] = f"{installer_copy} exists but is not on PATH"
        return report
    if spec.provider == "jsonl":
        report["status"] = "AVAILABLE"
        return report
    execution = run_argv(
        [binary, "auth", "status", "--agent"],
        cwd=root or Path.cwd(),
        timeout_seconds=5,
        output_cap=4096,
    )
    detail = (execution.stdout or execution.stderr).strip()[:1000]
    report["status"] = _provider_auth_status(execution.returncode, detail)
    report["detail"] = detail
    return report


def diagnose(start: Path | None = None) -> dict[str, Any]:
    began = time.monotonic()
    root = repo_root(start)
    codex = codex_installed()
    config = None
    profile: dict[str, Any] = {}
    if root is not None:
        try:
            config = load_config(root)
            profile = {"status": "PASS", "adapter_status": config.adapter_status}
        except FileNotFoundError:
            profile = {"status": "NOT_CONFIGURED", "next_action": "hermes-gate init"}
        except ConfigError as exc:
            profile = {"status": "ERROR", "reason": str(exc)}
    # Without a usable profile, report on the default provider so the operator
    # still learns whether the reviewer is ready once the profile is fixed.
    provider = _provider_report(config.review if config is not None else ReviewSpec(), root)
    if root is None:
        return {
            "schema": "hermes-gate/doctor-v1",
            "status": Status.NOT_APPLICABLE.value,
            "repository": None,
            "codex": codex,
            "provider": provider,
            "elapsed_ms": round((time.monotonic() - began) * 1000),
        }
    runner_ok, runner_detail = verify_runner(root)
    try:
        selected, scope_base = scope(root)
        if config:
            selected = [path for path in selected if config.included(path)]
        digest = diff_digest(root, selected, base=scope_base)
        input_error = None
    except (ContentReadError, ScopeError) as exc:
        digest = None
        input_error = str(exc)
    receipts: dict[str, Any] = {}
    for kind in ("fast", "review", "full"):
        receipt = read_receipt(root, kind)
        try:
            current_binding = capture_binding(root, kind, config) if config else None
        except (ContentReadError, OSError):
            current_binding = None
        receipts[kind] = {
            "status": "MISSING" if receipt is None else receipt.get("status", "ERROR"),
            "stale": bool(receipt and (
                digest is None or receipt.get("diff_sha256") != digest
                or current_binding is None or receipt.get("binding") != current_binding
            )),
        }
    statuses = [profile["status"], "PASS" if runner_ok else "NOT_CONFIGURED"]
    if input_error or profile["status"] == "ERROR":
        overall = "ERROR"
    elif all(item == "PASS" for item in statuses):
        overall = "PASS"
    else:
        overall = "NOT_CONFIGURED"
    return {
        "schema": "hermes-gate/doctor-v1",
        "status": overall,
        "repository": str(root),
        "profile": profile,
        "runner": {"status": "PASS" if runner_ok else "NOT_CONFIGURED", "detail": runner_detail},
        **({"input_error": input_error} if input_error else {}),
        "codex": codex,
        "provider": provider,
        "receipts": receipts,
        "elapsed_ms": round((time.monotonic() - began) * 1000),
    }
