---
name: quick-gate-js
description: Use when you need a deterministic JS/TS CI quality gate that unifies ESLint, TypeScript, build, and Lighthouse checks into one fail-fast result — with bounded auto-repair and structured escalation evidence for humans or agents — across Next.js, React, Vue, Svelte, or any Node project. A gate-and-escalate wrapper, not a dashboard.
license: MIT
compatibility: Requires Node.js 18+; installs via `npm install -g quick-gate` or runs standalone via `npx quick-gate`. Runs the project's own ESLint/TypeScript/build/Lighthouse tooling, no network access beyond what those tools need.
---

# quick-gate-js

quick-gate-js (npm package `quick-gate`) is a deterministic JS/TS CI quality
gate that unifies ESLint, TypeScript, build, and Lighthouse checks into one
fail-fast result, with bounded auto-repair and structured escalation
evidence for humans or agents. Works with Next.js, React, Vue, Svelte, or
any Node project. A gate-and-escalate wrapper, not a dashboard.

## Use it for

- Running lint/typecheck/build/Lighthouse as one CI gate with a single
  pass/fail exit
- Getting machine-readable failure evidence (`failures.json`,
  `run-metadata.json`) an agent can read and act on
- Bounded, deterministic auto-repair of common lint/format failures before
  escalating to a human or model
- Summarizing a failed run into an agent-consumable brief

## Do not use it for

- A general-purpose linting dashboard or historical trend tracker
- Unbounded auto-repair — the repair loop is capped and escalates instead of
  looping indefinitely
- Non-Node projects (use quick-gate-python for a Python-native gate)

## Quickstart

```bash
npm install -g quick-gate
quick-gate run --mode quick --changed-files src/index.ts
```

Or without installing, via `npx`:

```bash
npx quick-gate run --mode quick --changed-files src/index.ts
```

Real output from a run against a minimal project:

```json
{
  "status": "fail",
  "failuresPath": "/path/to/.quick-gate/failures.json",
  "metadataPath": "/path/to/.quick-gate/run-metadata.json",
  "runId": "run_20260915203220_b829e1af"
}
```

## Commands

```
quick-gate run --mode quick|full --changed-files <path>
quick-gate summarize --input .quick-gate/failures.json
quick-gate repair --input .quick-gate/failures.json [--max-attempts 3] [--deterministic-only]
```

## Output shape

- `run`: JSON with `status` (`pass`/`fail`), paths to `failures.json` and
  `run-metadata.json`, and a stable `runId`
- `summarize`: agent-readable brief distilled from `failures.json`
- `repair`: bounded repair attempts (`--deterministic-only` skips
  model-assisted repair and needs no Ollama)

## Common gotchas

- `run` always writes `.quick-gate/failures.json` even on the first failing
  check — read that file for the actual check-by-check detail, the top-level
  JSON is a pointer, not the full report.
- `--mode full` runs the complete check set (including Lighthouse where
  configured); `--mode quick` is the fast subset for pre-commit use.
- `repair` is bounded by `--max-attempts`; it escalates with structured
  evidence rather than looping past that cap.

## More

Full docs and CI integration: https://github.com/hermes-labs-ai/quick-gate-js
