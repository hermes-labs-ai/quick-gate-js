"""Fail closed when a downloaded release wheel is older than a published version."""

import email
import json
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

from packaging.version import Version


def check_version(candidate: str, releases: dict) -> None:
    """Reject a candidate when PyPI already has a newer nonempty release."""
    version = Version(candidate)
    newer = [Version(value) for value, files in releases.items() if files and Version(value) > version]
    if newer:
        raise ValueError(f"Refusing superseded {version}: PyPI already contains {max(newer)}")


def main() -> None:
    """Validate the sole downloaded wheel against current PyPI releases."""
    wheels = list(Path("dist").glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError("Expected exactly one release wheel")
    with ZipFile(wheels[0]) as wheel:
        metadata_path, = [name for name in wheel.namelist() if name.endswith(".dist-info/METADATA")]
        metadata = email.message_from_bytes(wheel.read(metadata_path))
    if metadata["Name"] != "hermes-gate":
        raise ValueError("Expected a hermes-gate wheel")
    with urlopen("https://pypi.org/pypi/hermes-gate/json", timeout=30) as response:
        releases = json.load(response)["releases"]
    check_version(metadata["Version"], releases)


if __name__ == "__main__":
    main()
