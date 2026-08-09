import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { evaluateGates } from '../src/api.js';
import { runCommand } from '../src/exec.js';
import { snapshotInput, stableStringify } from '../src/contract.js';
import { validateAgainstSchema } from '../src/schema.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function fixtureDir() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'quick-gate-contract-'));
  fs.writeFileSync(path.join(dir, 'package.json'), `${JSON.stringify({
    name: 'gate-contract-fixture',
    version: '1.2.3',
    private: true,
    scripts: {
      lint: 'node -e "process.exit(0)"',
      typecheck: 'node -e "process.exit(0)"',
      lighthouse: 'node -e "process.exit(0)"',
    },
  }, null, 2)}\n`);
  fs.writeFileSync(path.join(dir, 'src file.js'), 'export default 1;\n');
  return dir;
}

test('argv treats metacharacters and spaces as data', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'quick-gate-argv-'));
  const marker = path.join(dir, 'should-not-exist');
  const value = `$(touch ${marker}) && echo unsafe value`;
  const result = runCommand([
    process.execPath,
    '-e',
    'process.stdout.write(process.argv[1])',
    value,
  ], { cwd: dir });

  assert.equal(result.exit_code, 0);
  assert.equal(result.stdout, value);
  assert.equal(fs.existsSync(marker), false);
  assert.deepEqual(result.argv.slice(0, 1), [process.execPath]);
});

test('unsafe command strings are rejected unless explicitly enabled', () => {
  const blocked = runCommand('echo blocked');
  assert.equal(blocked.error_code, 'UNSAFE_COMMAND_REQUIRES_ARGV');
  const allowed = runCommand('printf allowed', { unsafeShell: true });
  assert.equal(allowed.exit_code, 0);
  assert.equal(allowed.stdout, 'allowed');
});

test('missing executable is represented without a fake exit code', () => {
  const result = runCommand(['quick-gate-command-that-does-not-exist']);
  assert.equal(result.exit_code, null);
  assert.equal(result.error_code, 'ENOENT');
  assert.equal(result.signal, null);
});

test('oversized output is capped with a truncation marker', () => {
  const result = runCommand([
    process.execPath,
    '-e',
    'process.stdout.write("x".repeat(1000))',
  ], { maxOutputBytes: 32 });
  assert.equal(result.exit_code, 0);
  assert.equal(result.output_truncated, true);
  assert.match(result.stdout, /\.\.\.\[truncated\]$/);
  assert.ok(result.stdout.length < 100);
});

test('timeout terminates descendants in the command process group', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'quick-gate-timeout-'));
  const marker = path.join(dir, 'descendant survived.txt');
  const childCode = `setTimeout(() => require('node:fs').writeFileSync(${JSON.stringify(marker)}, 'survived'), 500)`;
  const result = runCommand([
    process.execPath,
    '-e',
    `require('node:child_process').spawn(${JSON.stringify(process.execPath)}, ['-e', ${JSON.stringify(childCode)}], {stdio: 'ignore'}); setTimeout(() => {}, 5000)`,
  ], { cwd: dir, timeoutMs: 100 });
  await new Promise((resolve) => setTimeout(resolve, 700));
  assert.equal(result.timed_out, true);
  assert.equal(fs.existsSync(marker), false);
});

test('evaluateGates returns gate-result/v1 without writing artifacts', () => {
  const cwd = fixtureDir();
  const before = fs.readdirSync(cwd).sort();
  const result = evaluateGates({ mode: 'quick', cwd, changedFiles: ['src file.js'] });
  const after = fs.readdirSync(cwd).sort();

  assert.deepEqual(after, before);
  assert.equal(result.gateResult.schema, 'gate-result/v1');
  assert.equal(result.gateResult.version, 'gate-result/v1');
  assert.equal(result.gateResult.status, 'pass');
  assert.deepEqual(result.gateResult.checked_paths, ['package.json', 'src file.js']);
  assert.equal(result.gateResult.package_version, '0.2.3');
  assert.ok(result.gateResult.config_digest);
  assert.ok(result.gateResult.command_versions.lint.version);
  assert.equal(validateAgainstSchema('gate-result-v1.schema.json', result.gateResult).valid, true);
});

test('shared gate-result fixtures match the canonical schema', () => {
  const fixtures = JSON.parse(
    fs.readFileSync(path.join(__dirname, 'fixtures', 'gate-result-v1.fixtures.json'), 'utf8'),
  );
  for (const fixture of fixtures.cases) {
    const validation = validateAgainstSchema('gate-result-v1.schema.json', fixture.value);
    assert.equal(validation.valid, fixture.valid, `${fixture.name}: ${JSON.stringify(validation.errors)}`);
  }
});

test('stale input is rejected before command execution', () => {
  const cwd = fixtureDir();
  const baseline = evaluateGates({ mode: 'quick', cwd, changedFiles: ['src file.js'] });
  fs.appendFileSync(path.join(cwd, 'src file.js'), '// changed after snapshot\n');
  const result = evaluateGates({
    mode: 'quick',
    cwd,
    changedFiles: ['src file.js'],
    expectedSnapshotDigest: baseline.gateResult.snapshot_digest,
  });
  assert.equal(result.gateResult.status, 'error');
  assert.equal(result.gateResult.errors[0].code, 'STALE_INPUT');
  assert.deepEqual(result.gateResult.checks, []);
});

test('snapshot binds symlink identity and target bytes', () => {
  const cwd = fs.mkdtempSync(path.join(os.tmpdir(), 'quick-gate-symlink-'));
  fs.writeFileSync(path.join(cwd, 'target.txt'), 'first\n');
  fs.symlinkSync('target.txt', path.join(cwd, 'link.txt'));
  const first = snapshotInput({ cwd, paths: ['link.txt'] });
  fs.writeFileSync(path.join(cwd, 'target.txt'), 'second\n');
  const second = snapshotInput({ cwd, paths: ['link.txt'] });

  assert.deepEqual(first.checkedPaths, ['link.txt']);
  assert.notEqual(first.snapshotDigest, second.snapshotDigest);
});

test('stable serialization is independent of object key order', () => {
  assert.equal(
    stableStringify({ b: 2, a: { d: 4, c: 3 } }),
    stableStringify({ a: { c: 3, d: 4 }, b: 2 }),
  );
});
