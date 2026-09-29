# Configuration

The core reads `.hermes/gate.toml`. `init` proposes commands and writes a reversible
integration; inspect it before adopting it. The install manifest/backups and receipts
live under the worktree's Git directory. `uninstall-repo` restores installed files
only while they still match installed bytes.

## Deterministic checks

Each `[[fast]]` or `[[full]]` entry has `name`, `argv` (a nonempty string array),
`timeout_seconds`, and optional `globs` (default `**/*`). There is no implicit shell.
`{files}` expands into separate argv items. Commands own their behavior; a shell
inside a project's npm script is part of that declared command.

Fast selects changed paths from the worktree/index/untracked files or a committed
comparison. Use `--base <commit>` or `HERMES_GATE_BASE` for an explicit comparison.
Full executes the whole declared contract with every included repository input,
including clean checkouts. It records `execution_paths` separately from diff scope.

| `[gate]` key | Meaning |
| --- | --- |
| `fast_budget_seconds` | Fast subprocess budget, default 8s; input hashing adds size-dependent overhead |
| `exclusions` | Paths outside the workload; do not exclude sources/configuration your checks rely on |
| `full_required_local` | Require full evidence at push/PR boundaries; default false |
| `review_required` | Require a separate review receipt at push/PR boundaries |

Newly generated profiles set `review_required = false`, so local Git gating is
useful without a model or API. Existing profiles that omit the field retain their
legacy `true` policy. Changing policy is explicit and invalidates old evidence.
The profile and copied runner always enter receipt identity even if excluded from
fast path selection. Ignored files, excluded build outputs/dependencies and external
environment are outside the content guarantee. Directory inputs fail closed.

## Local routing

`run` defaults to `--mode auto`. `plan` previews its selection without running checks.
It uses changed paths and repository policy: project/dependency contracts, tests,
CI/gate config and auth/security/schema/migration paths escalate to full. Ordinary
changes use matching fast globs. These rules broaden checks and never invent commands
or install tools. Full-stage applicability is resolved against all included inputs
at execution. An empty/unsupported chosen contract fails with a receipt.

Optional `[routing]` keys extend the conservative defaults:

```toml
[routing]
full_globs = ["core/**", "db/**"]
review_globs = ["billing/**", "**/*.prompt"]
```

Review recommendations are advice, never silent model calls. Existing
`review_required` boundary policy is independent. Explicit `--mode fast|full` selects
that contract. Receipts record the route; `verify` defaults to the most recently
issued run receipt, including failed runs and cached runs. `--kind fast|full` chooses
one explicitly. Routing is deterministic pattern/policy interpretation, with no
semantic correctness claim or mandatory ML classifier.

## Optional Python adapter

`kwik-gate init --adapter pygate` generates:

```toml
[adapter]
enabled = true
name = "pygate"
argv = ["pygate"]
minimum_version = "0.3.2"
```

Install `pygate-ci` and its chosen Ruff/Pyright/pytest tools explicitly. Fast becomes
PyGate canary; full becomes PyGate full. Its default checks are whole-project checks,
not changed-file-only analysis. The core validates the same result/digest/exit contract
and wraps it in a completion receipt. Unicode/newline lists use JSON; each adapter's
existing canonical snapshot serialization is respected. The core itself stays stdlib.

## Optional JS adapter

`kwik-gate init --adapter quick-gate` generates:

```toml
[adapter]
enabled = true
name = "quick-gate"
argv = ["npx", "--no-install", "quick-gate"]
minimum_version = "0.3.2"
```

Install npm `quick-gate` yourself. It remains a standalone Node CLI/API. In adapter
mode the core writes input/result artifacts under Git, validates `gate-result/v1`,
checks path/digest/exit consistency, and creates the only completion receipt.
No primitive/tool/model is automatically installed. Explicit PyGate adapters remain supported (0.2.0+), with tested initialization
for the current 0.3.2 release.

Quick Gate retains its public quick/full behavior: lint, typecheck, Lighthouse,
and build in full. For a JS library without browser checks:

```json
{"gates": {"lighthouse": false}}
```

Disable typecheck only if it is truly inapplicable; missing enabled commands fail.
All-skipped evaluation cannot pass. Build outputs should be ignored or excluded;
source/config changes during a check invalidate PASS. The adapter adds manifest and
configuration to its snapshot and supports Unicode/space/newline file names.

## Explicit extensions

- `[[repair]]`: bounded deterministic repair command; mutates source; separate from run.
- `[lintlang]`: optional installed static prompt/config scanner, configured argv/globs.
- `[review]`: explicit installed provider, `coderabbit` or bounded `jsonl` output;
  provider argv, timeout, material severities/categories and optional fallback argv.
- `boundary commit|push|pr-create|pr-ready`: validate required receipts, never perform
  the Git/PR action or grant authorization.
- `install-codex` and `claude-plugin/`: explicit hook installation. Hooks inspect/advise
  or enforce configured receipts; they do not repair or silently invoke a reviewer.

`run` and `verify` use no semantic-review provider. Legacy `review` can use network
or local models according to its installed provider. Existing strict profiles and
owner instructions can independently require review; do not silently weaken them.

## Receipt contract

`hermes-gate/receipt-v1` stays compatible. Additive `binding` contains
`kwik-gate/binding-v1`, HEAD, included `input_paths`, content/execution-bit digest and
contract digest. `checked_paths`/`scope_base` identify the selected diff; checks record
actual argv and outcome. Additive `routing` records the selection and its evidence; `issued_at` records the
latest run/export even when actual check evidence is cached. Core implementation,
runtime/search-path identity and declared executable bytes (including ordinary
shebang interpreters) are bound;
recorded tool versions are observations, not a complete dependency/environment inventory.

Old receipts without binding require a rerun. Cache/verify reject incomplete or
failed checks, stale content/configuration/tool identity, and wrong checkout/HEAD.
These unsigned local receipts are trusted local evidence, not security attestations.
Exports remain bound to the originating checkout and are for inspection/readback,
not cross-machine certification.

## Git metadata discovery

Core snapshot queries disable Git's optional filesystem monitor for that command
only and time out after ten seconds. A timeout is an infrastructure failure, including
when checking an optional upstream or unborn HEAD; it cannot establish a checked PASS.
`run` still returns a failure receipt. This does not change user Git configuration.
