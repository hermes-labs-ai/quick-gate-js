# Five-project CI admission

As of 2026-09-29. These are integration proofs against real source snapshots, not
upstream approval, hosted CI results, or adoption. The source-pinned Action candidate
is local and unpublished. Preserve each project's native checks and intake policy;
do not add Gate as a runtime dependency or substitute it for the existing CI matrix.

## Current evidence

| Project / inspected commit | Fit | Technical proof | Submission state |
| --- | --- | --- | --- |
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk/tree/f1b6589088534632fef92238ee9750951e3c0185) | Protocol/tool infrastructure; receipt over native lint, types and tests | PASS, detailed below | [Policy](https://github.com/modelcontextprotocol/python-sdk/blob/f1b6589088534632fef92238ee9750951e3c0185/CONTRIBUTING.md) requires an assigned linked issue or help-wanted issue and human accountability; no submission made |
| [MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk/tree/dd22ba25ddbe7cd8822e1fe9c738a974996a28f6) | Native pnpm monorepo checks; no Python runtime dependency on its published SDK | FAIL receipt: checks/docs/build/distribution types/unit tests pass; E2E reports an unhandled timeout | [Policy](https://github.com/modelcontextprotocol/typescript-sdk/blob/dd22ba25ddbe7cd8822e1fe9c738a974996a28f6/CONTRIBUTING.md) requires discussion before significant changes; current README limits newcomer PRs |
| [Pydantic AI](https://github.com/pydantic/pydantic-ai/tree/a5b47bffc35b46cdbccba715584e0d91089a9c17) | Typed agent infrastructure; scoped offline agent behavior | PASS, 442 tests; stale/bad-source/restore probes pass | [Policy](https://github.com/pydantic/pydantic-ai/blob/a5b47bffc35b46cdbccba715584e0d91089a9c17/CONTRIBUTING.md) requires prior alignment and assignment for integrations |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent/tree/fc042f1d67bc393bf43920e92d4eb5082eddedfb) | Coding-agent consumer; native portable-contract CI guards | PASS, eight blocking guards; stale/bad-source/restore probes pass | [Third-party policy](https://github.com/NousResearch/hermes-agent/blob/fc042f1d67bc393bf43920e92d4eb5082eddedfb/CONTRIBUTING.md#third-party-product-integrations-ship-as-a-standalone-plugin) prefers standalone integration. Existing [PR #107124](https://github.com/NousResearch/hermes-agent/pull/107124) is separately owned |
| [pipx](https://github.com/pypa/pipx/tree/c2370d0e936830d1556fb7f8555930e83efe61b2) | Developer-tool distribution infrastructure | PASS, 1,140 tests; current source rebuilt, stale/bad-source/restore probes pass | [Contribution policy](https://github.com/pypa/pipx/blob/c2370d0e936830d1556fb7f8555930e83efe61b2/docs/contributing.rst) and native tox/uv workflow inspected |
| [PyPA packaging](https://github.com/pypa/packaging/tree/7b898d9f0b343ca06993157fc328d7caad51d5c2) | Dependency/version/metadata infrastructure | Native lint/build and CPython 3.14 tests/coverage PASS; scope and verification below | [Contribution policy](https://github.com/pypa/packaging/blob/7b898d9f0b343ca06993157fc328d7caad51d5c2/docs/development/submitting-patches.rst) favors focused patches and prior discussion of larger changes; no submission made |

The five readiness candidates are MCP Python, Pydantic AI, Hermes Agent, pipx and
PyPA packaging. MCP TypeScript remains a sixth, reproduced failure example, pending
upstream disposition. Intake approval is separate from technical compatibility.
Selection research used 21 external opens: six repository pages, six Git
snapshots and nine GitHub API queries. Local snapshot inspection adds no external
opens. The current selection cap is 30; no public mutation was made.

## MCP Python: executed native consumer

Profile: [gate.toml](../examples/ci-admission/mcp-python/gate.toml). Upstream evidence:
[development rules](https://github.com/modelcontextprotocol/python-sdk/blob/f1b6589088534632fef92238ee9750951e3c0185/AGENTS.md),
[shared CI](https://github.com/modelcontextprotocol/python-sdk/blob/f1b6589088534632fef92238ee9750951e3c0185/.github/workflows/shared.yml),
[native test script](https://github.com/modelcontextprotocol/python-sdk/blob/f1b6589088534632fef92238ee9750951e3c0185/scripts/test).

Installed the locked development environment explicitly with
`uv sync --frozen --all-extras --python 3.12` in a disposable upstream checkout.
The Action itself installs no tools; declared commands retain their native behavior
(the upstream test script uses `uv run --frozen`, which may sync dependencies).
Four declared full stages passed:
Ruff lint, Ruff format check, Pyright and the native test/coverage/strict-no-cover script.

The native script reported **5,968 passed, 10 skipped, one xfailed**, **100% configured
coverage**, and no wrongly marked no-cover pragmas. The Action reported PASS in
35,563 ms, exported a receipt and wrote its status/path outputs. This is macOS /
Python 3.12 evidence; it does not establish the upstream OS/Python/dependency matrix,
conformance tests, docs build or all pre-commit hooks.

Pyright's default macOS target initially rejected Linux-only `os.waitid` test code.
The profile explicitly checks the Linux target used by upstream's shared-check job;
`--pythonplatform Linux` then passed. No source, lockfile, checker version or rule was
changed to hide that platform distinction.

Verified the exported PASS against the same checkout. Injected an invalid Python
declaration into an actual SDK source file: the old PASS became stale, the explicit
fast run failed lint, and a FAIL receipt was exported. Restoring the exact original
bytes made the original full receipt valid again. The source restoration is verified;
the proposed profile is the only untracked integration file in the disposable checkout.

Local evidence: `/tmp/kwik-mcp-python-action.result.json`,
`/tmp/kwik-mcp-python-negative.result.json`, and their referenced receipt files.
These are validation artifacts, not committed completion receipts for this product.

This proves a useful technical integration. It does not satisfy the maintainer's
issue assignment or human-in-the-loop submission requirements. A source pin and
approved intake path must exist before preparing an upstream PR.

## MCP TypeScript: failure evidence is part of the proof

Profile: [gate.toml](../examples/ci-admission/mcp-typescript/gate.toml), preserving
[native Node CI commands](https://github.com/modelcontextprotocol/typescript-sdk/blob/dd22ba25ddbe7cd8822e1fe9c738a974996a28f6/.github/workflows/main.yml).
Explicit preparation used Node 24.19.0, pnpm 10.26.1 and
`pnpm install --frozen-lockfile`. Workspace release-age and build-script policies
were retained; the lockfile and tracked source stayed unchanged.

The native hook installer initially conflicted with this machine's shared hooks.
Preparation used a temporary Git configuration including the existing settings,
with hook installation confined to the disposable checkout. No global configuration
or shared hook was rewritten. This is a local setup accommodation, not a CI requirement.

The Action ran all five stages in **183,824 ms**. `check:all` (snippets, types, lint,
docs), `build:all`, distribution-type smoke checks and the native unit-test command
passed. E2E reported **2,641 passed, 147 expected failures**, but also an unhandled
`REQUEST_TIMEOUT` with a 200 ms timeout. Its process exited 1; the exported receipt
and Action outputs correctly report **FAIL**. It cannot verify as a reusable PASS.

An isolated native run of `scenarios/protocol.test.ts`, without Gate, reproduced
the timeout rejection: **358 passed, 50 expected failures, two unhandled errors**,
exit 1. No error suppression, removed stage, dependency update or source patch was
used to obtain green evidence. The exact underlying SDK/test cause is not yet established.

Local evidence: `/tmp/kwik-mcp-typescript-action.result.json`, its referenced export,
and `/tmp/kwik-mcp-typescript-protocol-native.log`. This establishes useful check
execution and honest failure propagation, not an all-green SDK or its Node/Bun/Deno
matrix. The E2E failure needs upstream disposition before claiming full CI readiness.

## Pydantic AI: scoped offline behavior

Profile: [gate.toml](../examples/ci-admission/pydantic-ai/gate.toml). Its
[development instructions](https://github.com/pydantic/pydantic-ai/blob/a5b47bffc35b46cdbccba715584e0d91089a9c17/AGENTS.md)
reserve repository-wide Pyright, pytest and coverage for upstream CI. This local
profile deliberately covers the public agent-behavior test module and TestModel
lint/format/types; `full` means all declared profile stages, not all upstream CI.

Explicit preparation used `uv sync --frozen --all-packages --group lint --python 3.13`.
Tests use `--record-mode=none`; existing model-request guards and blocking-call
detection remain enabled. No live provider or recording mode was requested.
The Action passed all four stages in **53,809 ms**: **442 passed, two skipped**,
with no type errors. This is Python 3.13/macOS evidence without a coverage claim.

The initial attempt correctly failed before checks because of four tracked directory
aliases under `.claude/skills`. The maintainer reviewed their actual consumers.
The profile now excludes only those four alias objects; their canonical
`.agents/skills/<name>/SKILL.md` files remain bound. Alias topology is outside this
receipt's guarantee. Newly introduced directory aliases still fail closed; no core
binding rule was weakened. Revisit this choice if declared checks start using aliases.

The exported PASS matches the result and verifies. Mutating actual TestModel source
made it stale; changed-source lint produced an exported FAIL; restoring exact bytes
restored PASS verification. Source and lockfile remain unchanged, with only the
proposed profile untracked. Evidence: `/tmp/kwik-pydantic-ai-action.result.json`,
`/tmp/kwik-pydantic-ai-verification.json`, and the referenced receipts.

An upstream integration is not a trivial correction: prior maintainer agreement and
issue assignment are required. This independently maintained example adds no dependency
to the framework and implies no upstream approval.

## Hermes Agent: native portability and import boundaries

Profile: [gate.toml](../examples/ci-admission/hermes-agent/gate.toml), derived with
the maintainer collaborator from the blocking
[lint/portability lane](https://github.com/NousResearch/hermes-agent/blob/fc042f1d67bc393bf43920e92d4eb5082eddedfb/.github/workflows/lint.yml),
[profile artifact guard](https://github.com/NousResearch/hermes-agent/blob/fc042f1d67bc393bf43920e92d4eb5082eddedfb/.github/workflows/profile-artifact-check.yml),
and [lazy dependency guard](https://github.com/NousResearch/hermes-agent/blob/fc042f1d67bc393bf43920e92d4eb5082eddedfb/.github/workflows/lazy-deps-guard.yml).

Explicit preparation used upstream PM's `scripts.ci.python_packages` helper for
Ruff 0.15.10, with a disposable development `HERMES_HOME`. The returned environment's
Python is put on PATH. PM owns this environment; no raw pip/uv mutation was used.
Preparation may download tools. The subsequent checks inspect local source/Git
inventories without model calls, credentials or the agent runtime.

All eight declared blocking stages passed in **27,911 ms**: Ruff, Windows footguns,
Bash shebangs, portable scratch paths, comment-preserving YAML writers, native OS
markers, profile archives and lazy dependency imports. Native SyntaxWarnings are
preserved in the receipt; the corresponding checkers return 0. Advisory diagnostics
that deliberately exit zero were not substituted for blocking checks.

The exported PASS matches and verifies. An invalid declaration in `hermes_state.py`
made it stale; fast lint exported FAIL; exact restoration restored verification.
Tracked source remains unchanged. Evidence: `/tmp/kwik-hermes-agent-action.result.json`
and `/tmp/kwik-hermes-agent-verification.json`.

These guards protect historical config-comment destruction, OS-marker blind spots,
profile leakage and lazy-install imports. They do not establish behavioral pytest,
coverage, the 96-core CI lane, native OS matrix or live-provider results. The native
test wrapper can synchronize dependencies and precompile the whole tree even with
few workers; it is not silently invoked by this low-compute profile.

Keep this example in KWIK-E-GATE. Upstream's third-party-product policy directs
external integrations outside its core tree. Existing PR #107124 remains independent.

## pipx: preserve native tox and fixture isolation

Profile: [gate.toml](../examples/ci-admission/pipx/gate.toml), preserving
[native tox configuration](https://github.com/pypa/pipx/blob/c2370d0e936830d1556fb7f8555930e83efe61b2/tox.toml)
and [CI preparation](https://github.com/pypa/pipx/blob/c2370d0e936830d1556fb7f8555930e83efe61b2/.github/workflows/tests.yml).
Explicitly prepared tox/tox-uv, the 3.14/type/lint environments, pre-commit hook
environments and the repository's test-package cache. This native project resolves
development dependencies from its declared ranges; they are not core dependencies.

The initial Action passed all native pre-commit hooks, ty and package-cache readiness.
The full suite reported **1,139 passed, 12 skipped, one xpassed**, and one failed
VCS fixture: the machine's shared commit hook required `mktemp`, while pipx's fixture
intentionally narrows PATH. Gate exported FAIL in **252,549 ms**.

No source, test or tracked configuration was changed. The failed case passed when
disposable fixture commits received process-scoped `core.hooksPath=/dev/null`.
Tox strips arbitrary environment variables, so the profile explicitly permits
`GIT_CONFIG_*` into that test environment. The separately declared native pre-commit
lint stage remains enabled; public/owned-repository boundaries are unaffected.
The first isolated full run passed: **1,140 passed, 12 skipped, one xpassed**, 94%
reported coverage, **242,977 ms**. That proves the host-fixture correction for the
unchanged prepared source. Evidence:
`/tmp/kwik-pipx-host-hook-failure.result.json` and `/tmp/kwik-pipx-vcs-native.log`.

The maintainer's package-consumer review revealed another risk: using native CI's
`--skip-pkg-install` after a later local source edit could run tests against a stale
wheel. A controlled probe added an import-time failure to real pipx source. The
prebuilt-wheel test still exited 0; normal tox rebuilt/reinstalled the current source
and failed with that exact marker (exit 4). The original source bytes were restored.
The final profile therefore lets tox rebuild/reinstall both wheel and editable
packages. The final full run passed all four stages in **226,204 ms**: **1,140 passed,
12 skipped, one xpassed**, 94% reported coverage on macOS/Python 3.14.7. Its receipt
retains the wheel/editable build and reinstall logs. This is not the upstream
OS/Python/docs/man/zipapp matrix.

This protects the relationship between bound source and executed package, beyond
whether tests are green. Existing output exclusions cover Hatch's generated version,
man page and tox intermediates; build inputs remain bound. Native commands can
install dependencies or fetch missing fixture packages, so this profile does not
guarantee network isolation. Evidence: `/tmp/kwik-pipx-wheel-source-probe.json`,
`/tmp/kwik-pipx-stale-wheel-native.log` and `/tmp/kwik-pipx-rebuilt-wheel-native.log`.

The final exported PASS matches the result and latest Action outputs and verifies.
Mutating real package source makes it stale; fast types exports FAIL; exact byte
restoration restores verification. Tracked source is unchanged. Evidence:
`/tmp/kwik-pipx-action.result.json` and `/tmp/kwik-pipx-verification.json`.

## PyPA packaging: native build inputs and prepared interpreters

Profile: [gate.toml](../examples/ci-admission/packaging/gate.toml), preserving the
[native Nox lint and test sessions](https://github.com/pypa/packaging/blob/7b898d9f0b343ca06993157fc328d7caad51d5c2/noxfile.py).
Explicit preparation installed Nox and the native `lint` / `tests-3.14` environments
and frozen prek hook environments in the disposable checkout. Lint uses Python 3.10;
tests use CPython 3.14. Both commands prohibit interpreter downloads during checks
and error on a missing interpreter. Native dependency installs remain enabled so the
editable test package and built wheel/sdist derive from current source.

The full profile retains every native lint hook, including mypy, Ruff, workflow
checks and frozen-revision checks, followed by distribution build and twine checks.
Frozen-revision checks query remote Git tags: this is network-dependent native
readiness, not an offline or hermetic proof. Hooks can repair source; Gate would reject
a checked workload changed by them. Tracked source remained unchanged.

The final Action passed both stages in **26,669 ms**. Its CPython 3.14 native
unit/coverage session passed the configured 100% branch-coverage threshold; a
read-only report of the resulting coverage file confirms zero statement/branch
misses. Native property tests are opt-in and remain outside this profile, along
with the interpreter/OS matrix, downstream, older-release pickle compatibility
and docs sessions. The large suite's
progress output is explicitly truncated in the receipt; its exit code and native
coverage-report command remain recorded. No count is inferred from truncated output.

The Action exports a matching PASS and status/path outputs. Mutating an actual
package source file invalidates that PASS; fast lint exports FAIL; restoring exact
bytes restores verification. The proposed profile is the only untracked integration
file. Evidence: `/tmp/kwik-packaging-action.result.json` and
`/tmp/kwik-packaging-verification.json`.

## Admission outcome

Five readiness examples have scoped local PASS proofs with source-mutation/failure/
restoration probes. MCP TypeScript is retained separately with a reproduced native
E2E FAIL. The maintainer reviewed profile design, actual package consumers and declared
limits. This is technical integration evidence, not five upstream approvals or a public
deployment. Intake alignment and a reviewed public source pin remain prerequisites
for upstream placement; the SDK E2E failure remains an upstream disposition item.

## Reproduce and place the integration

Review the chosen profile against the consumer's current source and intake policy.
Copy it to that checkout's `.hermes/gate.toml` only through explicit adoption.
Prepare the repository's own dependencies first. Then invoke the core with
`kwik-gate run --mode full`; inspect the receipt's declared argv and outcomes, and
verify its exported PASS against the same checkout. The SDK/agent package does not
gain a runtime dependency on Gate or its optional adapters.

For hosted CI, use the source-pinned Action recipe in the root README after this
candidate has a reviewed public commit. Preserve existing jobs/matrices and retain
the receipt artifact with `if: always()`, including failed jobs. The unintegrated
`REVIEWED_COMMIT` marker is not a usable public version. No upstream submission or
approval is implied by these local examples.
