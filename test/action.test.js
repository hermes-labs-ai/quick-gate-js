import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

test('composite action runs checked-out source with external output', () => {
  const action = fs.readFileSync('.github/actions/quick-gate/action.yml', 'utf8');
  assert.equal(action.includes('quick-gate@latest'), false);
  assert.match(action, /QUICK_GATE_ACTION_ROOT\/src\/cli\.js/);
  assert.match(action, /--output-dir \"\$QUICK_GATE_OUTPUT_DIR\"/);
  assert.match(action, /RUNNER_TEMP\/quick-gate-/);
});
