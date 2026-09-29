"""Conservative workload identity, separate from the diff used to select checks.

No commands are executed here. Executable bytes are identities, not attestations
about their dependencies or the environment. Ignored/excluded files are not inputs.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import sys
from pathlib import Path
from typing import Any

from .config import GateConfig, load_config
from .gitstate import ContentReadError, _digest_exact, git, head, snapshot


def _hash_file(path: Path) -> str:
    return _digest_exact(path, path.stat().st_size)


def _hash_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _executable(name: str, root: Path, *, depth: int = 0) -> dict[str, Any]:
    # Resolve relative PATH entries as the child process does, in its cwd.
    search = os.pathsep.join(
        str((root / entry).resolve()) if not Path(entry).is_absolute() else entry
        for entry in os.get_exec_path()
    )
    found = shutil.which(name, path=search) if not os.path.dirname(name) else None
    candidate = Path(found) if found else root / name
    if not candidate.is_file() or not os.access(candidate, os.X_OK):
        return {"status": "unavailable"}
    identity: dict[str, Any] = {"path": str(candidate.resolve()), "sha256": _hash_file(candidate)}
    # npm/npx and Python entry points are scripts. Bind their ordinary shebang
    # interpreter too, so an in-place Node/Python upgrade cannot reuse their PASS.
    if depth < 2:
        with candidate.open("rb") as stream:
            header = stream.readline(512)
        if header.startswith(b"#!"):
            try:
                words = shlex.split(header[2:].decode("utf-8").strip())
            except (UnicodeDecodeError, ValueError):
                words = []
            if words and Path(words[0]).name == "env":
                words = words[2:] if words[1:2] == ["-S"] else words[1:]
            if words and not words[0].startswith("-"):
                identity["interpreter"] = _executable(words[0], root, depth=depth + 1)
    return identity


def capture_binding(
    root: Path, kind: str, config: GateConfig | None = None
) -> dict[str, Any]:
    root = root.resolve()
    config = config or load_config(root)
    listed = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    paths = {
        item.decode("utf-8", "surrogateescape")
        for item in listed.stdout.split(b"\0") if item
    }
    paths = {path for path in paths if config.included(path)}
    # Even profiles that exclude .hermes cannot exclude the executed contract.
    paths.add(".hermes/gate.toml")
    runner = ".hermes/hermes_gate_runner.py"
    if (root / runner).exists():
        paths.add(runner)
    content = snapshot(root, paths)
    for path, identity in content.items():
        if identity == "DIRECTORY" or identity.endswith(":DIRECTORY"):
            raise ContentReadError(f"directory input is not supported: {path}")
        if ":UNREADABLE:" in identity:
            raise ContentReadError(f"cannot bind unreadable symlink target: {path}")
    modes = {
        path: ((root / path).lstat().st_mode & 0o111)
        for path in paths if os.path.lexists(root / path)
    }
    commands = config.fast if kind == "fast" else config.full if kind == "full" else ()
    executables = {spec.argv[0] for spec in commands}
    if kind == "review":
        executables.add(config.review.argv[0])
        if config.review.fallback_argv:
            executables.add(config.review.fallback_argv[0])
    if config.adapter.enabled and kind in {"fast", "full"} and config.adapter.argv:
        executables.add(config.adapter.argv[0])
    if config.lintlang.enabled and kind == "fast":
        executables.add(config.lintlang.argv[0])
    implementation = {
        path.name: _hash_file(path)
        for path in Path(__file__).parent.glob("*.py")
    }
    return {
        "schema": "kwik-gate/binding-v1",
        "head": head(root),
        "input_paths": sorted(paths),
        "input_digest": _hash_json({"content": content, "execution_bits": modes}),
        "contract_digest": _hash_json({
            "profile": _hash_file(root / ".hermes/gate.toml"),
            "executables": {name: _executable(name, root) for name in sorted(executables)},
            "implementation": implementation,
            "python_runtime": sys.version,
            "search_path": os.get_exec_path(),
        }),
    }
