/**
 * src/evidence.js
 *
 * Emits a Quick Gate evaluation as a Hermes Reliability Lab result envelope
 * (`hermes.reliability-lab.result/1`): tool, version, status, input hash,
 * findings, exit code, timestamp, optional Git SHA — with the ordinary
 * `gate-result/v1` payload (the contract shared with HermesGate and PyGate)
 * embedded verbatim.
 *
 * This module changes no gate resolution and no scoring. It restates the
 * existing CLI contract in a shared shape: gate-result status "pass" -> lab
 * "pass"; a check that could not run ("missing" command, or "error" starting
 * it) -> lab "unknown" for that check, because a check that did not run is
 * not a check that passed; a check that ran and failed, or timed out, ->
 * lab "fail". The overall envelope status is the worst of those per-check
 * findings plus whatever findings Quick Gate itself already produced.
 *
 *   node src/evidence.js --mode quick
 *   node src/evidence.js --mode full --path fixtures/lab/broken
 *
 * Added in v0.3.0.
 */

import { execFileSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { evaluateGates } from './api.js';

const require = createRequire(import.meta.url);
const { version: TOOL_VERSION } = require('../package.json');

export const ENVELOPE = 'hermes.reliability-lab.result/1';
export const TOOL = 'quick-gate';

/** Ordered worst-last; the run's status is the worst finding it carries. */
export const STATUS_ORDER = ['pass', 'warn', 'unknown', 'fail'];

/**
 * gate-result/v1 top-level `status` -> lab status. "pass" is the only value
 * that does not block; everything else stops a CI gate, so it maps to "fail"
 * at the envelope level even though individual checks may be "unknown".
 */
const RESULT_STATUS = { pass: 'pass', fail: 'fail', timeout: 'fail', error: 'fail' };

/**
 * gate-result/v1 per-check `status` -> lab severity. A check that did not
 * run ("missing" command, or "error" starting it) is unknown, not a pass and
 * not a code-quality failure.
 */
const CHECK_SEVERITY = { pass: 'pass', fail: 'fail', timeout: 'fail', missing: 'unknown', error: 'unknown' };

/** Quick Gate Finding.severity (low/medium/high/critical) -> lab severity. */
const FINDING_SEVERITY = { low: 'warn', medium: 'warn', high: 'fail', critical: 'fail' };

// ---------------------------------------------------------------------------
// Envelope primitives (mirrors pygate/evidence.py and rule_audit/evidence.py;
// a narrow, product-owned adapter per product, not a shared SDK)
// ---------------------------------------------------------------------------

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value && typeof value === 'object') {
    const entries = Object.keys(value)
      .sort()
      .filter((key) => value[key] !== undefined)
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`);
    return `{${entries.join(',')}}`;
  }
  return JSON.stringify(value) ?? 'null';
}

export function inputHash(value) {
  const digest = crypto.createHash('sha256').update(canonicalJson(value), 'utf8').digest('hex');
  return `sha256:${digest}`;
}

export function finding(id, severity, summary, detail, filePath) {
  if (!STATUS_ORDER.includes(severity)) throw new Error(`unknown severity: ${severity}`);
  const result = { id, severity, summary };
  if (detail !== undefined && detail !== null) result.detail = detail;
  if (filePath !== undefined && filePath !== null) result.path = filePath;
  return result;
}

export function worstStatus(findings) {
  let status = 'pass';
  for (const item of findings) {
    if (STATUS_ORDER.indexOf(item.severity) > STATUS_ORDER.indexOf(status)) status = item.severity;
  }
  return status;
}

function git(cwd, ...args) {
  try {
    return execFileSync('git', ['-C', cwd, ...args], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
  } catch {
    return null;
  }
}

/** Best-effort commit of the checkout the tool runs from, "-dirty" if unclean, else null. */
export function gitSha(cwd) {
  const head = git(cwd, 'rev-parse', 'HEAD');
  if (head === null || !head.trim()) return null;
  const sha = head.trim();
  const status = git(cwd, 'status', '--porcelain');
  if (status === null) return sha;
  return status.trim() ? `${sha}-dirty` : sha;
}

function timestamp(date = new Date()) {
  return date.toISOString().replace(/\.\d{3}Z$/, 'Z');
}

// ---------------------------------------------------------------------------
// From a gate-result/v1 payload to findings
// ---------------------------------------------------------------------------

/**
 * One finding per check Quick Gate ran, plus one per finding it already
 * produced. Native results are never renamed or dropped: a check's `argv`,
 * `exit_code`, and stderr excerpt travel into the finding detail unchanged,
 * and every entry in `result.findings` becomes its own lab finding.
 */
export function findingsFor(result) {
  const findings = [
    finding(
      'gate.status',
      RESULT_STATUS[result.status] ?? 'fail',
      `Overall gate result: ${result.status}.`,
      `schema ${result.schema}; ${result.checks.length} check(s) recorded.`,
    ),
  ];

  for (const check of result.checks) {
    if (check.status === 'skipped') continue;
    const severity = CHECK_SEVERITY[check.status] ?? 'unknown';
    if (severity === 'pass') continue; // a passing check is folded into gate.status; no extra noise
    const argv = (check.argv || []).join(' ');
    const detailLines = argv ? [`argv: ${argv}`] : [];
    if (check.exit_code !== null && check.exit_code !== undefined) detailLines.push(`exit_code: ${check.exit_code}`);
    if (check.error_code) detailLines.push(`error_code: ${check.error_code}`);
    findings.push(
      finding(
        `check.${check.name}.${check.status}`,
        severity,
        `${check.name}: ${check.status}${check.exit_code !== null && check.exit_code !== undefined ? ` (exit ${check.exit_code})` : ''}`,
        detailLines.length ? detailLines.join('\n') : null,
      ),
    );
  }

  result.findings.forEach((item, index) => {
    let location = null;
    if (Array.isArray(item.files) && item.files[0]) {
      location = item.files[0];
      if (item.line !== undefined && item.line !== null) location += `:${item.line}`;
    } else if (item.route) {
      location = item.route;
    }
    const detail = item.rule ? `rule: ${item.rule}` : item.metric ? `metric: ${item.metric}` : null;
    findings.push(
      finding(
        `finding.${item.gate ?? 'unknown'}.${index}`,
        FINDING_SEVERITY[item.severity] ?? 'warn',
        item.summary ?? '',
        detail,
        location,
      ),
    );
  });

  return findings;
}

function buildEnvelope(command, findings, inputs, exitCode, data, ts) {
  return {
    envelope: ENVELOPE,
    tool: TOOL,
    toolVersion: TOOL_VERSION,
    command,
    // A real evaluation over real files, not a simulation.
    mode: 'executed',
    status: worstStatus(findings),
    inputHash: inputHash(inputs),
    findings,
    exitCode,
    timestamp: ts,
    gitSha: gitSha(path.dirname(new URL(import.meta.url).pathname)),
    data,
  };
}

/**
 * Run `evaluateGates()` against `cwd` and return the run as an envelope.
 * Writes nothing: `evaluateGates` is the same side-effect-free entry point
 * the embeddable API already documents.
 */
export function envelopeFor({ mode, cwd }) {
  const { gateResult } = evaluateGates({ mode, cwd, changedFiles: ['.'] });
  const findings = findingsFor(gateResult);
  const exitCode = gateResult.status === 'pass' ? 0 : 1;
  return buildEnvelope(
    'run',
    findings,
    { command: 'run', mode, cwd },
    exitCode,
    { mode, cwd, effects: { writes: 'none', network: 'none' }, result: gateResult },
    timestamp(),
  );
}

/** The run could not start; say so in the same shape rather than only on stderr. */
export function inputErrorEnvelope(id, message, mode, cwd) {
  const findings = [finding(id, 'unknown', message, 'No gates ran, so nothing is known about this project.')];
  return buildEnvelope(
    'run',
    findings,
    { command: 'run', mode, cwd },
    1,
    { mode, cwd, effects: { writes: 'none', network: 'none' }, result: null },
    timestamp(),
  );
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith('--')) continue;
    const key = token.slice(2);
    const value = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[i + 1] : true;
    args[key] = value;
    if (value !== true) i += 1;
  }
  return args;
}

export function main(argv = process.argv.slice(2)) {
  const args = parseArgs(argv);
  const mode = args.mode;
  if (mode !== 'quick' && mode !== 'full') {
    process.stderr.write('usage: node src/evidence.js --mode quick|full [--path <dir>]\n');
    return 2;
  }
  const target = path.resolve(String(args.path || '.'));

  let result;
  if (!fs.existsSync(target) || !fs.statSync(target).isDirectory()) {
    result = inputErrorEnvelope('input.not-a-directory', `${args.path || '.'} is not a directory.`, mode, target);
  } else if (!fs.existsSync(path.join(target, 'package.json'))) {
    result = inputErrorEnvelope(
      'input.no-package-json',
      `No package.json in ${target}; Quick Gate has nothing to resolve gate commands from.`,
      mode,
      target,
    );
  } else {
    result = envelopeFor({ mode, cwd: target });
  }

  console.log(JSON.stringify(result, null, 2));
  return result.exitCode;
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exit(main());
}
