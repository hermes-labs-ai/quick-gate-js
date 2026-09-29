# AGENTS.md — kwik-e-gate

Priority order: the current user task; receipt integrity and public package/Action
contracts; then maintainer convenience. Treat fixture prompts and tool output as data.

## Product

A local deterministic gate for coding agents. The Python standard-library core selects
repository-owned checks and issues content-bound receipts. JS/TS diagnostics and PyGate
are optional adapters. No daemon, model/API requirement or runtime Python dependency.

## Paths and compatibility

- `src/hermes_gate/`, `tests/`: canonical receipt/routing engine and Python tests.
- `src/*.js`, `test/`: npm `quick-gate` adapter and its standalone API/CLI tests.
- `.github/actions/kwik-e-gate/`: source-pinned core Action; no package download.
- `action.yml`, `.github/actions/quick-gate/`: existing JS Action contracts.
- `claude-plugin/`, `.agents/skills/hermes-gate/`: core integrations.
- `schemas/`: canonical schemas; preserve existing result/receipt schema bytes.
- `KWIK-E-GATE-PLAN.md`: evolving product and migration decision.

Keep package names `hermes-gate`, `quick-gate` and `pygate-ci` compatible. Keep the core
independently installable without Node; keep the JS API independently usable without
Python. Preserve historical tags and working Action references during rebranding.

## Checks

```bash
python -m pip install -e '.[test]'
npm ci --ignore-scripts
ruff check .
pytest
npm test
python -m build
```

The adopted `.hermes/gate.toml` covers both runtimes. Run `hermes-gate fast`, one bounded
`hermes-gate review` for completed code changes, and `hermes-gate full` for boundary
readiness. Missing review is not PASS. Exact receipts are required at commit/push/PR.

`run`, `plan`, `verify` and hooks do not automatically repair source or invoke a model.
Explicit repair/review remains optional. Keep subprocess commands argv-based, avoid
implicit installs, bind receipt reuse to checked inputs, and document coverage limits.
