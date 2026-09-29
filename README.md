![KWIK-E-GATE — your local convenience code review. Don’t forget the receipt.](docs/assets/kwik-e-gate-header.jpg)

# Quick Gate JS

> **Existing Quick Gate users:** This repository stays at its original URL.
> Published `quick-gate` 0.3.2, historical tags and SHA pins, the root and nested
> Actions, plugin installs, issues, and releases remain here. The active
> [Kwik-e-gate product source](https://github.com/hermes-labs-ai/kwik-e-gate)
> is a new repository. Its 0.4.0 packages are not yet published.

**Fast local checks for coding agents. PASS / FAIL. Don't forget the receipt.**

Interpret the change against your repository’s declared gates, record what ran, and verify the
receipt before treating the work as checked. Free, local, no daemon, no model or API
required. Python 3.11+ and Git; zero runtime Python dependencies.

Developed by [Hermes Labs](https://hermes-labs.ai).

> **Unreleased 0.4.0 consolidation.** Public PyPI `hermes-gate` is 0.1.7; npm
> `quick-gate` is 0.3.2. Install this checkout to use the new commands. The distribution remains
> `hermes-gate`; `hermes-gate` and `kwik-gate` use the same engine.

## Start here

From this source checkout:

```bash
python3 -m venv /tmp/kwik-gate-venv
/tmp/kwik-gate-venv/bin/python -m pip install .
# Use the installed executable in the repository you want to check:
cd /path/to/your/git-repository
/tmp/kwik-gate-venv/bin/kwik-gate init
# Review .hermes/gate.toml: choose the checks that matter for this project.
/tmp/kwik-gate-venv/bin/kwik-gate run
/tmp/kwik-gate-venv/bin/kwik-gate verify
```

After 0.4.0 is published, `pip install hermes-gate==0.4.0` provides both commands.
Existing users can continue using `hermes-gate fast` and `hermes-gate full`.

| Command | Result |
| --- | --- |
| `kwik-gate plan` | Explain gate selection without executing checks; returns PLANNED, never a checked PASS |
| `kwik-gate run` | Automatically select applicable fast checks or escalate broader changes to full; issue a receipt |
| `kwik-gate run --mode fast` | Explicit fast checks; cached only with a matching input/contract identity |
| `kwik-gate run --mode full` | Every declared full stage, including file-driven checks on clean CI checkouts |
| `kwik-gate run --output /external/path/receipt.json` | Run plus an exported copy of the receipt |
| `kwik-gate verify` | Read-only verification of the latest run receipt, fast or full |
| `kwik-gate verify --kind full` | Verify the current full receipt |
| `kwik-gate verify --receipt /external/path/receipt.json` | Verify an exported receipt against this same local checkout |

Run exits **0 for PASS, 1 for FAIL**. Stdout is JSON containing `status`, `receipt`,
`receipt_path`, `routing`, `cached`, and elapsed time. Every started run issues a receipt,
including missing/invalid configuration, unavailable tools, timeouts and no-check
outcomes. A non-Git run stores its failure receipt in the user cache. If storage is
unavailable, stdout still contains a failure receipt; it cannot report PASS.
Help and argument-parser failures are not check executions.

Receipt files live under the worktree's Git directory, outside tracked source.
Exports must be outside the repository. `verify` runs no checks or reviewer and
exits 1 for missing, failed, stale or incomplete evidence. Receipts are intentionally
local to their checkout; copying a receipt to a different checkout does not prove
that checkout was checked.

## Choose the right gate locally

The default `auto` mode interprets changed paths and repository policy. Ordinary
source changes use matching fast stages. Dependency/project contracts, tests, CI,
gate configuration and sensitive auth/schema/migration paths escalate to full.
The receipt records the decision, evidence, selected/skipped stages and review advice.
`kwik-gate plan` previews that choice; it runs no tool, writes nothing and reports
PLANNED. It does not claim that checks have passed.

The selector reads no source files and calls no subprocess or model. Git discovery,
input hashing, process startup and the checks themselves take additional time.
This is an explainable path/policy interpretation, not semantic code comprehension.
Extend the policy with `[routing].full_globs` and `.review_globs` for project-specific
risk. `--mode fast` / `--mode full` explicitly select a contract.

An agent or human can use the plan with an LLM when available. `kwik-gate review`
adds the installed provider’s semantic judgment; it is separate evidence. Sensitive
changes can recommend review while deterministic checks still work without it.
Existing repository boundary policy remains authoritative.

## Declare the checks

`init` writes a reviewable `.hermes/gate.toml`, a stdlib runner, and a CI workflow.
It refuses to overwrite existing integration files without `--force`. It never
installs project tools. Detection is a starting point; adapt the profile for a
monorepo or any custom build system.

A minimal profile:

```toml
version = 1

[gate]
fast_budget_seconds = 8.0
exclusions = [".git/**", "node_modules/**", "dist/**", "build/**"]

[[fast]]
name = "lint"
argv = ["npm", "run", "lint"]
timeout_seconds = 6.0
globs = ["**/*"]

[[full]]
name = "test"
argv = ["npm", "test"]
timeout_seconds = 180.0
```

Use argv arrays, not shell strings. `{files}` expands to the selected paths for
file-aware tools. Fast stages run only when their globs match; full stages receive
all included repository inputs. Missing or wholly skipped checks never establish a
checked PASS. The fast command budget defaults to eight seconds; hashing inputs
and recording executable identities add overhead proportional to input size.

See [configuration](docs/CONFIGURATION.md) for adapters, exclusions and optional
review/boundary policy.

## Optional Python diagnostics

For normalized Ruff/Pyright/pytest findings, use
[Quick Gate Python (PyGate)](https://github.com/hermes-labs-ai/quick-gate-python):

```bash
python -m pip install pygate-ci==0.3.2 ruff pyright pytest pytest-json-report
kwik-gate init --adapter pygate
```

This explicitly uses the installed `pygate` executable. Fast maps to its `canary`
contract; full includes pytest. PyGate has its own native API and existing users
keep `pygate-ci` / `pygate`. Its optional Pydantic/tool dependencies never become
core dependencies. Both adapters produce diagnostics; the core issues the receipt.

## Optional JS/TS diagnostics

Native commands work with any language. For normalized JS/TS findings, use the
existing [Quick Gate adapter](https://github.com/hermes-labs-ai/quick-gate-js):

```bash
# Explicitly install the adapter in the target project's dependencies.
npm install --save-dev quick-gate@0.3.2
kwik-gate init --adapter quick-gate
```

The generated adapter argv is `npx --no-install quick-gate`: run never downloads
it. Review `quick-gate.config.json` and disable inapplicable gates explicitly.
Legacy Quick Gate quick mode includes Lighthouse; for a library or fast local
loop, set `gates.lighthouse` to `false`. Its `gate-result/v1` diagnostics are
validated by the core before issuing a completion receipt. npm users can still
use its standalone CLI/API without installing Python.

## CI and coding agents

Generated CI runs the same `kwik-gate run --mode full` command and preserves the
receipt as an artifact even when checks fail. Fresh workflows require the matching
CLI version to be published. The copied runner remains a compatible check executor;
it is not a second receipt authority.

The consolidated core Action runs the source selected by its Git ref, with no PyPI
installation. In this checkout use `./.github/actions/kwik-e-gate`; after integration,
pin its reviewed commit. The existing root Action keeps the standalone JS interface.

```yaml
- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
  with:
    fetch-depth: 0
    persist-credentials: false
- uses: hermes-labs-ai/kwik-e-gate/.github/actions/kwik-e-gate@5d6b486791a084bc312055e350983881dacbf512
  id: gate
  with:
    mode: full
- uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a
  if: always()
  with:
    name: kwik-e-gate-receipt
    path: ${{ steps.gate.outputs.receipt-path }}
```

The pinned commit is the accepted source import in the new repository; the 0.4.0
packages remain unpublished. The core Action exposes `status` and `receipt-path`, including
failing runs. For an ambiguous detached/merge checkout, supply its `base` input.
Old JS Action users retain their original inputs/outputs; see the
[standalone JS guide](docs/QUICK-GATE-JS.md).

[Five native readiness examples](docs/CI-ADMISSION.md) cover MCP Python,
Pydantic AI, Hermes Agent, pipx and PyPA packaging. Each declares its check scope and setup;
`full` executes that profile, not every upstream matrix job. The evidence includes
a sixth, MCP TypeScript E2E failure that remains FAIL despite passing test cases. Local compatibility
does not imply upstream adoption or approval.

The repository's [Agent Skill](.agents/skills/hermes-gate/SKILL.md) works in
compatible Agent Skills hosts. The self-contained [Claude/portable plugin](claude-plugin/)
and `hermes-gate install-codex` retain their installed hook contracts. Hooks and
legacy Git boundaries can require a separate review receipt: this advanced policy
is independent of the deterministic run/verify workflow. Installing hooks is an
explicit user choice; `run` does not install them.

## What PASS means

A PASS means at least one declared check ran successfully and the bound inputs and
contract stayed unchanged. Receipts bind HEAD, selected diff scope, all included
tracked/unignored inputs, profile/runner bytes, executable bytes/execution bits,
core implementation, check argv/results, tool version observations and time.
Changing an unrelated included input conservatively invalidates reuse.

This is evidence of declared checks, not proof of correctness, complete coverage,
hermetic execution, authenticity, or authorization to merge/release. Receipts are
unsigned; someone who can write local state can forge evidence. Commands retain
their own side effects, network access and flakiness. Ignored/excluded dependencies,
external services, environment variables, clock and imported tool dependencies are
not fully bound. Directory inputs (including gitlinks and directory symlinks) fail
closed until represented as explicit ordinary files or handled in a separate gate.
Output can be truncated; the receipt records that fact.

`run` never repairs source or invokes a model. Explicit `repair` remains available;
`review` is an optional semantic extension that uses the configured installed
provider. API/model review being unavailable does not prevent local run/verify.

## Migration, development and release

- [Configuration and receipt contracts](docs/CONFIGURATION.md)
- [Standalone Quick Gate JS adapter](docs/QUICK-GATE-JS.md)
- [Changelog](CHANGELOG.md), [security](SECURITY.md), [contributing](CONTRIBUTING.md)

```bash
python -m pip install -e '.[test]'
ruff check .
pytest
python -m build
```

The real JS adapter roundtrip also runs in CI. To run it locally, set
`KWIK_QUICK_GATE_CLI` to an installed checkout's `src/cli.js`, then run
`pytest tests/test_workflow.py -k real_js_adapter_roundtrip`.

The real PyGate roundtrip is also exercised in adapter CI. Set `KWIK_PYGATE_CLI`
to an installed `pygate` and run `pytest tests/test_routing.py -k real_pygate`.
