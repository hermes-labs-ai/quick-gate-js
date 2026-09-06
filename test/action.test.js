import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';

test('composite action runs checked-out source with external output', () => {
  const action = fs.readFileSync('.github/actions/quick-gate/action.yml', 'utf8');
  assert.equal(action.includes('quick-gate@latest'), false);
  assert.match(action, /QUICK_GATE_ACTION_ROOT\/src\/cli\.js/);
  assert.match(action, /--output-dir \"\$QUICK_GATE_OUTPUT_DIR\"/);
  assert.match(action, /RUNNER_TEMP\/quick-gate-/);
});

test('composite action fails unless the gate or bounded repair passes', () => {
  const conclude = (gateStatus, repairStatus) => spawnSync(
    'bash',
    ['.github/actions/quick-gate/conclude.sh', gateStatus, repairStatus],
    { encoding: 'utf8' },
  );

  assert.equal(conclude('pass', 'skipped').status, 0);
  assert.equal(conclude('fail', 'pass').status, 0);
  assert.equal(conclude('fail', 'escalated').status, 1);
  assert.equal(conclude('fail', 'skipped').status, 1);
  assert.equal(conclude('', 'pass').status, 1);
  assert.equal(conclude('', '').status, 1);
});

test('composite action concludes only after preserving reports', () => {
  const action = fs.readFileSync('.github/actions/quick-gate/action.yml', 'utf8');
  const uploadIndex = action.indexOf('- name: Upload artifacts');
  const concludeIndex = action.indexOf('- name: Conclude Quick Gate');

  assert.ok(uploadIndex >= 0);
  assert.ok(concludeIndex > uploadIndex);
  assert.match(action.slice(concludeIndex), /if: always\(\)/);
  assert.match(action.slice(concludeIndex), /GITHUB_ACTION_PATH\/conclude\.sh/);
});

test('copyable consumer workflow is not an active repository workflow', () => {
  assert.equal(fs.existsSync('.github/workflows/example-usage.yml'), false);
  assert.equal(fs.existsSync('examples/quick-gate.yml'), true);
  assert.match(fs.readFileSync('README.md', 'utf8'), /\[copyable workflow example\]\(examples\/quick-gate\.yml\)/);
});

test('repository CI keeps an active quality gate with meaningful plain-JS coverage', () => {
  const workflow = fs.readFileSync('.github/workflows/ci.yml', 'utf8');
  const config = JSON.parse(fs.readFileSync('quick-gate.config.json', 'utf8'));

  assert.match(workflow, /^  quality-gate:/m);
  assert.match(workflow, /uses: \.\/\.github\/actions\/quick-gate/);
  assert.match(workflow, /mode: full/);
  assert.deepEqual(config.gates, { typecheck: false, lighthouse: false });
  assert.deepEqual(config.commands.build, ['npm', 'pack', '--dry-run']);
  assert.equal(JSON.parse(fs.readFileSync('package.json', 'utf8')).scripts.lint, 'node --check src/*.js test/*.test.js');
});
