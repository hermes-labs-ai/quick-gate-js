from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .status import Status

MATERIAL_CATEGORIES = {
    "correctness",
    "security",
    "data-loss",
    "concurrency",
    "api-contract",
}
MATERIAL_SEVERITIES = {"critical", "major"}


@dataclass(frozen=True)
class Finding:
    severity: str
    category: str
    path: str
    line: int | None
    message: str


@dataclass(frozen=True)
class NormalizedReview:
    status: Status
    findings: tuple[Finding, ...]
    suppressed_count: int
    reason: str = ""


def normalize_coderabbit_output(
    payload: str | dict[str, Any] | list[Any],
    *,
    material_severities: Iterable[str] = MATERIAL_SEVERITIES,
    material_categories: Iterable[str] = MATERIAL_CATEGORIES,
) -> NormalizedReview:
    events: list[dict[str, Any]] = []
    if isinstance(payload, str):
        for line in payload.splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                events.append(item)
    elif isinstance(payload, dict):
        events = [payload]
    elif isinstance(payload, list):
        events = [item for item in payload if isinstance(item, dict)]
    if not events:
        return NormalizedReview(Status.REVIEW_UNAVAILABLE, (), 0, "no parseable agent events")

    severities = {item.lower() for item in material_severities}
    categories = {item.lower() for item in material_categories}
    findings: list[Finding] = []
    suppressed = 0
    completed = False
    error = ""
    for event in events:
        event_type = str(event.get("type", "")).lower()
        if event_type == "error":
            error = str(event.get("message") or event.get("error") or "provider error")
        if event_type in {"complete", "completed"}:
            completed = True
        if event_type != "finding":
            continue
        severity = str(event.get("severity", "info")).lower()
        message = str(
            event.get("message")
            or event.get("title")
            or event.get("codegenInstructions")
            or "CodeRabbit finding"
        )
        category = _category(event, message)
        material = severity in severities and category in categories
        if not material:
            suppressed += 1
            continue
        line = event.get("line") or event.get("lineNumber")
        findings.append(
            Finding(
                severity=severity,
                category=category,
                path=str(event.get("fileName") or event.get("path") or ""),
                line=int(line) if isinstance(line, int | float) else None,
                message=message,
            )
        )

    if error:
        return NormalizedReview(Status.REVIEW_UNAVAILABLE, tuple(findings), suppressed, error)
    if not completed:
        return NormalizedReview(
            Status.REVIEW_UNAVAILABLE, (), suppressed, "review did not complete"
        )
    return NormalizedReview(
        Status.FAIL if findings else Status.PASS,
        tuple(findings),
        suppressed,
    )


def normalize_jsonl_output(
    payload: str,
    *,
    digest: str,
    reviewed_paths: list[str],
    material_severities: Iterable[str] = MATERIAL_SEVERITIES,
    material_categories: Iterable[str] = MATERIAL_CATEGORIES,
) -> NormalizedReview:
    """Parse a bounded reviewer stream with an explicit exact-diff completion claim."""
    try:
        events = [json.loads(line) for line in payload.splitlines() if line.strip()]
    except json.JSONDecodeError:
        return NormalizedReview(Status.REVIEW_UNAVAILABLE, (), 0, "invalid JSONL review output")
    if not events or any(not isinstance(event, dict) for event in events):
        return NormalizedReview(Status.REVIEW_UNAVAILABLE, (), 0, "invalid JSONL review events")
    completions = [event for event in events if event.get("type") == "complete"]
    if len(completions) != 1 or events[-1] is not completions[0]:
        return NormalizedReview(Status.REVIEW_UNAVAILABLE, (), 0, "one final completion required")
    completion = completions[0]
    if completion.get("digest") != digest or completion.get("reviewed_paths") != reviewed_paths:
        return NormalizedReview(Status.REVIEW_UNAVAILABLE, (), 0, "review scope does not match current diff")
    severities = set(material_severities)
    categories = set(material_categories)
    findings: list[Finding] = []
    suppressed = 0
    for event in events[:-1]:
        if event.get("type") == "error":
            return NormalizedReview(
                Status.REVIEW_UNAVAILABLE, (), 0, str(event.get("message") or "provider error")
            )
        if event.get("type") != "finding":
            return NormalizedReview(Status.REVIEW_UNAVAILABLE, (), 0, "unknown review event")
        severity, category = event.get("severity"), event.get("category")
        path, message, line = event.get("path"), event.get("message"), event.get("line")
        if (
            not isinstance(severity, str)
            or not isinstance(category, str)
            or not isinstance(path, str)
            or path not in reviewed_paths
            or not isinstance(message, str)
            or not message.strip()
            or (line is not None and (not isinstance(line, int) or isinstance(line, bool) or line < 1))
        ):
            return NormalizedReview(Status.REVIEW_UNAVAILABLE, (), 0, "invalid or unscoped finding")
        if severity.lower() in severities and category.lower() in categories:
            findings.append(Finding(severity.lower(), category.lower(), path, line, message))
        else:
            suppressed += 1
    return NormalizedReview(Status.FAIL if findings else Status.PASS, tuple(findings), suppressed)


def _category(event: dict[str, Any], message: str) -> str:
    raw = str(event.get("category") or event.get("typeName") or "").lower().replace("_", "-")
    if raw in MATERIAL_CATEGORIES:
        return raw
    text = f"{raw} {message}".lower()
    mapping = (
        (
            "security",
            (
                "security",
                "vulnerab",
                "injection",
                "credential",
                "auth",
                "interpolat",
                "placeholder syntax",
                "bound parameter",
            ),
        ),
        ("data-loss", ("data loss", "truncate", "overwrite", "corrupt", "delete")),
        ("concurrency", ("race", "deadlock", "concurr", "thread", "atomic")),
        ("api-contract", ("api contract", "breaking change", "compatib", "schema")),
        ("correctness", ("correctness", "logic", "exception", "crash", "wrong", "bug", "null")),
    )
    for category, needles in mapping:
        if any(needle in text for needle in needles):
            return category
    return "other"
