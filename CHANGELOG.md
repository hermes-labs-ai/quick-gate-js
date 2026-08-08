# Changelog

All notable changes to this project will be documented in this file.

## [0.2.2] - 2026-08-08

### Changed
- Standardized the documented CLI on `quick|full` modes.
- Kept `canary` as a backward-compatible input alias that emits canonical `quick` artifacts.

## [0.2.0] - 2026-02-25

### Added
- Four quality gates: lint (ESLint), typecheck (tsc), build, and Lighthouse
- Bounded auto-repair loop with optional LLM-assisted patches via Ollama
- Machine-readable escalation evidence (`.quick-gate/escalation.json`)
- Changed-files mode for fast PR feedback
- `quick` and `full` run modes
- Broadened from Next.js-only to all TypeScript/ESLint projects
