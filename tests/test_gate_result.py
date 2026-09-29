from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

from hermes_gate.gate_result import load_schema, validate_gate_result


def test_packaged_schema_matches_canonical_repository_bytes() -> None:
    root_schema = Path("schemas/gate-result-v1.schema.json").read_bytes()
    packaged = (
        resources.files("hermes_gate").joinpath("schemas/gate-result-v1.schema.json").read_bytes()
    )
    assert packaged == root_schema
    assert load_schema()["properties"]["schema"]["const"] == "gate-result/v1"


def test_shared_gate_result_fixtures_have_expected_validity() -> None:
    fixtures = json.loads(
        Path("tests/fixtures/gate-result-v1.fixtures.json").read_text(encoding="utf-8")
    )
    for case in fixtures["cases"]:
        errors = validate_gate_result(case["value"])
        assert (not errors) is case["valid"], (case["name"], errors)
