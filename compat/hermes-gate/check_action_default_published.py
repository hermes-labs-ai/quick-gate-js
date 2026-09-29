"""Verify the Action install version during a release without reading README content.

The Action's literal version input default is the install version when present.
When it is absent, the release tag identifies the checked-out Action version.
The version being published may not exist on PyPI yet; older defaults must
already be published and have an Action manifest at their tag.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

ROOT = Path(__file__).resolve().parents[2]
REPO_SLUG = "hermes-labs-ai/hermes-gate"
PYPI_URL = "https://pypi.org/pypi/hermes-gate/json"
NETWORK_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1.0


def _input_default(manifest: str, input_name: str) -> str | None:
    """Return an Action input's default using YAML's safe scalar semantics."""
    try:
        document = yaml.safe_load(manifest)
    except yaml.YAMLError as exc:
        raise ValueError(f"action.yml is not valid YAML: {exc}") from exc
    if not isinstance(document, dict):
        return None
    inputs = document.get("inputs")
    if not isinstance(inputs, dict):
        return None
    definition = inputs.get(input_name)
    if not isinstance(definition, dict):
        return None
    value = definition.get("default")
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        preview = repr(value)
        if len(preview) > 80:
            preview = preview[:77] + "..."
        raise TypeError(
            f"inputs.{input_name}.default must be a string; got {type(value).__name__} {preview}"
        )
    return value


def read_action_default() -> str | None:
    """Return the `version` input's default from action.yml, or None when it
    is absent or an empty string (the version is then pinned at install time
    by the Action ref itself rather than by a literal default)."""
    manifest = (ROOT / "compat/hermes-gate/action.yml").read_text(encoding="utf-8")
    return _input_default(manifest, "version")


def check_published(version: str, releases: dict) -> None:
    """Reject a version absent from PyPI or published with no files."""
    files = releases.get(version)
    if not files:
        raise ValueError(f"hermes-gate {version!r} is not a published PyPI release")


def _get(
    url: str,
    *,
    headers: dict[str, str],
    timeout: float = 30,
    attempts: int = NETWORK_ATTEMPTS,
    sleep: Callable[[float], None] | None = None,
) -> tuple[int, bytes]:
    """GET `url` with bounded retries for transient transport/server failures."""
    if attempts < 1:
        raise ValueError("network attempts must be at least one")
    transient_statuses = {408, 425, 429, 500, 502, 503, 504}
    last_error: Exception | None = None
    sleep = sleep or time.sleep
    for attempt in range(attempts):
        try:
            with urlopen(Request(url, headers=headers), timeout=timeout) as response:
                status, body = response.status, response.read()
                response_headers = getattr(response, "headers", {})
            retryable = status in transient_statuses or (
                status == 403
                and (
                    response_headers.get("X-RateLimit-Remaining") == "0"
                    or bool(response_headers.get("Retry-After"))
                )
            )
            if not retryable or attempt + 1 == attempts:
                return status, body
            last_error = ValueError(f"HTTP {status}")
        except HTTPError as exc:
            retryable = exc.code in transient_statuses or (
                exc.code == 403
                and (
                    getattr(exc, "headers", {}).get("X-RateLimit-Remaining") == "0"
                    or bool(getattr(exc, "headers", {}).get("Retry-After"))
                )
            )
            if not retryable or attempt + 1 == attempts:
                return exc.code, exc.read()
            last_error = exc
        except (URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt + 1 == attempts:
                raise ValueError(
                    f"network error fetching {url} after {attempts} attempts: {exc}"
                ) from exc
        sleep(RETRY_DELAY_SECONDS * (2**attempt))
    raise ValueError(f"network error fetching {url} after {attempts} attempts: {last_error}")


def fetch_pypi_releases() -> dict:
    """Return the `releases` mapping from PyPI's JSON API for hermes-gate.

    Never sends a GitHub token or any Authorization header -- PyPI's JSON API
    is anonymous and unrelated to the GitHub contents lookup below.
    """
    status, body = _get(PYPI_URL, headers={"Accept": "application/json"})
    if status != 200:
        raise ValueError(f"PyPI lookup for hermes-gate failed with HTTP {status} ({PYPI_URL})")
    return json.loads(body)["releases"]


def _github_headers() -> dict[str, str]:
    """Headers for the GitHub contents API, authenticated when possible.

    A shared-IP hosted runner can hit GitHub's low unauthenticated rate limit
    and get a 403/429 that would otherwise fail this guard closed on a
    perfectly good release. `GITHUB_TOKEN` is provided by the publish
    workflow's own `permissions: contents: read`; when present it is sent as
    a bearer token, but the token is never required for this public repo and
    is never attached to the unrelated PyPI request in `fetch_pypi_releases`.
    """
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def tag_has_action_yml(version: str, *, fetch_status=None) -> bool:
    """Return whether tag v{version} of this repo contains action.yml at its root.

    Uses the public GitHub contents API rather than git, so this works without
    changing `actions/checkout`'s default shallow, tagless clone. `fetch_status`
    is injectable for tests; it takes a URL and returns an HTTP status code
    (raising ValueError on a transport failure), matching the shape of the
    real network call below.
    """
    tag = f"v{version}"
    url = f"https://api.github.com/repos/{REPO_SLUG}/contents/action.yml?ref={tag}"
    if fetch_status is None:
        status, _ = _get(url, headers=_github_headers())
    else:
        status = fetch_status(url)
    if status == 200:
        return True
    if status == 404:
        return False
    raise ValueError(f"GitHub contents lookup for tag {tag!r} failed with HTTP {status} ({url})")


def evaluate(
    *,
    default: str | None,
    release_tag: str,
    local_action_yml_exists: bool,
    fetch_pypi_releases=fetch_pypi_releases,
    tag_has_action_yml=tag_has_action_yml,
) -> str:
    """Check the install version named by Action metadata for this release."""
    if not local_action_yml_exists:
        raise ValueError(
            f"release tag {release_tag!r} checkout has no action.yml at the repository root"
        )
    if not default and not release_tag.startswith("v"):
        raise ValueError("action.yml has no version default and RELEASE_TAG is missing")
    action_version = default or release_tag[1:]

    if release_tag == f"v{action_version}":
        # Publishing this release makes its package available; PyPI cannot
        # contain it yet. The checked-out tag already contains action.yml.
        return (
            f"PASS: Action install version {action_version} is release tag "
            f"{release_tag!r} being published; action.yml is present"
        )

    releases = fetch_pypi_releases()
    check_published(action_version, releases)
    if not tag_has_action_yml(action_version):
        raise ValueError(
            f"tag 'v{action_version}' does not contain action.yml, so the Action "
            "default names a tag that cannot install the Marketplace Action"
        )
    return (
        f"PASS: Action install version {action_version} is a published PyPI release "
        f"and tag 'v{action_version}' contains action.yml"
    )


def main() -> None:
    default = read_action_default()
    release_tag = os.environ.get("RELEASE_TAG", "")
    message = evaluate(
        default=default,
        release_tag=release_tag,
        local_action_yml_exists=(ROOT / "compat/hermes-gate/action.yml").is_file(),
    )
    print(message)


if __name__ == "__main__":
    main()
