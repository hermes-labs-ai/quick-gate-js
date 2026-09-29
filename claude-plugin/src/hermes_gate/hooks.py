from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from .classification import is_code_path
from .command_detection import detect_boundary_command
from .engine import boundary, fast
from .gitstate import ContentReadError, repo_root, session_changed_paths, snapshot
from .status import Status


def run_hook(event: str, payload: dict[str, Any]) -> dict[str, Any]:
    if event == "session-start":
        return session_start(payload)
    if event == "stop":
        return stop(payload)
    if event == "pre-tool-use":
        return pre_tool_use(payload)
    return {"continue": True, "systemMessage": f"Hermes Gate: unknown hook event {event}"}


def session_start(payload: dict[str, Any]) -> dict[str, Any]:
    root = repo_root(payload.get("cwd"))
    if root is None:
        return {"continue": True}
    session_id = str(payload.get("session_id") or "unknown")
    path = _session_path(session_id, root)
    source = str(payload.get("source") or "startup")
    if source not in {"resume", "compact"} or not path.exists():
        try:
            baseline = snapshot(root)
        except ContentReadError as exc:
            return {
                "continue": True,
                "systemMessage": f"Hermes Gate cannot bind session state: {exc}",
            }
        _atomic_json(
            path,
            {
                "schema": "hermes-gate/session-v1",
                "session_id": session_id,
                "repository": str(root),
                "baseline": baseline,
            },
        )
    return {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": (
                "Hermes Gate completion rail is active. Run fast before completion. "
                "Review/full requirements follow the repository profile. "
                "Commit/push/PR boundaries validate exact receipts. "
                "Read-only, non-Git, unchanged, and non-code work is exempt."
            ),
        },
    }


def stop(payload: dict[str, Any]) -> dict[str, Any]:
    # This hook is intentionally advisory and never emits decision:block.
    root = repo_root(payload.get("cwd"))
    if root is None:
        return {"continue": True}
    session_id = str(payload.get("session_id") or "unknown")
    state = _read_json(_session_path(session_id, root))
    baseline = state.get("baseline") if state.get("repository") == str(root) else None
    try:
        files = session_changed_paths(root, baseline if isinstance(baseline, dict) else None)
    except ContentReadError as exc:
        return {"continue": True, "systemMessage": f"Hermes Gate cannot inspect session changes: {exc}"}
    files = [path for path in files if is_code_path(path)]
    if not files:
        return {"continue": True}
    outcome = fast(root, files=files)
    if outcome["status"] == Status.PASS:
        return {"continue": True}
    reason = str(outcome.get("reason") or "fast gate did not pass")
    return {
        "continue": True,
        "systemMessage": f"Hermes Gate {outcome['status']}: {reason}. Run hermes-gate fast after addressing it.",
    }


def pre_tool_use(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("tool_name") != "Bash":
        return {}
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return {}
    command = tool_input.get("command") or tool_input.get("cmd")
    if not isinstance(command, str):
        return {}
    detected = detect_boundary_command(command)
    if detected is None:
        return {}
    root = _boundary_root(payload.get("cwd"), detected.git_c_dirs)
    if root is None:
        if detected.git_c_dirs:
            return _boundary_deny("could not determine the repository selected by git -C")
        return {}
    outcome = boundary(root, detected.action.value)
    if outcome["status"] == Status.PASS:
        return {}
    reason = str(outcome.get("reason") or "required receipt is missing")
    return _boundary_deny(reason)


def _boundary_root(cwd: str | None, c_dirs: tuple[str, ...]) -> Path | None:
    """Resolve Git's ordered ``-C`` directories before locating its repository."""
    if not c_dirs:
        return repo_root(cwd)
    selected = Path(cwd or os.getcwd()).expanduser()
    for directory in c_dirs:
        candidate = Path(directory).expanduser()
        selected = candidate if candidate.is_absolute() else selected / candidate
    return repo_root(selected)


def _boundary_deny(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"Hermes Gate: {reason}",
        }
    }


def read_stdin_payload() -> dict[str, Any]:
    try:
        value = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _session_path(session_id: str, root: Path) -> Path:
    cache = (
        Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "hermes-gate" / "sessions"
    )
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f"{session_id}\0{root}".encode()).hexdigest()
    return cache / f"{key}.json"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
