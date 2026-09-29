from __future__ import annotations

import hashlib
import json
import os
import shutil
import tomllib
from pathlib import Path
from typing import Any

from . import __version__, repo_runner
from .gitstate import ContentReadError, git_dir, repo_identity, snapshot

# Single source of truth for pinned Action versions used by the generated workflow.
# Bump here when dependabot bumps .github/workflows/hermes-quality.yml, so the generator
# and the tracked file cannot desync (see test_tracked_workflow_matches_the_generator).
ACTION_VERSIONS = {
    "checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "setup-python": "5fda3b95a4ea91299a34e894583c3862153e4b97",
    "setup-node": "820762786026740c76f36085b0efc47a31fe5020",
    "upload-artifact": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
}
INTEGRATION_FILES = frozenset({
    ".hermes/gate.toml",
    ".hermes/hermes_gate_runner.py",
    ".github/workflows/hermes-quality.yml",
})


def _contained_file(base: Path, path: Path) -> bool:
    """Allow ordinary files and in-base aliases, including aliases in parents."""
    try:
        relative = path.relative_to(base)
        for depth in range(1, len(relative.parts)):
            parent = base.joinpath(*relative.parts[:depth])
            if parent.is_symlink() and not parent.is_dir():
                return False
            if parent.exists() and not parent.is_dir():
                return False
        if path.is_symlink() and not path.is_file():
            return False
        if path.exists() and not path.is_file():
            return False
        return path.resolve(strict=False).is_relative_to(base.resolve(strict=True))
    except (OSError, RuntimeError, ValueError):
        return False


def _metadata_state_safe(root: Path) -> bool:
    metadata = git_dir(root)
    state = metadata / "hermes-gate"
    manifest = state / "install.json"
    baseline = state / "baseline.json"
    backups = state / "install-backup"
    return (
        not state.is_symlink()
        and not manifest.is_symlink()
        and not baseline.is_symlink()
        and not backups.is_symlink()
        and _contained_file(metadata, manifest)
        and _contained_file(metadata, baseline)
        and all(
            not (backups / relative).is_symlink()
            and _contained_file(metadata, backups / relative)
            for relative in INTEGRATION_FILES
        )
    )


def initialize(root: Path, *, force: bool = False, adapter: str = "native") -> dict[str, Any]:
    if adapter not in {"native", "pygate", "quick-gate"}:
        return {"status": "ERROR", "reason": f"unsupported adapter: {adapter}"}
    hermes = root / ".hermes"
    profile = hermes / "gate.toml"
    runner = hermes / "hermes_gate_runner.py"
    workflow = root / ".github" / "workflows" / "hermes-quality.yml"
    targets = [profile, runner, workflow]
    dangling = [path for path in targets if path.is_symlink() and not path.exists()]
    if dangling:
        return {
            "status": "PARKED",
            "reason": "refusing to overwrite dangling integration symlink(s); preserve them manually",
            "existing": [str(path.relative_to(root)) for path in dangling],
        }
    unsafe = [path for path in targets if not _contained_file(root, path)]
    if unsafe:
        return {
            "status": "PARKED",
            "reason": "refusing integration path outside this repository or without a regular file",
            "existing": [str(path.relative_to(root)) for path in unsafe],
        }
    existing = [path for path in targets if path.exists()]
    if existing and not force:
        return {
            "status": "PARKED",
            "reason": "refusing to overwrite existing integration; rerun with --force after review",
            "existing": [str(path.relative_to(root)) for path in existing],
        }
    try:
        preflight_snapshot = snapshot(root)
    except ContentReadError as exc:
        return {"status": "PARKED", "reason": f"cannot read complete repository bytes: {exc}"}
    if not _metadata_state_safe(root):
        return {"status": "PARKED", "reason": "Gate state leaves the Git directory"}
    current_manifest = _install_manifest_path(root)
    legacy_manifest = root / ".hermes" / "install.json"
    if current_manifest.exists() or legacy_manifest.exists() or legacy_manifest.is_symlink():
        return {
            "status": "PARKED",
            "reason": "Gate is already installed; preserve its original backup and manifest",
        }
    backup_root = git_dir(root) / "hermes-gate" / "install-backup"
    metadata = git_dir(root)
    unsafe_backups = [
        backup_root / relative for relative in INTEGRATION_FILES
        if (backup_root / relative).is_symlink()
        or not _contained_file(metadata, backup_root / relative)
    ]
    if unsafe_backups:
        return {
            "status": "PARKED",
            "reason": "refusing backup path outside Git metadata or through a backup symlink",
            "existing": [str(path.relative_to(backup_root)) for path in unsafe_backups],
        }
    # An older install or interrupted rollback may have left backups behind.
    # Reuse only a byte-identical copy of a file still present in the checkout;
    # otherwise its original ownership cannot be inferred safely.
    for relative in INTEGRATION_FILES:
        backup = backup_root / relative
        if not backup.exists():
            continue
        target = root / relative
        try:
            if not target.is_file() or backup.read_bytes() != target.read_bytes():
                return {
                    "status": "PARKED",
                    "reason": f"stale backup without matching owner file: {relative}",
                }
        except OSError:
            return {"status": "PARKED", "reason": f"backup unreadable: {relative}"}
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_manifest: dict[str, str] = {}
    for path in existing:
        relative = path.relative_to(root)
        destination = backup_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        backup_manifest[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()

    hermes.mkdir(parents=True, exist_ok=True)
    workflow.parent.mkdir(parents=True, exist_ok=True)
    source = Path(repo_runner.__file__).read_bytes()
    intended = {
        profile: _detected_profile(root, adapter=adapter).encode("utf-8"),
        runner: source,
        workflow: _workflow(root).encode("utf-8"),
    }
    expected_hashes = {
        str(path.relative_to(root)): hashlib.sha256(content).hexdigest()
        for path, content in intended.items()
    }
    expected_snapshot = {
        str(path.relative_to(root)): (
            f"SYMLINK:{os.readlink(path)}:FILE:{expected_hashes[str(path.relative_to(root))]}"
            if path.is_symlink() else expected_hashes[str(path.relative_to(root))]
        )
        for path in targets
    }
    for path, content in intended.items():
        path.write_bytes(content)
    runner_sha = hashlib.sha256(source).hexdigest()
    manifest = {
        "schema": "hermes-gate/install-v1",
        "repository": repo_identity(root),
        "files": expected_hashes,
        "runner_sha256": runner_sha,
        "runner_version": repo_runner.RUNNER_VERSION,
        "backups": backup_manifest,
        "rollback": "hermes-gate uninstall-repo",
    }
    try:
        generated = snapshot(root, [str(path.relative_to(root)) for path in targets])
        if generated != expected_snapshot:
            raise ContentReadError("generated integration differs from intended bytes")
    except ContentReadError as exc:
        restored, removed, rollback_error = _rollback_generated_targets(
            root, targets, existing, backup_root
        )
        if rollback_error:
            return {
                "status": "ERROR",
                "reason": (
                    "generated integration could not be bound to complete bytes and rollback failed: "
                    f"{rollback_error}; preserve the checkout before retrying"
                ),
            }
        return {
            "status": "PARKED",
            "reason": (
                "generated integration could not be bound to complete bytes and was rolled back: "
                f"{exc}; restored {restored}, removed {removed}; recover storage, then rerun"
            ),
        }
    baseline = {"repository": repo_identity(root), "dirty": {**preflight_snapshot, **generated}}
    state_path = git_dir(root) / "hermes-gate" / "baseline.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(baseline, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path = _install_manifest_path(root)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "status": "PASS",
        "profile": str(profile),
        "runner": str(runner),
        "runner_sha256": runner_sha,
        "workflow": str(workflow),
        "adapter_status": "NATIVE_DEFAULT" if adapter == "native" else "EXPLICIT_ADAPTER",
        "reason": "profile written; review declared commands before running; tools are not installed",
    }


def _rollback_generated_targets(
    root: Path, targets: list[Path], existing: list[Path], backup_root: Path
) -> tuple[list[str], list[str], str | None]:
    restored: list[str] = []
    removed: list[str] = []
    existing_set = set(existing)
    if not _metadata_state_safe(root):
        return restored, removed, "Gate state leaves the Git directory"
    for target in targets:
        relative = target.relative_to(root)
        backup = backup_root / relative
        if not _contained_file(root, target):
            return restored, removed, f"unsafe restore path for {relative}"
        if target in existing_set and (
            backup.is_symlink() or not _contained_file(git_dir(root), backup)
        ):
            return restored, removed, f"unsafe backup path for {relative}"
    try:
        for target in targets:
            relative = target.relative_to(root)
            if target in existing_set:
                backup = backup_root / relative
                if not backup.is_file():
                    return restored, removed, f"missing backup for {relative}"
                shutil.copy2(backup, target)
                restored.append(str(relative))
            elif target.exists():
                target.unlink()
                removed.append(str(relative))
    except OSError as exc:
        return restored, removed, str(exc)
    return restored, removed, None


def uninstall(root: Path) -> dict[str, Any]:
    if not _metadata_state_safe(root):
        return {"status": "PARKED", "reason": "Gate state leaves the Git directory"}
    manifest_path = _manifest_path_for_read(root)
    if manifest_path != _install_manifest_path(root) and not _contained_file(root, manifest_path):
        return {"status": "PARKED", "reason": "legacy manifest path leaves the repository"}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"status": "NOT_CONFIGURED", "reason": "no install manifest"}
    backup_root = git_dir(root) / "hermes-gate" / "install-backup"
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != INTEGRATION_FILES:
        return {"status": "NOT_CONFIGURED", "reason": "malformed install manifest"}
    recorded_backups = manifest.get("backups", {})
    if (not isinstance(recorded_backups, dict)
            or any(key not in files or not isinstance(value, str)
                   for key, value in recorded_backups.items())):
        return {"status": "NOT_CONFIGURED", "reason": "malformed install backups"}

    # Never restore/remove an early target before proving that every generated
    # target is still the exact installed byte sequence.  A later local edit
    # must park the entire rollback, not leave a partially restored integration.
    planned: list[tuple[str, Path, Path]] = []
    for relative, installed_sha in files.items():
        if (not isinstance(relative, str) or relative not in INTEGRATION_FILES
                or not isinstance(installed_sha, str)):
            return {"status": "NOT_CONFIGURED", "reason": "malformed install manifest"}
        target = root / relative
        backup = backup_root / relative
        if not _contained_file(root, target):
            return {"status": "PARKED", "reason": f"unsafe installed path: {relative}"}
        if backup.is_symlink() or not _contained_file(git_dir(root), backup):
            return {"status": "PARKED", "reason": f"unsafe backup path: {relative}"}
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != installed_sha:
            return {
                "status": "PARKED",
                "reason": f"installed file changed: {relative}; preserve it manually",
            }
        planned.append((relative, target, backup))

    # An owner backup is an obligation, not an optional hint. Validate every one
    # before restoring or removing any generated file.
    for relative, _target, backup in planned:
        expected = recorded_backups.get(relative)
        if expected is None:
            if backup.exists():
                return {"status": "PARKED", "reason": f"unrecorded backup: {relative}"}
            continue
        try:
            if not backup.is_file() or hashlib.sha256(backup.read_bytes()).hexdigest() != expected:
                return {"status": "PARKED", "reason": f"backup changed: {relative}"}
        except OSError:
            return {"status": "PARKED", "reason": f"backup unreadable: {relative}"}

    restored: list[str] = []
    removed: list[str] = []
    for relative, target, backup in planned:
        if backup.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)
            restored.append(relative)
        elif target.exists():
            target.unlink()
            removed.append(relative)
    manifest_path.unlink(missing_ok=True)
    # The owner bytes are back in the checkout. These copies are no longer an
    # install obligation; leaving them would poison a later fresh install.
    try:
        for relative, _target, backup in planned:
            if relative in recorded_backups:
                backup.unlink()
    except OSError as exc:
        return {
            "status": "ERROR",
            "reason": f"integration restored but backup cleanup failed: {exc}",
            "restored": restored,
            "removed": removed,
        }
    return {"status": "PASS", "restored": restored, "removed": removed}


def verify_runner(root: Path) -> tuple[bool, str]:
    if not _metadata_state_safe(root):
        return False, "Gate state leaves the Git directory"
    manifest_path = _manifest_path_for_read(root)
    if manifest_path != _install_manifest_path(root) and not _contained_file(root, manifest_path):
        return False, "legacy manifest path leaves the repository"
    runner = root / ".hermes" / "hermes_gate_runner.py"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        actual = hashlib.sha256(runner.read_bytes()).hexdigest()
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        return False, str(exc)
    expected = str(manifest.get("runner_sha256", ""))
    return actual == expected, actual


def _detected_profile(root: Path, *, adapter: str = "native") -> str:
    python = (root / "pyproject.toml").is_file() or (root / "requirements.txt").is_file()
    javascript = (root / "package.json").is_file()
    fast: list[tuple[str, list[str], float, list[str]]] = []
    full: list[tuple[str, list[str], float, list[str]]] = []
    repair: list[tuple[str, list[str], float, list[str]]] = []
    adapter_status = "NATIVE_DEFAULT" if adapter == "native" else "EXPLICIT_ADAPTER"
    reviewer = "coderabbit"
    if python:
        fast.append(
            (
                "python-parse",
                [
                    "python3",
                    "-c",
                    "import ast,pathlib,sys; [ast.parse(pathlib.Path(p).read_bytes(), filename=p) for p in sys.argv[1:]]",
                    "{files}",
                ],
                6.0,
                ["**/*.py"],
            )
        )
        if (root / "src").is_dir():
            pytest_argv = [
                "python3",
                "-c",
                "import sys; sys.path.insert(0, 'src'); import pytest; raise SystemExit(pytest.main(['-q']))",
            ]
        else:
            pytest_argv = ["python3", "-m", "pytest", "-q"]
        full.append(("pytest", pytest_argv, 180.0, ["**/*"]))
        if shutil.which("ruff"):
            fast.insert(0, ("ruff", ["ruff", "check", "{files}"], 6.0, ["**/*.py"]))
            full.insert(0, ("ruff", ["ruff", "check", "."], 60.0, ["**/*"]))
            repair.append(("ruff-fix", ["ruff", "check", "--fix", "{files}"], 8.0, ["**/*.py"]))
    if javascript:
        package = _package_scripts(root / "package.json")
        manager = "pnpm" if (root / "pnpm-lock.yaml").exists() else "npm"
        if "lint" in package:
            fast.append(
                (
                    "lint",
                    [manager, "run", "lint"],
                    8.0,
                    ["**/*.js", "**/*.jsx", "**/*.ts", "**/*.tsx", "**/*.mjs", "**/*.cjs",
                     "**/*.vue", "**/*.svelte", "package.json", "**/*.config.*", ".eslintrc*"],
                )
            )
            full.append(("lint", [manager, "run", "lint"], 120.0, ["**/*"]))
        if "typecheck" in package:
            full.append(("typecheck", [manager, "run", "typecheck"], 120.0, ["**/*"]))
        if "test" in package:
            full.append(("test", [manager, "test"], 180.0, ["**/*"]))
        if "build" in package:
            full.append(("build", [manager, "run", "build"], 180.0, ["**/*"]))
    diff_argv = ["python3", ".hermes/hermes_gate_runner.py", "diff-check", "{files}"]
    if not full:
        full.append(("diff-check", diff_argv, 10.0, ["**/*"]))
    lines = [
        "version = 1",
        "",
        "[gate]",
        "fast_budget_seconds = 8.0",
        "full_required_local = false",
        "review_required = false",
        f'adapter_status = "{adapter_status}"',
        'exclusions = [".git/**", ".hermes/hermes_gate_runner.py", ".pytest_cache/**", ".ruff_cache/**", "**/__pycache__/**", "vendor/**", "node_modules/**", "dist/**", "build/**"]',
        "",
        "[adapter]",
        f"enabled = {'false' if adapter == 'native' else 'true'}",
        f'name = "{adapter}"',
        ("argv = []" if adapter == "native" else 'argv = ["pygate"]'
         if adapter == "pygate" else 'argv = ["npx", "--no-install", "quick-gate"]'),
        'minimum_version = ""' if adapter == "native" else 'minimum_version = "0.3.2"',
        "",
        "[lintlang]",
        f"enabled = {'true' if shutil.which('lintlang') else 'false'}",
        'argv = ["lintlang", "scan", "--format", "json", "--fail-on", "review", "{files}"]',
        'trigger_globs = ["**/AGENTS.md", "**/CLAUDE.md", "**/prompts/**", "**/*.prompt", ".codex/**", ".claude/**"]',
        "timeout_seconds = 4.0",
        'blocking_threshold = "MEDIUM"',
        "",
        "[review]",
        'provider = "coderabbit"',
        f"argv = {json.dumps([reviewer, 'review', '--agent'])}",
        "timeout_seconds = 180.0",
        'material_severities = ["critical", "major"]',
        'material_categories = ["correctness", "security", "data-loss", "concurrency", "api-contract"]',
        "fallback_argv = []",
    ]
    fast.append(("diff-check", diff_argv, 4.0, ["**/*"]))
    for table, commands in (("fast", fast), ("full", full), ("repair", repair)):
        for name, argv, timeout, globs in commands:
            lines.extend(
                [
                    "",
                    f"[[{table}]]",
                    f'name = "{name}"',
                    f"argv = {json.dumps(argv)}",
                    f"timeout_seconds = {timeout}",
                    f"globs = {json.dumps(globs)}",
                ]
            )
    return "\n".join(lines) + "\n"


def _workflow(root: Path) -> str:
    steps = [
        f"      - uses: actions/checkout@{ACTION_VERSIONS['checkout']}",
        "        with:",
        "          # The gate compares the pull request base with HEAD, so the base commit",
        "          # has to be in the checkout.",
        "          fetch-depth: 0",
        "          # The gate only reads the checkout. Do not leave the workflow token in",
        "          # .git/config where every later step and declared stage could read it.",
        "          persist-credentials: false",
        f"      - uses: actions/setup-python@{ACTION_VERSIONS['setup-python']}",
        "        with:",
        "          python-version: '3.12'",
    ]
    if (root / "pyproject.toml").is_file():
        install_target = ".[test]" if _has_test_extra(root / "pyproject.toml") else "."
        tools: list[str] = []
        if install_target == ".":
            if shutil.which("ruff"):
                tools.append("ruff")
            if shutil.which("pytest") or (root / "tests").is_dir():
                tools.append("pytest")
        tool_suffix = " " + " ".join(tools) if tools else ""
        steps.extend(
            [
                "      - name: Install project and declared gate tools",
                f"        run: python3 -m pip install -e '{install_target}'{tool_suffix}",
            ]
        )
    if (root / "package.json").is_file():
        install_command = "npm ci" if (root / "package-lock.json").is_file() else "npm install"
        steps.extend(
            [
                f"      - uses: actions/setup-node@{ACTION_VERSIONS['setup-node']}",
                "        with:",
                "          node-version: '24'",
                "      - name: Install JavaScript dependencies",
                f"        run: {install_command}",
            ]
        )
    try:
        own_project = tomllib.loads((root / "pyproject.toml").read_text()).get("project", {})
    except (OSError, tomllib.TOMLDecodeError):
        own_project = {}
    if own_project.get("name") != "hermes-gate":
        steps.extend([
            "      - name: Install the receipt CLI",
            f"        run: python3 -m pip install 'hermes-gate=={__version__}'",
        ])
    steps.extend(
        [
            # A hosted checkout has no worktree, index or untracked changes, so the default
            # local scope selects nothing and every file-driven stage would report a pass
            # over zero bytes. Name the range explicitly instead.
            "      - name: Run declared full gate against the pull request range",
            "        if: github.event_name == 'pull_request'",
            "        env:",
            "          HERMES_GATE_BASE: ${{ github.event.pull_request.base.sha }}",
            '        run: kwik-gate run --mode full --output "$RUNNER_TEMP/kwik-gate-receipt.json"',
            "      - name: Run declared full gate against every committed byte",
            "        if: github.event_name != 'pull_request'",
            '        run: kwik-gate run --mode full --output "$RUNNER_TEMP/kwik-gate-receipt.json"',
            "      - name: Preserve the receipt",
            "        if: always()",
            f"        uses: actions/upload-artifact@{ACTION_VERSIONS['upload-artifact']}",
            "        with:",
            "          name: kwik-gate-receipt",
            "          path: ${{ runner.temp }}/kwik-gate-receipt.json",
            "          if-no-files-found: warn",
        ]
    )
    return "\n".join(
        [
            "name: Hermes quality rail",
            "",
            "on:",
            "  pull_request:",
            "  push:",
            "    branches: [main]",
            "  workflow_dispatch:",
            "",
            "permissions:",
            "  contents: read",
            "",
            "jobs:",
            "  full:",
            "    runs-on: ubuntu-latest",
            "    steps:",
            *steps,
            "",
        ]
    )


def _package_scripts(path: Path) -> dict[str, str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    scripts = raw.get("scripts", {}) if isinstance(raw, dict) else {}
    return scripts if isinstance(scripts, dict) else {}


def _install_manifest_path(root: Path) -> Path:
    return git_dir(root) / "hermes-gate" / "install.json"


def _manifest_path_for_read(root: Path) -> Path:
    current = _install_manifest_path(root)
    legacy = root / ".hermes" / "install.json"
    return current if current.exists() else legacy


def is_adopted(root: Path) -> bool:
    """Whether this repository has a Gate installation manifest.

    A profile alone is enough to activate the rail, but its absence is
    ambiguous: it can mean either that a repository was never enrolled or
    that an enrolled repository lost its generated profile.  `initialize()`
    writes this manifest and `uninstall()` removes it, so it is the durable
    enrollment witness for that distinction.
    """
    return _manifest_path_for_read(root).is_file()


def _has_test_extra(path: Path) -> bool:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return False
    project = raw.get("project", {}) if isinstance(raw, dict) else {}
    optional = project.get("optional-dependencies", {}) if isinstance(project, dict) else {}
    return isinstance(optional, dict) and isinstance(optional.get("test"), list)
