#!/usr/bin/env python3
"""Claude Code plugin entry point for Hermes Gate's lifecycle hooks.

Delegates to `hermes_gate.hooks.run_hook(event, payload)`, which reads the
hook payload and does the actual work (see ../src/hermes_gate/hooks.py).
This wrapper exists only to locate the package and dispatch by event name:

  * The plugin ships hermes_gate's dependency-free runtime under `../src/`,
    so a marketplace install works without a separate pip install.
  * If the bundled runtime is absent, an already-installed `hermes-gate`
    package is still accepted as a compatibility fallback.
  * If neither is available, this fails open (`{"continue": true}`) rather
    than blocking a Claude Code session on a missing dependency.

Usage: hermes_gate_hook.py <session-start|stop|pre-tool-use>
Reads the hook JSON payload on stdin, writes the hook JSON response on
stdout, per src/hermes_gate/hooks.py's `run_hook` contract.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _prepend_plugin_src() -> None:
    """Use the runtime bundled in this plugin before any global install."""
    try:
        source = Path(__file__).resolve().parents[1] / "src"
    except IndexError:
        return
    if source.is_dir():
        sys.path.insert(0, str(source))


def main() -> int:
    _prepend_plugin_src()
    try:
        from hermes_gate.hooks import read_stdin_payload, run_hook
    except ImportError:
        print(json.dumps({"continue": True}))
        return 0  # no bundled or installed package - fail open

    if len(sys.argv) < 2:
        print(json.dumps({"continue": True}))
        return 0

    event = sys.argv[1]
    try:
        payload = read_stdin_payload()
        output = run_hook(event, payload)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        # Never let an unexpected internal error block a Claude Code
        # session; fail open exactly like a missing install would.
        print(json.dumps({"continue": True}))
        return 0

    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
