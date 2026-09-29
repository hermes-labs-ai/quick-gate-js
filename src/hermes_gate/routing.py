"""Explainable local gate selection. No subprocesses, file reads or model calls.

Interpret change paths against the repository's declared contract. The policy can
broaden checks; it never invents commands, installs tools, or claims semantic review.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from .config import GateConfig, _matches

_CONTRACTS = {
    "pyproject.toml", "setup.py", "setup.cfg", "tox.ini", "pytest.ini",
    "package.json", "package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml",
    "yarn.lock", "bun.lock", "bun.lockb", "uv.lock", "poetry.lock", "Pipfile",
    "Pipfile.lock", "Cargo.toml", "Cargo.lock", "go.mod", "go.sum", "Gemfile",
    "Gemfile.lock", "Makefile", "Justfile", "Dockerfile", "tsconfig.json",
    "pyrightconfig.json", "ruff.toml", ".ruff.toml", "pygate.toml",
    "quick-gate.config.json", "conftest.py",
}
_SENSITIVE = (
    "**/auth/**", "**/security/**", "**/migrations/**", "**/schema/**",
    "**/schemas/**", "**/*auth*.*", "**/*permission*.*", "**/*crypto*.*",
)


def select(config: GateConfig, paths: list[str], *, requested: str = "auto") -> dict[str, Any]:
    """Pure, deterministic routing; repository globs extend conservative defaults."""
    if requested not in {"auto", "fast", "full"}:
        raise ValueError("mode must be auto, fast or full")
    evidence: dict[str, list[str]] = {}
    review_paths: list[str] = []
    for path in sorted(set(paths)):
        item = PurePosixPath(path)
        name = item.name
        sensitive = any(_matches(path, pattern) for pattern in _SENSITIVE)
        category = ""
        if path.startswith((".hermes/", ".github/workflows/", ".github/actions/")):
            category = "gate-or-ci-contract"
        elif name in _CONTRACTS or name.startswith("requirements") or ".config." in name:
            category = "project-or-dependency-contract"
        elif (any(part in {"test", "tests", "__tests__"} for part in item.parts)
              or name.startswith("test_") or ".test." in name or ".spec." in name):
            category = "tests"
        elif sensitive:
            category = "sensitive-change"
        elif any(_matches(path, pattern) for pattern in config.routing_full_globs):
            category = "repository-full-policy"
        if category:
            evidence.setdefault(category, []).append(path)
        if (sensitive or name in {"AGENTS.md", "CLAUDE.md"}
                or any(_matches(path, p) for p in config.routing_review_globs)):
            review_paths.append(path)
    mode = "full" if requested == "auto" and evidence else (
        "fast" if requested == "auto" else requested
    )
    reason = ("broader impact requires the full declared contract" if evidence
              else "ordinary change uses applicable fast stages")
    if requested != "auto":
        reason = f"explicit {requested} mode"
    included = [path for path in sorted(set(paths)) if config.included(path)]
    stages = config.fast if mode == "fast" else config.full
    selected = [s.name for s in stages if mode == "full" or s.applies(included)]
    skipped = [s.name for s in stages if s.name not in selected]
    return {
        "schema": "kwik-gate/routing-v1", "requested_mode": requested, "mode": mode,
        "reason": reason, "evidence": evidence,
        "adapter": config.adapter.name if config.adapter.enabled else "native",
        "selected_stages": [] if config.adapter.enabled else selected,
        "skipped_stages": [] if config.adapter.enabled else skipped,
        "stage_scope": "all included inputs" if mode == "full" else "selected changed paths",
        "review_recommended": bool(review_paths), "review_paths": review_paths,
        "review_required_at_boundary": config.review_required,
        "review_executed": False,
    }
