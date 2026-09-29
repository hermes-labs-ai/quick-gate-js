from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .binding import capture_binding
from .config import ConfigError
from .gitstate import ContentReadError, GitError, diff_digest, git_dir, head, repo_identity

SCHEMA = "hermes-gate/receipt-v1"


def receipt_dir(root: Path) -> Path:
    return git_dir(root) / "hermes-gate" / "receipts"


def receipt_path(root: Path, kind: str) -> Path:
    return receipt_dir(root) / f"{kind}.json"


def write_receipt(
    root: Path,
    kind: str,
    *,
    status: str,
    digest: str,
    elapsed_ms: int,
    command_versions: dict[str, str] | None = None,
    checks: list[dict[str, Any]] | None = None,
    findings: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "kind": kind,
        "status": status,
        "created_at": datetime.now(UTC).isoformat(),
        "repository": repo_identity(root),
        "diff_sha256": digest,
        "elapsed_ms": elapsed_ms,
        "command_versions": command_versions or {},
        "checks": checks or [],
        "findings": findings or [],
    }
    if extra:
        payload.update(extra)
    _atomic_json(receipt_path(root, kind), payload)
    return payload


def read_receipt(root: Path, kind: str) -> dict[str, Any] | None:
    path = receipt_path(root, kind)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return raw if isinstance(raw, dict) else None


def valid_receipt(
    root: Path, kind: str, digest: str | None = None, *, binding: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    raw = read_receipt(root, kind)
    if not raw:
        return None
    return raw if receipt_matches(root, raw, kind, digest, binding=binding) else None


def receipt_matches(
    root: Path, raw: dict[str, Any], kind: str, digest: str | None = None,
    *, binding: dict[str, Any] | None = None,
) -> bool:
    """Validate stored or exported PASS evidence against current local inputs."""
    if raw.get("schema") != SCHEMA or raw.get("kind") != kind:
        return False
    try:
        expected = digest or diff_digest(root)
        current_binding = binding if binding is not None else capture_binding(root, kind)
    except (ContentReadError, GitError, ConfigError, OSError, ValueError, TypeError):
        return False
    if raw.get("status") != "PASS" or raw.get("diff_sha256") != expected:
        return False
    repository = raw.get("repository")
    if not isinstance(repository, dict) or repository.get("root") != str(root.resolve()):
        return False
    if repository.get("head") != head(root) or raw.get("binding") != current_binding:
        return False
    checks = raw.get("checks")
    if not isinstance(checks, list) or not checks:
        return False
    allowed = {"PASS", "NOT_APPLICABLE", "pass", "skipped"}
    return (
        all(isinstance(check, dict) and check.get("status") in allowed for check in checks)
        and any(check.get("status") in {"PASS", "pass"} for check in checks)
    )


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
