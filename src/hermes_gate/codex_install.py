from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MARKER_START = "<!-- hermes-gate:v0.1:start -->"
MARKER_END = "<!-- hermes-gate:v0.1:end -->"
CONTRACT = f"""
{MARKER_START}
## Hermes Gate completion rail

For code changes, run `hermes-gate fast` before declaring completion. Review and full receipts
are required at PR or release boundaries when the repository profile requires them.
Matching receipts are mandatory at commit, push, and PR boundaries. Read-only, non-Git,
unchanged, and non-code work is exempt. Hooks never repair files or authorize public actions.
{MARKER_END}
""".strip()


def install(executable: Path, *, codex_home: Path | None = None) -> dict[str, Any]:
    home = (codex_home or Path.home() / ".codex").resolve()
    home.mkdir(parents=True, exist_ok=True)
    hooks_path = home / "hooks.json"
    agents_path = home / "AGENTS.md"
    backup_dir = (
        Path.home()
        / ".local"
        / "state"
        / "hermes-gate"
        / "codex-backups"
        / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    )
    backup_dir.mkdir(parents=True, exist_ok=True)
    for path in (hooks_path, agents_path):
        if path.exists():
            shutil.copy2(path, backup_dir / path.name)

    hooks = _read_hooks(hooks_path)
    command = str(executable.resolve())
    for event in ("SessionStart", "Stop", "PreToolUse"):
        groups = hooks["hooks"].setdefault(event, [])
        hooks["hooks"][event] = [group for group in groups if not _is_ours(event, group)]
    hooks["hooks"]["SessionStart"].append(
        {
            "matcher": "startup|resume|clear|compact",
            "hooks": [
                {
                    "type": "command",
                    "command": f'"{command}" hook session-start',
                    "timeout": 3,
                    "additionalContextLimit": 500,
                }
            ],
        }
    )
    hooks["hooks"]["Stop"].append(
        {"hooks": [{"type": "command", "command": f'"{command}" hook stop', "timeout": 10}]}
    )
    hooks["hooks"]["PreToolUse"].append(
        {
            "matcher": "^Bash$",
            "hooks": [
                {
                    "type": "command",
                    "command": f'"{command}" hook pre-tool-use',
                    "timeout": 5,
                    "statusMessage": "Checking Hermes Gate receipts",
                }
            ],
        }
    )
    _atomic_json(hooks_path, hooks)
    original = agents_path.read_text(encoding="utf-8") if agents_path.exists() else ""
    agents_path.write_text(_replace_contract(original), encoding="utf-8")
    manifest = {
        "schema": "hermes-gate/codex-install-v1",
        "executable": command,
        "hooks_path": str(hooks_path),
        "hooks_sha256": hashlib.sha256(hooks_path.read_bytes()).hexdigest(),
        "agents_path": str(agents_path),
        "backup_dir": str(backup_dir),
        "rollback": f'"{command}" uninstall-codex',
        "trust_action": "Open /hooks in Codex and trust the three exact Hermes Gate command definitions.",
    }
    manifest_path = Path.home() / ".local" / "state" / "hermes-gate" / "codex-install.json"
    _atomic_json(manifest_path, manifest)
    return {"status": "PASS", **manifest}


def uninstall(*, codex_home: Path | None = None) -> dict[str, Any]:
    home = (codex_home or Path.home() / ".codex").resolve()
    hooks_path = home / "hooks.json"
    agents_path = home / "AGENTS.md"
    hooks = _read_hooks(hooks_path)
    removed = 0
    for event, groups in list(hooks.get("hooks", {}).items()):
        kept = [group for group in groups if not _is_ours(event, group)]
        removed += len(groups) - len(kept)
        hooks["hooks"][event] = kept
    _atomic_json(hooks_path, hooks)
    if agents_path.exists():
        agents_path.write_text(
            _replace_contract(agents_path.read_text(encoding="utf-8"), remove=True),
            encoding="utf-8",
        )
    return {"status": "PASS", "removed_hook_groups": removed, "preserved_unrelated_hooks": True}


def installed(*, codex_home: Path | None = None) -> dict[str, Any]:
    home = (codex_home or Path.home() / ".codex").resolve()
    hooks = _read_hooks(home / "hooks.json")
    counts = {
        event: sum(1 for group in hooks.get("hooks", {}).get(event, []) if _is_ours(event, group))
        for event in ("SessionStart", "Stop", "PreToolUse")
    }
    agents = (
        (home / "AGENTS.md").read_text(encoding="utf-8") if (home / "AGENTS.md").exists() else ""
    )
    return {
        "hook_groups": counts,
        "instruction": MARKER_START in agents,
        "status": "PASS"
        if all(value == 1 for value in counts.values()) and MARKER_START in agents
        else "NOT_CONFIGURED",
    }


def _read_hooks(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"description": "User lifecycle hooks", "hooks": {}}
    if not isinstance(raw, dict) or not isinstance(raw.get("hooks", {}), dict):
        raise TypeError(f"malformed Codex hook file: {path}")
    raw.setdefault("hooks", {})
    return raw


def _is_ours(event: str, group: Any) -> bool:
    """Recognize only the complete v0.1 hook definitions we install.

    Command text is user-owned configuration, so a substring such as
    ``hermes-gate`` is not an ownership marker: it can describe an unrelated
    hook like ``hermes-gate-notify``.  The complete event, matcher, hook shape,
    and parsed command argv must match instead.
    """
    expected = {
        "SessionStart": (
            "startup|resume|clear|compact",
            "session-start",
            3,
            {"additionalContextLimit": 500},
        ),
        "Stop": (None, "stop", 10, {}),
        "PreToolUse": (
            "^Bash$",
            "pre-tool-use",
            5,
            {"statusMessage": "Checking Hermes Gate receipts"},
        ),
    }.get(event)
    if expected is None or not isinstance(group, dict):
        return False
    matcher, action, timeout, extra = expected
    if group.get("matcher") != matcher or set(group) != (
        {"hooks"} if matcher is None else {"matcher", "hooks"}
    ):
        return False
    hook_items = group.get("hooks")
    if not isinstance(hook_items, list) or len(hook_items) != 1:
        return False
    hook = hook_items[0]
    if (
        not isinstance(hook, dict)
        or hook.get("type") != "command"
        or hook.get("timeout") != timeout
    ):
        return False
    allowed_keys = {"type", "command", "timeout", *extra}
    if set(hook) != allowed_keys or any(hook.get(key) != value for key, value in extra.items()):
        return False
    try:
        argv = shlex.split(str(hook["command"]))
    except (KeyError, TypeError, ValueError):
        return False
    return len(argv) == 3 and Path(argv[0]).name == "hermes-gate" and argv[1:] == ["hook", action]


def _replace_contract(text: str, *, remove: bool = False) -> str:
    start = text.find(MARKER_START)
    end = text.find(MARKER_END)
    if start >= 0 and end >= start:
        end += len(MARKER_END)
        text = (text[:start].rstrip() + "\n" + text[end:].lstrip()).rstrip()
    if remove:
        return text + ("\n" if text else "")
    return text.rstrip() + ("\n\n" if text.strip() else "") + CONTRACT + "\n"


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
