#!/usr/bin/env python3
"""Fail closed when a HermesGate release tag or built artifact drifts."""

from __future__ import annotations

import argparse
import ast
import configparser
import json
import re
import tarfile
import tomllib
import zipfile
from datetime import UTC, datetime, timedelta
from email.parser import BytesParser
from pathlib import Path


class ReleaseError(ValueError):
    """The release identity is incomplete or inconsistent."""


# The Agent Plugins 1.0.0 manifest is read at the plugin root; Claude Code reads its own
# manifest under `.claude-plugin/`. Both ship in the same artifact, so the release fails
# closed unless they agree with each other and with the packaged version.
AGENT_PLUGIN_MANIFEST = "claude-plugin/plugin.json"
CLAUDE_PLUGIN_MANIFEST = "claude-plugin/.claude-plugin/plugin.json"
AGENT_PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
# Agent Plugins 1.0.0 §5: the manifest schema is closed and every permitted field has a
# mandatory JSON type. A string field holding a list, or an author holding a non-string
# name, is a schema violation that a conforming client rejects.
AGENT_PLUGIN_FIELD_TYPES = {
    "$schema": str,
    "name": str,
    "version": str,
    "description": str,
    "author": dict,
    "homepage": str,
    "repository": str,
    "license": str,
    "keywords": list,
    "extensions": dict,
}
AGENT_PLUGIN_FIELDS = frozenset(AGENT_PLUGIN_FIELD_TYPES)
AGENT_PLUGIN_REQUIRED = ("$schema", "name", "version", "description")
AGENT_PLUGIN_AUTHOR_FIELDS = frozenset({"name", "email", "url"})
AGENT_PLUGIN_NAME = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
SHARED_PLUGIN_FIELDS = ("name", "version", "description", "license")

_V016_HERMES_REGISTRY_EXCEPTION = {
    "schema_version": 1,
    "release_tag": "v0.1.6",
    "surface": "Hermes Registry",
    "target": "hermesonehq/hermes-registry",
    "submission_url": "https://github.com/hermesonehq/hermes-registry/pull/5",
    "submitted_at": "2026-09-18T00:28:11Z",
    "expires_at": "2026-09-18T12:28:11Z",
}


def verify_distribution_exception(
    path: Path, tag: str, *, now: datetime | None = None
) -> str:
    """Verify the single, expiring release-distribution exception directly.

    This is intentionally separate from the publication workflow.  It proves a
    concrete external distribution submission during the short exception window;
    it never changes source, tag, runner, package, or artifact verification.
    """
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseError(f"distribution exception is unreadable: {exc}") from exc
    if not isinstance(value, dict) or set(value) != set(_V016_HERMES_REGISTRY_EXCEPTION):
        raise ReleaseError("distribution exception has an invalid schema")
    for field in ("schema_version", "release_tag", "surface", "target", "submission_url", "submitted_at"):
        if value[field] != _V016_HERMES_REGISTRY_EXCEPTION[field]:
            raise ReleaseError(f"distribution exception has an unexpected {field}")
    if tag != value["release_tag"]:
        raise ReleaseError(
            f"distribution exception is for {value['release_tag']!r}, not {tag!r}"
        )
    submitted_at = datetime.fromisoformat(value["submitted_at"])
    expires_at = datetime.fromisoformat(value["expires_at"])
    if expires_at - submitted_at != timedelta(hours=12):
        raise ReleaseError("distribution exception must expire exactly 12 hours after submission")
    expected_expiry = (submitted_at + timedelta(hours=12)).isoformat().replace("+00:00", "Z")
    if value["expires_at"] != expected_expiry:
        raise ReleaseError("distribution exception expiry must use canonical UTC form")
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        raise ReleaseError("distribution exception verification time must be timezone-aware")
    current_utc = current.astimezone(UTC)
    if current_utc < submitted_at:
        raise ReleaseError("distribution exception is not yet active")
    if current_utc >= expires_at:
        raise ReleaseError("distribution exception has expired")
    return f"PASS: active Hermes Registry distribution exception for {tag} until {value['expires_at']}"


def _metadata(raw: bytes, source: str, project: dict) -> tuple[str, str]:
    parsed = BytesParser().parsebytes(raw)
    name = parsed.get("Name")
    version = parsed.get("Version")
    if not name or not version:
        raise ReleaseError(f"{source}: package metadata lacks Name or Version")
    if len(parsed.get_all("Name", [])) != 1 or len(parsed.get_all("Version", [])) != 1:
        raise ReleaseError(f"{source}: duplicate package identity fields")
    expected_python = [project["requires-python"]] if project.get("requires-python") else []
    dependencies = list(project.get("dependencies", []))
    for extra, requirements in project.get("optional-dependencies", {}).items():
        for requirement in requirements:
            dependency, separator, marker = requirement.partition(";")
            condition = (
                f'({marker.strip()}) and extra == "{extra}"' if separator else f'extra == "{extra}"'
            )
            dependencies.append(f"{dependency.strip()}; {condition}")
    if (
        parsed.get_all("Requires-Python", []) != expected_python
        or sorted(parsed.get_all("Requires-Dist", [])) != sorted(dependencies)
        or sorted(parsed.get_all("Provides-Extra", []))
        != sorted(project.get("optional-dependencies", {}))
    ):
        raise ReleaseError(f"{source}: installation metadata differs from reviewed project")
    return name, version


def _literal_version(path: Path, variable: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == variable for target in node.targets
            )
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    raise ReleaseError(f"{path}: literal {variable} assignment not found")


def _verify_agent_plugin_types(manifest: dict) -> None:
    """Enforce the mandatory JSON types Agent Plugins 1.0.0 gives each permitted field."""
    for field, expected in AGENT_PLUGIN_FIELD_TYPES.items():
        if field in manifest and not isinstance(manifest[field], expected):
            raise ReleaseError(
                f"{AGENT_PLUGIN_MANIFEST}: field {field!r} must be a "
                f"{expected.__name__}, not {type(manifest[field]).__name__}"
            )

    name = manifest["name"]
    if not 1 <= len(name) <= 64 or not AGENT_PLUGIN_NAME.match(name):
        raise ReleaseError(f"{AGENT_PLUGIN_MANIFEST}: name {name!r} is not a valid plugin name")

    author = manifest.get("author", {})
    unexpected = sorted(set(author) - AGENT_PLUGIN_AUTHOR_FIELDS)
    if unexpected:
        raise ReleaseError(f"{AGENT_PLUGIN_MANIFEST}: author rejects field(s) {unexpected!r}")
    if not all(isinstance(value, str) for value in author.values()):
        raise ReleaseError(f"{AGENT_PLUGIN_MANIFEST}: every author value must be a string")

    if not all(isinstance(keyword, str) for keyword in manifest.get("keywords", [])):
        raise ReleaseError(f"{AGENT_PLUGIN_MANIFEST}: every keyword must be a string")
    if not all(isinstance(value, dict) for value in manifest.get("extensions", {}).values()):
        raise ReleaseError(f"{AGENT_PLUGIN_MANIFEST}: every extensions namespace must be an object")


def verify_plugin_manifests(root: Path, version: str) -> str:
    """Fail closed when either plugin manifest drifts from the other or from the release."""
    manifests: dict[str, dict] = {}
    for relative in (AGENT_PLUGIN_MANIFEST, CLAUDE_PLUGIN_MANIFEST):
        path = root / relative
        if not path.is_file():
            raise ReleaseError(f"{relative}: plugin manifest is missing")
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ReleaseError(f"{relative}: plugin manifest must be a JSON object")
        manifests[relative] = loaded

    agent_manifest = manifests[AGENT_PLUGIN_MANIFEST]
    claude_manifest = manifests[CLAUDE_PLUGIN_MANIFEST]

    for relative, manifest in manifests.items():
        if manifest.get("version") != version:
            raise ReleaseError(
                f"{relative}: version {manifest.get('version')!r} must equal {version!r}"
            )

    if agent_manifest.get("$schema") != AGENT_PLUGIN_SCHEMA:
        raise ReleaseError(
            f"{AGENT_PLUGIN_MANIFEST}: $schema {agent_manifest.get('$schema')!r} "
            f"must equal {AGENT_PLUGIN_SCHEMA!r}"
        )
    unexpected = sorted(set(agent_manifest) - AGENT_PLUGIN_FIELDS)
    if unexpected:
        raise ReleaseError(
            f"{AGENT_PLUGIN_MANIFEST}: Agent Plugins 1.0.0 rejects top-level field(s) {unexpected!r}"
        )
    missing = sorted(field for field in AGENT_PLUGIN_REQUIRED if not agent_manifest.get(field))
    if missing:
        raise ReleaseError(
            f"{AGENT_PLUGIN_MANIFEST}: Agent Plugins 1.0.0 requires field(s) {missing!r}"
        )
    _verify_agent_plugin_types(agent_manifest)

    drifted = sorted(
        field
        for field in SHARED_PLUGIN_FIELDS
        if agent_manifest.get(field) != claude_manifest.get(field)
    )
    if drifted:
        raise ReleaseError(
            f"{AGENT_PLUGIN_MANIFEST} and {CLAUDE_PLUGIN_MANIFEST} disagree on {drifted!r}"
        )
    return f"PASS: plugin manifests are {agent_manifest['name']} {version}"


def _verify_payload(payload: dict[str, bytes], expected: dict[str, bytes], source: str) -> None:
    if payload != expected:
        changed = sorted(
            key for key in payload.keys() | expected.keys() if payload.get(key) != expected.get(key)
        )
        raise ReleaseError(f"{source}: packaged source differs from reviewed source: {changed!r}")


def verify(
    root: Path,
    tag: str,
    dist: Path | None = None,
    distribution_exception: Path | None = None,
) -> str:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    name = project["name"]
    version = project["version"]
    expected_tag = f"v{version}"
    if tag != expected_tag:
        raise ReleaseError(f"release tag {tag!r} must equal {expected_tag!r}")

    version_paths = {
        "src/hermes_gate/__init__.py __version__": (
            root / "src" / "hermes_gate" / "__init__.py",
            "__version__",
        ),
        "src/hermes_gate/repo_runner.py RUNNER_VERSION": (
            root / "src" / "hermes_gate" / "repo_runner.py",
            "RUNNER_VERSION",
        ),
    }
    for label, (path, variable) in version_paths.items():
        source_version = _literal_version(path, variable)
        if source_version != version:
            raise ReleaseError(f"{label} {source_version!r} must equal {version!r}")

    runner = root / "src" / "hermes_gate" / "repo_runner.py"
    tracked_runner = root / ".hermes" / "hermes_gate_runner.py"
    if runner.read_bytes() != tracked_runner.read_bytes():
        raise ReleaseError("tracked .hermes runner must match src/hermes_gate/repo_runner.py")

    verify_plugin_manifests(root, version)

    distribution_result = ""
    if distribution_exception is not None:
        distribution_result = verify_distribution_exception(distribution_exception, tag)

    if dist is None:
        result = f"PASS: source identity is {name} {version} ({tag})"
        return f"{result}; {distribution_result}" if distribution_result else result

    wheel_name = f"hermes_gate-{version}-py3-none-any.whl"
    sdist_name = f"hermes_gate-{version}.tar.gz"
    actual = sorted(path.name for path in dist.iterdir() if path.is_file())
    expected_files = sorted([sdist_name, wheel_name])
    if actual != expected_files:
        raise ReleaseError(
            f"dist must contain exactly {sdist_name!r} and {wheel_name!r}; found {actual!r}"
        )

    wheel = dist / wheel_name
    package = root / "src" / "hermes_gate"
    source_payload = {
        path.relative_to(root / "src").as_posix(): path.read_bytes()
        for path in package.rglob("*")
        if path.is_file() and path.suffix in {".py", ".json"} and "__pycache__" not in path.parts
    }
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ReleaseError(f"{wheel.name}: duplicate archive entries")
        matches = [item for item in archive.namelist() if item.endswith(".dist-info/METADATA")]
        if len(matches) != 1:
            raise ReleaseError(f"{wheel.name}: expected exactly one METADATA file")
        wheel_identity = _metadata(archive.read(matches[0]), wheel.name, project)
        metadata_prefix = matches[0].rsplit("/", 1)[0] + "/"
        entrypoints = configparser.ConfigParser(interpolation=None)
        entrypoints.optionxform = str
        entrypoints.read_string(archive.read(metadata_prefix + "entry_points.txt").decode())
        expected_entries = {"console_scripts": project.get("scripts", {})}
        if project.get("gui-scripts"):
            expected_entries["gui_scripts"] = project["gui-scripts"]
        expected_entries.update(project.get("entry-points", {}))
        if {
            section: dict(entrypoints[section]) for section in entrypoints.sections()
        } != expected_entries or entrypoints.defaults():
            raise ReleaseError(f"{wheel.name}: entry points differ from reviewed project")
        payload = {
            item: archive.read(item)
            for item in names
            if not item.endswith("/") and not item.startswith(metadata_prefix)
        }
        _verify_payload(payload, source_payload, wheel.name)

    sdist = dist / sdist_name
    with tarfile.open(sdist, "r:gz") as archive:
        members = archive.getmembers()
        names = [item.name for item in members]
        if len(names) != len(set(names)):
            raise ReleaseError(f"{sdist.name}: duplicate archive entries")
        root_metadata = f"hermes_gate-{version}/PKG-INFO"
        matches = [item for item in archive.getmembers() if item.name == root_metadata]
        if len(matches) != 1:
            raise ReleaseError(f"{sdist.name}: expected exactly one PKG-INFO file")
        extracted = archive.extractfile(matches[0])
        if extracted is None:
            raise ReleaseError(f"{sdist.name}: could not read PKG-INFO")
        sdist_identity = _metadata(extracted.read(), sdist.name, project)
        archive_root = f"hermes_gate-{version}/"
        for filename in ("pyproject.toml", "setup.py", "setup.cfg", "MANIFEST.in"):
            source = root / filename
            archived = [item for item in members if item.name == archive_root + filename]
            if source.is_file():
                if len(archived) != 1 or not archived[0].isfile():
                    raise ReleaseError(f"{sdist.name}: missing regular build input {filename}")
                stream = archive.extractfile(archived[0])
                if stream is None or stream.read() != source.read_bytes():
                    raise ReleaseError(f"{sdist.name}: build input {filename} differs from source")
            elif filename == "setup.cfg" and archived:
                # setuptools emits this fixed, non-executable sdist-only configuration.
                if not archived[0].isfile():
                    raise ReleaseError(f"{sdist.name}: setup.cfg must be a regular file")
                stream = archive.extractfile(archived[0])
                if stream is None or stream.read() != b"[egg_info]\ntag_build = \ntag_date = 0\n\n":
                    raise ReleaseError(f"{sdist.name}: unexpected generated setup.cfg")
            elif archived:
                raise ReleaseError(f"{sdist.name}: unexpected build input {filename}")
        prefix = f"hermes_gate-{version}/src/hermes_gate/"
        payload = {}
        for item in members:
            if not item.name.startswith(prefix) or item.isdir():
                continue
            if not item.isfile():
                raise ReleaseError(f"{sdist.name}: package entry must be a regular file")
            stream = archive.extractfile(item)
            if stream is None:
                raise ReleaseError(f"{sdist.name}: unreadable package entry")
            payload["hermes_gate/" + item.name[len(prefix) :]] = stream.read()
        _verify_payload(payload, source_payload, sdist.name)

    expected = (name, version)
    if wheel_identity != expected or sdist_identity != expected:
        raise ReleaseError(
            f"artifact identity must be {expected!r}; wheel={wheel_identity!r}, "
            f"sdist={sdist_identity!r}"
        )
    result = f"PASS: artifacts are {name} {version} ({tag})"
    return f"{result}; {distribution_result}" if distribution_result else result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--dist", type=Path)
    parser.add_argument(
        "--distribution-exception",
        type=Path,
        help="directly verify the short-lived v0.1.6 Hermes Registry submission record",
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        print(verify(args.root, args.tag, args.dist, args.distribution_exception))
    except (
        KeyError,
        OSError,
        ReleaseError,
        configparser.Error,
        tarfile.TarError,
        zipfile.BadZipFile,
    ) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
