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
2. Install dependencies: `npm install`
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
npm install
npm test
```

## Questions?

Open a discussion or issue on GitHub. We are happy to help.

## License

By contributing, you agree that your contributions will be licensed under the
Apache License 2.0.
