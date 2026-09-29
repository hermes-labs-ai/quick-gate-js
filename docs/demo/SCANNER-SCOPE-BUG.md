# Demo evidence: the scanner crossed its declared scope

Captured 2026-09-29. This is the bug found during KWIK-E-GATE consolidation's
fast gate. Keep this evidence for the repository's stylized demo image.

## The bug

The profile said to scan `**/AGENTS.md`. Changing that file activated LintLang,
but Hermes Gate then forwarded **every changed path** to the scanner. Unrelated
source and instruction fixtures entered a gate that had not selected them.
In the consolidation run this produced a failed fast gate and a truncated JSON
report. The JavaScript/Python adapter AGENTS warnings were separate, pre-existing
priority/context issues and were also resolved.

The fix in `src/hermes_gate/engine.py` filters scanner arguments to existing
paths that match the configured trigger globs. The regression is
`tests/test_workflow.py::test_instruction_scanner_receives_only_declared_trigger_paths`.

## Saved trace

[scanner-scope-trace.json](scanner-scope-trace.json) contains a **controlled replay**
against original commit `91fd282405a0b4edec2354ec2bfeb08de1679292` and the corrected
source. It includes the complete fixture bytes, scanner argv/output, checks, both
receipt payloads and input digest. It was executed with real LintLang 0.6.0.
Temporary workspace paths are normalized; this is demo evidence, not a reusable
completion receipt for this repository.

| Evidence | Before | After |
| --- | --- | --- |
| Changed inputs | `AGENTS.md`, `app.py`, `notes/SKILL.md` | Identical bytes and comparison base |
| Declared scanner scope | `**/AGENTS.md` | Same profile |
| Python parse | PASS | PASS |
| Scanner argv paths | All three changed paths | `AGENTS.md` |
| Gate outcome | FAIL | PASS |
| Diff digest | `af58fb3b62b5…` | Same digest |

The out-of-scope skill fixture produces a real priority warning in the before
run. The after run evaluates the declared instruction-file gate. It still binds
all included inputs in the receipt; narrowing the scanner does not narrow the
receipt's content identity. The minimal replay does not reproduce the original
large-output truncation; it isolates the argument-selection fault.

Recheck the regression locally:

```bash
pytest tests/test_workflow.py -k instruction_scanner_receives_only_declared_trigger_paths
```

## Visual brief for the later demo image

- Stylized KWIK-E-GATE counter/kiosk with the line **DON'T FORGET THE RECEIPT.**
- Show the declared lane: `AGENTS.md → instruction gate`.
- Show the bug as an overflowing conveyor pulling in `app.py` and `SKILL.md`.
- Show the corrected lane selecting `AGENTS.md`, with Python parse in its own lane.
- A clearly labeled BEFORE / AFTER pair of receipts: FAIL → PASS, same input
  digest prefix `af58fb3b62b5`, explicit checked paths and gate choice.
- Supporting copy: **LOCAL. DETERMINISTIC. RECEIPTED.**
- Preserve readable evidence labels. The artwork may dramatize the conveyor;
  keep the outcomes, paths and digest grounded in the saved trace.
- No instant-suite, semantic-correctness or paid-review-equivalence claim. No
  speed number in this bug image: the separate selector timing is a different
  measurement.

No image has been generated or published from this brief yet.
