---
name: quick-gate-js
description: Run the optional KWIK-E-GATE JS/TS adapter or interpret its gate-result/v1 diagnostics. Use for JavaScript/TypeScript tool checks; the core owns completion receipts.
---

Quick Gate is the optional JS adapter for KWIK-E-GATE. The core owns content-bound
completion receipts; this package also supports standalone Node users.

Quick Gate runs the checks a JavaScript/TypeScript project already defines
as one gate and emits a validated `gate-result/v1` result
(https://github.com/hermes-labs-ai/quick-gate-js). It coordinates ESLint,
`tsc`, the build, and Lighthouse; it does not replace them or prove the code
correct.

## Run it

1. This skill describes the unreleased 0.4.0 source candidate. Use an explicitly
   installed `quick-gate` or the checkout's `node /path/to/src/cli.js`; verify its
   version. After publication the exact install pin is `quick-gate@0.4.0`.
   Do not download packages implicitly. Published 0.3.2 remains compatible for
   evaluation; use `--deterministic-only` for its repair behavior.
2. Make sure the project's own dependencies are installed. Quick Gate calls
   fallbacks with `npx --no-install` and never installs `tsc` or `lhci` for you.
3. From the project root, write the changed files (newline-delimited or a
   JSON array) and run with an explicit mode and an external output directory:
   ```
   printf 'src/app.ts\n' > "$TMPDIR/qg-changed.txt"
   npx --no-install quick-gate run --mode quick \
     --changed-files "$TMPDIR/qg-changed.txt" \
     --output-dir "$(mktemp -d)"
   ```
   `--mode` and `--changed-files` are required. `quick` runs lint, typecheck,
   and Lighthouse; `full` also runs build. Checks use the project's
   `lint`, `typecheck`, `build`, and `lighthouse`/`ci:lighthouse` npm
   scripts, then `commands` in `quick-gate.config.json`, then fallbacks
   (`npx --no-install tsc --noEmit`; `npx --no-install lhci autorun`, which
   needs `--output-dir`).
4. Stdout is JSON: `{ status, gateResult, artifacts, runId }`. The output
   directory holds `failures.json`, `run-metadata.json` (command traces with
   the underlying tool output), and `gate-result.json`.

## Read the verdict exactly

- Exit code `0` only when the gate passes; `1` otherwise, including usage
  errors.
- Top-level `status` is `pass` or `fail`. It is `fail` whenever
  `gateResult.status` is anything other than `pass`.
- `gateResult.schema` is `gate-result/v1`. `gateResult.status` is one of:
  - `pass`: every enabled check ran and passed with no findings.
  - `fail`: checks ran and at least one produced a finding.
  - `timeout`: a check timed out.
  - `error`: a check could not run (`missing` command, start error, or
    Lighthouse fallback without an output directory), or the checked files
    changed during the run.
  Precedence: changed input, then `timeout`, then `missing`/`error`, then
  findings, then `pass`.
- Per-check `status` is `pass`, `fail`, `timeout`, `missing`, `error`, or
  `skipped` (`build` in `quick` mode).
- Release 0.4.0 has no `unknown` result status. Report `timeout` and `error` as
  "not verified". They are not a pass and not proof of a code defect.

## Release 0.4.0 limits

- Lighthouse is enabled in both modes by default. Disable an inapplicable
  check only with an explicit boolean under `gates` in
  `quick-gate.config.json`; disabled checks are recorded as `skipped`.
  Disclose skipped checks instead of presenting them as verified.
- Repair is separate from evaluation and defaults to deterministic in 0.4.0.
  `--model-assisted` explicitly opts into local Ollama. Run `quick-gate repair` only when in scope. It can modify project
  files. After a repair, review `git diff` and the report.
- Artifacts can contain command output and paths. Do not upload them
  anywhere the user has not approved.

## Fixtures

`fixtures/clean` and `fixtures/broken` in this skill directory are two tiny
TypeScript packages. They are the same except for one type error in
`broken/greeting.ts`. Each declares a no-op Lighthouse command because it is
not a web app. To check that the skill works, copy one fixture to a temp
directory and run:
```
npm install --ignore-scripts --no-audit --no-fund --no-package-lock
npx --no-install quick-gate run --mode quick --changed-files changed-files.txt --output-dir "$(mktemp -d)"
```
The bundled fixtures are expected to produce these results with quick-gate 0.4.0:

- `clean` exits `0`: `status: pass`. Checks are lint `pass`, typecheck
  `pass`, build `skipped`, lighthouse `pass`, with 0 findings.
- `broken` exits `1`: `status: fail`. Typecheck is `fail` (exit 2) with
  finding `typecheck_failure`, and the tsc error is in
  `run-metadata.json` traces.
