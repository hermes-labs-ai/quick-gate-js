# Contributing to Quick Gate

Thank you for your interest in contributing to Quick Gate. This document provides
guidelines and information for contributors.

## Reporting Bugs

Please report bugs by opening an issue at:
https://github.com/hermes-labs-ai/quick-gate-js/issues

Include the following in your bug report:
- Quick Gate version (`quick-gate --version`)
- Node.js version (`node --version`)
- Operating system
- Steps to reproduce
- Expected vs actual behavior

## Submitting Pull Requests

1. Fork the repository and create your branch from `main`.
2. Install dependencies: `npm ci --ignore-scripts`
3. Make your changes and add tests if applicable.
4. Run the test suite: `npm test`
5. Ensure your code follows the existing style.
6. Write a clear PR description explaining **what** changed and **why**.

### PR Guidelines

- Keep PRs focused on a single change.
- Update documentation if your change affects user-facing behavior.
- Add a changelog entry under `## [Unreleased]` in `CHANGELOG.md`.

## Development Setup

```bash
git clone https://github.com/hermes-labs-ai/quick-gate-js.git
cd quick-gate-js
npm ci --ignore-scripts
npm test
```

Keep active checkouts in a local directory outside cloud-synced folders. On
macOS, iCloud-managed Desktop or Documents folders can evict source files and
Git objects while retaining their directory entries and reported sizes.

### Recovering an unreadable checkout

If `git status --short` reports `short read while indexing`, first check the
named file with `ls -lO path/to/file` on macOS. A `dataless` flag means the
provider must supply its contents. The same condition can affect `.git/config`
or `.git/objects`, so a failing Git command does not establish a Quick Gate bug.

Preserve the affected checkout, including uncommitted files and local branches.
Do not reset it, delete its index, or overwrite it with a clone. Clone the
remote into a new, unused directory outside the provider-backed folder, then
run `git status --short`, `git fsck --full`, `npm ci --ignore-scripts`, and
`npm test` there. A successful clean checkout restores work on the remote's
committed state; it does not recover unpublished work from the old checkout.
Reconcile that work only after the provider makes its files readable again.

### Maintainer gate

With Hermes Gate installed, run `hermes-gate fast`, `hermes-gate full`, and
`hermes-gate review` before handing off a code change. The canonical profile is
`.hermes/gate.toml`: fast checks Git object integrity, configuration and install
contracts, and whitespace; full runs the complete native `npm test` suite.
Independent review uses CodeRabbit. A missing reviewer is a review limitation,
not a test failure or a successful review.

The existing CI workflow runs `npm test` across its Node.js version matrix.
`git fsck` checks Git objects; it cannot make an evicted worktree file available
or prove that unpublished work has been recovered.

## Questions?

Open a discussion or issue on GitHub. We are happy to help.

## License

By contributing, you agree that your contributions will be licensed under the
Apache License 2.0.
