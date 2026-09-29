from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

MAX_OUTPUT_BYTES = 64 * 1024


@dataclass(frozen=True)
class Execution:
    argv: tuple[str, ...]
    returncode: int | None
    elapsed_ms: int
    stdout: str
    stderr: str
    timed_out: bool = False
    unavailable: bool = False
    output_truncated: bool = False


def run_argv(
    argv: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    output_cap: int = MAX_OUTPUT_BYTES,
    env: dict[str, str] | None = None,
) -> Execution:
    started = time.monotonic()
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    try:
        proc = subprocess.Popen(
            list(argv),
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            env=merged_env,
        )
    except FileNotFoundError:
        return Execution(
            tuple(argv), None, _elapsed(started), "", "executable not found", unavailable=True
        )
    try:
        stdout, stderr = proc.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = proc.communicate(timeout=0.25)
        except subprocess.TimeoutExpired:
            stdout = stderr = b""
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if proc.poll() is None:
            stdout, stderr = proc.communicate()
        return _result(argv, None, started, stdout, stderr, output_cap, timed_out=True)
    return _result(argv, proc.returncode, started, stdout, stderr, output_cap)


def _elapsed(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


def _result(
    argv: Sequence[str],
    returncode: int | None,
    started: float,
    stdout: bytes,
    stderr: bytes,
    cap: int,
    *,
    timed_out: bool = False,
) -> Execution:
    combined = len(stdout) + len(stderr)
    if combined > cap:
        stdout_cap = min(len(stdout), cap // 2)
        stderr_cap = max(0, cap - stdout_cap)
        stdout = stdout[:stdout_cap]
        stderr = stderr[:stderr_cap]
    return Execution(
        tuple(argv),
        returncode,
        _elapsed(started),
        stdout.decode("utf-8", "replace"),
        stderr.decode("utf-8", "replace"),
        timed_out=timed_out,
        output_truncated=combined > cap,
    )
