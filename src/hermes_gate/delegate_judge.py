"""``hermes-gate delegate-judge``: judge one child workspace with the fast gate.

Wire contract (see README "Hermes Agent quality-gate seam"): read one JSON request
object from stdin and write exactly one JSON ``{"verdict", "feedback"}``
object to stdout. This module never runs a shell and never changes the
process's working directory; every gate call is bound to the caller-supplied
``workspace`` argument, so concurrent invocations of this command in separate
processes cannot race.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TextIO

from .engine import fast
from .gitstate import repo_root
from .status import Status

REQUEST_VERSION = 1
MAX_FEEDBACK_CHARS = 800
MAX_FAILED_CHECKS = 5

# name -> expected type for fields the emitter always sends with a concrete value.
_REQUIRED_FIELDS: dict[str, type] = {
    "version": int,
    "goal": str,
    "summary": str,
    "attempt": int,
    "max_retries": int,
    "task_index": int,
    "completed": bool,
}
# name -> expected type for fields the emitter may send as ``null``.
_NULLABLE_FIELDS: dict[str, type] = {
    "subagent_id": str,
    "session_id": str,
    "model": str,
    "api_calls": int,
    "workspace": str,
}
# name -> expected type for fields the emitter may omit entirely.
_OPTIONAL_FIELDS: dict[str, type] = {
    "workspace_isolated": bool,
}
_TYPE_LABELS: dict[type, str] = {int: "an integer", str: "a string", bool: "a boolean"}
_NO_WORKSPACE = "workspace unavailable: request has no workspace path"
_NOT_A_DIRECTORY = "workspace unavailable: path is not a directory"
_UNDECODABLE_STDIN = "stdin is not decodable text"
_PASSING_STATUSES = (Status.PASS, Status.NOT_APPLICABLE)
_CHECK_PASSING_STATUSES = {"pass", "skipped", "not_applicable"}
# The exact sentinel `repo_runner._execute`, `adapters.run_adapter`, and
# `engine._execution_dict` all use when a check's executable cannot be
# launched. Checks that carry a structured `unavailable` bool are trusted
# directly; this is the fallback for check shapes that only report it in
# `reason` text, matched exactly rather than by substring so an unrelated
# check whose own output happens to mention "unavailable" is not misread.
_EXECUTABLE_UNAVAILABLE_REASON = "executable unavailable"


def read_request(stream: TextIO) -> tuple[dict[str, Any] | None, str]:
    """Read the one required JSON request object from ``stream``.

    Returns ``(request, "")`` on success, or ``(None, reason)`` when the bytes
    on the stream are not a single JSON object.
    """

    try:
        raw = stream.read()
    except OSError as exc:
        return None, f"cannot read stdin: {exc}"
    except UnicodeError:
        # The seam contract is exactly one JSON object on stdout; exception
        # text could carry raw undecodable bytes, so the reason stays fixed.
        return None, _UNDECODABLE_STDIN
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"stdin is not valid JSON: {exc}"
    if not isinstance(value, dict):
        return None, "request must be a JSON object"
    return value, ""


def validate_request(value: dict[str, Any]) -> str:
    """Return "" when ``value`` matches the consumer contract, else a compact reason."""

    for field, kind in _REQUIRED_FIELDS.items():
        if field not in value:
            return f"missing required field: {field}"
        if not _matches(value[field], kind):
            return f"{field} must be {_TYPE_LABELS[kind]}"
    for field, kind in _NULLABLE_FIELDS.items():
        if field in value and value[field] is not None and not _matches(value[field], kind):
            return f"{field} must be {_TYPE_LABELS[kind]} or null"
    for field, kind in _OPTIONAL_FIELDS.items():
        if field in value and not _matches(value[field], kind):
            return f"{field} must be {_TYPE_LABELS[kind]}"
    if not _feedback_shape_ok(value.get("previous_feedback")):
        return "previous_feedback must be a string, an array of strings, or null"
    if value["version"] != REQUEST_VERSION:
        return f"unsupported request version: {value['version']!r}"
    workspace = value.get("workspace")
    if isinstance(workspace, str) and not workspace.strip():
        return "workspace must not be empty"
    if value["attempt"] < 1:
        return "attempt must be a positive integer (attempts are one-based)"
    if value["max_retries"] < 0:
        return "max_retries must be non-negative"
    return ""


def _feedback_shape_ok(value: Any) -> bool:
    # The judge never reads prior feedback; the check only keeps the wire shape honest.
    if value is None or isinstance(value, str):
        return True
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _matches(value: Any, kind: type) -> bool:
    if kind is bool:
        return isinstance(value, bool)
    if kind is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, kind)


def judge(request: dict[str, Any]) -> dict[str, str]:
    """Map one delegate-judge request to a bounded ``{"verdict", "feedback"}`` object."""

    error = validate_request(request)
    if error:
        return {"verdict": "error", "feedback": _bound(f"invalid request: {error}")}
    workspace_value = request.get("workspace")
    if workspace_value is None:
        return {"verdict": "error", "feedback": _NO_WORKSPACE}
    workspace = Path(workspace_value).expanduser()
    if not workspace.is_dir():
        return {"verdict": "error", "feedback": _NOT_A_DIRECTORY}
    root = repo_root(workspace)
    if root is None:
        return {"verdict": "error", "feedback": "workspace is not a Git repository"}
    outcome = fast(root)
    return _map_outcome(outcome, attempt=request["attempt"], max_retries=request["max_retries"])


def _map_outcome(outcome: dict[str, Any], *, attempt: int, max_retries: int) -> dict[str, str]:
    try:
        status = Status(str(outcome.get("status", Status.ERROR.value)))
    except ValueError:
        status = Status.ERROR
    reason = str(outcome.get("reason") or "")
    if status in _PASSING_STATUSES:
        return {"verdict": "pass", "feedback": ""}
    if status is Status.NOT_CONFIGURED:
        return {"verdict": "error", "feedback": _bound(f"gate not configured: {reason}")}
    if status is Status.FAIL:
        failing = _failing_checks(outcome)
        feedback = _bound(_fail_feedback(reason, failing))
        if any(_check_unavailable(check) for check in failing):
            # A check that could not even launch is an environment/adapter
            # problem, not something a correction turn can fix: the seam
            # contract calls for "error" here, not "retry" or "reject".
            return {"verdict": "error", "feedback": feedback}
        # `attempt` is one-based (the first attempt is 1) and `max_retries` counts
        # allowed correction turns after that first attempt, so up to
        # `max_retries` further attempts are still owed while attempt <= max_retries.
        verdict = "retry" if attempt <= max_retries else "reject"
        return {"verdict": verdict, "feedback": feedback}
    # ERROR, and any status `fast` is not documented to return (PARKED,
    # REVIEW_UNAVAILABLE): treat conservatively as an adapter/tool problem.
    return {"verdict": "error", "feedback": _bound(f"gate error: {reason or status.value}")}


def _failing_checks(outcome: dict[str, Any]) -> list[dict[str, Any]]:
    receipt = outcome.get("receipt")
    checks = receipt.get("checks") if isinstance(receipt, dict) else None
    if not isinstance(checks, list):
        return []
    return [
        check
        for check in checks
        if isinstance(check, dict)
        and str(check.get("status", "")).lower() not in _CHECK_PASSING_STATUSES
    ]


def _check_unavailable(check: dict[str, Any]) -> bool:
    unavailable = check.get("unavailable")
    if isinstance(unavailable, bool):
        return unavailable
    return str(check.get("reason") or "") == _EXECUTABLE_UNAVAILABLE_REASON


def _fail_feedback(reason: str, failing: list[dict[str, Any]]) -> str:
    lines = [reason or "fast gate failed"]
    for check in failing[:MAX_FAILED_CHECKS]:
        name = str(check.get("name", "check"))
        detail = str(check.get("reason") or check.get("status") or "failed")
        lines.append(f"- {name}: {detail}")
    overflow = len(failing) - MAX_FAILED_CHECKS
    if overflow > 0:
        lines.append(f"...and {overflow} more failing check(s)")
    return "\n".join(lines)


def _bound(text: str) -> str:
    if len(text) <= MAX_FEEDBACK_CHARS:
        return text
    return text[: MAX_FEEDBACK_CHARS - 1].rstrip() + "…"
