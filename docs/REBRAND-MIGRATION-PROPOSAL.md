# Kwik-E-Gate repository migration proposal

**Status (2026-09-29): independently reviewed, proposed, not executed.** A Sol
technical reviewer returned **APPROVE** for this gated proposal after its initial
**HOLD** exposed the old-URL plugin-install gap. Approval does not establish live
compatibility or authorize cutover. This document specifies the URL and
release migration for the integrated 0.4.0 source. [KWIK-E-GATE-PLAN.md](../KWIK-E-GATE-PLAN.md)
is the architecture and due-diligence record; [MIGRATION.md](MIGRATION.md) specifies
existing interface and release behavior. This proposal is a cutover decision, not a
second runtime architecture.

## Decision

Use **Kwik-E-Gate** as the product name and **`hermes-labs-ai/kwik-e-gate`** as the
eventual canonical repository URL. Rename the existing five-star
`hermes-labs-ai/quick-gate-js` repository so its issues, history, and stars stay with
the product. Keep one maintained Python receipt/routing core and the optional JS and
PyGate adapters already integrated in 0.4.0. Keep the org as owner. The old
`hermes-labs-ai/hermes-gate` repository and Action remain available.

Preserve **package and consumer identities**: npm `quick-gate` and its exports/bin,
PyPI `hermes-gate`/`hermes_gate`/`hermes-gate`, PyPI `pygate-ci`/`pygate`, the new
`kwik-gate` alias in the same core distribution, `gate-result/v1`, existing receipt
verification semantics, the legacy root and nested JS Action contracts, and old-URL
plugin/skill installs. Do not
create `kwik-e-gate` npm/PyPI packages merely to match the URL. Do not transfer a
repository to a personal account, move tags, deprecate working packages, unpublish,
delete, or create a second receipt engine.

The literal URL rename has a **compatibility condition**. GitHub preserves stars and
ordinary web/Git redirects on rename, but [does not redirect Action references](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository).
Recreating `quick-gate-js` makes its old web/Git URL point to that compatibility
repository instead of redirecting to the new product URL. We prioritize working
`uses: hermes-labs-ai/quick-gate-js@...` consumers over transparent old web/Git
redirects. This also changes old issue, PR, release, and file deep links: they can
land in the new compatibility repository or fail instead of reaching their original
content. The compatibility repository must say prominently that active development
and new source pins live at `hermes-labs-ai/kwik-e-gate`. This differs from GitHub's
documented default recommendation to leave the old Action repository in place and
create a new one; our design needs a live consumer proof before it can be accepted.

If old Action references cannot be proven at their existing tags **and representative
full commit SHA pins**, hold the URL rename. Continue presenting the product as
Kwik-E-Gate at `quick-gate-js` until a safe path is found. Five stars are a useful
identity tie-breaker, not a reason to break users.

## Evidence behind the decision

- Consolidation PR [#44](https://github.com/hermes-labs-ai/quick-gate-js/pull/44)
  merged the one-core 0.4.0 source; plan update [#45](https://github.com/hermes-labs-ai/quick-gate-js/pull/45)
  records passing local and hosted checks. The [CI admission notes](CI-ADMISSION.md)
  report five scoped local consumer PASS proofs and one MCP TypeScript E2E FAIL;
  none is an upstream adoption claim.
- At this proposal's public readback, `quick-gate-js` has five stars,
  `hermes-gate` three; `kwik-e-gate` does not yet exist. npm `quick-gate` is 0.3.2,
  PyPI `hermes-gate` is 0.1.7, and no 0.4.0 tag/release is public. Recheck all of
  these immediately before any cutover.
- The GitHub API reports `quick-gate-js` repository ID `1163923316` and an `npm`
  environment with no required reviewer; it has **no `pypi` environment**. The
  separate `hermes-gate` repository has a `pypi` environment requiring reviewer
  `roli-lpci`. Renaming the JS repository does not bring over a different
  repository's environment. The new canonical repository needs its own protected
  `pypi` environment before any release is published.
- The current repository's [npm workflow](../.github/workflows/publish.yml) runs on
  a pushed `v*` tag, while its [PyPI workflow](../.github/workflows/publish-core.yml)
  runs when a GitHub release is published. Importing old tags into a compatibility
  repository could therefore start copied publication workflows. GitHub [documents
  tag pushes as workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows).
- The [JS adapter's documented agent-plugin installs](QUICK-GATE-JS.md#agent-plugin)
  use the old repository's **default branch** for Claude, Codex, Gemini, and
  skills.sh. Those need the marketplace/extension manifests, `plugin.json`, the
  `skills/quick-gate-js` payload, and its referenced files, not just an Action or
  redirect README. This is an additional live old-path contract.
- [npm trusted publishing](https://docs.npmjs.com/trusted-publishers/) binds the
  owner, repository, workflow filename, and optional environment; [PyPI trusted
  publishing](https://docs.pypi.org/trusted-publishers/adding-a-publisher/) also
  binds the owner, repository, and workflow filename. PyPI [documents repo-rename
  mismatches](https://docs.pypi.org/trusted-publishers/troubleshooting/). Neither
  binding may be assumed to follow a rename.

## Controlled cutover

Each phase has a separate go/no-go record. Owner authorization is required for the
repository identity change, registry publisher binding changes, and release. This
proposal and independent technical review do **not** authorize those effects.

### 0. Freeze and preflight

Record the accepted `main` SHA, open PRs, branch protection/rulesets, all tags and
releases, current repo IDs/stars, Action paths and input/output contracts, external
`uses:` references that can be found, old-URL plugin/skill installer commands and
their manifests/payload, representative old issue/PR/release deep links, and
npm/PyPI publisher settings and GitHub
`npm`/`pypi` environment reviewers. Re-run the exact-state Gate, package builds,
source Action and legacy JS Action checks, and hosted required checks. Check the
actual account has org repository admin access and that `kwik-e-gate` is still free.
Record the old SHA/tag sample as an executable consumer fixture.

No cutover proceeds with an unreviewed source diff, missing publisher access, or a
broken old Action fixture. Updating product-title casing, repository metadata,
README/skill links, package source URLs, plugin links, CITATION metadata, and any
hard-coded Action references is a **reviewed source change** before its release tag.
Do not replace accurate live URLs with an uncreated one in published instructions;
prepare the diff and apply it at the cutover boundary. Product display spelling is
`Kwik-E-Gate`; slug and Action directory are lowercase `kwik-e-gate`.

### 1. Rehearse compatibility without touching either public name

Prepare a full-fidelity Git copy of the existing JS Action repository, including
the historical commits and tags needed for full-SHA and tag pins. The compatibility
default branch must retain the legacy root and `.github/actions/quick-gate` Actions
**and** the working plugin/skill install surface: `.claude-plugin`,
`.agents/plugins/marketplace.json`, root `plugin.json`, `gemini-extension.json`,
`skills/quick-gate-js`, and any referenced payload. Pin its default-branch plugin
guidance to the actually released `quick-gate@0.3.2` until 0.4.0 registry readback;
add a prominent README and metadata links to the canonical product. Do not leave
unreleased 0.4.0 instructions on an old-path compatibility branch. This branch is
for compatibility fixes only, not a second core development branch. Rehearse this
arrangement using disposable names, including a real caller workflow at `v0.3.2`
and its full SHA for the root Action, older tags at paths that actually existed,
and a current supported pin. Test whether the proposed publishing-workflow
containment still permits **external** Action use. Rehearse representative old-URL
Claude/Codex/Gemini/skills.sh installs and check their installed skill can invoke
the released adapter, rather than merely parsing a marketplace manifest.

Do not assume `git push --mirror` is safe. First establish a tested procedure that
keeps the compatibility repository's historical `.github/workflows/publish.yml`
and any release-triggered publisher workflow from publishing during ref import.
Possible GitHub Actions settings or disabled-workflow controls are implementation
options, **not verified guarantees**; verify both no unintended publish runs and
old Action resolution in the rehearsal. If the two conditions cannot coexist, stop
and revise the migration. A README-only compatibility shell or current-only tag
cannot support historical SHA pins.

### 2. Rename and restore the old Action path

In a short announced maintenance window, after authorization and phase-1 proof:

1. Freeze merges, tags, and releases; capture a read-only backup/ref manifest.
2. Rename the existing org repository to `kwik-e-gate`; verify its repository ID,
   stars, issues, history, branches, protected settings, and new URL.
3. Create `hermes-labs-ai/quick-gate-js` as a clearly labeled compatibility repo.
   Apply the proven publish-containment setting **before importing any release ref**.
   Import the historical branches/tags needed to make supported Action pins
   reachable by the rehearsed procedure; preserve commit
   objects and historical tag/SHA pins exactly. The default branch must contain
   the rehearsed Action **and plugin** compatibility payload. Do not copy publishing secrets or
   trusted-publisher permissions to this repository.
4. From a separate caller repository, run the legacy root and nested Actions using
   a representative historical tag, full SHA, and current supported pin at the
   Action paths present in those refs. Check
   behavior and output names, not just that GitHub resolves the URL. Run the new
   source-pinned `hermes-labs-ai/kwik-e-gate/.github/actions/kwik-e-gate@<SHA>`
   with PASS and FAIL receipt assertions. Verify no compatibility-repo publish run
   started. Repeat the old-URL plugin/skill install probes against the real
   compatibility repository; verify old web/Git URLs so their changed destination
   is explicit.

Expect a brief interval between rename and the restored old Action path; no
zero-downtime guarantee is claimed. Stop promotion if any consumer fixture fails.
Rollback is **not** a blind reverse rename: the recreated old name blocks it. First
stabilize the old Action path and diagnose; any reversal requires a separate verified
sequence that frees the old name without dropping historical Action consumers.
Document the observed partial state and do not publish 0.4.0 while it is unresolved.

### 3. Bind publishers and release 0.4.0

After both repository URLs and Actions work, update the npm `quick-gate` and PyPI
`hermes-gate` trusted publisher configurations to owner
`hermes-labs-ai`, repository `kwik-e-gate`, and the actual workflow files
`publish.yml` and `publish-core.yml`, with the intended `npm` and `pypi`
environments. Create/configure the canonical repository's missing `pypi`
environment with owner-selected required reviewer protection, and read it back;
the protection on the old `hermes-gate` repository is not inherited. Verify
`id-token: write` on both publish jobs. Confirm npm allows
direct `npm publish` for this binding; current npm setup can require that choice.
Keep old trust only as long as a documented transition needs it; do not bind the
compatibility repo as a publisher. Do not use a personal token fallback.

Complete and review the final source/metadata diff at a single accepted commit.
Set the citation release date. Once independent publisher approval and all release
gates pass, create **one immutable `v0.4.0` tag** on the canonical repository.
Pushing it triggers npm publication. Observe the workflow and install/read back
`quick-gate@0.4.0` from npm before publishing the GitHub release. Publishing that
release triggers PyPI; observe its environment approval, workflow, and a fresh
`hermes-gate==0.4.0` install with PASS/FAIL/export/verify. Test the core Action at
the release pin and preserve the legacy Action pins. Do not move a tag to repair a
partial release. Update README/skill “released” wording only after registry readback.

### 4. Maintain compatibility

Keep the old `quick-gate-js` Action path, historical refs, and default-branch
plugin/skill installs working. The compatibility branch may remain on the released
0.3.2 adapter while clearly pointing users to the canonical repository for 0.4.0;
its support policy should promise compatibility repairs, not duplicate feature
development. Route new issues, source contributions, and releases to the canonical
repository.
Keep `hermes-gate` historical releases/Action and all three established package
names. State the exact support policy for the compatibility repo in both READMEs.
Spot-check old tag/SHA Action pins, npm/PyPI installs, public provenance, old Git
remote behavior, receipt verification, and stale-source rejection after cutover.
New optional adapters should bind to the single core, not fork it. Upstream
admission requires each upstream maintainer's process; local profile PASS does not
grant upstream acceptance.

## Approval and decision boundary

The requested independent Sol review should approve the **proposal's technical
safety and evidence**, not claim that migration has occurred. Before execution,
the owner must authorize the literal repository rename and old-name recreation,
including loss of automatic old web/Git and issue/PR deep-link redirects; publisher
identity changes and 0.4.0 publication are separate effects. The Action and plugin
rehearsals and exact
current public state can still veto cutover. If those checks fail, keep the existing
repository URL and the Kwik-E-Gate product branding while revising the sequence.
