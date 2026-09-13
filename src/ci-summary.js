import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ACTION_STATUSES = new Set(['pass', 'fail']);
const REPAIR_STATUSES = new Set(['pass', 'escalated', 'skipped']);
const RESULT_STATUSES = new Set(['pass', 'fail', 'timeout', 'error']);
const CHECK_STATUSES = new Set(['pass', 'fail', 'timeout', 'missing', 'error', 'skipped']);
const MAX_CHECKS = 24;
const SOURCE_URL = 'https://github.com/hermes-labs-ai/quick-gate-js';

function boundedText(value, fallback = 'unavailable') {
  if (typeof value !== 'string') return fallback;
  const normalized = value.replace(/[\r\n\t]+/g, ' ').trim();
  return normalized ? normalized.slice(0, 80) : fallback;
}

function escapeMarkdown(value) {
  return boundedText(value, 'unnamed check').replace(/[\\`*_{}\[\]()<>#+\-.!|]/g, '\\$&');
}

function allowed(value, allowed, fallback = 'unavailable') {
  return allowed.has(value) ? value : fallback;
}

function checkRows(result) {
  if (!result || typeof result !== 'object' || !Array.isArray(result.checks)) return [];
  return result.checks.map((check) => ({
    name: escapeMarkdown(check?.name),
    status: allowed(check?.status, CHECK_STATUSES),
  }));
}

function checkCounts(checks) {
  return checks.reduce((counts, check) => {
    counts[check.status] = (counts[check.status] || 0) + 1;
    return counts;
  }, {});
}

export function renderCiSummary({ gateStatus, repairStatus, result } = {}) {
  const checks = checkRows(result);
  const counts = checkCounts(checks);
  const resultStatus = allowed(result?.status, RESULT_STATUSES);
  const normalizedGateStatus = allowed(gateStatus, ACTION_STATUSES);
  const normalizedRepairStatus = allowed(repairStatus, REPAIR_STATUSES);
  const countText = checks.length === 0
    ? 'unavailable'
    : `${checks.length} total; ${counts.pass || 0} pass; ${checks.fail || 0} fail; ${counts.timeout || 0} timeout; ${counts.missing || 0} missing; ${counts.error || 0} error; ${counts.skipped || 0} skipped`;
  const lines = [
    '## Quick Gate CI quality gate',
    '',
    `[Quick Gate](${SOURCE_URL}) runs this job from the checked-out action source.`,
    '',
    '| Field | Result |',
    '| --- | --- |',
    `| Gate status | \`${normalizedGateStatus}\` |`,
    `| Result-envelope status | \`${resultStatus}\` |`,
    `| Checks | ${countText} |`,
    `| Repair | \`${normalizedRepairStatus}\` |`,
  ];

  if (checks.length > 0) {
    lines.push('', `### Checks (${checks.length})`);
    for (const check of checks.slice(0, MAX_CHECKS)) {
      lines.push(`- ${check.name}: \`${check.status}\``);
    }
    if (checks.length > MAX_CHECKS) lines.push(`- ${checks.length - MAX_CHECKS} additional checks omitted`);
  }

  return `${lines.join('\n')}\n`;
}

export function renderCiSummaryFromFile({ input, gateStatus, repairStatus } = {}) {
  let result;
  try {
    result = JSON.parse(fs.readFileSync(input, 'utf8'));
  } catch {
    result = null;
  }
  return renderCiSummary({ gateStatus, repairStatus, result });
}

function argumentValue(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.stdout.write(renderCiSummaryFromFile({
    input: argumentValue('--input'),
    gateStatus: argumentValue('--gate-status'),
    repairStatus: argumentValue('--repair-status'),
  }));
}
