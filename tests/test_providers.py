"""Provider normalization is deliberately narrow and deterministic."""

from __future__ import annotations

import json
from pathlib import Path

from hermes_gate.providers import normalize_coderabbit_output, normalize_jsonl_output

FIXTURES = Path(__file__).parent / "fixtures"


def payload(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_normalization_keeps_only_material_categories_and_counts_suppression() -> None:
    result = normalize_coderabbit_output(payload("coderabbit_material.json"))

    assert result.status == "FAIL"
    assert result.suppressed_count == 2
    assert [finding.category for finding in result.findings] == [
        "security",
        "correctness",
        "data-loss",
        "concurrency",
        "api-contract",
    ]
    assert [(finding.path, finding.line) for finding in result.findings] == [
        ("src/auth.py", 41),
        ("src/queue.py", 73),
        ("src/store.py", 18),
        ("src/worker.py", 95),
        ("src/api.py", 12),
    ]


def test_clean_structured_output_is_a_pass() -> None:
    result = normalize_coderabbit_output(payload("coderabbit_clean.json"))

    assert result.status == "PASS"
    assert result.findings == ()
    assert result.suppressed_count == 0


def test_malformed_output_is_honestly_unavailable() -> None:
    result = normalize_coderabbit_output(payload("coderabbit_malformed.json"))

    assert result.status == "REVIEW_UNAVAILABLE"
    assert result.findings == ()
    assert result.suppressed_count == 0
    assert result.reason


def test_provider_error_is_honestly_unavailable() -> None:
    result = normalize_coderabbit_output(payload("coderabbit_unavailable.json"))

    assert result.status == "REVIEW_UNAVAILABLE"
    assert result.findings == ()
    assert "rate" in result.reason.lower()


def test_normalization_accepts_an_already_decoded_agent_event() -> None:
    result = normalize_coderabbit_output(json.loads(payload("coderabbit_clean.json")))

    assert result.status == "PASS"


def test_finding_stream_without_completion_is_unavailable() -> None:
    result = normalize_coderabbit_output(
        '{"type":"finding","severity":"low","category":"style","message":"nit"}'
    )

    assert result.status == "REVIEW_UNAVAILABLE"
    assert result.reason == "review did not complete"


def test_actual_cli_parameterization_finding_is_material_security() -> None:
    payload = "\n".join(
        [
            json.dumps(
                {
                    "type": "finding",
                    "severity": "critical",
                    "fileName": "storage.py",
                    "codegenInstructions": (
                        "Remove direct user_id interpolation and use placeholder syntax "
                        "with a bound parameter."
                    ),
                }
            ),
            json.dumps({"type": "complete", "status": "review_completed", "findings": 1}),
        ]
    )

    result = normalize_coderabbit_output(payload)

    assert result.status == "FAIL"
    assert result.findings[0].category == "security"
    assert result.findings[0].path == "storage.py"


def test_jsonl_review_requires_exact_scope_and_accounts_for_findings() -> None:
    events = "\n".join(
        json.dumps(item)
        for item in (
            {"type": "finding", "severity": "major", "category": "correctness",
             "path": "src/store.py", "line": 12, "message": "duplicate stored twice"},
            {"type": "finding", "severity": "minor", "category": "style",
             "path": "src/store.py", "message": "rename local"},
            {"type": "complete", "digest": "exact", "reviewed_paths": ["src/store.py"]},
        )
    )
    result = normalize_jsonl_output(events, digest="exact", reviewed_paths=["src/store.py"])
    assert result.status == "FAIL"
    assert result.suppressed_count == 1
    assert result.findings[0].message == "duplicate stored twice"
    assert normalize_jsonl_output(events, digest="stale", reviewed_paths=["src/store.py"]).status == "REVIEW_UNAVAILABLE"
    assert normalize_jsonl_output(events, digest="exact", reviewed_paths=["other.py"]).status == "REVIEW_UNAVAILABLE"


def test_jsonl_review_rejects_malformed_or_unscoped_claims() -> None:
    complete = json.dumps({"type": "complete", "digest": "exact", "reviewed_paths": ["src/store.py"]})
    for payload in (
        "not json\n" + complete,
        json.dumps({"type": "finding", "severity": "major", "category": "correctness",
                    "path": "other.py", "message": "outside scope"}) + "\n" + complete,
        complete + "\n" + complete,
        json.dumps({"type": "error", "message": "review failed"}) + "\n" + complete,
    ):
        assert normalize_jsonl_output(payload, digest="exact", reviewed_paths=["src/store.py"]).status == "REVIEW_UNAVAILABLE"
