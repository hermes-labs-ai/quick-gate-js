"""Self-contained deterministic repository runner; copied byte-for-byte by init."""

from __future__ import annotations

import fnmatch
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

# The copied runner has the same minimum runtime as the installed CLI. This guard is a
# runtime check on whatever interpreter actually invokes the standalone copied file
# (which can be an older system python3, not the pinned venv), so it is not dead code
# even though pyproject.toml's target-version is already >=3.11.
if sys.version_info < (3, 11):  # noqa: UP036
    raise SystemExit("Hermes Gate runner requires Python 3.11 or newer; use that interpreter to run this file.")

import tomllib

RUNNER_VERSION = "0.4.0"
OUTPUT_CAP = 65536
# Git's canonical empty tree: diffing it against HEAD reviews every committed byte.
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
# Child stages read the resolved review range so nested `diff-check` runs review the
# same bytes the parent selected. Empty means the default worktree/index/untracked scope.
RANGE_ENV = "HERMES_GATE_RANGE"
BASE_ENV = "HERMES_GATE_BASE"


class RangeError(RuntimeError):
    """The requested review range could not be resolved against this checkout."""


def _root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise RuntimeError("not a Git repository")
    return Path(result.stdout.strip()).resolve()


def _changed(root: Path) -> list[str]:
    values: set[str] = set()
    for args in (
        ("diff", "--name-only", "-z"),
        ("diff", "--cached", "--name-only", "-z"),
        ("ls-files", "--others", "--exclude-standard", "-z"),
    ):
        proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)
        values.update(x.decode("utf-8", "surrogateescape") for x in proc.stdout.split(b"\0") if x)
    return sorted(values)


def _range_spec(root: Path, base: str | None, whole_tree: bool) -> str:
    """Resolve the requested review range into a single Git diff revision argument."""
    if whole_tree:
        return f"{EMPTY_TREE}..HEAD"
    if base is None:
        # Only an omitted base selects the local worktree, index and untracked scope.
        return ""
    if not base.strip():
        # An explicitly empty base is a misconfiguration, not a request for the local
        # scope: a hosted rail whose base expression resolved to nothing would otherwise
        # review a pristine checkout and report a pass over zero bytes.
        raise RangeError(
            "base revision is empty; omit --base and HERMES_GATE_BASE for the local "
            "worktree scope, or name a revision"
        )
    resolved = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    revision = resolved.stdout.strip()
    if resolved.returncode or not revision:
        raise RangeError(
            f"base revision {base!r} is not present in this checkout; "
            "fetch it (actions/checkout fetch-depth: 0) before running the gate"
        )
    # Three dots compares the merge base with HEAD, so the range holds only the
    # changes this head introduced, whether HEAD is the head or the merge commit.
    return f"{revision}...HEAD"


def _range_changed(root: Path, spec: str) -> list[str]:
    proc = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-only", "-z", spec],
        capture_output=True,
        check=False,
    )
    if proc.returncode:
        detail = proc.stderr.decode("utf-8", "replace").strip() or "git diff failed"
        raise RangeError(f"cannot compare {spec!r}: {detail}")
    return sorted(x.decode("utf-8", "surrogateescape") for x in proc.stdout.split(b"\0") if x)


def _match(path: str, pattern: str) -> bool:
    return fnmatch.fnmatch(path, pattern) or (
        pattern.startswith("**/") and fnmatch.fnmatch(path, pattern[3:])
    )


def run(
    mode: str,
    *,
    root: Path | None = None,
    files: list[str] | None = None,
    base: str | None = None,
    whole_tree: bool = False,
) -> dict[str, object]:
    started = time.monotonic()
    root = (root or _root()).resolve()
    config_path = root / ".hermes" / "gate.toml"
    if not config_path.is_file():
        return _result(mode, "NOT_CONFIGURED", started, [], "run hermes-gate init")
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return _result(mode, "ERROR", started, [], f"invalid profile: {exc}")
    spec = ""
    try:
        spec = _range_spec(root, base, whole_tree)
        if files is not None:
            paths = list(files)
        elif spec:
            paths = _range_changed(root, spec)
        else:
            # Default, and the only local behaviour: worktree, index and untracked bytes.
            paths = _changed(root)
    except RangeError as exc:
        return _result(mode, "ERROR", started, [], str(exc), range_spec=spec)
    paths = [path for path in paths if os.path.lexists(root / path)]
    exclusions = config.get("gate", {}).get("exclusions", [])
    paths = [path for path in paths if not any(_match(path, pattern) for pattern in exclusions)]
    if mode == "fast" and not paths:
        return _result(mode, "NOT_APPLICABLE", started, [], "no changed files")
    commands = list(config.get(mode, []))
    if not commands:
        return _result(mode, "NOT_CONFIGURED", started, [], f"no [[{mode}]] commands")
    budget = (
        float(config.get("gate", {}).get("fast_budget_seconds", 8.0)) if mode == "fast" else None
    )
    environment = {**os.environ, RANGE_ENV: spec}
    checks: list[dict[str, object]] = []
    executed = 0
    failed: list[str] = []
    invalid: list[str] = []
    for index, command in enumerate(commands):
        globs = command.get("globs", ["**/*"])
        selected = [path for path in paths if any(_match(path, pattern) for pattern in globs)]
        if mode == "fast" and not selected:
            # Fast keeps its original selection guard: a stage whose globs match nothing
            # is skipped outright, whether or not its argv reads {files}, so a narrow
            # fast stage never runs against an unrelated edit or eats the budget.
            continue
        raw_argv = command.get("argv", [])
        # Validate the container before converting it: a scalar argv must be reported as
        # this stage's error, not raise out of the loop and deny the caller a receipt.
        declared = list(raw_argv) if isinstance(raw_argv, list) else []
        name = str(command.get("name", declared[0] if declared else f"{mode}[{index}]"))
        if (
            not isinstance(raw_argv, list)
            or not declared
            or any(not isinstance(part, str) for part in declared)
        ):
            reason = "argv must be a non-empty string array"
            # One unusable declaration is that stage's error; the remaining declared
            # stages still owe the caller a result.
            if mode == "fast":
                return _result(mode, "ERROR", started, checks, reason, range_spec=spec)
            checks.append(
                {"name": name, "argv": declared, "status": "ERROR", "reason": reason}
            )
            invalid.append(name)
            continue
        if not selected and "{files}" in declared:
            # A file-driven stage with nothing to read checks no bytes; recording it as a
            # pass is how a hosted checkout used to report a green gate over nothing.
            checks.append({
                "name": name,
                "argv": declared,
                "status": "NOT_APPLICABLE",
                "reason": "no selected files for this stage",
            })
            continue
        argv: list[str] = []
        for part in declared:
            argv.extend(selected if part == "{files}" else [part])
        if not argv:
            reason = "argv must be a non-empty string array"
            if mode == "fast":
                return _result(mode, "ERROR", started, checks, reason, range_spec=spec)
            checks.append({"name": name, "argv": declared, "status": "ERROR", "reason": reason})
            invalid.append(name)
            continue
        elapsed = time.monotonic() - started
        timeout = float(command.get("timeout_seconds", 8.0))
        if budget is not None:
            timeout = min(timeout, max(0.01, budget - elapsed))
        check = _execute(argv, root, timeout, name, environment)
        checks.append(check)
        executed += 1
        if check["status"] != "PASS":
            # Fast keeps its first-failure exit so the local budget still holds; full owes
            # the caller the result of every declared stage.
            if mode == "fast":
                return _result(
                    mode, "FAIL", started, checks, str(check.get("reason", "check failed")),
                    range_spec=spec,
                )
            failed.append(name)
        if budget is not None and time.monotonic() - started >= budget:
            return _result(mode, "FAIL", started, checks, "fast budget exhausted", range_spec=spec)
    if invalid:
        reason = "unusable stage declarations: " + ", ".join(invalid)
        if failed:
            reason += "; failed stages: " + ", ".join(failed)
        return _result(mode, "ERROR", started, checks, reason, range_spec=spec)
    if failed:
        return _result(
            mode, "FAIL", started, checks, "failed stages: " + ", ".join(failed), range_spec=spec
        )
    if not executed:
        return _result(
            mode, "NOT_APPLICABLE", started, checks, "no commands matched changed files",
            range_spec=spec,
        )
    return _result(mode, "PASS", started, checks, "", range_spec=spec)


def _execute(
    argv: list[str],
    root: Path,
    timeout: float,
    name: str,
    environment: dict[str, str] | None = None,
) -> dict[str, object]:
    started = time.monotonic()
    try:
        proc = subprocess.Popen(
            argv,
            cwd=root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as exc:
        # A command that cannot be launched at all - missing, not executable, or the
        # wrong binary format - is this stage's failure, not the whole gate's.
        detail = "executable unavailable" if isinstance(exc, FileNotFoundError) else str(exc)
        return {"name": name, "argv": argv, "status": "FAIL", "reason": detail}

    stdout_capture: dict[str, object] = {"data": b"", "total": 0}
    stderr_capture: dict[str, object] = {"data": b"", "total": 0}
    assert proc.stdout is not None
    assert proc.stderr is not None
    threads = [
        threading.Thread(
            target=_drain_bounded,
            args=(proc.stdout, OUTPUT_CAP // 2, stdout_capture),
            daemon=True,
        ),
        threading.Thread(
            target=_drain_bounded,
            args=(proc.stderr, OUTPUT_CAP // 2, stderr_capture),
            daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()

    deadline = started + timeout
    while proc.poll() is None or any(thread.is_alive() for thread in threads):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(0.01, remaining))
    timed_out = proc.poll() is None or any(thread.is_alive() for thread in threads)
    if timed_out:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=0.25)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if proc.poll() is None:
            proc.wait()
        for thread in threads:
            thread.join(timeout=0.5)
        return {"name": name, "argv": argv, "status": "FAIL", "reason": "timeout"}

    for thread in threads:
        thread.join()
    stdout = bytes(stdout_capture["data"])
    stderr = bytes(stderr_capture["data"])
    total_output = int(stdout_capture["total"]) + int(stderr_capture["total"])
    return {
        "name": name,
        "argv": argv,
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "returncode": proc.returncode,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "stdout": stdout.decode("utf-8", "replace"),
        "stderr": stderr.decode("utf-8", "replace"),
        "output_truncated": total_output > len(stdout) + len(stderr),
    }


def _drain_bounded(pipe, cap: int, capture: dict[str, object]) -> None:
    kept = bytearray()
    total = 0
    try:
        while chunk := pipe.read(65536):
            total += len(chunk)
            remaining = cap - len(kept)
            if remaining > 0:
                kept.extend(chunk[:remaining])
    finally:
        pipe.close()
        capture["data"] = bytes(kept)
        capture["total"] = total


def _diff_check(root: Path, paths: list[str]) -> int:
    """Check selected worktree, index and untracked bytes using Git's whitespace rules."""
    if not paths:
        return 0
    git = ["git", "--literal-pathspecs", "-C", str(root)]
    review_range = os.environ.get(RANGE_ENV, "")
    if review_range:
        # A hosted checkout has no worktree or index changes, so the committed range is
        # the only thing worth checking; the parent resolved it once for every stage.
        result = subprocess.run(
            [*git, "diff", "--check", review_range, "--", *paths], check=False
        )
        return result.returncode
    for flags in ([], ["--cached"]):
        result = subprocess.run([*git, "diff", *flags, "--check", "--", *paths], check=False)
        if result.returncode:
            return result.returncode
    untracked = subprocess.run(
        [*git, "ls-files", "--others", "--exclude-standard", "-z", "--", *paths],
        capture_output=True, check=False,
    )
    if untracked.returncode:
        sys.stderr.buffer.write(untracked.stderr)
        return untracked.returncode
    for raw in untracked.stdout.split(b"\0"):
        if not raw:
            continue
        path = root / os.fsdecode(raw)
        # Git stores a symlink target, not the contents of its destination.
        if path.is_symlink() or not path.is_file():
            continue
        result = subprocess.run(
            [*git, "diff", "--no-index", "--check", "--", os.devnull, str(path)],
            check=False,
        )
        # --no-index implies --exit-code: 1 means a clean new-file diff;
        # --check reports whitespace errors with bit 2 set.
        if result.returncode not in (0, 1):
            return result.returncode
    return 0


def _result(
    mode: str,
    status: str,
    started: float,
    checks: list[dict[str, object]],
    reason: str,
    *,
    range_spec: str = "",
) -> dict[str, object]:
    return {
        "schema": "hermes-gate/runner-v1",
        "runner_version": RUNNER_VERSION,
        "command": mode,
        "status": status,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "checks": checks,
        "range": range_spec,
        "reason": reason,
    }


USAGE = "usage: runner.py fast|full [--base REV | --all]"


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if args and args[0] == "diff-check":
        return _diff_check(_root(), args[1:])
    if not args or args[0] not in {"fast", "full"}:
        print(json.dumps({"status": "ERROR", "reason": USAGE}))
        return 2
    mode, rest = args[0], args[1:]
    # Absent and empty are different requests: absent selects the local scope, while a
    # variable that is set but blank is kept so it fails clearly below instead of being
    # mistaken for "no base". An explicit --base still overrides the environment.
    environment_base = os.environ.get(BASE_ENV)
    base = environment_base.strip() if environment_base is not None else None
    base_source = BASE_ENV
    whole_tree = False
    while rest:
        option = rest.pop(0)
        if option == "--all":
            whole_tree = True
        elif option == "--base":
            if not rest:
                print(json.dumps({"status": "ERROR", "reason": "--base needs a revision"}))
                return 2
            base = rest.pop(0)
            base_source = "--base"
        elif option.startswith("--base="):
            base = option.split("=", 1)[1]
            base_source = "--base"
        else:
            print(json.dumps({"status": "ERROR", "reason": f"unknown option {option!r}; {USAGE}"}))
            return 2
    if base is not None and not base.strip():
        print(json.dumps({
            "status": "ERROR",
            "reason": f"{base_source} is set but empty; omit it for the local worktree scope "
            "or name a revision",
        }))
        return 2
    if whole_tree and base is not None:
        print(json.dumps({"status": "ERROR", "reason": "--all and --base are exclusive"}))
        return 2
    result = run(mode, base=base, whole_tree=whole_tree)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"PASS", "NOT_APPLICABLE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
