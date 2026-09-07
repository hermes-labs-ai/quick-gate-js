import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import { mkdtempSync, cpSync, rmSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { createRequire } from 'node:module';

import {
  envelopeFor,
  findingsFor,
  finding,
  worstStatus,
  gitSha,
  main,
} from '../src/evidence.js';

const require = createRequire(import.meta.url);
const { version: TOOL_VERSION } = require('../package.json');

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const FIXTURES = path.join(REPO_ROOT, 'fixtures', 'lab');

function copyFixture(name) {
  const dest = mkdtempSync(path.join(os.tmpdir(), `quick-gate-lab-${name}-`));
  cpSync(path.join(FIXTURES, name), dest, { recursive: true });
  return dest;
}

function listAll(root) {
  return fs.readdirSync(root, { recursive: true }).sort();
}

/** execFileSync throws on a non-zero exit; assert the code and still return stdout. */
function runExpectingExit(args, expectedCode) {
  try {
    const stdout = execFileSync(process.execPath, args, { encoding: 'utf8' });
    assert.equal(expectedCode, 0, 'expected a non-zero exit but the command succeeded');
    return stdout;
  } catch (error) {
    assert.equal(error.status, expectedCode);
    return error.stdout;
  }
}

test('the clean fixture is a stable pass with no extra findings', () => {
  const project = copyFixture('clean');
  try {
    const result = envelopeFor({ mode: 'quick', cwd: project });
    const again = envelopeFor({ mode: 'quick', cwd: project });

    assert.equal(result.envelope, 'hermes.reliability-lab.result/1');
    assert.equal(result.tool, 'quick-gate');
    assert.equal(result.toolVersion, TOOL_VERSION);
    assert.equal(result.command, 'run');
    assert.equal(result.mode, 'executed');
    assert.equal(result.status, 'pass');
    assert.equal(result.status, worstStatus(result.findings));
    assert.equal(result.exitCode, 0);
    assert.deepEqual(result.findings.map((f) => f.id), ['gate.status']);
    assert.equal(result.data.result.checks[0].status, 'pass');
    assert.deepEqual(JSON.parse(JSON.stringify(result)), result);

    assert.equal(result.status, again.status);
    assert.equal(result.exitCode, again.exitCode);
    assert.match(result.inputHash, /^sha256:[0-9a-f]{64}$/);
  } finally {
    rmSync(project, { recursive: true, force: true });
  }
});

test('the broken fixture fails on typecheck with the real tsc exit code', () => {
  const project = copyFixture('broken');
  try {
    const result = envelopeFor({ mode: 'quick', cwd: project });

    assert.equal(result.status, 'fail');
    assert.equal(result.exitCode, 1);
    const ids = result.findings.map((f) => f.id);
    assert.ok(ids.includes('check.typecheck.fail'));
    assert.ok(ids.some((id) => id.startsWith('finding.typecheck.')));
    const typecheckFinding = result.findings.find((f) => f.id.startsWith('finding.typecheck.'));
    assert.match(typecheckFinding.summary, /exit code/);
    assert.equal(typecheckFinding.severity, 'fail');
    // lint stayed clean: no check.lint.* finding at all (a passing check adds nothing).
    assert.ok(!ids.some((id) => id.startsWith('check.lint.')));
  } finally {
    rmSync(project, { recursive: true, force: true });
  }
});

test('a missing native tool is reported as unknown, not silently folded into a pass', () => {
  const project = copyFixture('clean');
  const restricted = mkdtempSync(path.join(os.tmpdir(), 'quick-gate-lab-restricted-'));
  fs.symlinkSync(process.execPath, path.join(restricted, 'node'));
  const originalPath = process.env.PATH;
  process.env.PATH = restricted;
  try {
    const result = envelopeFor({ mode: 'quick', cwd: project });
    const byId = Object.fromEntries(result.findings.map((f) => [f.id, f]));
    assert.ok(byId['check.lint.missing']);
    assert.equal(byId['check.lint.missing'].severity, 'unknown');
    assert.ok(byId['check.typecheck.missing']);
    // Quick Gate's own gate-result/v1 still records a fail-shaped Finding for a
    // missing check (unlike pygate, which records none) — the lab shows what
    // is really there rather than normalizing the two products to agree.
    assert.ok(result.findings.some((f) => f.id === 'finding.lint.0'));
    assert.equal(result.status, 'fail');
    assert.equal(result.exitCode, 1);
  } finally {
    process.env.PATH = originalPath;
    rmSync(project, { recursive: true, force: true });
    rmSync(restricted, { recursive: true, force: true });
  }
});

test('findings never rename or drop a native result', () => {
  const gateResult = {
    schema: 'gate-result/v1',
    status: 'fail',
    checks: [
      { name: 'lint', status: 'pass', argv: ['npm', 'run', 'lint'], exit_code: 0 },
      { name: 'typecheck', status: 'timeout', argv: ['npx', 'tsc'], exit_code: null },
      { name: 'build', status: 'skipped', argv: [] },
    ],
    findings: [
      {
        gate: 'lint',
        severity: 'critical',
        summary: 'no-unused-vars',
        rule: 'no-unused-vars',
        files: ['a.ts'],
        line: 3,
      },
    ],
  };
  const findings = findingsFor(gateResult);
  assert.deepEqual(
    findings.map((f) => f.id),
    ['gate.status', 'check.typecheck.timeout', 'finding.lint.0'],
  );
  assert.equal(findings[1].severity, 'fail'); // timeout blocks completion, same as fail
  assert.equal(findings[2].path, 'a.ts:3');
  assert.equal(findings[2].detail, 'rule: no-unused-vars');
  assert.equal(findings[2].severity, 'fail'); // critical -> fail, not silently downgraded
});

test('input errors exit non-zero with an unknown envelope', () => {
  const missingDirExit = main(['--mode', 'quick', '--path', path.join(os.tmpdir(), 'does-not-exist-quick-gate')]);
  assert.equal(missingDirExit, 1);

  const empty = mkdtempSync(path.join(os.tmpdir(), 'quick-gate-lab-empty-'));
  try {
    const output = runExpectingExit(
      [path.join(REPO_ROOT, 'src', 'evidence.js'), '--mode', 'quick', '--path', empty],
      1,
    );
    const payload = JSON.parse(output);
    assert.equal(payload.status, 'unknown');
    assert.equal(payload.exitCode, 1);
    assert.equal(payload.findings[0].id, 'input.no-package-json');
    assert.equal(payload.data.result, null);
  } finally {
    rmSync(empty, { recursive: true, force: true });
  }
});

test('overall status is the worst finding present', () => {
  assert.equal(worstStatus([]), 'pass');
  assert.equal(worstStatus([finding('a', 'warn', 'x'), finding('b', 'unknown', 'y')]), 'unknown');
  assert.equal(worstStatus([finding('a', 'unknown', 'x'), finding('b', 'fail', 'y')]), 'fail');
  assert.throws(() => finding('a', 'bad', 'x'));
});

test('input hash is stable for the same project and moves with mode', () => {
  const project = copyFixture('clean');
  try {
    const first = envelopeFor({ mode: 'quick', cwd: project }).inputHash;
    const again = envelopeFor({ mode: 'quick', cwd: project }).inputHash;
    const full = envelopeFor({ mode: 'full', cwd: project }).inputHash;
    assert.equal(first, again);
    assert.notEqual(first, full);
  } finally {
    rmSync(project, { recursive: true, force: true });
  }
});

test('a run writes nothing outside the fixture', () => {
  const project = copyFixture('clean');
  try {
    const before = listAll(project);
    const output = execFileSync(
      process.execPath,
      [path.join(REPO_ROOT, 'src', 'evidence.js'), '--mode', 'quick'],
      { cwd: project, encoding: 'utf8' },
    );
    assert.equal(JSON.parse(output).status, 'pass');
    assert.deepEqual(listAll(project), before);
  } finally {
    rmSync(project, { recursive: true, force: true });
  }
});

test('git sha marks a tree whose commit does not describe the code', () => {
  const scratch = mkdtempSync(path.join(os.tmpdir(), 'quick-gate-lab-git-'));
  try {
    assert.equal(gitSha(scratch), null);
    const run = (...args) => execFileSync('git', ['-C', scratch, ...args], { stdio: 'ignore' });
    run('init', '-q');
    run('config', 'user.email', 'test@example.invalid');
    run('config', 'user.name', 'Test');
    fs.writeFileSync(path.join(scratch, 'a.txt'), 'one\n');
    run('add', '-A');
    run('commit', '-qm', 'first');
    const clean = gitSha(scratch);
    assert.match(clean, /^[0-9a-f]{40}$/);
    fs.writeFileSync(path.join(scratch, 'a.txt'), 'two\n');
    assert.equal(gitSha(scratch), `${clean}-dirty`);
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});
