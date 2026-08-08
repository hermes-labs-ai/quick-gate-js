# quick-gate-js is a deterministic JS/TS quality gate

quick-gate-js is a deterministic JS/TS quality gate that unifies ESLint, TypeScript, build, and Lighthouse checks into one fail-fast result, with bounded auto-repair and structured escalation evidence.

> **Repo `quick-gate-js`, npm package `quick-gate`.** Install the CLI from npm
> and use the canonical `quick|full` mode names shown below.

JavaScript and TypeScript CI failures are noisy, tool-specific, and expensive to triage when ESLint, TypeScript, build steps, and Lighthouse all fail in different ways. Quick Gate turns those checks into one deterministic JS/TS quality gate with bounded auto-repair and structured escalation evidence.

- "The PR failed, but I have to piece together ESLint, TypeScript, build, and Lighthouse output by hand."
- "We want fail-fast frontend CI, not another dashboard."
- "Auto-fix should stop when it stops helping instead of chewing through the repo."
- "If repair cannot finish, I want a clean escalation artifact that an engineer or agent can actually use."

```bash
npm install -g quick-gate@0.2.3
```

```bash
quick-gate --help
```

```text
Quick Gate v0.2.3

Commands:
  quick-gate run --mode quick|full --changed-files <path>
  quick-gate summarize --input .quick-gate/failures.json
  quick-gate repair --input .quick-gate/failures.json [--max-attempts 3] [--deterministic-only]
```

**When To Use It**

Use Quick Gate when you want one deterministic CI gate over JavaScript or TypeScript project checks, optional bounded repair, and machine-readable escalation artifacts for follow-up work.

**When Not To Use It**

Do not use Quick Gate as a generic lint dashboard, a semantic code-repair engine, or a replacement for your underlying ESLint, TypeScript, build, or Lighthouse setup.

![quick-gate preview](assets/preview.png)

[![npm version](https://img.shields.io/npm/v/quick-gate)](https://www.npmjs.com/package/quick-gate)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Node.js >= 18](https://img.shields.io/badge/node-%3E%3D18-brightgreen)](https://nodejs.org)
[![CI](https://github.com/hermes-labs-ai/quick-gate-js/actions/workflows/ci.yml/badge.svg)](https://github.com/hermes-labs-ai/quick-gate-js/actions/workflows/ci.yml)

Deterministic quality gate CLI for JavaScript and TypeScript projects with bounded auto-repair and explicit escalation evidence. Works with Next.js, React, Vue, Svelte, Angular, or any Node.js project with TypeScript.

## Quick Start

Requires **Node.js >= 18** and a project with dependencies installed (`npm ci`).

```bash
# From your project directory:
npx quick-gate@0.2.3 run --mode quick --changed-files <path>

# Or install globally:
npm install -g quick-gate@0.2.3
quick-gate --help
```

Create a changed-files list (newline-delimited or JSON array):

```bash
echo "app/page.tsx" > /tmp/changed.txt
quick-gate run --mode quick --changed-files /tmp/changed.txt
```

Existing automation may continue to pass `--mode canary`; Quick Gate treats it
as a backward-compatible alias and records the canonical mode `quick` in output
artifacts. New commands and configurations should use `quick`.

## What It Does

Quick Gate runs up to four deterministic quality gates on your project. In **quick** mode (default): lint + typecheck + lighthouse. In **full** mode: all four including build.

1. **lint** -- runs your ESLint config
2. **typecheck** -- runs TypeScript compiler
3. **build** -- runs production build (full mode only)
4. **lighthouse** -- runs Lighthouse CI assertions

When gates fail, it produces structured evidence (not just exit codes) and optionally runs a bounded repair loop that:
- Applies deterministic fixes first (eslint --fix on scoped files)
- Optionally uses local LLM models (via Ollama) for model-assisted patches
- Enforces hard limits on attempts, patch size, and wall-clock time
- Escalates with machine-readable evidence when it can't resolve

## Commands

```bash
# Run quality gates
quick-gate run --mode quick|full --changed-files <path>

# Generate agent brief from failures
quick-gate summarize --input .quick-gate/failures.json

# Bounded repair loop
quick-gate repair --input .quick-gate/failures.json [--max-attempts 3] [--deterministic-only]
```

## Artifacts

Generated in your project under `.quick-gate/`:

| File | Description |
|------|-------------|
| `failures.json` | Structured findings with severity, thresholds, evidence |
| `run-metadata.json` | Gate execution traces (commands, stdout, stderr) |
| `agent-brief.json` | Priority actions + retry policy for downstream agents |
| `agent-brief.md` | Human-readable summary |
| `repair-report.json` | Repair attempt history (on success) |
| `escalation.json` | Escalation reason + evidence (when repair fails) |

## Repair Policy

| Parameter | Default | Description |
|-----------|---------|-------------|
| max attempts | 3 | Total repair attempts before escalation |
| max patch lines | 150 | Per-attempt patch size budget |
| no-improvement abort | 2 | Consecutive no-improvement attempts before abort |
| time cap | 20 min | Wall-clock limit for entire repair loop |

Escalation reason codes: `NO_IMPROVEMENT`, `PATCH_BUDGET_EXCEEDED`, `ARCHITECTURAL_CHANGE_REQUIRED`, `FLAKY_EVALUATOR`, `UNKNOWN_BLOCKER`

## Model-Assisted Repair (Optional)

Requires [Ollama](https://ollama.com) installed locally. Without Ollama, Quick Gate still works -- it runs deterministic fixes only and escalates what it can't resolve.

With Ollama:
- **Hint model** (default: `qwen2.5:1.5b`): Generates repair hints
- **Patch model** (default: `mistral:7b`): Generates scoped edit plans
- Safety: edit plans are scored for relevance and enforced against patch-line budget before apply

Environment overrides:

```bash
QUICK_GATE_HINT_MODEL=qwen3:4b
QUICK_GATE_PATCH_MODEL=mistral:7b
QUICK_GATE_MODEL_TIMEOUT_MS=60000
QUICK_GATE_ALLOW_HINT_ONLY_PATCH=0
```

## GitHub Action

Add Quick Gate to any PR workflow with one step:

```yaml
# .github/workflows/quick-gate.yml
name: Quick Gate
on:
  pull_request:
    branches: [main]
permissions:
  contents: read
  pull-requests: write
jobs:
  quality-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - run: npm ci
      - uses: hermes-labs-ai/quick-gate-js/.github/actions/quick-gate@main
        with:
          mode: quick
          repair: "true"
          post-comment: "true"
```

This will:
- Detect changed files from the PR diff
- Run lint, typecheck, and Lighthouse gates
- Attempt deterministic repair (eslint --fix) on failures
- Post a structured findings comment on the PR
- Upload `.quick-gate/` artifacts for inspection

No Ollama required -- CI runs in deterministic-only mode by default.

## Configuration

Create `quick-gate.config.json` in your project root to override defaults:

```json
{
  "commands": {
    "lint": "npm run lint",
    "typecheck": "npm run typecheck",
    "build": "npm run build",
    "lighthouse": "npm run ci:lighthouse"
  },
  "policy": {
    "maxAttempts": 3,
    "maxPatchLines": 150,
    "abortOnNoImprovement": 2,
    "timeCapMs": 1200000
  }
}
```

## License

Apache 2.0 -- See [LICENSE](LICENSE) for details.

---

## About Hermes Labs

[Hermes Labs](https://hermes-labs.ai) is an AI reliability engineering studio for product and engineering teams shipping production agents and LLM applications. We find the structural AI failures standard evals miss, then harden retrieval, memory, agents, and the language layers around production AI systems with runtime controls and defensible evidence.

Browse the [open-source catalog](https://hermes-labs.ai/open-source) or contact [roli@hermes-labs.ai](mailto:roli@hermes-labs.ai).
