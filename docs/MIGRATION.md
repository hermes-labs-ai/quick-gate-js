# Migration and release

## Current status

This checkout is an **unreleased 0.4.0 candidate**. Public PyPI/GitHub latest is
0.1.7 as verified 2026-09-29. The JS checkout is an **unreleased 0.4.0 candidate**;
public npm/GitHub latest is 0.3.2. Nothing has been published by this consolidation.

## Existing users

| Surface | Migration |
| --- | --- |
| PyPI `hermes-gate`, import `hermes_gate` | Preserved; upgrade the same distribution |
| `hermes-gate` CLI | Preserved; `kwik-gate` is another entry point to the same engine |
| `fast/full/review/boundary` status API | Preserved, with stronger evidence validation |
| `.hermes/gate.toml` | Preserved; no automatic rewrite/installation |
| Old receipts | Rerun checks; receipts without complete binding cannot be reused |
| Existing review-required profiles | Remain review-required when the new key is omitted |
| New profiles | `review_required=false`; optionally enable review/full policy explicitly |
| PyPI `pygate-ci`, `pygate` and its API | Preserved as optional Python diagnostics adapter; no PyGate runtime rewrite |
| npm `quick-gate`, `evaluateGates`, `runCommand` | Preserved as standalone JS surfaces and optional adapter |
| `gate-result/v1` | Canonical bytes unchanged; still an adapter result rather than boundary receipt |
| JS `quick/full/canary`, artifact paths and Action inputs | Preserved (`canary` remains the quick alias) |
| JS Action `node-version` default | Changes from 20 to 24; explicitly set a supported version to retain a project's runtime |
| New source-pinned core Action | Executes `run` with auto routing; select `mode: fast` or `mode: full` explicitly |
| Existing public Hermes Gate Action | Retains its separate `command` contract at the old repository; it is not the new mode-based Action |
| JS repair default | 0.4.0 makes it deterministic; `--model-assisted` or API `deterministicOnly:false` opts into Ollama |

Full now executes file-driven stages over all included inputs. A mutating check
that previously passed now returns ERROR through the legacy API and FAIL through
`run`. All-skipped JS evaluation is ERROR. JS shell permission now enters config
identity. Review failures/config changes cannot silently reuse previous evidence.

Do not run `init --force` merely to upgrade. Existing profiles/CI remain valid; adopt
new generated CI, portable JS command detection and policy keys through a reviewed
diff. Commit only intended integration updates. Rollback: retain the previous package
pin and profile/CI files; old receipts must still be regenerated, never relabeled.

`run` now defaults to explainable auto selection. Use `--mode fast` for the former
explicit fast behavior. `verify` selects the latest issued run receipt; use `--kind`
for a particular contract. `plan` is a read-only preview and reports PLANNED. Custom
routing globs only extend defaults; optional review advice cannot replace checks.

## Product name, repository URLs and existing users

Use **KWIK-E-GATE** as the product title and carry the existing five-star
`hermes-labs-ai/quick-gate-js` repository identity forward as its product home. This
supersedes the earlier recommendation to keep Hermes Gate as the product home. The
implemented Python core and optional JS/PyGate adapters retain their architecture;
repository branding and source placement are independent of those runtime roles.
Live stars on 2026-09-29 were 5 / 3 / 0 for JS / core / PyGate. No personal GitHub
redirect repository is needed. Source placement is implemented locally in this candidate; public cutover is pending.

Preserve npm `quick-gate`, its import/API/bin surface, PyPI `hermes-gate` and `pygate-ci`,
and old Action owner/repository/tag/commit references. The new `kwik-gate` CLI is an
alias in the existing core distribution. A repository's branding and these install
contracts are separate decisions. No old user needs to change runtimes merely to use
the existing npm adapter.

**Do not rely on a GitHub rename to protect Action users.** Normal web/Git traffic and
stars follow a rename, but GitHub explicitly does not redirect calls to hosted Actions.
Reusing the old repository name ends its normal redirects. A README-only or personal
account shell cannot substitute for a working historical Action reference.
See [GitHub rename documentation](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository).

Stage the completed product in the five-star repository without breaking its existing
JS Action contract. Verify builds, plugin paths, package metadata and publishing
configuration after source placement. Existing local test results do not prove a new
layout. The new core Action runs pinned source directly, without a PyPI install. The old
Hermes Gate Action path must continue to work during and after public cutover.

If the five-star repository is literally renamed to `kwik-e-gate`, first prepare a
working old `quick-gate-js` Action compatibility repository with historical tags/SHAs.
Recreating that old path cancels its automatic GitHub redirect; old web/Git users would
reach that compatibility repository, whose docs point to the canonical product. This
is a proposed migration, not a tested public guarantee. GitHub's default recommendation
is a new Action repository with the old one preserved, which would leave the five stars
on the old repository. The plan records this tradeoff. No rename or new repository
has been executed; no stars from separate repositories are being combined.

## Local candidate verification

```bash
python -m pip install -e '.[test]'
ruff check .
pytest
python -m build
python scripts/verify_release.py --tag v0.4.0 --dist dist
```

Run the real JS roundtrip with `KWIK_QUICK_GATE_CLI=/path/to/quick-gate-js/src/cli.js`
and installed JS checkout dependencies. Set `KWIK_PYGATE_CLI` to installed
`pygate` for the real Python-adapter roundtrip (including Unicode/newline paths). For the JS candidate: `npm ci`, `npm run lint`,
`npm test`, `npm pack --dry-run`. Test the built wheel and tarball in fresh environments.
Adopted repositories also require their own Gate fast/review/full receipts at boundaries.

## Validation and review status

The corrected consolidated 0.4.0 source passed its full gate: 393 Python tests, 95 JS tests,
Ruff and Git integrity, including real Python/JS adapter roundtrips. The wheel/sdist
identity guard passed. A fresh Python 3.14.3 wheel with no runtime dependencies or
Node PATH passed plan/run/export/verify and produced a FAIL receipt for bad syntax.
The npm tarball preserves CLI/API behavior and excludes Python source.

The core's Git metadata queries now disable the optional filesystem monitor per
command and have a ten-second bound. A real sleeping-Git regression proves timeout
cannot become an unchanged/unborn PASS and still produces a failure receipt.

The configured CodeRabbit review passed the completed consolidation tree
`1f09ced23cc1484ec9f76ab18c2b17607590878a` in 195.940 seconds with no material
findings, superseding the earlier timeout/rate-limit attempts.
A subscription-backed independent Claude review returned source PASS for the preceding
staged candidate and publication HOLD, with explicit coverage limits. Its findings led
to the current Action bootstrap, pinned workflow and documentation corrections.
The maintainer collaborator additionally caught missing-package
fallback and failure-receipt edge cases and accepted the resulting local packet as PASS.
Native profile review also corrected stale-wheel tests and implicit Nox interpreter
downloads. These reviews do not substitute for publisher approval. Before a commit/
push/PR, obtain matching receipts for the exact final state, including later profile
and documentation changes. The [admission notes](CI-ADMISSION.md) distinguish five
verified scoped PASS proofs and a sixth reproduced native E2E FAIL. None implies
upstream approval or hosted CI adoption.

The subsequent committed review found timing-wrapper and explicit Git-target hook
bypasses. Their correction is commit `9d2b6d7a0bb82905496613fb0ecb224fa1108ea0`:
420 Python / 95 JS tests passed (full 108.606 seconds), fast passed in 0.838 seconds,
and CodeRabbit returned PASS with no material findings in 250.002 seconds. It also
covers the maintainer's symlink-loop and actual five-second hook-transport findings.
See [hook command scope](CONFIGURATION.md#hook-command-scope) for supported contexts.
The corrected wheel/sdist identity guard passed; the independent npm archive remains
27 files and ships no Python runtime. These results cover that exact local commit.
Later commits require fresh boundary receipts; public checks and source readback belong
to the consolidation PR. No 0.4.0 registry publication is claimed.

## Publication sequence

1. Review/integrate this combined candidate using repository checks and exact receipts.
   Rebase if main changes; preserve the separately owned core/PyGate pull requests.
   Before creating a tag, verify both publisher bindings and any environment approvals
   with the independent publisher. Tag creation itself is a publishing boundary here.
2. Set the actual release date in citation metadata in the reviewed source, then create
   the new immutable `v0.4.0` tag at that accepted commit. **Pushing this tag immediately
   triggers `publish.yml` for npm**; a draft GitHub release does not prevent that trigger.
   Do not push it while intending only to prepare a PyPI release.
3. Observe npm's build/publish workflow and read back `quick-gate` **0.4.0** in the registry.
   Verify package/lock/plugin parity, runtime exports/bin paths, and a fresh install's
   passing/failing gate and deterministic-default repair. Preserve the historical tags.
4. Publish the GitHub `v0.4.0` release only after source and artifact acceptance.
   **The `release: published` event triggers `publish-core.yml` for PyPI.** Its source/
   wheel/sdist guard and source-pinned Action tests must pass; its environment approval
   and trusted publisher binding are separate from npm's. The adapter contracts already
   accept `quick-gate` 0.3.2, so a partial registry outage need not break existing users.
5. Read back PyPI `hermes-gate` **0.4.0**, both workflow results and GitHub release state.
   Install the public wheel afresh; run `kwik-gate run`, export and verify on a disposable
   repository. Test the new source-pinned Action's `mode: full` outputs before recommending
   its release pin. The root Action retains its historical JS interface.
6. Update README/skill released-state wording only after each corresponding publication
   is observed. The combined adapter CI uses this checkout's JS source; historical Action
   references remain supported. A failed publication is a partial release to investigate,
   never a reason to move a tag or claim both registries succeeded.

Repository rebranding/cutover follows the compatibility sequence above. Package
renames, deletion, npm deprecation/unpublishing, tag movement and new package identities
remain unnecessary. Keep historical releases accessible. Release
approval/independent publisher requirements remain governed by the owning lane; local
implementation is not a public release.

## Publisher identity and the combined repository

Core and JS candidate versions are both 0.4.0; the planned repository slug is exactly
`kwik-e-gate`. Current public URLs stay truthful until the rename is observed. Core
PyPI trusted publishing currently belongs to the old repository: its repository and
workflow binding must be authorized and verified for the selected home before upload.
Repository renaming can also affect npm's repository-bound publishing configuration.
Do not substitute an API token, alter an account, or claim publication from local builds.
The source-pinned core Action remains usable independently of PyPI publication.
