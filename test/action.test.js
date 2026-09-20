import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { renderCiSummary, renderCiSummaryFromFile } from '../src/ci-summary.js';

test('composite action runs checked-out source with external output', () => {
  const action = fs.readFileSync('.github/actions/quick-gate/action.yml', 'utf8');
  assert.equal(action.includes('quick-gate@latest'), false);
  assert.match(action, /QUICK_GATE_ACTION_ROOT\/src\/cli\.js/);
  assert.match(action, /--output-dir \"\$QUICK_GATE_OUTPUT_DIR\"/);
  assert.match(action, /RUNNER_TEMP\/quick-gate-/);
  assert.match(action, /actions\/setup-node@[0-9a-f]{40}/);
  assert.match(action, /actions\/upload-artifact@[0-9a-f]{40}/);
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

test('composite action publishes a bounded result-envelope job summary', () => {
  const action = fs.readFileSync('.github/actions/quick-gate/action.yml', 'utf8');
  const summaryIndex = action.indexOf('- name: Publish Quick Gate summary');
  const concludeIndex = action.indexOf('- name: Conclude Quick Gate');

  assert.ok(summaryIndex >= 0);
  assert.ok(summaryIndex < concludeIndex);
  assert.match(action.slice(summaryIndex, concludeIndex), /if: always\(\)/);
  assert.match(action.slice(summaryIndex, concludeIndex), /gate-result\.json/);
  assert.match(action.slice(summaryIndex, concludeIndex), /GITHUB_STEP_SUMMARY/);
});

test('CI summary renders stable status and check counts from gate-result/v1', () => {
  const summary = renderCiSummary({
    gateStatus: 'pass',
    repairStatus: 'skipped',
    result: {
      schema: 'gate-result/v1',
      status: 'pass',
      checks: [
        { name: 'lint', status: 'pass' },
        { name: 'typecheck', status: 'skipped' },
        { name: 'build', status: 'pass' },
      ],
    },
  });

  assert.match(summary, /Quick Gate CI quality gate/);
  assert.match(summary, /https:\/\/github\.com\/hermes-labs-ai\/quick-gate-js/);
  assert.match(summary, /3 total; 2 pass; 0 fail; 0 timeout; 0 missing; 0 error; 1 skipped/);
  assert.match(summary, /- lint: `pass`/);
  assert.match(summary, /- typecheck: `skipped`/);
});

test('CI summary stays bounded for missing or malformed results and unsafe labels', () => {
  const malformedDir = fs.mkdtempSync(path.join(os.tmpdir(), 'quick-gate-summary-'));
  const malformedPath = path.join(malformedDir, 'gate-result.json');
  fs.writeFileSync(malformedPath, '{not valid JSON');
  const missing = renderCiSummaryFromFile({
    input: path.join(os.tmpdir(), 'quick-gate-summary-result-does-not-exist.json'),
    gateStatus: 'fail',
    repairStatus: 'skipped',
  });
  const malformed = renderCiSummaryFromFile({
    input: malformedPath,
    gateStatus: 'fail',
    repairStatus: 'skipped',
  });
  const unsafe = renderCiSummary({
    gateStatus: 'unexpected',
    repairStatus: 'unexpected',
    result: {
      status: 'unexpected',
      checks: [{ name: 'lint\n<script>alert(1)</script>| `argv` /private/path', status: 'unexpected' }],
      errors: ['secret-like error text must never render'],
    },
  });

  assert.match(missing, /Result-envelope status \| `unavailable`/);
  assert.match(missing, /Checks \| unavailable/);
  assert.equal(malformed, missing);
  assert.match(unsafe, /Gate status \| `unavailable`/);
  assert.ok(unsafe.includes('lint \\<script\\>alert\\(1\\)\\</script\\>\\| \\`argv\\` /private/path'));
  assert.equal(unsafe.includes('secret-like error text must never render'), false);
  assert.equal(unsafe.includes('\n<script>'), false);
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
  assert.equal(
    JSON.parse(fs.readFileSync('package.json', 'utf8')).scripts.lint,
    'for file in src/*.js test/*.test.js; do node --check "$file" || exit 1; done',
  );
});

test('root Marketplace action forwards the nested action contract with safe defaults', () => {
  const rootAction = fs.readFileSync('action.yml', 'utf8');

  assert.match(rootAction, /^name: Quick Gate$/m);
  assert.match(rootAction, /^author: Hermes Labs$/m);
  assert.match(rootAction, /branding:\n  color: blue\n  icon: check-circle/);
  assert.match(rootAction, /repair:\n    description:[^\n]+\n    required: false\n    default: "false"/);
  assert.match(rootAction, /post-comment:\n    description:[^\n]+\n    required: false\n    default: "false"/);
  assert.match(rootAction, /uses: \$\/\.github\/actions\/quick-gate/);

  for (const input of [
    'mode',
    'repair',
    'max-attempts',
    'node-version',
    'post-comment',
    'output-dir',
  ]) {
    assert.ok(rootAction.includes('        ' + input + ': ${{ inputs.' + input + ' }}'));
  }

  for (const output of ['status', 'failures-json', 'repair-status']) {
    const source = output === 'repair-status'
      ? 'steps.normalized.outputs.status'
      : output === 'failures-json'
        ? "steps.nested.outputs['failures-json']"
        : 'steps.nested.outputs.' + output;
    assert.ok(rootAction.includes('value: ${{ ' + source + ' }}'));
  }
  assert.match(rootAction, /id: normalized/);
  assert.match(rootAction, /NESTED_REPAIR_STATUS: \$\{\{ steps\.nested\.outputs\['repair-status'\] \}\}/);
  assert.match(rootAction, /echo "status=skipped" >> "\$GITHUB_OUTPUT"/);
});

test('CI and copyable example exercise the root action with least permissions', () => {
  const workflow = fs.readFileSync('.github/workflows/ci.yml', 'utf8');
  const example = fs.readFileSync('examples/quick-gate.yml', 'utf8');

  assert.match(workflow, /marketplace-action:/);
  assert.match(workflow, /uses: \.\//);
  assert.match(workflow, /- run: npm run lint/);
  assert.match(workflow, /GATE_STATUS: \$\{\{ steps\.gate\.outputs\.status \}\}/);
  assert.match(example, /contents: read/);
  assert.doesNotMatch(example, /pull-requests: write/);
  assert.match(example, /actions\/checkout@[0-9a-f]{40}/);
  assert.match(example, /run: npm ci/);
  assert.match(example, /uses: hermes-labs-ai\/quick-gate-js@main/);
  assert.match(example, /repair: "false"/);
  assert.match(example, /post-comment: "false"/);
});
