# AGENTS.md

Quick Gate is a deterministic JavaScript and TypeScript CI gate with bounded repair and escalation artifacts.

## Use it for

- running one fail-fast gate over lint, typecheck, build, and Lighthouse results
- generating machine-readable artifacts for follow-up agents or humans
- attempting bounded deterministic repair before escalating

## Do not use it for

- replacing ESLint, TypeScript, build, or Lighthouse
- unbounded auto-fixing
- semantic repair beyond deterministic scoped edits

## Minimal commands

```bash
npm install
npx quick-gate --help
npx quick-gate summarize --input .quick-gate/failures.json
npm test
```

## Output shape

- `quick-gate run`: writes `failures.json`, `run-metadata.json`, and `gate-result.json` to an external temporary directory by default; use `--output-dir` for an explicit directory
- `quick-gate summarize`: writes `.quick-gate/agent-brief.json` and `.quick-gate/agent-brief.md`
- `quick-gate repair`: writes `.quick-gate/repair-report.json` or `.quick-gate/escalation.json`

## Success means

- gate outputs normalize into a stable artifact schema
- deterministic repair stays within the configured policy budget
- escalation artifacts explain what blocked automatic completion

## Common failure cases

- required underlying project commands are missing
- users expect Quick Gate to invent semantic fixes
- downstream automation ignores escalation codes and retries without new information

## Maintainer notes

- keep schema files aligned with runtime validation
- keep the repair loop bounded and explicit
- keep README examples aligned with actual CLI behavior
