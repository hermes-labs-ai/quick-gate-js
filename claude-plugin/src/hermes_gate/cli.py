from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import __version__
from .codex_install import install as install_codex
from .codex_install import uninstall as uninstall_codex
from .delegate_judge import judge as delegate_judge
from .delegate_judge import read_request as read_delegate_request
from .doctor import diagnose
from .engine import boundary, fast, full, repair, review
from .gitstate import repo_root
from .hooks import read_stdin_payload, run_hook
from .init_repo import initialize, uninstall
from .status import EXIT_CODES, Status
from .workflow import plan as plan_workflow
from .workflow import run as run_workflow
from .workflow import verify as verify_workflow


def parser(prog: str = "hermes-gate") -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog=prog, description="KWIK-E-GATE: local checks, PASS/FAIL, content-bound receipts"
    )
    root.add_argument("--version", action="version", version=f"{prog} {__version__}")
    sub = root.add_subparsers(dest="command", required=True)
    init = sub.add_parser(
        "init", help="install a repository profile, runner, workflow, and baseline"
    )
    init.add_argument("--force", action="store_true")
    init.add_argument("--adapter", choices=("native", "pygate", "quick-gate"), default="native")
    run_command = sub.add_parser("run", help="run local checks and always issue a PASS/FAIL receipt")
    run_command.add_argument("--mode", default="auto", help="auto (default), fast or full")
    run_command.add_argument("--base", help="explicit committed comparison base")
    run_command.add_argument("--output", type=Path, help="export receipt outside the repository")
    verify_command = sub.add_parser("verify", help="verify a receipt against current inputs, read-only")
    verify_command.add_argument("--receipt", type=Path, help="exported receipt to verify")
    verify_command.add_argument("--kind", choices=("auto", "fast", "full"), default="auto")
    plan_command = sub.add_parser("plan", help="explain gate selection without executing checks")
    plan_command.add_argument("--mode", default="auto", help="auto (default), fast or full")
    plan_command.add_argument("--base", help="explicit committed comparison base")
    fast_command = sub.add_parser("fast", help="run the cached session-scoped deterministic gate")
    fast_command.add_argument("--base", help="committed base revision for a clean detached checkout")
    sub.add_parser("repair", help="run one configured deterministic repair")
    review_command = sub.add_parser("review", help="run one bounded independent review")
    review_command.add_argument("--base", help="committed base revision for a clean detached checkout")
    full_command = sub.add_parser("full", help="run the complete declared repository contract")
    full_command.add_argument("--base", help="explicit committed comparison base")
    bound = sub.add_parser("boundary", help="validate exact receipts for a Git or PR boundary")
    bound.add_argument("action", choices=("commit", "push", "pr-create", "pr-ready"))
    sub.add_parser("doctor", help="read-only installation and receipt diagnostics")
    sub.add_parser("install-codex", help=argparse.SUPPRESS)
    sub.add_parser("uninstall-codex", help=argparse.SUPPRESS)
    sub.add_parser("uninstall-repo", help=argparse.SUPPRESS)
    sub.add_parser("delegate-judge", help=argparse.SUPPRESS)
    hook = sub.add_parser("hook", help=argparse.SUPPRESS)
    hook.add_argument("event", choices=("session-start", "stop", "pre-tool-use"))
    return root


def main(argv: list[str] | None = None, *, prog: str = "hermes-gate") -> int:
    args = parser(prog).parse_args(argv)
    if args.command == "run":
        return _emit(run_workflow(
            Path.cwd(), mode=args.mode, base=_scope_base(args), output=args.output
        ))
    if args.command == "verify":
        return _emit(verify_workflow(Path.cwd(), path=args.receipt, kind=args.kind))
    if args.command == "plan":
        result = plan_workflow(Path.cwd(), mode=args.mode, base=_scope_base(args))
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] == "PLANNED" else 2
    if args.command == "hook":
        output = run_hook(args.event, read_stdin_payload())
        print(json.dumps(output, sort_keys=True))
        return 0
    if args.command == "doctor":
        output = diagnose(Path.cwd())
        return _emit(output)
    if args.command == "install-codex":
        executable = Path(sys.argv[0])
        output = install_codex(executable)
        return _emit(output)
    if args.command == "uninstall-codex":
        return _emit(uninstall_codex())
    if args.command == "delegate-judge":
        return _run_delegate_judge()
    root = repo_root(Path.cwd())
    if root is None:
        return _emit(
            {
                "schema": "hermes-gate/result-v1",
                "command": args.command,
                "status": Status.NOT_APPLICABLE.value,
                "reason": "not a Git repository",
                "elapsed_ms": 0,
            }
        )
    routes: dict[str, Callable[[], dict[str, Any]]] = {
        "init": lambda: _wrap_init(root, args.force, args.adapter),
        "fast": lambda: fast(root, base=_scope_base(args)),
        "repair": lambda: repair(root),
        "review": lambda: review(root, base=_scope_base(args)),
        "full": lambda: full(root, base=_scope_base(args)),
        "boundary": lambda: boundary(root, args.action),
        "uninstall-repo": lambda: _wrap_uninstall(root),
    }
    return _emit(routes[args.command]())


def kwik_main(argv: list[str] | None = None) -> int:
    return main(argv, prog="kwik-gate")


def _wrap_init(root: Path, force: bool, adapter: str = "native") -> dict[str, Any]:
    started = time.monotonic()
    value = initialize(root, force=force, adapter=adapter)
    return {
        "schema": "hermes-gate/result-v1",
        "command": "init",
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        **value,
    }


def _scope_base(args: argparse.Namespace) -> str | None:
    explicit = getattr(args, "base", None)
    return explicit if explicit is not None else os.environ.get("HERMES_GATE_BASE")


def _wrap_uninstall(root: Path) -> dict[str, Any]:
    started = time.monotonic()
    value = uninstall(root)
    return {
        "schema": "hermes-gate/result-v1",
        "command": "uninstall-repo",
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        **value,
    }


def _run_delegate_judge() -> int:
    request, error = read_delegate_request(sys.stdin)
    if error:
        output: dict[str, str] = {"verdict": "error", "feedback": error}
    else:
        assert request is not None
        try:
            output = delegate_judge(request)
        except Exception:  # noqa: BLE001 -- the seam must never crash a quality-gate child process
            # Exception text can carry paths, argv, or profile bytes, so the
            # harness-visible feedback stays a fixed string.
            output = {"verdict": "error", "feedback": "internal error while judging the workspace"}
    print(json.dumps(output, sort_keys=True))
    return 0


def _emit(output: dict[str, Any]) -> int:
    print(json.dumps(output, indent=2, sort_keys=True))
    try:
        status = Status(str(output.get("status", Status.ERROR.value)))
    except ValueError:
        status = Status.ERROR
    return EXIT_CODES[status]


if __name__ == "__main__":
    raise SystemExit(main())
