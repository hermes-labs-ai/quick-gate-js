# Provider trial contract

- Candidate: CodeRabbit CLI, exact installed version recorded by `hermes-gate doctor`.
- Bottleneck: one independent material-defect pass for a completed local diff.
- Incumbent: `hermes-pr-review` with `gpt-5.6-terra`, clean committed diffs only.
- Frozen fixtures: one clean and one seeded material bug, with SHA-256 recorded in the trial receipt.
- Success: structured agent output parses deterministically, terminates within the configured bound,
  invalidates after edits, detects at least the seeded sample’s material defect, and makes no write.
- Falsifiers: unsafe/unparseable output, unexpected mutation, unbounded runtime, auth/rate-limit ambiguity,
  or missed sample after the configured trial set (not a claim about broad reviewer capability).
- Forbidden effects: pay-as-you-go credits, automatic Pro purchase, public PR, repository permission,
  token capture, autofix, or provider-driven commit.
- Isolation/state budget: disposable local Git fixtures and Git-internal receipts only.
- Endpoint: `ADOPT_NARROWLY`, `ADAPT_IDEA_ONLY`, `REJECT`, or `INCONCLUSIVE`.
- Rollback: remove the CLI using its documented installer method and set the profile provider to the
  bounded fallback or `REVIEW_UNAVAILABLE`.

Raw measurements and the adoption judgment are recorded separately.
