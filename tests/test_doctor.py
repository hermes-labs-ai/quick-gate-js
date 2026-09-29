from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from hermes_gate.doctor import _provider_auth_status, diagnose
from hermes_gate.execution import Execution

PROFILE = """version = 1
[gate]
fast_budget_seconds = 8.0
[review]
provider = "{provider}"
argv = {argv}
timeout_seconds = 1.0
[[fast]]
name = "noop"
argv = ["python3", "-c", "raise SystemExit(0)"]
timeout_seconds = 2.0
"""


def _repo(tmp_path: Path, *, provider: str, argv: list[str]) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    for args in (
        ["init", "-q"],
        ["config", "user.email", "test@example.com"],
        ["config", "user.name", "Test"],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    (root / ".hermes").mkdir()
    (root / ".hermes" / "gate.toml").write_text(
        PROFILE.format(provider=provider, argv=json.dumps(argv)), encoding="utf-8"
    )
    return root


def test_provider_auth_status_rejects_false_agent_event_even_on_zero_exit() -> None:
    output = '{"type":"status","status":"not_authenticated","authenticated":false}'

    assert _provider_auth_status(0, output) == "AUTH_REQUIRED"


def test_provider_auth_status_accepts_true_agent_event() -> None:
    output = '{"type":"status","status":"authenticated","authenticated":true}'

    assert _provider_auth_status(0, output) == "AUTHENTICATED"


def test_provider_auth_status_falls_back_for_legacy_output() -> None:
    assert _provider_auth_status(0, "Signed in") == "AUTHENTICATED"
    assert _provider_auth_status(1, "Sign-in required") == "AUTH_REQUIRED"


def test_diagnose_reports_unsupported_review_provider_as_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, provider="hermes-pr-review", argv=["hermes-pr-review"])
    monkeypatch.setattr("hermes_gate.doctor._provider_executable", lambda name, root: None)

    report = diagnose(root)

    assert report["profile"]["status"] == "ERROR"
    assert 'review.provider "hermes-pr-review"' in report["profile"]["reason"]
    assert report["status"] == "ERROR"


def test_diagnose_probes_the_configured_review_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, provider="coderabbit", argv=["review-wrapper", "review", "--agent"])
    looked_up: list[str] = []

    def missing(name: str, root: Path | None) -> None:
        looked_up.append(name)

    monkeypatch.setattr("hermes_gate.doctor._provider_executable", missing)

    report = diagnose(root)

    assert looked_up == ["review-wrapper"]
    assert report["provider"] == {
        "name": "coderabbit",
        "argv0": "review-wrapper",
        "binary": None,
        "status": "NOT_CONFIGURED",
    }


def test_diagnose_reports_auth_for_the_configured_review_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, provider="coderabbit", argv=["cr", "review", "--agent"])
    monkeypatch.setattr("hermes_gate.doctor._provider_executable", lambda name, root: "/opt/bin/cr")
    calls: list[list[str]] = []

    def probe(argv: list[str], **kwargs: object) -> Execution:
        calls.append(list(argv))
        return Execution(tuple(argv), 0, 1, '{"authenticated": true}', "")

    monkeypatch.setattr("hermes_gate.doctor.run_argv", probe)

    report = diagnose(root)

    assert calls == [["/opt/bin/cr", "auth", "status", "--agent"]]
    assert report["provider"]["argv0"] == "cr"
    assert report["provider"]["binary"] == "/opt/bin/cr"
    assert report["provider"]["status"] == "AUTHENTICATED"
    assert report["profile"]["status"] == "PASS"
