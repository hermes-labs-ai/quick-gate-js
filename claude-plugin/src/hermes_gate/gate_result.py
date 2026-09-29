from __future__ import annotations

import json
from importlib import resources
from typing import Any

RESULT_STATUSES = frozenset({"pass", "fail", "timeout", "error"})
CHECK_STATUSES = frozenset({"pass", "fail", "timeout", "missing", "error", "skipped"})
REQUIRED_FIELDS = (
    "schema",
    "status",
    "snapshot_digest",
    "checked_paths",
    "checks",
    "findings",
    "command_versions",
    "elapsed_ms",
    "output_truncated",
    "errors",
)


def load_schema() -> dict[str, Any]:
    """Load the packaged canonical gate-result/v1 schema using stdlib only."""

    schema_resource = resources.files("hermes_gate").joinpath("schemas/gate-result-v1.schema.json")
    value = json.loads(schema_resource.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("packaged gate-result/v1 schema is not an object")
    return value


def validate_gate_result(value: object) -> list[str]:
    """Return deterministic contract errors for the supported v1 schema."""

    if not isinstance(value, dict):
        return ["result must be an object"]
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in value:
            errors.append(f"missing required field: {field}")
    if value.get("schema") != "gate-result/v1":
        errors.append("schema must equal gate-result/v1")
    if "version" in value and value["version"] != "gate-result/v1":
        errors.append("deprecated version must equal gate-result/v1 when present")
    if value.get("status") not in RESULT_STATUSES:
        errors.append("status is not a gate-result/v1 status")
    if not isinstance(value.get("snapshot_digest"), str) or not value.get("snapshot_digest"):
        errors.append("snapshot_digest must be a non-empty string")
    if "snapshot_digest_after" in value and not isinstance(
        value["snapshot_digest_after"], (str, type(None))
    ):
        errors.append("snapshot_digest_after must be a string or null when present")
    if "snapshot_changed" in value and not isinstance(value["snapshot_changed"], bool):
        errors.append("snapshot_changed must be a boolean when present")
    if not isinstance(value.get("checked_paths"), list) or not all(
        isinstance(item, str) for item in value.get("checked_paths", [])
    ):
        errors.append("checked_paths must be an array of strings")
    checks = value.get("checks")
    if not isinstance(checks, list):
        errors.append("checks must be an array")
    else:
        for index, check in enumerate(checks):
            if not isinstance(check, dict):
                errors.append(f"checks[{index}] must be an object")
                continue
            if not isinstance(check.get("name"), str) or not check.get("name"):
                errors.append(f"checks[{index}].name must be a non-empty string")
            if check.get("status") not in CHECK_STATUSES:
                errors.append(f"checks[{index}].status is not a gate-result/v1 check status")
            for field in ("argv", "elapsed_ms", "timed_out", "output_truncated"):
                if field not in check:
                    errors.append(f"checks[{index}] is missing required field: {field}")
            if "argv" in check and not (
                isinstance(check["argv"], list)
                and all(isinstance(item, str) for item in check["argv"])
            ):
                errors.append(f"checks[{index}].argv must be an array of strings")
            if "elapsed_ms" in check and not _non_negative_integer(check["elapsed_ms"]):
                errors.append(f"checks[{index}].elapsed_ms must be a non-negative integer")
            if "exit_code" in check and not _integer_or_null(check["exit_code"]):
                errors.append(f"checks[{index}].exit_code must be an integer or null")
            if "signal" in check and not (
                check["signal"] is None
                or isinstance(check["signal"], str)
                or _integer(check["signal"])
            ):
                errors.append(f"checks[{index}].signal must be an integer, string, or null")
            for field in ("timed_out", "output_truncated"):
                if field in check and not isinstance(check[field], bool):
                    errors.append(f"checks[{index}].{field} must be a boolean")
    for field in ("findings", "errors"):
        if not isinstance(value.get(field), list):
            errors.append(f"{field} must be an array")
    if isinstance(value.get("errors"), list) and not all(
        isinstance(item, (str, dict)) for item in value["errors"]
    ):
        errors.append("errors items must be strings or objects")
    if not isinstance(value.get("command_versions"), dict):
        errors.append("command_versions must be an object")
    elif not all(
        isinstance(name, str) and isinstance(version, (str, dict))
        for name, version in value["command_versions"].items()
    ):
        errors.append("command_versions values must be strings or objects")
    elapsed = value.get("elapsed_ms")
    if not _non_negative_integer(elapsed):
        errors.append("elapsed_ms must be a non-negative integer")
    if not isinstance(value.get("output_truncated"), bool):
        errors.append("output_truncated must be a boolean")
    if "diagnostics" in value and not isinstance(value["diagnostics"], list):
        errors.append("diagnostics must be an array when present")
    elif isinstance(value.get("diagnostics"), list) and not all(
        isinstance(item, (str, dict)) for item in value["diagnostics"]
    ):
        errors.append("diagnostics items must be strings or objects")
    if "config_identity" in value and not isinstance(value["config_identity"], (str, dict)):
        errors.append("config_identity must be a string or object when present")
    for field in ("config_digest", "config_version", "package_version"):
        if field in value and not isinstance(value[field], str):
            errors.append(f"{field} must be a string when present")
    if "state_dir" in value and not isinstance(value["state_dir"], (str, type(None))):
        errors.append("state_dir must be a string or null when present")
    return errors


def _integer(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and (not isinstance(value, float) or value.is_integer())
    )


def _integer_or_null(value: object) -> bool:
    return value is None or _integer(value)


def _non_negative_integer(value: object) -> bool:
    return _integer(value) and isinstance(value, (int, float)) and value >= 0
