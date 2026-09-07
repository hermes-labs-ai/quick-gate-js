# Reliability Lab fixtures

Two throwaway projects used only to generate the Hermes Reliability Lab's
Quick Gate captures (`node scripts/capture-quick-gate-fixture.mjs` in the
site repo). Not part of the npm package, not covered by `npm test`.

- `clean/` — `evaluateGates({ mode: "quick" })` passes: no lint or type
  findings. Lighthouse is disabled in `quick-gate.config.json`, the same
  documented option this repository uses on itself, because these fixtures
  are plain packages, not web apps.
- `broken/` — the same shape with one real type error (`greeting()` is
  annotated `-> string` and returns `42`). The typecheck gate fails; lint
  stays clean.

`npm install` must be run once inside each fixture (devDependencies:
eslint, typescript) so `npx --no-install tsc` and `eslint .` resolve real
local binaries — that install is local to the fixture and is not part of
what the deployed lab does.

Regenerate nothing by hand here; these are inputs, not outputs.
