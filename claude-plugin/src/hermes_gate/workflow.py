"""The local run / receipt / verify workflow. No repair or reviewer calls."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import load_config
from .engine import fast, full
from .gitstate import ContentReadError, GitError, diff_digest, repo_identity, repo_root, scope
from .receipts import SCHEMA, _atomic_json, read_receipt, receipt_matches, receipt_path
from .routing import select


def plan(start: Path, *, mode: str = "auto", base: str | None = None) -> dict[str, Any]:
    """Read-only selection preview. PLANNED is not a checked PASS."""
    try:
        root = repo_root(start)
        if root is None:
            raise ValueError("not a Git repository")
        paths, scope_base = scope(root, base=base)
        route = select(load_config(root), paths, requested=mode)
        return {"schema": "kwik-gate/plan-v1", "status": "PLANNED",
                "routing": route, "checked_paths": paths, "scope_base": scope_base}
    except (OSError, GitError, ValueError, TypeError) as exc:
        return {"schema": "kwik-gate/plan-v1", "status": "ERROR", "reason": str(exc)}


def run(
    start: Path, *, mode: str = "auto", base: str | None = None, output: Path | None = None
) -> dict[str, Any]:
    """Run declared checks and persist a receipt for every terminal outcome.

    stdout contains the receipt even if storage is unavailable. A persistence
    failure cannot be returned as PASS. Help/argument-parser errors are not runs.
    """
    began = time.monotonic()
    root = None
    kind = mode if mode in {"fast", "full"} else "fast"
    destination = None
    exported = False
    export_allowed = False
    route = None
    if output is not None:
        output = output.expanduser().resolve()
        export_allowed = not output.is_relative_to(root or start.resolve())
    try:
        root = repo_root(start)
        if root is None:
            raise ValueError("not a Git repository")
        if mode not in {"auto", "fast", "full"}:
            raise ValueError("mode must be auto, fast or full")
        if output is not None:
            if output.is_relative_to(root):
                export_allowed = False
                raise ValueError("receipt export must be outside the repository")
            export_allowed = True
        paths, _ = scope(root, base=base)
        route = select(load_config(root), paths, requested=mode)
        kind = route["mode"]
        outcome = fast(root, base=base) if kind == "fast" else full(root, base=base)
        checked = outcome.get("receipt", {}).get("checked_paths")
        if isinstance(checked, list):
            route = select(load_config(root), checked, requested=mode)
            if route["mode"] != kind:
                outcome.update(status="ERROR", reason="gate decision changed before execution; rerun")
    except (OSError, GitError, ValueError, TypeError) as exc:
        outcome = {"status": "ERROR", "reason": str(exc)}
    except Exception as exc:  # noqa: BLE001 -- every failed run must still issue a receipt
        outcome = {"status": "ERROR", "reason": f"internal execution error ({type(exc).__name__})"}
    payload = outcome.get("receipt")
    if not isinstance(payload, dict):
        payload = {
            "schema": SCHEMA,
            "kind": kind,
            "created_at": datetime.now(UTC).isoformat(),
            "repository": _repository(root or start, is_git=root is not None),
            "diff_sha256": "0" * 64,
            "elapsed_ms": round((time.monotonic() - began) * 1000),
            "command_versions": {},
            "checks": [],
            "findings": [],
        }
    payload = dict(payload)
    if route is not None:
        payload["routing"] = route
    checks = payload.get("checks", [])
    passed = outcome.get("status") == "PASS" and any(
        check.get("status") in {"PASS", "pass"} for check in checks
    )
    payload.update({
        "status": "PASS" if passed else "FAIL",
        "issued_at": datetime.now(UTC).isoformat(),
        "reason_code": outcome.get("status", "ERROR"),
        "reason": outcome.get("reason", ""),
    })
    if outcome.get("status") == "PASS" and not passed:
        payload.update(reason_code="NO_CHECKS_EXECUTED", reason="no checks executed")
    try:
        destination = receipt_path(root, kind) if root else _failure_path()
        _atomic_json(destination, payload)
        if output is not None and export_allowed:
            _atomic_json(output, payload)
            exported = True
    except (OSError, GitError) as exc:
        payload.update(status="FAIL", reason_code="RECEIPT_WRITE_ERROR", reason=str(exc))
        # The JSON result remains a receipt even if both destinations are unwritable.
        if destination is not None:
            try:
                _atomic_json(destination, payload)
            except OSError:
                destination = None
    return {
        "schema": "hermes-gate/result-v1",
        "command": "run",
        "status": payload["status"],
        "reason": payload["reason"],
        "receipt": payload,
        "receipt_path": str(destination) if destination is not None else None,
        "export_path": str(output) if exported else None,
        "cached": bool(outcome.get("cached")),
        "routing": route,
        "elapsed_ms": round((time.monotonic() - began) * 1000),
    }


def verify(start: Path, *, path: Path | None = None, kind: str = "auto") -> dict[str, Any]:
    """Read-only verification; uses recorded scope and current complete workload."""
    began = time.monotonic()
    passed = False
    try:
        root = repo_root(start)
        raw = json.loads(path.read_text()) if path else read_receipt(root, kind) if (
            root and kind != "auto"
        ) else None
        if root and path is None and kind == "auto":
            candidates = [(receipt_path(root, item), item) for item in ("fast", "full")]
            candidates = [(p.stat().st_mtime_ns, item) for p, item in candidates if p.exists()]
            latest = max(candidates, default=None)
            raw = read_receipt(root, latest[1]) if latest else None
        if root is not None and isinstance(raw, dict):
            recorded_kind = raw.get("kind")
            paths = raw.get("checked_paths")
            base = raw.get("scope_base")
            if (
                recorded_kind in {"fast", "full"}
                and isinstance(paths, list)
                and all(
                    isinstance(item, str) and not Path(item).is_absolute()
                    and ".." not in Path(item).parts for item in paths
                )
                and isinstance(base, str)
            ):
                digest = diff_digest(root, paths, base=base)
                passed = receipt_matches(root, raw, recorded_kind, digest)
    except (OSError, GitError, ContentReadError, ValueError, TypeError):
        pass
    return {
        "schema": "hermes-gate/result-v1",
        "command": "verify",
        "status": "PASS" if passed else "FAIL",
        "reason": "" if passed else "receipt is missing, failed, stale, or incomplete; run kwik-gate run",
        "elapsed_ms": round((time.monotonic() - began) * 1000),
    }


def _failure_path() -> Path:
    cache = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return cache / "kwik-gate" / "receipts" / f"failure-{uuid.uuid4().hex}.json"


def _repository(root: Path, *, is_git: bool) -> dict[str, str]:
    if is_git:
        try:
            return repo_identity(root)
        except (OSError, GitError):
            pass
    return {"root": str(root.resolve()), "head": "NONE", "remote": "NONE"}
