from __future__ import annotations

import fnmatch
import json
import os
import shutil
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .adapters import run_adapter
from .binding import capture_binding
from .classification import is_code_path
from .config import ConfigError, GateConfig, load_config
from .execution import Execution, run_argv
from .gitstate import (
    ContentReadError,
    ScopeError,
    changed_paths,
    diff_digest,
    git,
    git_dir,
    head,
    scope,
    staged_paths,
)
from .init_repo import is_adopted
from .providers import NormalizedReview, normalize_coderabbit_output, normalize_jsonl_output
from .receipts import read_receipt, valid_receipt, write_receipt
from .repo_runner import run as run_repository
from .status import Status


def fast(
    root: Path, *, files: list[str] | None = None, base: str | None = None
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        config = load_config(root)
    except FileNotFoundError:
        return result("fast", Status.NOT_CONFIGURED, started, reason="run hermes-gate init")
    except ConfigError as exc:
        return result("fast", Status.ERROR, started, reason=f"invalid profile: {exc}")
    raw_selected, scope_base, scope_failure = _scope_or_error(
        root, "fast", started, files=files, base=base
    )
    if scope_failure:
        return scope_failure
    assert raw_selected is not None and scope_base is not None
    selected = [path for path in raw_selected if config.included(path)]
    digest, failure = _digest_or_error(root, selected, "fast", started, base=scope_base)
    if failure:
        return failure
    binding, failure = _binding_or_error(root, "fast", started, config)
    if failure:
        return failure
    cached = valid_receipt(root, "fast", digest, binding=binding)
    if cached:
        return result("fast", Status.PASS, started, receipt=cached, cached=True)
    runner_result = _run_gate(config, "fast", root, selected)
    checks = list(runner_result.get("checks", []))
    status = Status(str(runner_result["status"]))
    reason = str(runner_result.get("reason", ""))
    elapsed = time.monotonic() - started
    lintlang_paths = [path for path in selected if os.path.lexists(root / path)
                     and _lintlang_applies(config, [path])]
    if status in {Status.PASS, Status.NOT_APPLICABLE} and _lintlang_applies(config, lintlang_paths):
        remaining = config.fast_budget_seconds - elapsed
        if remaining <= 0:
            status, reason = Status.FAIL, "fast budget exhausted before LintLang"
        else:
            check = _run_spec(
                config.lintlang.argv,
                lintlang_paths,
                root,
                min(config.lintlang.timeout_seconds, remaining),
                "lintlang",
            )
            checks.append(check)
            if check["status"] != Status.PASS:
                status, reason = Status.FAIL, str(check.get("reason", "LintLang failed"))
    versions = _command_versions(
        runner_result, checks, root, deadline=started + config.fast_budget_seconds
    )
    if not _binding_unchanged(root, "fast", config, binding):
        status, reason = Status.ERROR, "check inputs or contract changed during execution"
    receipt = write_receipt(
        root,
        "fast",
        status=status.value,
        digest=digest,
        elapsed_ms=_elapsed(started),
        command_versions=versions,
        checks=checks,
        extra={
            "binding": binding,
            "checked_paths": selected,
            "scope_base": scope_base,
            "reason": reason,
            "runner_version": runner_result.get("runner_version"),
        },
    )
    return result("fast", status, started, reason=reason, receipt=receipt)


def full(root: Path, *, base: str | None = None) -> dict[str, Any]:
    started = time.monotonic()
    try:
        config = load_config(root)
    except FileNotFoundError:
        return result("full", Status.NOT_CONFIGURED, started, reason="run hermes-gate init")
    except ConfigError as exc:
        return result("full", Status.ERROR, started, reason=f"invalid profile: {exc}")
    raw_selected, scope_base, scope_failure = _scope_or_error(root, "full", started, base=base)
    if scope_failure:
        return scope_failure
    assert raw_selected is not None and scope_base is not None
    selected = [path for path in raw_selected if config.included(path)]
    digest, failure = _digest_or_error(root, selected, "full", started, base=scope_base)
    if failure:
        return failure
    binding, failure = _binding_or_error(root, "full", started, config)
    if failure:
        return failure
    # Full means the whole declared contract, including file-driven stages on
    # clean CI checkouts. Diff scope still controls compatibility boundaries.
    execution_paths = list(binding["input_paths"]) if binding else selected
    runner_result = _run_gate(config, "full", root, execution_paths)
    status = Status(str(runner_result["status"]))
    reason = str(runner_result.get("reason", ""))
    versions = _command_versions(runner_result, list(runner_result.get("checks", [])), root)
    if not _binding_unchanged(root, "full", config, binding):
        status, reason = Status.ERROR, "check inputs or contract changed during execution"
    receipt = write_receipt(
        root,
        "full",
        status=status.value,
        digest=digest,
        elapsed_ms=_elapsed(started),
        command_versions=versions,
        checks=list(runner_result.get("checks", [])),
        extra={
            "binding": binding,
            "execution_paths": execution_paths,
            "checked_paths": selected,
            "scope_base": scope_base,
            "reason": reason,
        },
    )
    if status is Status.PASS:
        _state_file(root, "review-budget.json").unlink(missing_ok=True)
    return result(
        "full", status, started, reason=reason, receipt=receipt
    )


def repair(root: Path) -> dict[str, Any]:
    started = time.monotonic()
    try:
        config = load_config(root)
    except FileNotFoundError:
        return result("repair", Status.NOT_CONFIGURED, started, reason="run hermes-gate init")
    except ConfigError as exc:
        return result("repair", Status.ERROR, started, reason=f"invalid profile: {exc}")
    raw_selected, scope_base, scope_failure = _scope_or_error(root, "repair", started)
    if scope_failure:
        return scope_failure
    assert raw_selected is not None and scope_base is not None
    selected = [path for path in raw_selected if config.included(path)]
    if not selected:
        return result("repair", Status.NOT_APPLICABLE, started, reason="no changed files")
    if not config.repair:
        return result("repair", Status.NOT_CONFIGURED, started, reason="no [[repair]] command")
    digest, failure = _digest_or_error(root, selected, "repair", started, base=scope_base)
    if failure:
        return failure
    state_path = _state_file(root, "repair-budget.json")
    state = _read_json(state_path)
    if state.get("digest") == digest and int(state.get("attempts", 0)) >= 1:
        return result(
            "repair",
            Status.PARKED,
            started,
            reason="one deterministic repair already attempted for this diff",
        )
    _write_json(state_path, {"digest": digest, "attempts": 1})
    checks: list[dict[str, Any]] = []
    status, reason = Status.PASS, ""
    for spec in config.repair:
        if not spec.applies(selected):
            continue
        check = _run_spec(spec.argv, selected, root, spec.timeout_seconds, spec.name)
        checks.append(check)
        if check["status"] != Status.PASS:
            status, reason = Status.FAIL, str(check.get("reason", "repair failed"))
            break
    return result("repair", status, started, reason=reason, checks=checks)


def review(root: Path, *, base: str | None = None) -> dict[str, Any]:
    started = time.monotonic()
    try:
        config = load_config(root)
    except FileNotFoundError:
        return result("review", Status.NOT_CONFIGURED, started, reason="run hermes-gate init")
    except ConfigError as exc:
        return result("review", Status.ERROR, started, reason=f"invalid profile: {exc}")
    raw_selected, scope_base, scope_failure = _scope_or_error(root, "review", started, base=base)
    if scope_failure:
        return scope_failure
    assert raw_selected is not None and scope_base is not None
    selected = [path for path in raw_selected if config.included(path)]
    digest, failure = _digest_or_error(root, selected, "review", started, base=scope_base)
    if failure:
        return failure
    if not valid_receipt(root, "fast", digest):
        return result(
            "review",
            Status.PARKED,
            started,
            reason="matching fast PASS required; run hermes-gate fast",
        )
    binding, failure = _binding_or_error(root, "review", started, config)
    if failure:
        return failure
    cached = valid_receipt(root, "review", digest, binding=binding)
    if cached and _review_provider_matches(cached, config.review.provider):
        return result("review", Status.PASS, started, receipt=cached, cached=True)
    budget_path = _state_file(root, "review-budget.json")
    budget = _read_json(budget_path)
    attempts_by_digest = _review_attempts_by_digest(budget)
    attempt_key = digest if config.review.provider == "coderabbit" else f"{config.review.provider}:{digest}"
    if attempts_by_digest.get(attempt_key, 0) >= 2:
        return result(
            "review",
            Status.PARKED,
            started,
            reason="one initial review and one re-review exhausted for this diff; run hermes-gate full",
        )

    provider_version = _tool_version(config.review.argv[0], root)
    provider_argv = _provider_review_argv(config, root, base=scope_base)
    provider_env = None
    if config.review.provider == "jsonl":
        provider_env = {
            "HERMES_GATE_DIFF_DIGEST": digest,
            "HERMES_GATE_REVIEWED_PATHS": json.dumps(selected),
            "HERMES_GATE_SCOPE_BASE": scope_base,
        }
    execution = run_argv(
        provider_argv,
        cwd=root,
        timeout_seconds=config.review.timeout_seconds,
        env=provider_env,
    )
    if execution.unavailable or execution.timed_out or execution.output_truncated:
        normalized = NormalizedReview(
            Status.REVIEW_UNAVAILABLE, (), 0, "provider unavailable, timed out, or truncated"
        )
    elif execution.returncode != 0:
        normalized = normalize_coderabbit_output(
            {"type": "error", "message": f"provider exited {execution.returncode}"},
            material_severities=config.review.material_severities,
            material_categories=config.review.material_categories,
        )
    elif config.review.provider == "jsonl":
        normalized = normalize_jsonl_output(
            execution.stdout,
            digest=digest,
            reviewed_paths=selected,
            material_severities=config.review.material_severities,
            material_categories=config.review.material_categories,
        )
    else:
        normalized = normalize_coderabbit_output(
            execution.stdout,
            material_severities=config.review.material_severities,
            material_categories=config.review.material_categories,
        )
    provider = config.review.provider
    fallback_attempted = False
    fallback_provider = ""
    fallback_reason = ""
    if config.review.provider == "coderabbit" and (
        execution.unavailable
        or execution.timed_out
        or normalized.status is Status.REVIEW_UNAVAILABLE
    ):
        fallback_argv = config.review.fallback_argv
        if (
            not fallback_argv
            and shutil.which("hermes-pr-review")
            and not changed_paths(root)
            and _automatic_fallback_base(root, scope_base) is not None
        ):
            fallback_argv = ("hermes-pr-review",)
        fallback_attempted = bool(fallback_argv)
        fallback_provider = fallback_argv[0] if fallback_argv else ""
        fallback = _fallback_review(config, root, digest, base=scope_base)
        if fallback is not None:
            execution, normalized, provider, provider_version = fallback
        elif fallback_attempted:
            fallback_reason = "fallback provider returned no usable review result"
    if config.review.provider == "jsonl":
        post_digest, failure = _digest_or_error(root, selected, "review", started, base=scope_base)
        if failure:
            return failure
        if post_digest != digest:
            normalized = NormalizedReview(
                Status.REVIEW_UNAVAILABLE, (), 0, "reviewer changed the scoped files"
            )
    if not _binding_unchanged(root, "review", config, binding):
        normalized = NormalizedReview(
            Status.REVIEW_UNAVAILABLE, (), 0, "reviewer changed check inputs or contract"
        )
    status = normalized.status
    findings = [asdict(item) for item in normalized.findings]
    reason = normalized.reason
    # Provider/adapter failures are retryable infrastructure outcomes. Only a
    # completed semantic result spends one of the two bounded attempts, and the
    # budget is keyed by the exact current digest so stale prior diffs cannot
    # park a changed review.
    if status is not Status.REVIEW_UNAVAILABLE:
        attempts_by_digest[attempt_key] = attempts_by_digest.get(attempt_key, 0) + 1
        _write_json(budget_path, {"attempts_by_digest": attempts_by_digest})
    receipt = write_receipt(
        root,
        "review",
        status=status.value,
        digest=digest,
        elapsed_ms=_elapsed(started),
        command_versions={provider: provider_version},
        findings=findings,
        checks=[_execution_dict(execution, provider)],
        extra={
            "binding": binding,
            "provider": provider,
            "configured_provider": config.review.provider,
            "suppressed_count": normalized.suppressed_count,
            "reviewed_paths": selected,
            "scope_base": scope_base,
            "reason": reason,
            "fallback_attempted": fallback_attempted,
            "fallback_provider": fallback_provider,
            "fallback_reason": fallback_reason,
        },
    )
    return result("review", status, started, reason=reason, receipt=receipt, findings=findings)


def boundary(root: Path, action: str) -> dict[str, Any]:
    started = time.monotonic()
    if action == "commit":
        raw_selected = staged_paths(root)
        scope_base = head(root)
    else:
        raw_selected, scope_base, scope_failure = _scope_or_error(root, "boundary", started)
        if scope_failure:
            return scope_failure
        assert raw_selected is not None and scope_base is not None
    try:
        config = load_config(root)
    except FileNotFoundError:
        if not any(is_code_path(path) for path in raw_selected):
            return result(
                "boundary", Status.PASS, started, reason="non-code boundary is exempt", required=[]
            )
        if not is_adopted(root):
            return result(
                "boundary",
                Status.PASS,
                started,
                reason="repository is outside the Gate rail",
                required=[],
            )
        return result("boundary", Status.NOT_CONFIGURED, started, reason="run hermes-gate init")
    except ConfigError as exc:
        return result("boundary", Status.ERROR, started, reason=f"invalid profile: {exc}")
    if not any(is_code_path(path) for path in raw_selected):
        return result(
            "boundary", Status.PASS, started, reason="non-code boundary is exempt", required=[]
        )
    selected = [path for path in raw_selected if config.included(path)]
    if action == "commit" and selected:
        staged_difference = git(root, "diff", "--quiet", "--", *selected, check=False)
        if staged_difference.returncode:
            return result(
                "boundary", Status.FAIL, started,
                reason="staged bytes differ from checked working-tree bytes; stage checked bytes and run fast",
                required=["fast"], missing=["fast"],
            )
    digest, failure = _digest_or_error(root, selected, "boundary", started, base=scope_base)
    if failure:
        return failure
    requirements = ["fast"]
    if action in {"push", "pr-create", "pr-ready"}:
        if config.review_required:
            requirements.append("review")
        if config.full_required_local:
            requirements.append("full")
    missing: list[str] = []
    for kind in requirements:
        receipt = valid_receipt(root, kind, digest)
        if receipt and (kind != "review" or _review_provider_matches(receipt, config.review.provider)):
            continue
        if action == "commit" and _receipt_covers(root, kind, raw_selected):
            continue
        missing.append(kind)
    if missing:
        commands = " && ".join(f"hermes-gate {kind}" for kind in missing)
        return result(
            "boundary",
            Status.FAIL,
            started,
            reason=f"{action} requires matching {' + '.join(missing)} PASS receipt(s); run {commands}",
            required=requirements,
            missing=missing,
        )
    return result("boundary", Status.PASS, started, required=requirements)


def _review_provider_matches(receipt: dict[str, Any], configured_provider: str) -> bool:
    recorded = receipt.get("configured_provider")
    if isinstance(recorded, str):
        return recorded == configured_provider
    actual = receipt.get("provider")
    return actual == configured_provider or (
        configured_provider == "coderabbit" and actual == "hermes-pr-review"
    )


def _receipt_covers(root: Path, kind: str, selected: list[str]) -> bool:
    receipt = read_receipt(root, kind)
    checked = receipt.get("checked_paths", []) if receipt else []
    if not receipt or not set(selected).issubset(set(checked)):
        return False
    try:
        base = receipt.get("scope_base")
        digest = diff_digest(root, checked, base=base if isinstance(base, str) else None)
    except ContentReadError:
        return False
    return valid_receipt(root, kind, digest) is not None


def _scope_or_error(
    root: Path,
    command: str,
    started: float,
    *,
    files: list[str] | None = None,
    base: str | None = None,
) -> tuple[list[str] | None, str | None, dict[str, Any] | None]:
    try:
        if files is not None:
            _, resolved_base = scope(root, base=base)
            return files, resolved_base, None
        selected, resolved_base = scope(root, base=base)
        return selected, resolved_base, None
    except ScopeError as exc:
        return None, None, result(command, Status.ERROR, started, reason=str(exc))


def _digest_or_error(
    root: Path, selected: list[str], kind: str, started: float, *, base: str | None
) -> tuple[str | None, dict[str, Any] | None]:
    try:
        return diff_digest(root, selected, base=base), None
    except ContentReadError as exc:
        return None, result(
            kind,
            Status.ERROR,
            started,
            reason=f"cannot bind receipt to complete input bytes: {exc}",
        )


def _binding_or_error(
    root: Path, kind: str, started: float, config: GateConfig
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        return capture_binding(root, kind, config), None
    except (ContentReadError, OSError) as exc:
        return None, result(kind, Status.ERROR, started, reason=f"cannot bind check inputs: {exc}")


def _binding_unchanged(
    root: Path, kind: str, config: GateConfig, before: dict[str, Any] | None
) -> bool:
    try:
        return before == capture_binding(root, kind, config)
    except (ContentReadError, OSError):
        return False


def _lintlang_applies(config: GateConfig, files: list[str]) -> bool:
    return config.lintlang.enabled and any(
        any(
            fnmatch.fnmatch(path, pattern)
            or (pattern.startswith("**/") and fnmatch.fnmatch(path, pattern[3:]))
            for pattern in config.lintlang.trigger_globs
        )
        for path in files
    )


def _run_gate(config: GateConfig, mode: str, root: Path, selected: list[str]) -> dict[str, Any]:
    if config.adapter.enabled:
        timeout = (
            config.fast_budget_seconds
            if mode == "fast"
            else sum(spec.timeout_seconds for spec in config.full) or 600.0
        )
        return run_adapter(
            config.adapter,
            root=root,
            mode=mode,
            checked_paths=selected,
            timeout_seconds=timeout,
        )
    return run_repository(mode, root=root, files=selected)


def _command_versions(
    runner_result: dict[str, Any],
    checks: list[dict[str, Any]],
    root: Path,
    *,
    deadline: float | None = None,
) -> dict[str, str]:
    versions = {
        str(name): value if isinstance(value, str) else json.dumps(value, sort_keys=True)
        for name, value in dict(runner_result.get("command_versions", {})).items()
    }
    for check in checks:
        argv = check.get("argv", [])
        if isinstance(argv, list) and argv and isinstance(argv[0], str):
            name = argv[0]
            if name in versions:
                continue
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                versions[name] = "BUDGET_EXHAUSTED"
            else:
                versions[name] = _tool_version(
                    name,
                    root,
                    timeout_seconds=min(3, remaining) if remaining is not None else 3,
                )
    return versions


def _run_spec(
    argv: tuple[str, ...], files: list[str], root: Path, timeout: float, name: str
) -> dict[str, Any]:
    expanded: list[str] = []
    for part in argv:
        expanded.extend(files if part == "{files}" else [part])
    return _execution_dict(run_argv(expanded, cwd=root, timeout_seconds=timeout), name)


def _execution_dict(execution: Execution, name: str) -> dict[str, Any]:
    if execution.unavailable:
        status, reason = Status.FAIL, "executable unavailable"
    elif execution.timed_out:
        status, reason = Status.FAIL, "timeout"
    elif execution.returncode == 0:
        status, reason = Status.PASS, ""
    else:
        status, reason = Status.FAIL, f"exit {execution.returncode}"
    return {
        "name": name,
        "argv": list(execution.argv),
        "status": status.value,
        "returncode": execution.returncode,
        "elapsed_ms": execution.elapsed_ms,
        "stdout": execution.stdout,
        "stderr": execution.stderr,
        "timed_out": execution.timed_out,
        "unavailable": execution.unavailable,
        "output_truncated": execution.output_truncated,
        "reason": reason,
    }


def _automatic_fallback_base(root: Path, base: str | None) -> str | None:
    """Return a non-empty committed comparison base for the automatic fallback."""
    if base is None:
        resolved = git(root, "rev-parse", "HEAD^", check=False)
    else:
        resolved = git(root, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}", check=False)
    if resolved.returncode:
        return None
    exact_base = resolved.stdout.decode().strip()
    diff = git(root, "diff", "--quiet", exact_base, "HEAD", "--", check=False)
    return exact_base if diff.returncode == 1 else None


def _fallback_review(
    config: GateConfig, root: Path, digest: str, *, base: str | None = None
):
    argv = config.review.fallback_argv
    environment: dict[str, str] | None = None
    if base is not None:
        resolved = git(root, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}", check=False)
        if resolved.returncode:
            return None
        environment = {"HERMES_GATE_BASE": resolved.stdout.decode().strip()}
    output_dir: Path | None = None
    if not argv and shutil.which("hermes-pr-review") and not changed_paths(root):
        fallback_base = _automatic_fallback_base(root, base)
        if fallback_base is None:
            return None
        output_dir = git_dir(root) / "hermes-gate" / "providers" / "hermes-pr-review" / digest
        output_dir.mkdir(parents=True, exist_ok=True)
        argv = (
            "hermes-pr-review",
            "--repo",
            str(root),
            "--base",
            fallback_base,
            "--output-dir",
            str(output_dir),
            "--run-codex",
            "--model",
            "gpt-5.6-terra",
            "--reasoning-effort",
            "high",
            "--deadline-seconds",
            str(min(config.review.timeout_seconds, 180.0)),
        )
    if not argv:
        return None
    execution = run_argv(
        argv, cwd=root, timeout_seconds=config.review.timeout_seconds + 5, env=environment
    )
    if execution.unavailable or execution.timed_out:
        return None
    if output_dir is not None:
        try:
            raw = json.loads((output_dir / "review.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        if raw.get("verdict") == "UNEVALUATED":
            return None
        events: list[dict[str, Any]] = []
        for finding in raw.get("findings", []):
            events.append(
                {
                    "type": "finding",
                    "severity": "major"
                    if finding.get("severity") in {"ERROR", "WARNING"}
                    else "minor",
                    "fileName": finding.get("path", ""),
                    "line": finding.get("line"),
                    "message": f"correctness: {finding.get('title', '')} {finding.get('body', '')}",
                    "category": "correctness",
                }
            )
        events.append({"type": "complete"})
        normalized = normalize_coderabbit_output(
            events,
            material_severities=config.review.material_severities,
            material_categories=config.review.material_categories,
        )
    else:
        # Configured fallbacks must emit the CodeRabbit-compatible JSONL event contract.
        normalized = normalize_coderabbit_output(
            execution.stdout,
            material_severities=config.review.material_severities,
            material_categories=config.review.material_categories,
        )
    if normalized.status is Status.REVIEW_UNAVAILABLE:
        return None
    name = argv[0]
    return execution, normalized, name, _tool_version(name, root)


def _provider_review_argv(
    config: GateConfig, root: Path, *, base: str | None = None
) -> tuple[str, ...]:
    """Bind CodeRabbit to the exact local dirty or committed boundary."""
    argv = tuple(config.review.argv)
    if config.review.provider != "coderabbit":
        return argv
    if base is not None:
        resolved = git(root, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}", check=False)
        if resolved.returncode:
            return argv
        exact_base = resolved.stdout.decode().strip()
        rewritten: list[str] = []
        seen_committed = False
        skip_base_value = False
        dirty = bool(changed_paths(root))
        for item in argv:
            if skip_base_value:
                skip_base_value = False
                continue
            if item == "--base-commit":
                skip_base_value = True
                continue
            if item.startswith("--base-commit=") or item == "--uncommitted":
                continue
            if item == "--committed":
                if dirty:
                    continue
                if seen_committed:
                    continue
                seen_committed = True
            rewritten.append(item)
        if dirty:
            if "--include-untracked" not in rewritten:
                rewritten.append("--include-untracked")
        elif not seen_committed:
            rewritten.append("--committed")
        return (*rewritten, "--base-commit", exact_base)
    boundary_flags = ("--base", "--base-commit", "--committed", "--uncommitted")
    if any(
        item == flag or item.startswith(f"{flag}=") for item in argv for flag in boundary_flags
    ):
        return argv
    branch = git(root, "branch", "--show-current", check=False).stdout.decode().strip()
    base_selector: tuple[str, ...] = ("--base", branch) if branch else ()
    if changed_paths(root):
        return (*argv, "--include-untracked", *base_selector, "--base-commit", "HEAD")
    base = git(root, "merge-base", "HEAD", "@{upstream}", check=False)
    if base.returncode:
        base = git(root, "rev-parse", "HEAD^", check=False)
    if base.returncode:
        return (*argv, "--include-untracked", *base_selector, "--base-commit", "HEAD")
    return (
        *argv,
        "--committed",
        *base_selector,
        "--base-commit",
        base.stdout.decode().strip(),
    )


def _tool_version(name: str, root: Path, *, timeout_seconds: float = 3) -> str:
    path = shutil.which(name)
    if path:
        executable = str(Path(path).resolve())
    else:
        candidate = root / name
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            return "UNAVAILABLE"
        executable = str(candidate)
    execution = run_argv(
        [executable, "--version"],
        cwd=root,
        timeout_seconds=max(0.001, timeout_seconds),
        output_cap=2048,
    )
    lines = (execution.stdout or execution.stderr).strip().splitlines()
    return lines[0][:200] if lines else "UNKNOWN"


def _state_file(root: Path, name: str) -> Path:
    from .gitstate import git_dir

    path = git_dir(root) / "hermes-gate" / "state" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _review_attempts_by_digest(budget: dict[str, Any]) -> dict[str, int]:
    """Read current and legacy review budgets without letting old digests block."""
    current = budget.get("attempts_by_digest")
    if isinstance(current, dict):
        return {
            str(digest): int(attempts)
            for digest, attempts in current.items()
            if isinstance(digest, str) and isinstance(attempts, int) and attempts >= 0
        }
    # Older Gate versions stored one entry per attempted digest. Preserve that
    # evidence as one attempt for each digest, but do not apply a global cap.
    legacy = budget.get("digests", [])
    if isinstance(legacy, list):
        return {str(digest): 1 for digest in legacy if isinstance(digest, str)}
    return {}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _elapsed(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


def result(command: str, status: Status, started: float, **extra: Any) -> dict[str, Any]:
    return {
        "schema": "hermes-gate/result-v1",
        "command": command,
        "status": status.value,
        "elapsed_ms": _elapsed(started),
        **extra,
    }
