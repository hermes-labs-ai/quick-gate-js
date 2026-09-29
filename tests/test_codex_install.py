from __future__ import annotations

import json
from pathlib import Path

from hermes_gate.codex_install import install, installed, uninstall


def test_codex_install_merges_and_rollback_preserves_unrelated_bytes(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    unrelated = {
        "description": "existing",
        "hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": "/usr/local/bin/existing-hook"}]}]
        },
    }
    (codex_home / "hooks.json").write_text(json.dumps(unrelated), encoding="utf-8")
    (codex_home / "AGENTS.md").write_text("# Existing\n\nKeep me.\n", encoding="utf-8")
    executable = tmp_path / "bin" / "hermes-gate"
    executable.parent.mkdir()
    executable.write_text("fixture\n", encoding="utf-8")

    outcome = install(executable, codex_home=codex_home)
    assert outcome["status"] == "PASS"
    assert installed(codex_home=codex_home)["status"] == "PASS"
    merged = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))
    assert any(
        hook.get("command") == "/usr/local/bin/existing-hook"
        for group in merged["hooks"]["Stop"]
        for hook in group["hooks"]
    )

    rolled_back = uninstall(codex_home=codex_home)
    assert rolled_back["status"] == "PASS"
    after = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))
    assert after["hooks"]["Stop"] == unrelated["hooks"]["Stop"]
    assert (codex_home / "AGENTS.md").read_text(encoding="utf-8") == "# Existing\n\nKeep me.\n"


def test_codex_uninstall_preserves_similarly_named_unrelated_hook(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    unrelated_group = {
        "hooks": [
            {
                "type": "command",
                "command": '"/usr/local/bin/hermes-gate-notify" hook stop',
                "timeout": 10,
            }
        ]
    }
    (codex_home / "hooks.json").write_text(
        json.dumps({"hooks": {"Stop": [unrelated_group]}}), encoding="utf-8"
    )
    executable = tmp_path / "bin" / "hermes-gate"
    executable.parent.mkdir()
    executable.write_text("fixture\n", encoding="utf-8")

    install(executable, codex_home=codex_home)
    assert installed(codex_home=codex_home)["hook_groups"]["Stop"] == 1
    outcome = uninstall(codex_home=codex_home)

    assert outcome["status"] == "PASS"
    hooks = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))
    assert hooks["hooks"]["Stop"] == [unrelated_group]
