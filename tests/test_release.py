from __future__ import annotations

import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
TAG = f"v{VERSION}"
SPEC = importlib.util.spec_from_file_location("verify_release", ROOT / "scripts/verify_release.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
ReleaseError = MODULE.ReleaseError

EXCEPTION = ROOT / "release" / "distribution-exceptions" / "v0.1.6-hermes-registry.json"
EXCEPTION_TAG = "v0.1.6"
ACTIVE_EXCEPTION_TIME = datetime(2026, 9, 18, 0, 29, tzinfo=UTC)


@pytest.fixture(scope="module")
def built_dist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("release") / "repo"
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(
        ".git", ".venv", "dist", "build", "node_modules", "__pycache__", "*.egg-info"
    ))
    subprocess.run([sys.executable, "-m", "build", "--outdir", str(root / "dist")], cwd=root, check=True)
    return root


def test_release_identity_accepts_exact_tag_and_built_artifacts(built_dist: Path) -> None:
    assert MODULE.verify(built_dist, TAG, built_dist / "dist").startswith("PASS:")


def test_release_identity_rejects_tag_and_source_version_drift(
    built_dist: Path, tmp_path: Path
) -> None:
    with pytest.raises(ReleaseError, match="release tag"):
        MODULE.verify(built_dist, "v9.9.8")

    root = tmp_path / "repo"
    shutil.copytree(built_dist, root)
    init = root / "src" / "hermes_gate" / "__init__.py"
    init.write_text(init.read_text().replace(f'"{VERSION}"', '"9.9.9"'), encoding="utf-8")
    with pytest.raises(ReleaseError, match="__version__"):
        MODULE.verify(root, TAG)

    runner_root = tmp_path / "runner-repo"
    shutil.copytree(built_dist, runner_root)
    runner = runner_root / "src" / "hermes_gate" / "repo_runner.py"
    runner.write_text(runner.read_text().replace(f'"{VERSION}"', '"9.9.9"'), encoding="utf-8")
    with pytest.raises(ReleaseError, match="RUNNER_VERSION '9.9.9'"):
        MODULE.verify(runner_root, TAG)


@pytest.mark.parametrize(
    ("manifest", "mutation", "message"),
    [
        ("claude-plugin/plugin.json", {"version": "9.9.9"}, "version '9.9.9' must equal"),
        (
            "claude-plugin/.claude-plugin/plugin.json",
            {"version": "9.9.9"},
            "version '9.9.9' must equal",
        ),
        ("claude-plugin/plugin.json", {"$schema": "https://example.test/x"}, "must equal"),
        ("claude-plugin/plugin.json", {"displayName": "hermes-gate"}, "rejects top-level field"),
        ("claude-plugin/plugin.json", {"description": "drifted"}, "disagree on"),
    ],
)
def test_release_identity_rejects_plugin_manifest_drift(
    built_dist: Path, tmp_path: Path, manifest: str, mutation: dict, message: str
) -> None:
    root = tmp_path / "repo"
    shutil.copytree(built_dist, root)
    path = root / manifest
    record = json.loads(path.read_text(encoding="utf-8"))
    record.update(mutation)
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ReleaseError, match=message):
        MODULE.verify(root, TAG)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"description": ["drifted"]}, "must be a str"),
        ({"author": []}, "must be a dict"),
        ({"keywords": "hooks"}, "must be a list"),
        ({"author": {"name": 1}}, "author value must be a string"),
        ({"author": {"handle": "hermes"}}, "author rejects field"),
        ({"keywords": ["hooks", 2]}, "keyword must be a string"),
        ({"extensions": {"ai.hermes-labs": "on"}}, "namespace must be an object"),
        ({"name": "Hermes-Gate"}, "is not a valid plugin name"),
    ],
)
def test_release_identity_rejects_an_ill_typed_agent_plugins_manifest(
    built_dist: Path, tmp_path: Path, mutation: dict, message: str
) -> None:
    root = tmp_path / "repo"
    shutil.copytree(built_dist, root)
    for relative in ("claude-plugin/plugin.json", "claude-plugin/.claude-plugin/plugin.json"):
        path = root / relative
        record = json.loads(path.read_text(encoding="utf-8"))
        record.update(mutation)
        path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ReleaseError, match=message):
        MODULE.verify(root, TAG)


def test_release_identity_rejects_a_missing_agent_plugins_manifest(
    built_dist: Path, tmp_path: Path
) -> None:
    root = tmp_path / "repo"
    shutil.copytree(built_dist, root)
    (root / "claude-plugin" / "plugin.json").rename(root / "claude-plugin" / "plugin.json.bak")
    with pytest.raises(ReleaseError, match="plugin manifest is missing"):
        MODULE.verify(root, TAG)


def test_release_identity_rejects_tracked_runner_drift(built_dist: Path, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    shutil.copytree(built_dist, root)
    tracked = root / ".hermes" / "hermes_gate_runner.py"
    tracked.write_text(tracked.read_text() + "\n# stale copy\n", encoding="utf-8")
    with pytest.raises(ReleaseError, match="tracked .hermes runner must match"):
        MODULE.verify(root, TAG)


def test_distribution_exception_accepts_only_active_exact_v016_record() -> None:
    assert "PASS:" in MODULE.verify_distribution_exception(
        EXCEPTION, "v0.1.6", now=ACTIVE_EXCEPTION_TIME
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("release_tag", "v0.1.5", "unexpected release_tag"),
        ("expires_at", "2026-09-18T12:28:12Z", "exactly 12 hours"),
        ("submission_url", "https://example.test/pr/5", "unexpected submission_url"),
    ],
)
def test_distribution_exception_rejects_wrong_record_fields(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    record = json.loads(EXCEPTION.read_text(encoding="utf-8"))
    record[field] = value
    path = tmp_path / "exception.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ReleaseError, match=message):
        MODULE.verify_distribution_exception(path, EXCEPTION_TAG, now=ACTIVE_EXCEPTION_TIME)


def test_distribution_exception_rejects_expiration_and_wrong_requested_tag() -> None:
    with pytest.raises(ReleaseError, match="not yet active"):
        MODULE.verify_distribution_exception(
            EXCEPTION, EXCEPTION_TAG, now=datetime(2026, 9, 18, 0, 28, 10, tzinfo=UTC)
        )
    assert "PASS:" in MODULE.verify_distribution_exception(
        EXCEPTION, EXCEPTION_TAG, now=datetime(2026, 9, 18, 0, 28, 11, tzinfo=UTC)
    )
    with pytest.raises(ReleaseError, match="expired"):
        MODULE.verify_distribution_exception(
            EXCEPTION, EXCEPTION_TAG, now=datetime(2026, 9, 18, 12, 28, 11, tzinfo=UTC)
        )
    with pytest.raises(ReleaseError, match="not 'v0.1.5'"):
        MODULE.verify_distribution_exception(EXCEPTION, "v0.1.5", now=ACTIVE_EXCEPTION_TIME)


def test_distribution_exception_never_bypasses_identity_failure(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(
        ".git", ".venv", "dist", "build", "node_modules", "__pycache__", "*.egg-info"
    ))
    init = root / "src" / "hermes_gate" / "__init__.py"
    init.write_text(init.read_text().replace(f'"{VERSION}"', '"9.9.9"'), encoding="utf-8")
    with pytest.raises(ReleaseError, match="__version__"):
        MODULE.verify(root, TAG, distribution_exception=EXCEPTION)


def test_release_identity_rejects_extra_or_mislabeled_artifacts(
    built_dist: Path, tmp_path: Path
) -> None:
    dist = tmp_path / "dist"
    shutil.copytree(built_dist / "dist", dist)
    (dist / "unreviewed.txt").write_text("unexpected", encoding="utf-8")
    with pytest.raises(ReleaseError, match="must contain exactly"):
        MODULE.verify(built_dist, TAG, dist)

    (dist / "unreviewed.txt").unlink()
    wheel = next(dist.glob("*.whl"))
    wheel.rename(dist / "hermes_gate-9.9.8-py3-none-any.whl")
    with pytest.raises(ReleaseError, match="must contain exactly"):
        MODULE.verify(built_dist, TAG, dist)


@pytest.mark.parametrize("artifact", ["wheel", "sdist"])
@pytest.mark.parametrize(
    "mutation", ["metadata", "module", "unexpected-module", "execution", "dependency", "python"]
)
def test_release_identity_rejects_embedded_metadata_drift(
    built_dist: Path, tmp_path: Path, artifact: str, mutation: str
) -> None:
    dist = tmp_path / "dist"
    shutil.copytree(built_dist / "dist", dist)
    if artifact == "wheel":
        path = next(dist.glob("*.whl"))
        with zipfile.ZipFile(path) as archive:
            members = [(item, archive.read(item)) for item in archive.infolist()]
        with zipfile.ZipFile(path, "w") as archive:
            for item, data in members:
                if mutation == "metadata" and item.filename.endswith(".dist-info/METADATA"):
                    data = data.replace(f"Version: {VERSION}".encode(), b"Version: 9.9.9")
                if mutation == "dependency" and item.filename.endswith(".dist-info/METADATA"):
                    data = data.replace(
                        b"Metadata-Version:",
                        b"Requires-Dist: unexpected-package\nMetadata-Version:",
                    )
                if mutation == "python" and item.filename.endswith(".dist-info/METADATA"):
                    data = data.replace(b"Requires-Python: >=3.11", b"Requires-Python: >=3.9")
                if mutation == "module" and item.filename == "hermes_gate/cli.py":
                    data += b"\n# changed package module\n"
                if mutation == "execution" and item.filename.endswith("/entry_points.txt"):
                    data = data.replace(b"hermes_gate.cli:main", b"hermes_gate.cli:parser")
                archive.writestr(item, data)
            if mutation == "unexpected-module":
                archive.writestr("hermes_gate/unexpected.py", b"# unexpected module\n")
    else:
        path = next(dist.glob("*.tar.gz"))
        with tarfile.open(path, "r:gz") as archive:
            members = []
            for item in archive.getmembers():
                stream = archive.extractfile(item) if item.isfile() else None
                members.append((item, stream.read() if stream else None))
        with tarfile.open(path, "w:gz") as archive:
            for item, data in members:
                if data is not None and item.name == f"hermes_gate-{VERSION}/PKG-INFO":
                    if mutation == "dependency":
                        data = data.replace(
                            b"Metadata-Version:",
                            b"Requires-Dist: unexpected-package\nMetadata-Version:",
                        )
                    if mutation == "python":
                        data = data.replace(b"Requires-Python: >=3.11", b"Requires-Python: >=3.9")
                    item.size = len(data)
                if (
                    mutation == "metadata"
                    and item.name == f"hermes_gate-{VERSION}/PKG-INFO"
                    and data is not None
                ):
                    data = data.replace(f"Version: {VERSION}".encode(), b"Version: 9.9.9")
                    item.size = len(data)
                if (
                    mutation == "module"
                    and item.name == f"hermes_gate-{VERSION}/src/hermes_gate/cli.py"
                    and data is not None
                ):
                    data += b"\n# changed package module\n"
                    item.size = len(data)
                if (
                    mutation == "execution"
                    and item.name == f"hermes_gate-{VERSION}/pyproject.toml"
                    and data is not None
                ):
                    data = data.replace(b"setuptools.build_meta", b"unexpected_backend")
                    item.size = len(data)
                archive.addfile(item, io.BytesIO(data) if data is not None else None)
            if mutation == "unexpected-module":
                item = tarfile.TarInfo(f"hermes_gate-{VERSION}/src/hermes_gate/unexpected.py")
                data = b"# unexpected module\n"
                item.size = len(data)
                archive.addfile(item, io.BytesIO(data))
    message = "artifact identity must be" if mutation == "metadata" else "packaged source differs"
    if mutation == "execution":
        message = "entry points differ" if artifact == "wheel" else "build input pyproject.toml"
    if mutation in {"dependency", "python"}:
        message = "installation metadata differs"
    with pytest.raises(ReleaseError, match=message):
        MODULE.verify(built_dist, TAG, dist)
