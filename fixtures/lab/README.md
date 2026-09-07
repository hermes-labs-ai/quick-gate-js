# Reliability Lab fixtures

Two throwaway projects used to test and generate the Hermes Reliability Lab's
Quick Gate captures (`node scripts/capture-quick-gate-fixture.mjs` in the
site repo). They are covered by `npm test` but are not part of the npm package.

- `clean/` — `evaluateGates({ mode: "quick" })` passes: no lint or type
  findings. Lighthouse is disabled in `quick-gate.config.json`, the same
  documented option this repository uses on itself, because these fixtures
  are plain packages, not web apps.
- `broken/` — the same shape with one real type error (`greeting()` is
  annotated `-> string` and returns `42`). The typecheck gate fails; lint
  stays clean.

The root `npm test` command installs each fixture's locked devDependencies
(ESLint and TypeScript) before running the suite so a fresh checkout exercises
the same real local binaries without manual setup. Those installs stay local
to the fixtures and are not part of what the deployed lab does.

Regenerate nothing by hand here; these are inputs, not outputs.
