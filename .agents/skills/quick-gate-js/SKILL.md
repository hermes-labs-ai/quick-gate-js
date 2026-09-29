---
name: quick-gate-js
description: Run the optional KWIK-E-GATE JS/TS adapter or interpret its gate-result/v1 diagnostics. Use for JavaScript/TypeScript project checks; the core owns completion receipts.
license: Apache-2.0
---

# Quick Gate JS adapter

Requires Node.js 18+ and explicitly installed project tooling. Standalone use
does not require Python.

Use an explicitly installed `quick-gate` or this checkout's `node src/cli.js`.
The source candidate is 0.4.0; published 0.3.2 remains compatible for evaluation.
Do not download packages implicitly.

Quick Gate collects the project's lint, typecheck, build and Lighthouse results.
It emits validated `gate-result/v1` diagnostics; use the core's `kwik-gate run`
for content-bound completion receipts. Neither result proves code correctness.

Prepare a changed-files manifest (newline-delimited paths or a JSON array), then run:

```sh
npx --no-install quick-gate run --mode quick \
  --changed-files /path/to/changed-files.txt \
  --output-dir /path/to/external-output
```

Read stdout's `gateResult`, `artifacts` and `runId`. Run artifacts use an external
temporary directory by default, including `failures.json`, `run-metadata.json`
and `gate-result.json`; follow the returned paths. Missing enabled tools, timeouts,
changed inputs and all-skipped evaluation cannot become a verified pass. `full`
adds the build stage; explicitly disable inapplicable checks in project config.

Repair is separate and can modify source. In 0.4.0 it defaults to deterministic;
`--model-assisted` explicitly opts into Ollama. Published 0.3.2 users must request
`--deterministic-only`. Inspect the repair report and source diff before accepting.

For configuration, exact verdict/exit semantics and complete examples, read the
[standalone JS guide](../../../docs/QUICK-GATE-JS.md). The packaged plugin's
[detailed entrypoint](../../../skills/quick-gate-js/SKILL.md) describes its fixtures.
