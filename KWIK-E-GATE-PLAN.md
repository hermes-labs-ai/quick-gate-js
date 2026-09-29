# KWIK-E-GATE: product and architecture decision

Status: 0.4.0 source is integrated in `hermes-labs-ai/quick-gate-js` main by PR #44. Five native readiness profiles have verified scoped PASS proofs; a sixth retains a reproduced upstream E2E FAIL. Product identity cutover and package publication remain separate effects.
Evidence date: 2026-09-29. This document is the consolidation source of truth.

## Product contract

Cheap/free → local → deterministic → fast → dependency-light. Useful without a model,
API, reviewer subscription, daemon, or network service. Run declared checks → PASS/FAIL
→ issue a receipt bound to the input and check contract. **DON'T FORGET THE RECEIPT.**

The core promise is evidence of execution, not a proof of correctness. Deterministic
orchestration does not make flaky tests, network commands, or external tools deterministic.
Receipts are local evidence, not signed attestations or permission to publish.

### Maintenance in historical context

The owner requested a dedicated maintainer collaborator, now primed from all three
projects' source/history. The lead owns edits/integration; the collaborator interprets
contracts and critiques fixes independently. Reuse that role for bounded follow-ups.
Regression review asks:

1. Which historical failure motivated this constraint, and what would show it returning?
2. Which actual consumer invokes the surface: CLI/API, runner, plugin, live Action or fixture?
3. Which bytes/implementation were checked; can scope, index, cache or mutation change that answer?
4. Are the chosen checks useful, correctly scoped, affordable, and honest about coverage?
5. What evidence and exit/path information reaches the caller when startup/execution/storage fails?
6. Which interface or dependency promise survives, or needs an explicit migration?

These are review habits, not additional release bureaucracy. Full execution after
zero-file CI scopes (core `4ac6ac3`), never-adopted hook scope (`c6c7ff3`), stale pytest
report reuse (PyGate `888f574`), unavailable Action defaults (core `725ece3`) and the
saved scanner-scope bug explain why those distinctions matter. Keep diff selection,
workload binding, diagnostics, receipts, coverage and authorization separate.

## Evidence scope and stop rule

Inspect the current public main branches of the original two projects and, after
owner clarification, Quick Gate Python, source, tests, schemas, package manifests,
history, release workflows, plugins/actions and references. Check their own GitHub,
PyPI and npm records; stop external research when current versions and interfaces are
established. Use implementation probes to resolve architecture uncertainties.
No general market survey or new distribution campaign is required.

The owner supplied the product banner after initial diligence. The exact image is the
README header at `docs/assets/kwik-e-gate-header.jpg`; the repository name is lowercase
`kwik-e-gate`. Its convenience-store positioning informs the product story, while the
written execution/receipt requirements remain authoritative.

### Five-project CI admission packet

Question: which five active infrastructure/agent projects can use this source-pinned
gate with their own checks, without adding a mandatory reviewer or model? Establish
submission readiness through their current policies, duplicate/open-submission checks,
real native-check execution and receipt verification. As of 2026-09-29, use only official
repository/package sources; cap this selection pass at 30 source opens (each evidence
page or source-file fetch counts, including API pages). No upstream adoption or approval
is inferred from local compatibility. A maintainer rejection, existing integration, or
inability to run useful native checks would change the selection. Research is read-only;
public submission is a subsequent effect with its own admission and exact-state gates.

## Due diligence: observed state

| Surface | HermesGate | Quick Gate JS |
| --- | --- | --- |
| Public main inspected | `91fd282` | `4a52c15` |
| Published package | PyPI `hermes-gate` 0.1.7 | npm `quick-gate` 0.3.2 |
| GitHub release | `v0.1.7`, 2026-09-19 | `v0.3.2`, 2026-09-20 |
| Runtime | Python ≥3.11, Git; no runtime Python dependencies | Node ≥18; Ajv and ajv-formats |
| Primary interface | `fast`, `full`, `review`, `boundary`, `init`, `doctor` | `run`, `summarize`, `repair`; `evaluateGates` JS API |
| Check execution | Declared argv commands, per-command limits, 8s default fast budget | lint, typecheck, build, Lighthouse; argv worker with output/time limits |
| Evidence | Git-local `hermes-gate/receipt-v1`, content/scope digest | portable `gate-result/v1`, failure artifacts and command traces |
| Agent integration | Claude hooks/plugin, Codex installer/skill, delegate judge | portable Agent Skill/plugin; Claude, Codex, Gemini metadata |
| CI | copied stdlib runner and composite Action installing PyPI | composite Action running checked-out JS and uploading artifacts |

Primary sources: [HermesGate](https://github.com/hermes-labs-ai/hermes-gate),
[PyPI](https://pypi.org/project/hermes-gate/),
[Quick Gate JS](https://github.com/hermes-labs-ai/quick-gate-js),
[npm](https://www.npmjs.com/package/quick-gate).
Package registries were read directly, not inferred from repository version strings.

### What each actually does

HermesGate runs a repository-owned TOML contract through a dependency-free runner,
selects a dirty or committed diff, records receipts in the worktree's Git directory,
caches fast/review PASS results, and enforces selected commit/push/PR boundaries.
Review providers normalize CodeRabbit or bounded JSONL output. Recent history adds
detached-merge scope safety, local Claude review, and release identity guards.
There is an open PR #50 for internal review-provider configuration; it is independent
of deterministic check/receipt consolidation and must not be overwritten.

Quick Gate JS evaluates four opinionated JS/TS stages, normalizes failures and
Lighthouse assertions, generates agent briefs, and optionally repairs scoped lint
problems or uses local Ollama for hint/patch plans. Its quick mode still runs
Lighthouse by default; despite “fail-fast” positioning the loop evaluates every stage.
It already hashes selected input before/after evaluation and reports mutation as an
error. npm exports only `evaluateGates` and `runCommand`; plugins and Actions are
repository surfaces, not npm tarball contents. History records the `canary` alias,
shared result schema, external artifact placement, Action fixes and OIDC publishing.
There are no current open JS PRs.

### Overlap and complementarity

Both coordinate subprocesses, timeouts, output and artifacts. Neither replaces the
project's linter, compiler or tests. Both have repair commands and agent integration.
Duplicating the receipt authority, model routing, and product story is unnecessary.

The useful split is a **single product/receipt authority** and an optional native JS
diagnostic adapter. HermesGate's Python core can gate any language via argv; JS adds
normalized tool diagnostics and its existing npm API without forcing Python on
standalone npm users. Shared `gate-result/v1` is an adapter result, not a reusable
completion receipt. Preserve its exact schema bytes.

### Preserve

- Stdlib core, no daemon, bounded argv execution, explicit tool installation.
- Git scope handling, worktree-local state, exclusion policy, atomic receipts.
- Repository-native commands as the default; optional adapters as an explicit choice.
- Portable result contract and JS API; actionable failure and escalation evidence.
- Release identity guards, immutable tags, package-name continuity and existing Actions.

### Complexity and integrity concerns to challenge

- “Completion ceremony/rail” hides the concrete run/result/receipt workflow.
- External semantic review is mixed into completion policy. It must be optional for
  the canonical deterministic workflow, never a prerequisite for local usefulness.
- Fast receipt cache identity currently hashes selected changed paths, not the whole
  configured check input/contract. Editing an unchanged profile can reuse a stale PASS.
- Native fast/full execution has no post-check input comparison. A successful mutating
  command can generate a PASS for pre-check bytes.
- The JS adapter independently selects `package.json` and config, while the Python
  adapter computes expected digest from the supplied changed paths. Real interoperability
  needs proof; fixture-only adapter tests do not establish it.
- npm repair automatically chooses the model path when Ollama is installed. That is
  surprising for a deterministic default and should require explicit opt-in.
- Duplicate plugin source trees, legacy trial docs and model experiment scripts must
  stay outside the main user journey; do not rewrite or copy them into another core.

### Quick Gate Python: scope added by owner clarification

On 2026-09-29 the owner explicitly asked to include Quick Gate Python and emphasized
context-aware, cheap gate selection. Inspected current main `9a513b4` (original local
checkout was stale), source/evaluation/snapshot/config/repair, tests, history, schemas,
Action/plugin/pre-commit surfaces and release/package identity. Public package
`pygate-ci` / CLI `pygate` is 0.3.2 (GitHub release 2026-09-20), Python ≥3.10,
Pydantic runtime dependency, Ruff/Pyright/pytest as separately installed tools.
Sources: [repository](https://github.com/hermes-labs-ai/quick-gate-python),
[PyPI](https://pypi.org/project/pygate-ci/).

PyGate canary normalizes lint/typecheck; full adds tests. Its API is side-effect-free
apart from declared commands; explicit artifacts use `gate-result/v1`. Changed-file
lists identify snapshot coverage and do not rewrite project-wide check commands.
Python snapshots use ASCII-escaped JSON/codepoint sorting; JS uses Unicode/UTF-16
sorting. The adapter must honor each existing serialization, not redefine schemas.
PyGate is complementary normalized Python diagnostics, not another receipt authority.
No core Pydantic dependency or merger of adapter/receipt responsibilities is justified. Existing repair/config
hardening PR #61 is independently owned and must not be overwritten. Baseline default
suite: 196 passed, 5 integration tests deselected in 24.19s. Its runtime remains unchanged;
this consolidation adds explicit core initialization, real interoperability, CI and
product-role documentation in an isolated `quick-gate-python-kwik` worktree.

## Proposed canonical end state

1. **KWIK-E-GATE** is the product; `kwik-gate` is its concise CLI entry point.
2. Keep the PyPI distribution `hermes-gate`, Python import path and `hermes-gate` CLI
   for compatibility. Add the new entry point to the same package, not another engine.
3. Canonical workflow: `kwik-gate init`, optional `kwik-gate plan`, `kwik-gate run`,
   `kwik-gate verify`. Run defaults to explainable auto selection with explicit fast/full overrides, no model calls, an inspectable PASS/FAIL receipt
   for every terminal outcome, and optional external receipt export. Verification is
   read-only and rejects stale/incomplete evidence.
4. Strengthen the existing receipt engine so cache reuse and Git boundaries bind the
   repository inputs, profile/runner, and declared execution contract; detect mutation
   before issuing PASS. Keep scope selection distinct from workload identity.
5. Keep npm `quick-gate` and PyPI `pygate-ci`
   as optional language diagnostic adapters and compatibility packages. Use the existing
   five-star Quick Gate JS repository as the canonical product identity; the implemented
   architecture does not depend on its current name or source location. Publish one clear product story and a tested integration. No mandatory Node
   in the core and no mandatory Python in the standalone JS API.
6. Deterministic repair remains explicit and separate from run. Model-assisted repair
   and semantic review are optional extensions. They cannot silently change run behavior.
7. Existing package names, result schema, config files and Actions remain addressable.
   Existing receipts that cannot prove the strengthened identity must be regenerated.
8. Do not rename/delete repositories, unpublish packages, move tags, or publish releases
   during implementation. Leave concrete migration and release instructions.

### Why this shape

A Node rewrite discards mature Git scope/hooks without reducing integration work and
adds a mandatory runtime to Python users. Repository identity and source placement can
change while the core and optional adapter remain independently installable packages.
A new package name creates migration overhead before its value is proven. Two competing
gate products behind a shared logo would keep the confusion. One engine/product with
an optional language adapter preserves useful native surfaces at the smallest cost.

## Critical review / revision log

The baseline is clean: Python 333/333 under Python 3.11 in a normal interpreter
path; JS 92/92. Initial Python failures came from space-containing interpreter
shebangs, not product regressions.

Three direct probes against unmodified main falsified stronger existing assumptions:

1. A native command rewrote `source.py` and still returned PASS.
2. A fast run with explicit file scope reused cached PASS after its profile's command
   changed from exit 0 to exit 1.
3. A real Python→Node adapter failed path coverage (macOS `/var` versus `/private/var`
   root spelling). Inspection also confirms the additional JS manifest/config snapshot
   mismatch. Existing synthetic adapter tests missed both integration problems.

**Revision:** keep diff scope for selecting fast checks, but bind receipt reuse to all
tracked and unignored repository inputs allowed by the profile, always including the
profile/runner, execution bits, declared executable identities and core implementation.
Hashing is conservative: a changed unrelated input may force a rerun. This is preferable
to inventing a static dependency graph for arbitrary project commands. Excluded/generated
files and external environment remain outside the guarantee and must be documented.

**Revision:** `run` stays purely deterministic and always reports a terminal PASS/FAIL
with a receipt, including setup errors and no-check cases. Legacy `fast/full/review`
retain their detailed status API. `verify` reads the same receipt authority; there is no
second receipt format or engine. Model review is a separate explicit command, and legacy
boundary review requirements are preserved as an advanced policy, not inherited by run.

**Revision:** preserve separate core and adapter responsibilities. Demonstrate the optional JS integration with real
Node execution and expose adapter selection through initialization. Preserve npm's
legacy quick/full semantics rather than silently redefining them. The native default
requires neither npm nor a browser and invokes exactly the project's declared commands.

**Owner correction, public identity:** the implemented architecture is already selected.
Choosing the existing five-star repository as its product home is a distribution and
repository-placement decision. The earlier recommendation to keep Hermes Gate as the
product home conflated those decisions and is superseded. Carry the existing Quick
Gate JS repository identity forward; retain the core/adapter/package contracts when
placing the completed product there. The core source is now placed in the selected local candidate; public cutover remains pending.

**Revision during implementation:** a receipt could otherwise approve staged bad bytes
while checks observed a fixed worktree. Commit boundaries now require selected staged
paths to match checked worktree bytes. This preserves partial staging when the selected
bytes match, while refusing a different index snapshot.

**Revision during implementation:** executable scripts require interpreter identity too.
Bind ordinary shebang interpreters, Python runtime and command search path; reject
non-finite command timeouts and unreadable directory/symlink inputs. These are bounded
execution/evidence requirements, not a promise to identify every tool dependency.

**September 2026 fit:** the normal Node runtime and generated JS CI use Node 24 LTS;
Node 22 remains supported and Node 18 is tested only for existing compatibility. Node
18/20 are past upstream support. The core still needs only Python ≥3.11 and Git, and a
wheel install without dependencies works on Python 3.14. Source:
[official Node release schedule](https://raw.githubusercontent.com/nodejs/Release/main/schedule.json).
Agent surfaces use portable repository skills, existing Codex/Claude integration and
GitHub Actions; no service, MCP server, browser or agent SDK is required.

**Revision after owner clarification:** receipt integrity alone is insufficient product
intelligence. Add a pure local selector that interprets change paths and repository
policy, chooses matching fast stages or full for dependency/contracts, tests, CI/gate,
auth/security/schema/migration changes, and explains its evidence. Project-specific
`[routing]` globs broaden the defaults. `plan` is a read-only PLANNED preview, never a
checked PASS. Optional semantic providers or the calling coding agent can supply LLM
judgment separately; review advice never silently calls a model or substitutes for
checks. Race between selection and actual scope fails if it changes the required mode.
Native init preserves both Python and JS contracts in polyglot repositories.

The selector performs no I/O/model work. A measured 23-path fixture, 5 repeats of 1,000
choices each, took 0.1967–0.1995 milliseconds per decision on this host. This is selector
cost only; Git, startup, hashing and actual checks are separate, size-dependent costs.
No low-millisecond end-to-end suite or semantic comprehension claim is made.

**Revision from the final fast gate:** LintLang activation respected trigger globs,
but its argv received every changed file. One agent-instruction edit could therefore
scan unrelated source/test fixture prompts, produce irrelevant findings and truncate
its JSON. Restrict scanner argv to existing matching trigger paths; add a regression.
The two adapter AGENTS files also had pre-existing H4/H5 priority/context warnings.
State current-task priority and repository scope clearly. All three fast gates pass. At the owner’s request, preserve the bug and a real
before/after controlled replay in [docs/demo/SCANNER-SCOPE-BUG.md](docs/demo/SCANNER-SCOPE-BUG.md)
and its linked JSON trace for a later stylized repository demo image. Same fixture
bytes/diff digest: original forwards three paths and FAILs; corrected forwards only
AGENTS.md and PASSes. The demo trace is explicitly not a reusable completion receipt.

No implementation requires owner input or irreversible public actions.

## Implementation and acceptance

Accepted implementation scope. Required invariants:

- Default run executes no reviewer/model, installs nothing, and always leaves a receipt.
- Empty/skipped/error execution cannot be presented as a checked PASS.
- PASS cannot survive changed check inputs, configuration, execution contract or HEAD.
- Checks that change bound inputs cannot issue a valid PASS.
- Python and JS agree on snapshot paths/digest for a real adapter evaluation.
- `hermes-gate` and existing npm APIs remain usable; published schema bytes unchanged.
- Tests before/after, clean package build/install, Gate fast and one bounded review.

### Delivered implementation

- Core `workflow.py` implements receipt-producing `run` and read-only `verify` using
  the existing result/receipt schemas. Setup errors, invalid modes/configuration,
  internal execution errors and storage failures return FAIL evidence. If storage is
  unavailable the JSON result still carries the failure receipt; a failed export
  cannot be presented as PASS.
- `routing.py` is the pure explainable selector; `plan` previews it and run/receipts
  expose the actual choice. Auto is the canonical default; explicit modes remain.
  Default verify checks the latest written run receipt and rejects corrupted newest
  evidence, including after a prior PASS.
- `binding.py` separates selected diff scope from conservative workload identity.
  `engine.py`/`receipts.py` reuse that binding for cache, post-check mutation detection,
  review and boundaries. Full file-driven stages see all included inputs.
- Existing `hermes-gate` commands/package/imports remain. `kwik-gate` aliases the same
  engine. New profiles set `review_required=false`; old omitted policy stays strict.
  Hooks/installer source respect repository policy. No global hooks/settings changed.
- Native command detection no longer assumes Jest-only flags or lint file arguments.
  Initialization explicitly selects native checks or the installed Quick Gate adapter;
  adapter argv uses `npx --no-install` and never silently downloads npm tools.
- The real Python→JS adapter normalizes repository paths, manifest/config inputs,
  Unicode sorting and newline filenames. An immutable compatible JS checkout is used
  by an added CI contract test. Shared `gate-result/v1` schema bytes are unchanged. PyGate initialization uses an
  installed `pygate`, respects Python snapshot encoding, and has a matching real
  pass/fail Unicode/newline roundtrip. Neither adapter is automatically installed.
- The core Action now defaults to receipt-producing run (auto mode), exposes status
  and receipt-path, and preserves explicit legacy commands. Generated CI runs full and
  uploads exported evidence even after failure.
- JS remains a standalone npm CLI/API. Repair defaults to deterministic behavior;
  `--model-assisted` / `deterministicOnly:false` explicitly enables local Ollama.
  All-skipped evaluations fail, and unsafe-shell policy participates in config identity.
- Main README, configuration/migration docs, portable skills, llms.txt, changelogs and
  package/plugin metadata explain the same product. Historical trial/review code remains
  outside the canonical run path. Existing semantic review extensions remain optional.

### Practical limits

Receipts bind included tracked/unignored bytes, execution bits, HEAD, declared contract,
executable/interpreter identity and core implementation. They do not bind excluded or
ignored dependency trees, environment-variable values, remote services or a hermetic
runtime. Users choose deterministic project commands and declare exclusions consciously.
A locally editable receipt is not a signed security attestation. No claim of semantic
correctness, cross-machine portability or Windows process isolation is made.

## Migration / release

Concrete instructions are in [docs/MIGRATION.md](docs/MIGRATION.md), with the contract
in [docs/CONFIGURATION.md](docs/CONFIGURATION.md). Integrated source versions are
`hermes-gate` 0.4.0 and `quick-gate` 0.4.0. Package names and
schemas remain stable, old receipts are regenerated, and model repair opt-in is explicit.
The combined repository's tag push triggers npm publication; GitHub release publication
triggers PyPI. Follow the actual coordinated event sequence in MIGRATION.md, rather than
the earlier separate-repository core-first idea. Run identity guards and install/read
back published artifacts. No 0.4.0 tag or registry publication was performed by this work.

The canonical source is the public `hermes-labs-ai/quick-gate-js` main branch at
merge commit `d312dd2b803dddc0af8f4546f950c31911001319`. The isolated worktree
and sibling core candidate remain historical comparisons; the Python-adapter worktree
contains role documentation, not another engine. Original checkouts and unrelated
state were preserved. Independently owned core/PyGate pull requests were not
incorporated or overwritten.

## Public identity and redirects: final due diligence

Decision question, refined by the owner: can the existing five-star Quick Gate JS
repository become the canonical KWIK-E-GATE home while preserving the already-built
architecture and existing consumers? Evidence as of 2026-09-29. Initial research:
six official-page cap, four opens and three live GitHub metadata queries. Refinement:
two official-page cap, one open (GitHub rename documentation), plus local Action and
release-tag inspection. No public identity mutation was performed.

Live GitHub: `quick-gate-js` has 5 stars, `hermes-gate` 3 (and 1 fork),
`quick-gate-python` 0. **Choose the existing five-star repository as the product home
and rebrand it KWIK-E-GATE.** Its current JS name does not constrain the architecture
or language of the source it can host. Preserve that repository's identity and stars;
do not create a fresh canonical repository and expect stars to transfer to it.

### Corrected recommendation

The completed dependency-free Python engine remains the receipt/routing authority.
The npm and PyGate surfaces remain optional, independently installable adapters.
Move the necessary product source, docs and publishing surfaces into the selected
product home through a tested placement cutover. This does not require rewriting the
engine, making Node mandatory, or renaming packages. The selected Quick Gate JS worktree now contains the core source and adapter.
The old core worktree is preserved for comparison; no public rename has happened.
Keep ownership in `hermes-labs-ai`; no personal GitHub redirect repository is needed.

| Surface | Concrete migration |
| --- | --- |
| Product title/artwork/docs | KWIK-E-GATE; canonical workflow is plan → run → verify |
| Canonical product repository | Rebrand the existing `hermes-labs-ai/quick-gate-js` identity as KWIK-E-GATE; preserve its stars/history |
| Existing Hermes Gate repo | Preserve historical releases and working Action references; migrate core maintenance to the product home after verified cutover |
| JS package | Keep it an optional adapter regardless of the product repository's name |
| Python adapter repo | Keep `quick-gate-python` / PyGate role |
| npm install/import/bin | Keep `quick-gate`, existing exports, CLI arguments and result schema |
| PyPI install/import/bin | Keep `hermes-gate` / `hermes_gate` / `hermes-gate`; add `kwik-gate` alias in that same distribution |
| PyGate package/interface | Keep `pygate-ci`, `pygate` and native API |
| Existing Action references | Preserve working old paths, historical tags and commit pins before a literal URL rename |
| Personal GitHub account | No transfer, redirect shell or duplicate core |

Maintenance remains factored: receipt/routing changes in one core; tool-output
normalization in each adapter. Historical Action compatibility surfaces must not grow
independent copies of the receipt engine. Repository placement can change while the
runtime and package architecture stays the same.

### What a rename actually guarantees

GitHub documents that a rename carries stars and redirects web/Git traffic, but
**calls to an Action hosted in a renamed repository do not redirect**. Both original
repositories expose public Actions. Renaming either can break existing workflows even
when their normal repository links and Git remotes still work. Recreating the old
repository name also ends its automatic redirect.
Source: [GitHub repository rename documentation](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository).

An organization-to-personal transfer adds ownership/access changes and does not solve
package/interface migration. GitHub also warns that recreating the previous location
removes transfer redirects. Source:
[GitHub transfer documentation](https://docs.github.com/en/repositories/creating-and-managing-repositories/transferring-a-repository).

GitHub redirects do not change what `npm install quick-gate`, imports, CLI calls or
PyPI dependencies request. Preserve those package contracts directly. If a future
new package identity is justified, provide a tested compatible implementation/wrapper
under the old name before encouraging migration. A deprecation notice only prints an
install warning; it does not perform migration. npm recommends deprecation over
unpublishing to avoid removing packages depended on by users. No deprecation is
needed while `quick-gate` remains a supported adapter. Source:
[npm deprecation documentation](https://docs.npmjs.com/deprecating-and-undeprecating-packages-or-package-versions/).

### Rebranding and literal URL rename sequence

1. Stage the product in the existing five-star repository. Keep its existing JS Action
   and npm interfaces working during the transition; expose the core Action separately
   rather than replacing an existing interface with incompatible inputs/outputs.
2. Verify package builds, source/plugin parity, Action consumers and publishing identity
   after placement. Review the consolidation before release; old local validation does
   not prove a changed source layout or publishing configuration.
3. Rebrand product title/docs immediately in the candidate. A literal `kwik-e-gate`
   slug is a separate public cutover after Action compatibility is implemented.
4. If renaming the five-star repository, preserve or reconstruct a working old
   `hermes-labs-ai/quick-gate-js` Action surface with its historical revisions. Reusing
   that old name cancels GitHub's automatic redirect: ordinary old links/remotes then
   reach the compatibility repository, which must clearly point to the product home.
   This tradeoff must be explicit. A README-only shell does not protect Action users.
5. Keep the old Hermes Gate Action path and package distributions working. Update
   package metadata, plugin sources, release links and repository-bound publishing
   configuration to the verified product home without moving historical release tags.

GitHub's documented default for Actions is a new repository/action with the old one
preserved. That default would not carry the five-star identity to a new repository;
the proposed rename plus old-path compatibility is a migration design that still needs
an actual end-to-end consumer test. Confidence is high that repository identity can
carry the product independently of architecture. Compatibility of that public cutover
is not yet established. Stars from independent repositories are not being combined.

## Validation

| Check | Observed result |
| --- | --- |
| Core baseline | 333 passed, Python 3.11.15, 50.9s |
| Core final full gate | PASS, Ruff and all 382 tests, 86.8s including binding/version overhead |
| JS baseline | 92 passed, 33.1s |
| JS final full gate | PASS, repository integrity and all 95 tests, Node 24.19.0, 31.1s |
| PyGate unchanged runtime | 196 passed, 5 integration tests deselected, 24.19s |
| Real Python/JS adapter roundtrips | PASS and FAIL correctly normalized; Unicode/newline inputs proved |
| Core / JS / PyGate fast gates | PASS, including scoped instruction scanner |
| Core build/release identity guard | Wheel + sdist built; v0.2.0 artifact identity PASS |
| Isolated core wheel | Python 3.14.3, installed --no-deps; only Python/Git PATH; init, plan, auto fast/full, export and verify PASS; failed syntax leaves FAIL receipt |
| Composite Action run step | Real Bash execution: correct exit/status/receipt-path for PASS and FAIL |
| npm lint/pack/fresh install | PASS, 0.4.0 tarball; actual CLI/API exports pass and fail correctly on Node 24 |
| Canonical schemas | Byte-identical to public main; all three gate-result/v1 copies match |
| Bug demo capture | Original FAIL, corrected PASS, identical fixture/diff digest; trace saved in docs/demo |
| JS bounded independent review | CodeRabbit PASS, no material findings, 168.7s |
| Core bounded independent review | REVIEW_UNAVAILABLE: selected diff exceeds provider's 128 KiB limit |

The five deselected PyGate tests were not run as a new complete upstream integration
suite; its runtime was not changed. Core integration directly executes the real PyGate
CLI, not a mocked adapter. The Node 18/22 CI matrix is retained for compatibility;
local final runtime evidence is Node 24, not a claim that every platform was tested.

The configured core reviewer returned unavailable with the exact stderr:
`review unavailable: selected diff empty or over 128 KiB limit`. The diff is nonempty;
this consolidation exceeds the provider's bound. An earlier native Claude alternative
also refused workspace trust before starting. Neither attempt is review evidence and
no trust/account setting was changed. The JS CodeRabbit review did complete. Core
independent review remains required before integration/public release; strict receipt
policy has not been weakened to manufacture PASS.

Evidence is local, tested and uncommitted. No commits/pushes/PRs/tags, publication,
repository deletion or unpublishing have occurred. Final documentation/demo saves
followed runtime validation; they do not imply fresh matching boundary receipts.
Any commit/push/PR must rerun the configured exact-state receipt gates.

## Owner decisions

The architecture remains selected. The owner corrected the identity decision: carry
the existing five-star Quick Gate JS repository forward as the KWIK-E-GATE product
home. Package names and runtime factoring remain stable. Source placement is implemented;
public Action compatibility and literal URL cutover remain unproven.
No additional architecture question is being sent to the owner.

Subscription-backed Claude review is now available without a trust/account change.
Its source PASS covered the preceding staged candidate, with publication HOLD and
coverage limits. The new maintainer collaborator is reviewing the fixes in historical
context. Configured CodeRabbit review has now returned PASS for staged tree
`1f09ced23cc1484ec9f76ab18c2b17607590878a` (195.940 seconds, no material findings).
This supersedes the earlier timeout/rate-limit entries below. Additional profile/docs
changes require matching receipts at a future commit/push/PR boundary.
Publisher identity bindings and Action-safe cutover
are release requirements to resolve concretely before any owner-only approval.

The requested bug/trace has been preserved for the future stylized demo image. Its
visual brief is grounded in the captured replay; no image or public asset was generated.

## Consolidated source placement — 0.4.0

The owner supplied the exact README header, specified the lowercase repository name
`kwik-e-gate`, and chose a higher consolidated version. Use **0.4.0** for both the core
PyPI distribution and npm adapter. This avoids the pre-existing JS `v0.2.0` tag without
moving historical tags or requiring separate tag namespaces for this release.

The existing `quick-gate-js-kwik` worktree is now the canonical implementation candidate:
`src/hermes_gate/` and `tests/` hold the core; `src/*.js` and `test/` hold the JS adapter.
Setuptools selects only `hermes_gate*`; npm selects only JS files, schema JSON and its
small documentation assets. Installing either package does not install the other.
PyGate remains the compatible external adapter, exercised by real integration tests.

The existing root and nested JS Actions remain intact. The new
`.github/actions/kwik-e-gate` Action uses its pinned core source in isolated Python,
with no pip/build/package download. Its real tests cover PASS, failed checks, invalid
mode, missing profile, external receipt output and resistance to project import
shadowing. A legacy Hermes Action/guard snapshot under `compat/hermes-gate` preserves
historical interface regression coverage; it is not a second maintained engine.

The supplied header is saved byte-for-byte at `docs/assets/kwik-e-gate-header.jpg` and
used at the top of README.md. The scanner bug/trace remains in `docs/demo/`. No image
editing or public upload was performed.

Previous validation above applies to the earlier separate-worktree candidates. This
placement requires fresh combined validation before readiness is claimed. Remaining
work includes independent review, five concrete project/CI admission proofs, package
publisher repository binding, and the Action-safe public identity cutover. The goal
remains active; local placement does not establish public release or external adoption.

### Placement validation and correction

- 0.4.0 wheel/sdist built; release identity guard PASS.
- npm 0.4.0 tarball built: 27 files, 120,144 bytes, no Python payload.
- Fresh Python 3.14.3 wheel install with no dependencies/Node PATH: version, plan,
  run, export and verify PASS; bad syntax gives FAIL plus a receipt.
- Fresh npm install: existing CLI and evaluateGates/runCommand exports work without
  Python; native command success/failure codes preserved.
- Initial combined full run: JS 95/95 PASS; Python exceeded its old 180-second limit.
  Diagnostic Python run: 385 passed, one failure (omitted generated workflow), 251.79s.
  Restored the actual polyglot generated workflow; its targeted regression now PASS.
  Python full timeout is 360 seconds, with fast budget unchanged.
- Ruff, diff whitespace and workflow YAML parse checks PASS. Final combined full and
  independent review are being rebound to this corrected placement.

All of these are local results. Public source integration/rename/publication and the
five project admission proofs are still pending; none is implied by package builds.

### Git discovery bound and final review

The corrected placement full gate passed on 2026-09-29: 386 Python tests and 95 JS
tests, Ruff and Git integrity, 190.172 seconds total. Its bounded CodeRabbit review
timed out at 180 seconds before a verdict; partial output contained status/heartbeat
events, no completed review. This is not independent acceptance.

A separate local `git status --short` query stalled in the optional filesystem monitor;
a process-level `core.fsmonitor=false` query returned normally. Inspection found the
core's own Git metadata queries had no timeout. They now disable that optional monitor
per command (no user config change), have a 10-second cap, and raise GitError on timeout
even for normally optional queries. A real sleeping-Git regression proves a terminal
FAIL and saved receipt, rather than interpreting a timeout as an unborn/unchanged repo.
The core/plugin Git helper bytes match. The focused timeout/Action/plugin suite passed
14 tests. These code changes require a fresh full gate and review; earlier PASS applies
to the preceding revision. The maintainer review timeout is now bounded at 600 seconds
for the larger consolidated source; severity/category policy is unchanged.

The existing JS `demo/` ignore rule hid the copied `docs/demo` archive from Git. Scoped
negations now admit the requested scanner bug/trace while keeping generated demos
ignored. Both replay artifacts are staged with the product, alongside the supplied
header. No commit, push, repository rename, package release or external CI submission
has occurred. The active goal still includes five concrete project admission proofs.

### Latest verified 0.4.0 state

After the Git discovery fix, the combined full gate is **PASS**: Ruff, repository
integrity, **388 Python tests and 95 JS tests**, 106.027 seconds total. The final
wheel/sdist release identity guard is PASS. The rebuilt wheel works in a fresh
Python 3.14.3 environment with zero runtime dependencies and no Node PATH: plan,
run, external receipt export and verify PASS; bad syntax produces FAIL and a saved
receipt. The npm 0.4.0 tarball/API independence proof remains valid; its JS payload
was not changed by the Git fix.

The last independent review attempt returned **REVIEW_UNAVAILABLE** with the provider
event `Rate limit exceeded`. No complete review or PASS is claimed. Do not retry the
same unavailable service blindly or substitute an API-spend fallback. Next work is
an available independent review route and five concrete project/CI admission proofs.
Publisher binding and compatibility-safe rename remain separate public effects.

The canonical product candidate and source of truth now live in the selected
`quick-gate-js-kwik` worktree. The old core worktree remains a preserved comparison,
not the delivery source. Changes are staged but uncommitted. No push, PR, tag, public
rename or package publication was performed. This results note followed runtime
validation; exact boundary receipts must be regenerated before a commit/push/PR.

### Maintainer-guided corrections and first CI proof

Native subscription-backed Claude session `10265b42-a69e-4ad7-94cd-b9bd4d227d40`
returned source PASS for staged tree `ed3206d17409cccb88f28e4f4f77c2ffb34cb23c`, with
publication HOLD and explicit review limits. No trust/account change was needed.
This supersedes unavailable native-launch evidence, not the configured CodeRabbit
failure. The following changes postdate that reviewed tree and need fresh acceptance.

The new Action now emits bootstrap FAIL evidence for unsupported Python/core loading;
its small runner can execute on Python 3.10 solely to report that failure. The maintainer
caught installed-package fallback through a missing initializer and symlink-loop errors
inside failure handling. Source presence and imported module origin are now checked;
those failures cannot become a reusable PASS. Nine Action tests pass, including missing
core/initializer, invalid paths and unavailable export. A real Python 3.10 launch also
produced FAIL, a matching export and status/path outputs. Platform setup failures before
the runner starts remain outside this guarantee.

Generated/core release Actions are SHA-pinned; generator/plugin bytes match, release
checkout credentials are disabled and build/PyYAML pins align. The historical Hermes
Action is now the exact public 0.1.7 snapshot, with provenance and 48 offline compatibility
tests passing. It is not a live replacement for the old public repository. JS default
Node 20→24 and new Action `mode` vs historical `command` are documented. The moved JS
guide's links and actual npm-tag/PyPI-release event sequence are corrected.

The first actual upstream consumer proof is complete: MCP Python's native lint, format,
Linux-targeted type check and test/coverage script passed through the source Action in
35,563 ms. The exported PASS verified; source mutation made it stale, a bad-source run
issued FAIL, and restoring bytes restored verification. See [CI admission](docs/CI-ADMISSION.md)
for exact snapshot, native results, intake restrictions and the other four pending proofs.
This is technical compatibility, not upstream approval or adoption. Research is at
17/30 external opens. Public integration/rename/publisher binding remain unresolved.

The maintainer collaborator accepted this local correction packet as PASS after reviewing
15 changed tracked files and three new artifacts against staged tree `ed3206d17409cccb88f28e4f4f77c2ffb34cb23c`.
Its remaining wording clarification is incorporated: the Action itself installs no tools;
native declared commands retain their own dependency/network behavior. This is local
acceptance, not a configured Gate review receipt, publisher approval or upstream adoption.

The corrected product full gate passed in 166.136 seconds: **393 Python tests**, **95 JS
tests**, Ruff and Git integrity. Rebuilt wheel/sdist identity passed; the installed rebuilt
wheel has the pinned generator, validates a PASS, rejects mutation and exports a FAIL
for bad source. These results apply to the completed code packet before this final
documentation update. No unchanged suites are being rerun for this results note; exact
receipts must be regenerated at any future commit/push/PR boundary. Nothing is published.

### Native consumer scope challenges

The maintainer collaborator's history/consumer review now drives the remaining
admission profiles. All five profiles retain repository-owned checks and add no
runtime dependency to the SDKs/agents. Their dependency preparation is explicit;
core execution does not acquire tools or call a model. See [CI admission](docs/CI-ADMISSION.md)
for exact snapshots, commands, measured results and intake limits.

Pydantic AI reserves broad local type/test/coverage runs for CI. Its local profile
therefore declares scoped offline agent behavior and TestModel lint/format/types:
442 tests pass, two skip, source mutation invalidates the receipt and a bad-source
run exports FAIL. Its four directory skill aliases initially failed binding correctly.
Only those reviewed alias objects are excluded; canonical target files remain bound.
Directory-symlink support would need membership/content, retargeting, containment and
cycle handling. Do not weaken the existing rule or broadly ignore agent metadata.

Hermes Agent uses eight existing blocking portable-contract guards, all PASS with
stale/bad-source/restore probes. Preserve its historical YAML comments, real OS lanes,
profile boundaries and lazy-install isolation. Its expensive behavior/matrix lanes
are explicitly outside this profile. Its third-party integration policy points to
an independently maintained example, with existing PR #107124 kept separate.

MCP TypeScript's native checks/docs/build/distribution types/unit stages pass. E2E
reports passing test cases plus an unhandled 200 ms request timeout; the Action issues
FAIL. An isolated native protocol-test invocation reproduces the error without Gate.
This is useful failure evidence, not five-project all-green readiness. No suppression,
removed check or patched SDK was used to manufacture a passing result.

pipx's first full run exposes host-hook interference in its disposable VCS fixture.
Its failing case passes with process-scoped fixture Git settings passed through tox;
native pre-commit, ty, cache and full-suite stages stay enabled. The isolated full
rerun passes (1,140 tests, 12 skips, one xpass). A further maintainer challenge exposed
old-wheel reuse after a local source edit: a broken-source probe still passed with
`--skip-pkg-install` and failed when native tox rebuilt the package. The final profile
now rebuilds/reinstalls the current wheel and editable packages; validation of that
contract passes in 226,204 ms (1,140 tests, 12 skips, one xpass, 94% reported coverage),
with fresh build/reinstall logs and stale/bad-source/restore probes. Build inputs
remain bound, generated outputs remain excluded.
No user Git configuration, global hook or upstream source was permanently changed.

These findings reinforce the architecture: selection, declared check coverage,
workload binding and actual process success are distinct. A `full` run executes the
whole declared profile; it does not infer every upstream matrix job or prove correctness.
Regression mindfulness requires preserving a justified FAIL as well as a justified PASS.

The maintainer accepted the four added profiles as a bounded local integration packet,
and confirmed the pipx source/package correction against native tox implementation.
These are independent source/consumer reviews, not a configured release receipt or
upstream approval. All five profiles now have local execution evidence; the active
goal's all-green/admission and public distribution requirements remain open.

### Final readiness selection and historical review

Do not turn MCP TypeScript's reproduced native E2E timeout into a passing profile
by removing the failing stage. Retain it as a sixth failure example. The five scoped
readiness proofs are MCP Python, Pydantic AI, Hermes Agent, pipx and PyPA packaging.
The sixth repository expands selection research to 21/30 official-source opens;
no upstream submission or approval is implied.

Packaging retains native Nox lint/hooks/distribution build and CPython 3.14 tests/
100% branch coverage. The maintainer found Nox's default runtime acquisition: both
stages now prohibit Python downloads and fail if a prepared interpreter is missing.
Current-source editable installs remain enabled. Frozen-tag verification needs
network; matrix, property, downstream, old-pickle and docs checks stay explicitly
outside the profile. Native output truncation is recorded, not used to infer counts.
The exact final profile passed in 26,669 ms, with export/output parity, source-staleness,
bad-source FAIL and byte-restoration PASS proofs. Source and lock state are preserved.

These corrections exercise regression mindfulness in actual consumers: preserve the
source/package relationship, distinguish native policies from host setup, retain a
justified FAIL, and state evidence limits. CodeRabbit also returned PASS for the
completed consolidation tree noted above. Neither a model review nor a local native
proof grants upstream approval or permission for an identity/account change.

The requested deliverable is the unreleased, reviewable 0.4.0 implementation and its
migration/release route. Public adoption, registry publication and repository rename
are not claims of this local completion. A reviewed public source pin, publisher
bindings and working old-path Action consumers must be verified at those boundaries.

The maintainer accepted the final packaging profile, README and CI admission notes
as a bounded local packet: executed/canonical profile parity, both prepared-interpreter
requirements, all native hooks/installs, the 26.669-second PASS, receipt mutation/failure/
restoration evidence and 100% native branch coverage are directly evidenced. No material
issue remains in that packet. Root delivery remains local and uncommitted; the exact
fast receipt and final wheel/sdist/npm artifacts live outside the checked source.

### Public source integration packet

Live `quick-gate-js` main advanced to `6b2bf80645ed9246dd34bb64b84ba83d88d3cbae`
through documentation PRs #42/#43. The unpublished branch now starts from that tip,
preserving both commits and the staged consolidation. Their substantive corrections
survive: adapters emit diagnostics, composition is optional, package/command interfaces
remain compatible, missing adapters cannot pass, and deterministic normalization does
not promise early termination. The former three-product/repository positioning is
superseded by this product decision; its task-reset instruction does not override the
owner's current continuity mandate.

The native JS agent skill was still describing old repair defaults, an incorrect
changed-files invocation and worktree artifact paths. It now gives the current adapter
contract and links to maintained details. Its license is Apache-2.0; its frontmatter
passes the Codex skill validator. Zenodo title/description now match the product
without asserting a publication. The misleading `fail-fast` keyword is removed.

The generated quality rail retains byte parity with the workflow generator: adopted
consumer repositories do not contain this repository's local Action. A proposed direct
replacement failed the existing parity test and was reverted. The separate existing
`core.yml` full-receipt job already exercises the advertised source Action with both
real adapters and uploads its actual receipt path under `if: always()`. Its next consumer
is this repository's consolidation PR. Main's required Node 20 check is retained alongside
Node 18/22/24 so compatibility readiness does not leave a required check absent.
Hosted results are still unproved. The local commit boundary requires matching fast
evidence and completed-diff review; public push/PR boundaries additionally require
configured full/review receipts for the committed HEAD. HEAD changes invalidate prior
receipts, so those public-boundary checks run again after commit. No tag, package release, rename or publisher-account change
is part of this packet.

#### Committed review correction: timing and Git context

The first local consolidation commit is `9dc91c8b67f55dc968f1f843c6fcf472fee7df27`.
Its fresh full receipt passed (393 Python / 95 JS tests; 103.647 seconds), but the
committed-diff review returned two material findings through the existing
`hermes-pr-review` fallback: `time git commit` escaped detection, and explicit
`--git-dir`/`--work-tree` selection from a non-Git cwd lost the target repository.
That review is FAIL, not CodeRabbit acceptance. It blocks the public boundary.
The before trace is `/tmp/kwik-hook-context-before.json`; no actual commit was
executed in that reproduction. New tests failed against the old implementation.

The correction recognizes timing wrappers, preserves literal Git globals and resolves
them through the existing bounded native Git helper. It compares both canonical
toplevel and absolute Git directory against independent normal worktree discovery;
a receipt for different metadata or a subdirectory worktree cannot license the
selected command. Linked worktrees, `.git` files, harmless assignments and the
never-adopted exemption survive. Inherited repository/index overrides and explicit
namespaces are denied. Native Git rejects joined `-Cpath`/`-ckey=value` on this host;
preserving their literal argv means denial, not invented support.

The maintainer's historical constraint is that a receipt for the caller's checkout
cannot license an action targeting another checkout. This fix preserves the parser's
bounded role; preceding `cd`, command-local repository/index assignments, arbitrary
expansion and multiple target repositories are outside its supported context.
Integration documentation and plugin wording now name that scope. The focused parser/
hook tests pass (65 cases). Fresh complete-diff review and committed-HEAD receipts
are still required before push; the earlier successful full run does not cover this
correction.

The maintainer then identified the supported Python 3.11/3.12 `Path.resolve()`
symlink-loop `RuntimeError`, and the actual plugin/Codex five-second PreToolUse
transport versus ten seconds per Git query. Path/boundary errors now return denial.
All PreToolUse metadata queries share a three-second context-local deadline; ordinary
CLI queries keep their ten-second limit. The existing installed hook definitions and
their ownership/removal recognition stay compatible. Plugin entry-point tests exercise
both one stalled Git process and cumulative slow queries under its actual host timeout,
without a pip install. Both manifest descriptions remain synchronized. These are
historical consumer constraints, not reasons to broaden the shell interpreter.
The maintainer accepted this bounded local correction after those fixes, with no
remaining material finding. Its read-only acceptance does not substitute for the
configured committed-diff review or public-boundary receipts. The uncommitted
CodeRabbit attempt was rate-limited and recorded REVIEW_UNAVAILABLE.

### Final implementation validation and integration route

Correction commit `9d2b6d7a0bb82905496613fb0ecb224fa1108ea0` passed fresh fast
(0.838 seconds), full (108.606 seconds; 420 Python / 95 JS tests), and the configured
CodeRabbit committed-diff review (250.002 seconds; no material findings). Its correction
commit boundary passed with matching fast evidence and completed maintainer review.
The rebuilt 0.4.0 core wheel/sdist identity guard passed. The independent npm archive
is still 27 files and has unchanged integrity, confirming that Python core changes do
not drag a runtime into the JS package. The failed no-isolation build attempt lacked
the declared setuptools build backend; the normal isolated build succeeded without
adding a runtime dependency or changing the test environment.

The next concrete consumer is the consolidation PR in the existing
`hermes-labs-ai/quick-gate-js` repository. The final documentation commit requires fresh
committed-HEAD fast/full/review and public-boundary validation before its ordinary
branch push. Its PR records the immutable public source pin, terminal validation and
hosted check results; that live PR is authoritative for integration status. No source
change after those receipts is accepted implicitly. This implements a reviewable
0.4.0 candidate, not a tag, registry upload or repository rename.

The five-project admission packet is ready at the documented native scopes: MCP Python,
Pydantic AI, Hermes Agent, pipx and PyPA packaging. Each includes a PASS, receipt
verification, actual-source staleness/failure and restoration probes, plus contribution
intake constraints. MCP TypeScript remains a sixth honest FAIL. These are local
integration proofs, not upstream approval or evidence that an unrun matrix passed.

Remaining owner decisions concern external cutover: approve repository-bound publisher
rebinding/release when source acceptance is complete; select the old Actions compatibility
cutover before a literal lowercase `kwik-e-gate` rename; and supply human accountability/
issue alignment where an upstream project's intake requires it. Package/API names and
historical tags stay compatible. No additional architecture decision is needed.

### Hosted Python 3.14 bootstrap correction

The consolidation is public as PR #44 in the existing product repository. At initial
head `b6986b8a9d2b074c741537b5a71694b92db2fbe0`, hosted Node 18/20/22/24,
Python 3.11, generated quality rail and real-adapter full-receipt jobs passed.
The Python 3.14 job exposed a platform assumption in bootstrap export: non-strict
`Path.resolve()` can return an unresolved symlink loop instead of raising. The
existing regression correctly held the integration. The failure was reproduced
locally with Python 3.14.7; the test is retained rather than relaxed by version.

Bootstrap now requires strict resolution of an existing working directory before
proving that an export is outside it. Missing and regular-file working directories
have dedicated failure cases. Valid directory symlinks continue to resolve, and the
new receipt path remains non-strict because it does not exist yet. If storage cannot
be established, stdout still contains the FAIL receipt and the Action exports an
empty receipt path. No reusable binding or checked PASS can arise from bootstrap
failure. The maintainer accepted this invariant; final patch/hosted acceptance is
still required.

All five consumer profiles were refreshed with this core and verified, including new
actual-source staleness/native FAIL/exact-restoration probes; tracked consumer source
is unchanged. This Action-only correction leaves their core/profile/tool bindings
unchanged. Their local results do not imply upstream approval.

Hosted CodeRabbit's SUCCESS is explicitly a skipped review (automatic review disabled
in organization settings). Sourcery's terminal SKIPPED/COMMENTED result states that it
cannot fetch a diff over 20,000 lines. Neither is technical review acceptance. Exact
configured local CodeRabbit reviews and independent maintainer/steward acceptance are
recorded separately; settings and reviewer findings are not suppressed for integration.
The maintainer accepted the actual three-file correction with no material finding.
All 12 source Action cases pass locally on both Python 3.11.15 and 3.14.7, including
the retained loop regression, new invalid-directory cases and valid directory alias.
The final public head still needs fresh configured receipts and hosted checks.

### Raw review evidence correction: temporary storage and classification

At local head `fe5e689e2993375a99969f671bf4db572bdba9a8`, CodeRabbit's completed
retry normalized to PASS but contained one suppressed **major** finding. Inspecting
the raw event established a real bootstrap bug: `os.environ.get` eagerly evaluated
`tempfile.gettempdir()` before the failure handler, even with valid `RUNNER_TEMP`.
A broken system temporary directory could therefore prevent any receipt. The prior
PASS and maintainer acceptance do not license this newly discovered failure.

The normalizer already read `codegenInstructions`; its keyword classifier returned
`other` and silently suppressed this uncategorized major finding. The actual finding
is preserved in `tests/fixtures/coderabbit_unclassified_major.json`. Selected-severity
unknown findings now remain visible as `unclassified` and block acceptance. Recognized
material categories still follow the configured policy; explicit style/documentation
suppression and the typed JSONL contract survive. The bundled plugin stays byte-identical.

Action export selection is now lazy and inside the bootstrap handler. No export path
exists until selection succeeds. A failure to discover a system temp directory emits
stdout FAIL and an empty Action receipt path without retrying discovery; a valid
`RUNNER_TEMP` never consults the broken fallback. Four new regressions failed before
the patch. Focused Action/provider/plugin cases passed on Python 3.11, and Action/provider
cases passed on Python 3.14. Fresh completed-diff review and boundary receipts remain
required after the correction.

The maintainer explicitly caught the provenance consequence: `providers.py` enters
every executing-core binding. The five prior consumer receipts become historical
evidence even though those checks never invoke semantic review. Refresh all five
before claiming current-core verification; no weakened binding or relabeled receipt
can substitute. This is regression mindfulness applied to review evidence itself.

### Forced-install physical path correction

The next completed-diff review at `39941b8ef082f16d5ba9301c74c740296057bb21`
returned a material correctness FAIL through the existing `hermes-pr-review` fallback:
`init --force` followed an existing symlinked integration file and overwrote bytes
outside the checkout. The same path existed in rollback/uninstall restoration. This
review is **FAIL**, despite the local full gate passing, and no public push occurred.

Before patching, ten focused tests reproduced actual unsafe behavior: three external
leaf aliases during force-init, three during uninstall even with matching installed
hashes, an external parent alias during uninstall, a symlinked backup destination,
a traversal key in the install manifest and an external legacy-manifest parent. All
had returned success instead of parking or rejecting. Internal file aliases were
historically supported and remain so; rejecting every symlink would regress a real
contract. Linked worktree Git directories may legitimately live outside the checkout.

Initialization now checks every physical integration target before backup/write and
every backup destination against its canonical Git directory. Rollback rechecks both
surfaces before restoration. Uninstall validates every allowed manifest key, target,
backup source and legacy manifest location before the first restore/remove. Static
external, dangling, looping and non-file targets park, preserving the repository and
external bytes. In-repository regular-file aliases and linked worktrees still pass.
The core and plugin copies are synchronized. Targeted init/uninstall tests pass;
fresh full gate, configured review, five current-core consumer receipts and hosted
validation remain required before integration. This is an explicit physical-path
preflight, not a claim of protection from a concurrently hostile filesystem.

The maintainer's subsequent review caught two gaps in that first correction: an
empty-backup install still wrote state through an aliased Git metadata directory,
and uninstall treated backups as optional despite their recorded digests. Four more
tests failed the first correction: outside metadata alias, missing backup, changed
backup and unrecorded backup all returned success. State placement is now checked
before any install write and before manifest/runner readback; promised backups must
be present and byte-identical, and unrecorded backups park uninstall. A linked
worktree's actual Git directory remains the allowed metadata root. The expanded
targeted init/plugin suite and Ruff pass; the maintainer's exact-patch acceptance
and final committed/public receipts still follow.

The next maintainer pass found two more zero-existing-target paths. A symlinked
`baseline.json` allowed a fresh install to overwrite an outside file, and an
outside `install-backup` directory alias allowed a misleading PASS that could not
later uninstall. Both were reproduced by failing tests before correction. The
state preflight now covers both state files and the backup root plus all known
backup destinations, even when nothing needs backing up. The expanded focused
init/plugin suite passes on Python 3.11; final independent acceptance, committed
receipts and hosted checks still govern integration.

The last restore review exposed two inherited witness-loss paths. A truncated v1
manifest could uninstall only a subset of the three generated files, delete the
manifest and report PASS. A second `init --force` over an enrolled repo replaced
the original owner backup with generated bytes; later uninstall reported PASS while
leaving generated files. Both were reproduced by failing tests. Public v1 source
always wrote exactly three file keys, so exact-key validation preserves its contract.
An existing current or legacy install manifest now parks repeat force-init before
rewriting backups; first force over user-owned files still works. Uninstall first only
when the installed bytes still match, otherwise resolve edits manually. The focused
init/plugin suite passes; exact-source review and final receipts remain required.

The stricter unrecorded-backup rule exposed a two-install lifecycle regression:
successful uninstall retained its obsolete backup, so a later fresh install could
pass yet become impossible to uninstall. Two tests first reproduced this sequence
and an orphaned backup with no owner target. Successful uninstall now removes only
its validated recorded backup copies after restoring owner files and revoking the
manifest. Fresh initialization inspects all known backup destinations. It may reuse
leftover bytes from an older install or interrupted rollback only if the current
owner file exists and matches exactly; an orphan or mismatch parks before mutation.
A matching-backup acceptance test covers retry compatibility. The focused suite now
passes 49 init/plugin cases on Python 3.11, 39 init cases on Python 3.14, and Ruff;
the exact-source review and final committed/public receipts remain outstanding.

### Consolidation verification before public update

Commit `2a3a79c87aecd6571955882288f60c4c3988dee7` includes the complete
physical-path and reversible-install correction. The independent maintainer
accepted its exact local patch. The root Gate fast and full receipts passed;
full ran 452 Python and 95 JavaScript tests. The configured `hermes-pr-review`
fallback returned a validated PASS with zero findings on that commit. Its
result is distinct from the earlier `fe5e689` CodeRabbit PASS whose raw major
finding was suppressed, and from CodeRabbit's skipped public automatic review.

The 0.4.0 wheel and sdist built from `2a3a79c`; the release identity guard passed.
A clean Python 3.14.3 wheel install with no Node on PATH and no mandatory runtime
dependencies produced `plan` PLANNED, `run` PASS with an exported receipt, and
`verify` PASS. A source mutation made verification FAIL and `run` issue a FAIL
receipt; restoring bytes made the original exported receipt verify again.

Five scoped native Action runs using that same source passed and exported locally
verifiable receipts: MCP Python, PydanticAI, Hermes Agent, pipx, and PyPA Packaging.
For each, mutating actual checked source made the prior receipt stale and a fresh
fast run FAIL with a receipt; restoration made the prior receipt verify again.
Tracked consumer source remained unchanged at the end. These are scoped local
CI-admission proofs, not upstream CI approvals. The MCP TypeScript E2E failure
remains openly recorded in the admission packet.

This evidence binds `2a3a79c`. The plan update itself changes tracked input bytes,
so exact-source receipts must be refreshed after this documentation commit before
push and PR readiness. The final public head and hosted checks govern integration.

### Claude hook host-interpreter correction

The completed-diff fallback review of the plan-only `cb6f125` head found one
material plugin reliability path. The Claude manifest invokes unversioned `python3`,
which can be older than the bundled core's Python 3.11 minimum. A portable
regression simulated Python 3.9 at the entry point and reproduced a non-JSON exit
from the runner import before the hook could issue its fail-open response. That test
failed before correction. The hook now checks the interpreter before importing
the bundled runtime and returns `{"continue": true}` on older hosts. The real
system Python 3.9 also returns this response. All 11 plugin tests and Ruff pass.
The maintainer caught a pre-guard parser barrier in the wrapper's unnecessary
`from __future__ import annotations`: Python 3.6 cannot parse that future import.
Removing it keeps the shim parseable on older Python 3 hosts so the version guard
can answer before any bundled-core import. This is an explicit host compatibility
boundary, not a change to the Python 3.11+ core requirement. Final committed
receipts, review and hosted results are recorded below.

## Integrated 0.4.0 source and remaining cutover

[Consolidation PR #44](https://github.com/hermes-labs-ai/quick-gate-js/pull/44)
merged the exact accepted head `fd9e21c48bc0b3117df6255c52cb3f44d3875c2b`
on 2026-09-29 at 17:30:22 UTC, producing main commit
`d312dd2b803dddc0af8f4546f950c31911001319`. The README presents the supplied
header under lowercase `kwik-e-gate`. Both package source versions are 0.4.0;
the three historical package identities and existing Action paths remain intact.

The final local fast/full receipts passed; full ran 453 Python and 95 JavaScript
tests plus Ruff and repository integrity. The configured `hermes-pr-review`
fallback returned a validated PASS on the exact head with zero findings. The
independent maintainer and GitHub steward accepted that same public head after
checking prior material findings. Wheel/sdist build and release identity passed.
Five scoped native consumer receipts remain verifiable against the unchanged
executing core, including stale-source and recovery probes. The separate MCP
TypeScript E2E failure remains disclosed.

Hosted checks for Node 18/20/22/24, Python 3.11/3.14, both quality matrices,
marketplace Action, full receipt and required quality gate all passed on that
head. Public CodeRabbit reported a terminal skipped review because automatic
reviews are disabled, and Sourcery reported that the diff exceeded its fetch
limit; neither was counted as technical acceptance. The local validated review
and independent exact-head steward review supplied the technical acceptance.

The remaining owner-controlled cutover is: arrange and verify the repository-bound
publisher identities and any required release environment approval; then follow
[the publication sequence](docs/MIGRATION.md#publication-sequence) for the npm
tag-trigger and PyPI release-trigger with public artifact readback. A literal
repository slug change to `kwik-e-gate` requires a working old-path Actions
compatibility surface first, with an explicit choice about old web/Git redirects.
No repository deletion, unpublishing, package deprecation, tag movement, publisher
account change, 0.4.0 publication, or slug rename was part of PR #44. Upstream
admission still requires the individual maintainers' intake processes and approval;
the five local profiles are technical proofs, not upstream integrations.
