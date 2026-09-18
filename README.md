# Quick Gate

[![CI](https://github.com/hermes-labs-ai/quick-gate-js/actions/workflows/ci.yml/badge.svg)](https://github.com/hermes-labs-ai/quick-gate-js/actions/workflows/ci.yml)
[![Node.js >= 18](https://img.shields.io/badge/node-%3E%3D18-brightgreen)](https://nodejs.org/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

Quick Gate turns noisy JavaScript and TypeScript checks into one deterministic CI result with structured findings and bounded repair/escalation artifacts.

When lint, typechecking, builds, and Lighthouse assertions fail independently, a developer has to reconstruct the state of a change from several tools and logs. Quick Gate runs the checks as one explicit gate, records what it checked and how each command ended, and gives the next engineer or agent a bounded evidence packet to act on.

## First success

Quick Gate requires Node.js 18 or newer and a project whose dependencies are already installed. From this repository, the verified setup is:

```bash
git clone https://github.com/hermes-labs-ai/quick-gate-js.git
cd quick-gate-js
npm install
npx --no-install quick-gate --help
```

From the JavaScript or TypeScript project you want to check, install Quick Gate as a development dependency and use the local binary. The first recipe is for POSIX shells (macOS, Linux, or WSL):

```bash
npm install --save-dev quick-gate

QG_CHANGED="$(mktemp)"
QG_OUTPUT="$(mktemp -d)"
printf 'src/app.ts\n' > "$QG_CHANGED"
npx --no-install quick-gate run \
  --mode quick \
  --changed-files "$QG_CHANGED" \
  --output-dir "$QG_OUTPUT"
```

For PowerShell, use the equivalent temporary paths and local binary:

```powershell
npm install --save-dev quick-gate

$qgChanged = Join-Path ([System.IO.Path]::GetTempPath()) ("quick-gate-changed-" + [guid]::NewGuid() + ".txt")
$qgOutput = Join-Path ([System.IO.Path]::GetTempPath()) ("quick-gate-output-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $qgOutput | Out-Null
"src/app.ts" | Set-Content -NoNewline $qgChanged
npx --no-install quick-gate run `
  --mode quick `
  --changed-files $qgChanged `
  --output-dir $qgOutput
```

The changed-files input is either a newline-delimited file or a JSON array. The commands above assume your project provides the underlying checks; if a check is not configured or available, Quick Gate reports that as a finding instead of inventing a result.

### Verify the runtime you are about to run

Quick Gate has three release surfaces that move independently. Check the row you actually depend on before you install or debug against it:

| Surface | Current value | Where it's declared |
| --- | --- | --- |
| npm runtime (published package) | [`0.2.3`](https://www.npmjs.com/package/quick-gate/v/0.2.3) | [GitHub release `v0.2.3`](https://github.com/hermes-labs-ai/quick-gate-js/releases/tag/v0.2.3), [changelog entry](CHANGELOG.md#023---2026-08-08) |
| repository source (this checkout) | `0.3.0` | `package.json` |
| agent plugin (GitHub release) | [`v0.3.1`](https://github.com/hermes-labs-ai/quick-gate-js/releases/tag/v0.3.1) | latest tagged GitHub release |

`0.3.0` is a source-checkout identifier only, not an npm package version. Do not run `npm install -g quick-gate@0.3.0`: npm does not provide that version. Installing `quick-gate` from npm always resolves to the npm runtime row above.

After installing into a project, read back the local runtime without asking npm to install anything:

```bash
npx --no-install quick-gate --version
# quick-gate 0.2.3
```

To verify the public artifact independently of a project checkout, use its exact published pin:

```bash
npx --yes quick-gate@0.2.3 --version
# quick-gate 0.2.3
```

To inspect the source checkout instead, read its package metadata directly:

```bash
node -p "require('./package.json').version"
# 0.3.0
```

Worked example, run against the published package in a throwaway directory:

```console
$ npm install --save-dev quick-gate
added 7 packages, and audited 8 packages in 5s
found 0 vulnerabilities

$ npx --no-install quick-gate --help
Quick Gate v0.2.3

Commands:
  quick-gate run --mode quick|full --changed-files <path>
    --output-dir <external-directory>
  quick-gate summarize --input .quick-gate/failures.json
  quick-gate repair --input .quick-gate/failures.json [--output-dir <external-directory>]
    [--max-attempts 3] [--deterministic-only]

Options:
  --deterministic-only   Skip model-assisted repair (no Ollama required)
  --help, -h             Show this help message
```

## Agent plugin

The repository root is also one agent plugin. Claude Code, Codex CLI, Gemini CLI, and `npx skills` all install the same skill, [`skills/quick-gate-js/SKILL.md`](skills/quick-gate-js/SKILL.md). The skill runs the released `quick-gate@0.2.3` package and reports its `gate-result/v1` verdict.

| Host | Install | Read back |
| --- | --- | --- |
| Claude Code | `claude plugin marketplace add hermes-labs-ai/quick-gate-js && claude plugin install quick-gate-js@quick-gate-js` | `claude plugin list` |
| Codex CLI | `codex plugin marketplace add hermes-labs-ai/quick-gate-js && codex plugin add quick-gate-js@quick-gate-js` | `codex plugin list` |
| Gemini CLI | `gemini extensions install https://github.com/hermes-labs-ai/quick-gate-js --ref main` | `gemini skills list` |
| skills.sh | `npx skills add hermes-labs-ai/quick-gate-js` | `npx skills list` |

Each host reads its own manifest:

- Claude Code reads `.claude-plugin/marketplace.json` and `.claude-plugin/plugin.json`.
- Codex reads `.agents/plugins/marketplace.json`, whose entry is the repository root, and the portable Agent Plugins `plugin.json`.
- Gemini CLI reads `gemini-extension.json` and finds the skill under `skills/`.

## What it runs

Quick Gate is a coordinator around the commands already defined by your project. It does not replace ESLint, TypeScript, your build, or Lighthouse.

| Mode | Checks |
| --- | --- |
| `quick` | lint, typecheck, and Lighthouse |
| `full` | lint, typecheck, Lighthouse, and build |

The CLI requires an explicit mode. In a project with matching npm scripts, Quick Gate uses `npm run lint`, `npm run typecheck`, `npm run build`, and an available Lighthouse script. You can override commands in `quick-gate.config.json`. If no `typecheck` script exists, it tries `npx --no-install tsc --noEmit`; if no Lighthouse script exists, the Lighthouse fallback requires an explicit output directory so its filesystem results have a known home.

These are the default checks. Declare inapplicable checks explicitly in `quick-gate.config.json`; Quick Gate does not infer applicability from missing scripts. For a plain JavaScript library with a lint script, no typecheck, no build step, and no website to audit:

```json
{
  "gates": {
    "typecheck": false,
    "build": false,
    "lighthouse": false
  }
}
```

`gates` accepts only `lint`, `typecheck`, `build`, and `lighthouse` with boolean values. Omitted entries stay enabled for their mode; `build: true` still requires `full` mode. Disabled checks are recorded as `skipped` and launch no commands. Missing or failing enabled checks still fail the run. This configuration applies to the CLI, repair reruns, and the composite GitHub Action; API callers can provide the same `gates` object in their configuration.

Every run records `pass`, `fail`, `timeout`, `missing`, `error`, or `skipped` checks, command traces, exit and timeout information, findings, command versions, a snapshot digest for the checked paths, and whether output was truncated. A run exits `0` when the gate passes and `1` otherwise.

## Artifacts and output directories

`run` writes artifacts to an external temporary directory by default. The CLI prints the run result and uses a directory named like `quick-gate-run-*` under the operating system temporary directory. Nothing is implicitly added to the reviewed worktree.

Choose a directory explicitly when CI or another process needs a stable path. The following example continues the `QG_OUTPUT` shell variables from First success:

```bash
npx --no-install quick-gate run \
  --mode quick \
  --changed-files "$QG_CHANGED" \
  --output-dir "$QG_OUTPUT"
```

An explicit run directory contains:

| File | Purpose |
| --- | --- |
| `failures.json` | Run status, changed files, gate statuses, and structured findings |
| `run-metadata.json` | Timing, configuration source, command traces, and artifact location |
| `gate-result.json` | Validated `gate-result/v1` result |

The following commands have separate, legacy worktree behavior:

```bash
npx --no-install quick-gate summarize \
  --input "$QG_OUTPUT/failures.json" \
  --output-dir "$QG_OUTPUT"

npx --no-install quick-gate repair \
  --input "$QG_OUTPUT/failures.json" \
  --output-dir "$QG_OUTPUT" \
  --deterministic-only
```

When `--output-dir` is provided, `summarize` and `repair` keep their reports, rerun artifacts, escalation, and backup directories in that same external directory. Without it, they retain the legacy `.quick-gate/` behavior. Repair may modify project files, so inspect the diff before accepting changes.

## The next useful command

After a failed run, turn its findings into prioritized human- and agent-readable actions:

```bash
npx --no-install quick-gate summarize \
  --input "$QG_OUTPUT/failures.json" \
  --output-dir "$QG_OUTPUT"
```

For repair, start with deterministic-only mode. It can apply scoped ESLint fixes, rerun the gate, and escalate when it cannot make bounded progress. Model-assisted repair is optional and only runs when Ollama is available and deterministic-only mode is not requested.

```bash
npx --no-install quick-gate repair \
  --input "$QG_OUTPUT/failures.json" \
  --output-dir "$QG_OUTPUT" \
  --max-attempts 3 \
  --deterministic-only
```

Repair exits `0` on a pass and `2` when it escalates. Its default policy is three attempts, a 150-line patch budget per attempt, a two-attempt no-improvement cap, and a 20-minute wall-clock cap. Escalation reason codes include `NO_IMPROVEMENT`, `PATCH_BUDGET_EXCEEDED`, `ARCHITECTURAL_CHANGE_REQUIRED`, `FLAKY_EVALUATOR`, and `UNKNOWN_BLOCKER`.

## Embeddable API

Use the API when an application needs the structured evaluation result without Quick Gate writing its own artifact files:

```js
import { evaluateGates } from 'quick-gate';

const { gateResult, findings } = evaluateGates({
  mode: 'quick',
  cwd: process.cwd(),
  changedFiles: ['src/app.ts'],
});

console.log(gateResult.status, findings);
```

`evaluateGates` returns a `gate-result/v1` result and does not write Quick Gate artifacts or invoke repair. It still executes the configured project commands, so those commands remain responsible for their own behavior and side effects. The result is an evaluation of the configured checks and captured inputs—not a universal correctness proof.

## The shared result contract

The `gate-result/v1` contract gives downstream tooling a common envelope for:

- overall `pass`, `fail`, `timeout`, or `error` status;
- checked paths and a snapshot digest;
- per-gate check status, timing, command, timeout, and exit information;
- structured findings and command-version information; and
- truncation, error, configuration, package, and state-directory metadata when available.

The repository validates the emitted contract against [`schemas/gate-result-v1.schema.json`](schemas/gate-result-v1.schema.json). The contract standardizes evidence shape; it does not make the underlying lint, typecheck, build, or Lighthouse evaluator correct, complete, or secure.

### Machine-readable result envelope

For tooling that compares results across products, the same evaluation can be
emitted as a Hermes Reliability Lab result envelope — the ordinary
`gate-result/v1` payload embedded verbatim, plus tool version, a hash of the
exact input, one finding per check and per finding Quick Gate already
produced, the exit code, a timestamp, and the Git commit when run from a
checkout:

```bash
node src/evidence.js --mode quick
node src/evidence.js --mode full --path path/to/project
```

It changes no gate resolution or scoring and writes nothing beyond what
`evaluateGates` already writes (nothing). A check Quick Gate could not run —
missing command, or an error starting it — is reported as `unknown`, not
folded into a pass or silently treated as a code-quality failure.

## Configuration

Create `quick-gate.config.json` in the project root when the default command discovery is not enough:

```json
{
  "commands": {
    "lint": ["npm", "run", "lint"],
    "typecheck": ["npm", "run", "typecheck"],
    "build": ["npm", "run", "build"],
    "lighthouse": ["npm", "run", "ci:lighthouse"]
  },
  "policy": {
    "maxAttempts": 3,
    "maxPatchLines": 150,
    "abortOnNoImprovement": 2,
    "timeCapMs": 1200000,
    "commandTimeoutMs": 120000,
    "gateTimeoutMs": 300000,
    "outputCapBytes": 65536
  },
  "allowUnsafeShellCommands": false
}
```

Prefer argv arrays. Commands run with `shell: false` by default, and command strings are rejected unless `allowUnsafeShellCommands` is explicitly enabled. Quick Gate's own fallback calls use `npx --no-install`; it does not silently install missing project packages.

Environment variables for optional Ollama repair are:

```bash
QUICK_GATE_HINT_MODEL=qwen3:4b
QUICK_GATE_PATCH_MODEL=mistral:7b
QUICK_GATE_MODEL_TIMEOUT_MS=60000
QUICK_GATE_ALLOW_HINT_ONLY_PATCH=0
```

Without Ollama, Quick Gate still runs deterministic gates and deterministic repair. When enabled, the model adapter invokes the local `ollama` command and provides bounded snippets of findings and selected files to it; configure and secure that local service according to your environment.

## GitHub Actions

For a direct workflow, keep the changed-file list and artifacts outside the checkout and make the output directory explicit:

```yaml
name: Quick Gate

on:
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  quality-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - run: npm ci
      - name: Collect changed files
        run: git diff --name-only "${{ github.event.pull_request.base.sha }}...${{ github.sha }}" > "$RUNNER_TEMP/quick-gate-changed.txt"
      - name: Run Quick Gate
        run: >-
          npx --no-install quick-gate run
          --mode quick
          --changed-files "$RUNNER_TEMP/quick-gate-changed.txt"
          --output-dir "$RUNNER_TEMP/quick-gate"
```

The repository also contains a composite action at [`.github/actions/quick-gate/action.yml`](.github/actions/quick-gate/action.yml) and a [copyable workflow example](examples/quick-gate.yml). The action executes its checkout's own `src/cli.js`, installs only that checkout's declared runtime dependencies, and writes run artifacts to either the `output-dir` input or a runner-temporary directory. This keeps the action and CLI versions aligned while leaving the caller's checkout free of run artifacts. The action fails after posting its report and uploading artifacts when the gate remains unresolved; a bounded repair that passes makes the action succeed. Neither the CLI nor the action has automatic merge authority; any PR comment or write permission is a workflow decision you must review.

## Safety, privacy, and limits

Quick Gate is a bounded evidence and repair coordinator. It does not promise:

- universal correctness, complete coverage, or a security guarantee;
- that a passing result means the application is production-ready;
- semantic repair, architectural changes, or a useful fix for every failure;
- automatic merge, release, or deployment authority; or
- hidden package installation or hidden network access.

The underlying project commands can have their own network access and side effects. Command output, stderr, paths, and selected failure context can be written to artifacts. Treat artifacts as potentially sensitive and avoid uploading them to third parties without review. The optional model-assisted path calls local Ollama only when enabled; it is not a hosted model service built into Quick Gate.

`repair` is the mutating command: deterministic ESLint repair and accepted model edit plans can change files, with bounded attempts and backups under `.quick-gate/`. Review `git diff`, the repair report, and any escalation evidence before committing. For security reports, see [`SECURITY.md`](SECURITY.md).

## Troubleshooting

- **`run requires --mode quick|full`** — pass `--mode quick` or `--mode full`; the CLI does not infer a mode.
- **Missing-command findings** — add the corresponding npm script or configure an argv command in `quick-gate.config.json`.
- **`EXTERNAL_STATE_DIR_REQUIRED` for Lighthouse** — pass `--output-dir /absolute/path`, or configure a Lighthouse script that writes its own results.
- **`npx --no-install` cannot find `tsc` or `lhci`** — install the project dependency first; Quick Gate will not fetch it for you.
- **No `.quick-gate` directory after `run`** — this is expected unless you explicitly set `--output-dir .quick-gate`; the default is external temporary storage.
- **`canary` appears in older automation** — it remains accepted as a backward-compatible alias for `quick` and is recorded canonically as `quick`. New commands should use `quick`.

Use `quick-gate --version` for the installed package version and `quick-gate --help` for usage. The version is also recorded in package metadata and run artifacts.

## Development and contribution

```bash
npm install
npm test
```

The test suite exercises the CLI, gate execution, artifact contracts, configuration, bounded repair, and argv safety. Please keep changes focused, add tests for behavior changes, and see [`CONTRIBUTING.md`](CONTRIBUTING.md) for repository conventions. The project is licensed under [Apache License 2.0](LICENSE).

## Also from Hermes Labs

- [quick-gate-python](https://github.com/hermes-labs-ai/quick-gate-python) (PyPI: `pygate-ci`) — the Python counterpart to this repo: a deterministic Python CI quality gate that normalizes Ruff, Pyright, and pytest results into one fail-fast decision, attempts bounded auto-repair, and escalates with machine-readable evidence when it cannot finish safely.
- [lintlang](https://github.com/hermes-labs-ai/lintlang) — static analysis for AI agent configs, tool descriptions, and system prompts; catches vague tool descriptions, missing stop conditions, and schema gaps before they reach runtime.
- [zer0dex](https://github.com/hermes-labs-ai/zer0dex) — a local dual-layer memory pattern for AI agents pairing a compact markdown index with semantic retrieval from a local vector store.
- [little-canary](https://github.com/hermes-labs-ai/little-canary) — detects prompt injection by its effect on a sacrificial canary model rather than pattern matching alone, returning block, flag, or pass before the primary model acts.
- [fidelis](https://github.com/hermes-labs-ai/fidelis) — zero-LLM agent memory using local-first BM25, dense-vector, and reciprocal-rank-fusion retrieval, returning original passages verbatim by default. Available on PyPI as `fidelis-memory`.

## About Hermes Labs

[Hermes Labs](https://hermes-labs.ai) builds reliability tooling for teams shipping production agents and AI applications. Quick Gate is an open-source JavaScript/TypeScript quality-gate utility from that work.
