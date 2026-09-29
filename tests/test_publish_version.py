"""Regression coverage for the post-approval release version guard."""

import runpy
from pathlib import Path

import pytest

check_version = runpy.run_path(
    str(Path(__file__).parents[1] / ".github/scripts/check_pypi_version.py")
)["check_version"]


@pytest.mark.parametrize(
    ("candidate", "published"),
    [("0.1.1", "0.1.2"), ("0.1.9", "0.1.10"), ("0.2.0rc1", "0.2.0")],
)
def test_rejects_older_artifact(candidate: str, published: str) -> None:
    """Reject versions older than a release with published files."""
    with pytest.raises(ValueError, match="Refusing superseded"):
        check_version(candidate, {published: [{}]})


@pytest.mark.parametrize("candidate", ["0.1.2", "0.1.3", "0.1.10"])
def test_current_or_newer_artifact(candidate: str) -> None:
    """Allow the current release and newer candidate versions."""
    check_version(candidate, {"0.1.2": [{}]})


def test_empty_release_does_not_count_as_published() -> None:
    """Ignore PyPI release keys that have no published files."""
    check_version("0.1.2", {"0.1.3": []})


def test_invalid_version_fails_closed() -> None:
    """Fail closed when the candidate is not a valid version."""
    with pytest.raises(ValueError):
        check_version("invalid", {"0.1.2": [{}]})
