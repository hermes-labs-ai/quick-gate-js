"""The claude-plugin artifact must run without the Python package being pip-installed."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "claude-plugin"
PROJECT_VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]

# Agent Plugins 1.0.0 resolves the manifest at the plugin root only; `.claude-plugin/` is
# not a recognized location for it, and Claude Code reads only `.claude-plugin/`.
AGENT_PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
AGENT_PLUGIN_FIELDS = {
    "$schema",
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
    "extensions",
}
AGENT_PLUGIN_NAME = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")


def _agent_manifest() -> dict:
    return json.loads((PLUGIN_ROOT / "plugin.json").read_text())


def _claude_manifest() -> dict:
    return json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text())


def test_plugin_manifest_and_hooks_files_exist():
    manifest = _claude_manifest()
    assert manifest["name"] == "hermes-gate"
    assert (PLUGIN_ROOT / "hooks" / "hooks.json").is_file()
    hooks = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text())
    assert set(hooks["hooks"]) == {"SessionStart", "Stop", "PreToolUse"}


def test_agent_plugins_manifest_sits_at_the_plugin_root_and_matches_the_spec():
    manifest = _agent_manifest()
    assert manifest["$schema"] == AGENT_PLUGIN_SCHEMA
    assert set(manifest) <= AGENT_PLUGIN_FIELDS
    assert AGENT_PLUGIN_NAME.match(manifest["name"])
    assert 1 <= len(manifest["name"]) <= 64
    assert manifest["version"] and manifest["description"]
    assert set(manifest["author"]) <= {"name", "email", "url"}
    assert all(isinstance(keyword, str) for keyword in manifest["keywords"])


def test_both_plugin_manifests_track_the_packaged_version_and_each_other():
    agent_manifest = _agent_manifest()
    claude_manifest = _claude_manifest()
    assert agent_manifest["version"] == PROJECT_VERSION
    assert claude_manifest["version"] == PROJECT_VERSION
    for field in ("name", "version", "description", "license"):
        assert agent_manifest[field] == claude_manifest[field]


def test_claude_code_manifest_keeps_its_client_only_field():
    # Claude Code reads `displayName`; Agent Plugins 1.0.0 rejects it as an unknown
    # top-level field, so it must stay out of the root manifest.
    assert _claude_manifest()["displayName"] == "hermes-gate"
    assert "displayName" not in _agent_manifest()


def test_plugin_runtime_is_synced_with_the_source_package():
    source = ROOT / "src" / "hermes_gate"
    bundled = PLUGIN_ROOT / "src" / "hermes_gate"

    def runtime_files(directory):
        return sorted(
            p.relative_to(directory)
            for p in directory.rglob("*")
            if p.is_file() and p.suffix in {".py", ".json"} and "__pycache__" not in p.parts
        )

    source_files = runtime_files(source)
    bundled_files = runtime_files(bundled)
    assert bundled_files == source_files
    for relative in source_files:
        assert (bundled / relative).read_bytes() == (source / relative).read_bytes()


def _run_hook(event: str, payload: dict, cwd: Path) -> dict:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-S", str(PLUGIN_ROOT / "scripts" / "hermes_gate_hook.py"), event],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=cwd,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_plugin_session_start_hook_runs_without_a_pip_install(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    output = _run_hook(
        "session-start",
        {"cwd": str(tmp_path), "session_id": "plugin-artifact-test"},
        tmp_path,
    )
    assert output["continue"] is True
    assert output["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "Hermes Gate completion rail is active" in (
        output["hookSpecificOutput"]["additionalContext"]
    )


def test_plugin_pre_tool_use_hook_ignores_non_bash_tools_without_a_pip_install(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    output = _run_hook(
        "pre-tool-use",
        {"cwd": str(tmp_path), "tool_name": "Read"},
        tmp_path,
    )
    assert output == {}


def test_plugin_hook_fails_open_on_an_unknown_event_without_a_pip_install(tmp_path):
    output = _run_hook("bogus-event", {}, tmp_path)
    assert output["continue"] is True
