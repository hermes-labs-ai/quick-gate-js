"""Test-wide isolation from the gate that is running the tests.

The generated pull request workflow exports `HERMES_GATE_BASE`, and the runner
publishes the resolved range to child stages as `HERMES_GATE_RANGE`. Both reach
pytest, because pytest is itself a declared gate stage. Without this fixture a
temporary fixture repository would inherit the enclosing repository's base
revision - which does not exist in that repository - so runner tests would fail
under CI while passing locally. Tests that need a range set it explicitly.
"""

from __future__ import annotations

import pytest

from hermes_gate.repo_runner import BASE_ENV, RANGE_ENV


@pytest.fixture(autouse=True)
def _isolate_gate_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in (BASE_ENV, RANGE_ENV):
        monkeypatch.delenv(variable, raising=False)
