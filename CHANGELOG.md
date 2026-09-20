# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Fixed
- Added an optional `artifact-name` action input so matrix jobs can preserve separate reports without Artifact v4 name conflicts.
- Return `skipped` in the action’s `repair-status` output when repair is not run. Repository CI exercises both outputs across two Node versions.

## [0.3.0] - 2026-09-07

### Added
- `node src/evidence.js`: emit a `run` evaluation as a Hermes Reliability Lab result envelope (tool, version, status, input hash, per-check and per-finding evidence, exit code, timestamp, Git commit) with the ordinary `gate-result/v1` payload embedded verbatim. No change to gate resolution or scoring.

### Fixed
- Made the composite action return a failing status when gate failures remain unresolved, after preserving its report and artifacts.
- Moved the copyable Quick Gate workflow example out of the active workflow directory so it does not run against this repository's intentionally minimal package scripts.

## [0.2.2] - 2026-04-19

### Changed
- Renamed `canary` mode to `quick` mode (tracked ahead of the 0.2.3 backward-compatible alias).
- Hardened public repo surface documentation.
- Bumped `actions/checkout` and `actions/setup-node` in CI.

## [0.2.1] - 2026-03-02

### Added
- CI workflow, CHANGELOG, and community health files (CODE_OF_CONDUCT, SECURITY, CONTRIBUTING).
- `llms.txt`, `AGENTS.md`, and `CLAUDE.md` for agent discoverability.

### Fixed
- CI test glob quoting for `node --test`.
- npm `homepage` URL corrected from `lpci.ai` to `hermes-labs.ai`.

## [0.2.3] - 2026-08-08

### Changed
- Standardized the documented CLI on `quick|full` modes.
- Kept `canary` as a backward-compatible input alias that emits canonical `quick` artifacts.
- Added the canonical `schema: "gate-result/v1"` discriminator while retaining deprecated `version` for one release.
- Made the composite action execute its checked-out source and keep run artifacts in an explicit external directory.

## [0.2.0] - 2026-02-25

### Added
- Four quality gates: lint (ESLint), typecheck (tsc), build, and Lighthouse
- Bounded auto-repair loop with optional LLM-assisted patches via Ollama
- Machine-readable escalation evidence (`.quick-gate/escalation.json`)
- Changed-files mode for fast PR feedback
- `quick` and `full` run modes
- Broadened from Next.js-only to all TypeScript/ESLint projects
