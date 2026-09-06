# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Fixed
- Made the composite action return a failing status when gate failures remain unresolved, after preserving its report and artifacts.
- Moved the copyable Quick Gate workflow example out of the active workflow directory so it does not run against this repository's intentionally minimal package scripts.

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
