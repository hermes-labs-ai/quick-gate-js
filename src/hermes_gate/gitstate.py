from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from collections.abc import Iterable
from pathlib import Path

GIT_TIMEOUT_SECONDS = 10.0


class GitError(RuntimeError):
    pass


class ScopeError(GitError):
    """The committed scope cannot be selected without risking a false PASS."""


class ContentReadError(RuntimeError):
    """A path advertised bytes that could not be read faithfully."""


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    # Metadata queries need no optional monitor. A stalled daemon must not hang
    # discovery before the workflow can issue its failure receipt.
    argv = ["git", "-C", str(root), "-c", "core.fsmonitor=false", *args]
    try:
        proc = subprocess.run(
            argv, capture_output=True, check=False, timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        # Timeout is an infrastructure failure even for expected nonzero queries
        # such as an unborn HEAD or missing upstream. It cannot mean "no changes".
        raise GitError(f"git metadata query timed out after {GIT_TIMEOUT_SECONDS:g}s") from exc
    if check and proc.returncode:
        raise GitError(proc.stderr.decode("utf-8", "replace").strip() or "git command failed")
    return proc


def repo_root(start: Path | str | None = None) -> Path | None:
    cwd = Path(start or os.getcwd()).expanduser().resolve()
    proc = git(cwd, "rev-parse", "--show-toplevel", check=False)
    if proc.returncode:
        return None
    return Path(proc.stdout.decode().strip()).resolve()


def head(root: Path) -> str:
    proc = git(root, "rev-parse", "HEAD", check=False)
    return proc.stdout.decode().strip() if proc.returncode == 0 else "UNBORN"


def git_dir(root: Path) -> Path:
    return Path(git(root, "rev-parse", "--absolute-git-dir").stdout.decode().strip()).resolve()


def changed_paths(root: Path) -> list[str]:
    tracked = git(root, "diff", "--name-only", "-z", "--diff-filter=ACDMRTUXB", check=False)
    staged = git(
        root, "diff", "--cached", "--name-only", "-z", "--diff-filter=ACDMRTUXB", check=False
    )
    untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z")
    values: set[str] = set()
    for payload in (tracked.stdout, staged.stdout, untracked.stdout):
        values.update(
            item.decode("utf-8", "surrogateescape") for item in payload.split(b"\0") if item
        )
    return sorted(values)


def staged_paths(root: Path) -> list[str]:
    proc = git(
        root, "diff", "--cached", "--name-only", "-z", "--diff-filter=ACDMRTUXB", check=False
    )
    return sorted(
        item.decode("utf-8", "surrogateescape") for item in proc.stdout.split(b"\0") if item
    )


def scope(root: Path, *, base: str | None = None) -> tuple[list[str], str]:
    """Return changed paths and the exact commit that defines their comparison boundary."""
    dirty = changed_paths(root)
    if dirty:
        if base is None:
            upstream = git(
                root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", check=False
            )
            parents = git(root, "rev-list", "--parents", "-n", "1", "HEAD", check=False)
            if upstream.returncode and parents.returncode == 0 and len(parents.stdout.split()) > 2:
                raise ScopeError("scope unresolved: HEAD is a merge commit with no upstream or --base")
            return dirty, head(root)
        resolved = _resolve_base(root, base)
        committed = _diff_names(root, resolved, "HEAD")
        return sorted(set(committed) | set(dirty)), resolved
    if base is not None:
        resolved = _resolve_base(root, base)
        return _diff_names(root, resolved, "HEAD"), resolved
    upstream = git(
        root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", check=False
    )
    if upstream.returncode == 0:
        base = git(root, "merge-base", "HEAD", upstream.stdout.decode().strip(), check=False)
        if base.returncode == 0:
            resolved = base.stdout.decode().strip()
            return _diff_names(root, resolved, "HEAD"), resolved
    parents = git(root, "rev-list", "--parents", "-n", "1", "HEAD", check=False)
    if parents.returncode == 0 and len(parents.stdout.split()) > 2:
        raise ScopeError("scope unresolved: HEAD is a merge commit with no upstream or --base")
    parent = git(root, "rev-parse", "HEAD^", check=False)
    if parent.returncode == 0:
        resolved = parent.stdout.decode().strip()
        return _diff_names(root, resolved, "HEAD"), resolved
    tracked = git(root, "ls-files", "-z", check=False)
    return (
        sorted(item.decode("utf-8", "surrogateescape") for item in tracked.stdout.split(b"\0") if item),
        head(root),
    )


def scope_paths(root: Path, *, base: str | None = None) -> list[str]:
    """Current dirty paths, otherwise committed paths since an explicit base, upstream, or parent."""
    return scope(root, base=base)[0]


def _resolve_base(root: Path, base: str) -> str:
    resolved = git(root, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}", check=False)
    if resolved.returncode:
        raise ScopeError(f"scope unresolved: --base {base!r} is not a commit")
    return resolved.stdout.decode().strip()


def _diff_names(root: Path, base: str, target: str) -> list[str]:
    proc = git(
        root, "diff", "--name-only", "-z", "--diff-filter=ACDMRTUXB", base, target, check=False
    )
    return sorted(
        item.decode("utf-8", "surrogateescape") for item in proc.stdout.split(b"\0") if item
    )


def _path_digest(root: Path, relative: str) -> str:
    path = root / relative
    if not path.exists() and not path.is_symlink():
        return "MISSING"
    if path.is_symlink():
        identity = "SYMLINK:" + os.readlink(path)
        try:
            target_stat = path.stat()
        except FileNotFoundError:
            return f"{identity}:MISSING"
        except OSError as exc:
            return f"{identity}:UNREADABLE:{type(exc).__name__}"
        if not stat.S_ISREG(target_stat.st_mode):
            target_type = "DIRECTORY" if stat.S_ISDIR(target_stat.st_mode) else "OTHER"
            return f"{identity}:{target_type}"
        try:
            digest = _digest_exact(path, target_stat.st_size)
        except OSError as exc:
            return f"{identity}:UNREADABLE:{type(exc).__name__}"
        return f"{identity}:FILE:{digest}"
    if path.is_dir():
        return "DIRECTORY"
    try:
        expected_size = path.stat().st_size
        return _digest_exact(path, expected_size)
    except OSError as exc:
        raise ContentReadError(f"cannot read {relative}: {type(exc).__name__}") from exc


def _digest_exact(path: Path, expected_size: int) -> str:
    digest = hashlib.sha256()
    actual_size = 0
    with path.open("rb") as handle:
        while actual_size <= expected_size:
            chunk = handle.read(min(1024 * 1024, expected_size - actual_size + 1))
            if not chunk:
                break
            digest.update(chunk)
            actual_size += len(chunk)
    if actual_size != expected_size:
        raise ContentReadError(
            f"short read for {path}: expected {expected_size} bytes, got {actual_size}"
        )
    return digest.hexdigest()


def snapshot(root: Path, paths: Iterable[str] | None = None) -> dict[str, str]:
    selected = sorted(set(paths if paths is not None else changed_paths(root)))
    return {path: _path_digest(root, path) for path in selected}


def session_changed_paths(root: Path, baseline: dict[str, str] | None) -> list[str]:
    current_paths = changed_paths(root)
    current = snapshot(root, current_paths)
    if baseline is None:
        return current_paths
    return sorted(path for path, digest in current.items() if baseline.get(path) != digest)


def diff_digest(
    root: Path, paths: Iterable[str] | None = None, *, base: str | None = None
) -> str:
    if paths is None and base is None:
        selected, base = scope(root)
    else:
        selected = list(paths) if paths is not None else scope_paths(root, base=base)
    payload = {
        "base": base,
        "repo": str(root.resolve()),
        "paths": snapshot(root, selected),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def repo_identity(root: Path) -> dict[str, str]:
    remote = git(root, "config", "--get", "remote.origin.url", check=False).stdout.decode().strip()
    return {"root": str(root.resolve()), "head": head(root), "remote": remote or "NONE"}
