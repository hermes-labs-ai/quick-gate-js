from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_historical_hermes_action_contract_is_preserved() -> None:
    manifest = (ROOT / "compat/hermes-gate/action.yml").read_text(encoding="utf-8")

    assert "name: Hermes Gate" in manifest
    assert "using: composite" in manifest
    assert "uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97" in manifest
    assert 'default: 0.1.7' in manifest
    assert 'default: fast' in manifest
    assert 'default: "3.11"' in manifest
    assert 'HERMES_GATE_VERSION: ${{ inputs.version }}' in manifest
    assert 'hermes-gate==${HERMES_GATE_VERSION}' in manifest
    assert 'HERMES_GATE_COMMAND: ${{ inputs.command }}' in manifest
    assert 'fast|full|review|doctor) hermes-gate "${HERMES_GATE_COMMAND}"' in manifest
    assert "command must be one of: fast, full, review, doctor" in manifest
