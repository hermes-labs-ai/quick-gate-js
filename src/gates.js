import fs from 'node:fs';
import path from 'node:path';
import { runCommand } from './exec.js';
import { buildGateResult, configIdentity, packageVersion, snapshotInput } from './contract.js';

function packageScripts(cwd) {
  const packagePath = path.join(cwd, 'package.json');
  if (!fs.existsSync(packagePath)) throw new Error(`No package.json found in ${cwd}`);
  const pkg = JSON.parse(fs.readFileSync(packagePath, 'utf8'));
  return pkg.scripts || {};
}

function configuredCommand(value, allowUnsafeShellCommands) {
  if (Array.isArray(value) || (value && typeof value === 'object')) return value;
  if (typeof value === 'string') return { command: value, unsafeShell: allowUnsafeShellCommands };
  return null;
}

function resolveGateCommand(gate, scripts, config) {
  if (config.commands[gate]) return configuredCommand(config.commands[gate], config.allowUnsafeShellCommands);
  if (gate === 'typecheck') {
    if (scripts.typecheck) return ['npm', 'run', 'typecheck'];
    return ['npx', '--no-install', 'tsc', '--noEmit'];
  }
  if (scripts[gate]) return ['npm', 'run', gate];
  if (gate === 'lighthouse') {
    if (scripts.lighthouse) return ['npm', 'run', 'lighthouse'];
    if (scripts['ci:lighthouse']) return ['npm', 'run', 'ci:lighthouse'];
    if (scripts.lhci) return ['npm', 'run', 'lhci'];
    return null;
  }
  return null;
}

function commandExecutable(command) {
  if (Array.isArray(command) && command.length > 0) return String(command[0]);
  if (command && typeof command === 'object' && command.file) return String(command.file);
  return null;
}

function commandVersion(command, cwd, timeoutMs, maxOutputBytes) {
  const executable = commandExecutable(command);
  if (!executable) return { executable: 'shell', version: 'unknown' };
  const result = runCommand([executable, '--version'], { cwd, timeoutMs, maxOutputBytes });
  const output = `${result.stdout}\n${result.stderr}`.trim().split(/\r?\n/)[0] || 'unknown';
  return { executable, version: output, timed_out: result.timed_out, error_code: result.error_code || null };
}

function parseLighthouseFindings(cwd, stateDir, thresholds) {
  const candidates = [path.join(cwd, '.lighthouseci', 'assertion-results.json')];
  if (stateDir) candidates.push(path.join(stateDir, 'lhci', 'assertion-results.json'));
  const assertionResultsPath = candidates.find((candidate) => fs.existsSync(candidate));
  if (!assertionResultsPath) return [];

  const data = JSON.parse(fs.readFileSync(assertionResultsPath, 'utf8'));
  const findings = [];
  const metricThresholds = thresholds || {};
  const routePath = (rawUrl) => {
    if (!rawUrl) return '/';
    try {
      return new URL(rawUrl).pathname || '/';
    } catch {
      return String(rawUrl);
    }
  };

  const thresholdForAssertion = (row) => {
    if (typeof row.expected === 'number' || typeof row.expected === 'string') {
      return { value: row.expected, source: 'assertion_expected' };
    }
    const assertion = String(row.assertion || '');
    const parts = assertion.split(':');
    if (parts.length === 2 && parts[0] === 'categories' && metricThresholds[parts[1]] !== undefined) {
      return { value: metricThresholds[parts[1]], source: `config_category:${parts[1]}` };
    }
    if (metricThresholds[assertion] !== undefined) {
      return { value: metricThresholds[assertion], source: `config_metric:${assertion}` };
    }
    return { value: 'n/a', source: 'unknown' };
  };

  for (const row of data) {
    if (row.passed) continue;
    const route = routePath(row.url);
    const metric = String(row.assertion || 'lighthouse_assertion');
    const threshold = thresholdForAssertion(row);
    const findingId = `lh_${route.replace(/[^a-zA-Z0-9]+/g, '_')}_${metric.replace(/[^a-zA-Z0-9]+/g, '_')}`.toLowerCase();
    findings.push({
      id: findingId,
      gate: 'lighthouse',
      severity: 'high',
      summary: row.message || `Lighthouse assertion failed: ${metric}`,
      route,
      metric,
      actual: typeof row.numericValue === 'number' ? row.numericValue : String(row.value ?? 'n/a'),
      threshold: threshold.value,
      status: 'fail',
      raw: {
        level: row.level,
        auditProperty: row.auditProperty,
        threshold_source: threshold.source,
        operator: row.operator ?? null,
      },
    });
  }
  return findings;
}

function findingForExitCode(gate, result) {
  const reason = result.timed_out
    ? `timed out after ${result.duration_ms}ms`
    : result.error_code
      ? `could not execute (${result.error_code})`
      : result.signal
        ? `terminated by ${result.signal}`
        : `exit code ${result.exit_code}`;
  return {
    id: `${gate}_failure`,
    gate,
    severity: gate === 'build' ? 'critical' : 'high',
    summary: `${gate} command failed: ${reason}`,
    actual: result.exit_code ?? result.error_code ?? result.signal ?? 'unknown',
    threshold: 0,
    status: 'fail',
    raw: {
      command: result.command,
      error_code: result.error_code || null,
      signal: result.signal || null,
      timed_out: result.timed_out,
      stderr_excerpt: result.stderr.split('\n').slice(0, 30).join('\n'),
      stdout_excerpt: result.stdout.split('\n').slice(0, 30).join('\n'),
    },
  };
}

function checkedPathsFor({ cwd, changedFiles, config }) {
  const paths = [...changedFiles, 'package.json'];
  if (config.source && config.source !== 'defaults') paths.push(path.relative(cwd, config.source));
  return paths;
}

function checkRecord(name, result, timeoutMs) {
  let status = 'fail';
  if (result.timed_out) status = 'timeout';
  else if (result.error_code === 'ENOENT') status = 'missing';
  else if (result.error_code) status = 'error';
  else if (result.exit_code === 0) status = 'pass';
  return {
    name,
    status,
    elapsed_ms: result.duration_ms,
    command: result.command,
    argv: result.argv,
    timeout_ms: timeoutMs,
    exit_code: result.exit_code,
    signal: result.signal || null,
    error_code: result.error_code || null,
    timed_out: result.timed_out,
    output_truncated: result.output_truncated,
  };
}

export function runDeterministicGates({
  mode,
  cwd,
  config,
  changedFiles = [],
  stateDir,
  expectedSnapshotDigest,
  commandTimeoutMs,
  gateTimeoutMs,
  maxOutputBytes,
} = {}) {
  const startedAt = Date.now();
  const resolvedCwd = path.resolve(cwd || process.cwd());
  const resolvedConfig = {
    policy: {},
    commands: {},
    lighthouse: { thresholds: {} },
    allowUnsafeShellCommands: false,
    ...(config || {}),
  };
  const scripts = packageScripts(resolvedCwd);
  const policy = resolvedConfig.policy || {};
  const perCommandTimeout = Math.max(1, Number(commandTimeoutMs || policy.commandTimeoutMs || 120_000));
  const perGateTimeout = Math.max(1, Number(gateTimeoutMs || policy.gateTimeoutMs || 300_000));
  const outputLimit = Math.max(0, Number(maxOutputBytes || policy.outputCapBytes || 64 * 1024));
  const externalStateDir = stateDir || null;
  const snapshot = snapshotInput({ cwd: resolvedCwd, paths: checkedPathsFor({ cwd: resolvedCwd, changedFiles, config: resolvedConfig }) });
  const identity = configIdentity(resolvedConfig);
  const errors = [];

  if (expectedSnapshotDigest && expectedSnapshotDigest !== snapshot.snapshotDigest) {
    errors.push({ code: 'STALE_INPUT', expected: expectedSnapshotDigest, actual: snapshot.snapshotDigest });
    const staleResult = buildGateResult({
      status: 'error',
      snapshotDigest: snapshot.snapshotDigest,
      checkedPaths: snapshot.checkedPaths,
      checks: [],
      findings: [],
      commandVersions: { node: process.version },
      elapsedMs: Date.now() - startedAt,
      outputTruncated: false,
      errors,
      config_identity: identity,
      config_digest: identity.digest,
      config_version: identity.version,
      package_version: packageVersion(resolvedCwd),
      state_dir: externalStateDir,
    });
    return { gates: [], findings: [], traces: [], gateResult: staleResult };
  }

  const traces = [];
  const findings = [];
  const checks = [];
  const commandVersions = { node: process.version };
  const gates = [];
  const gatePlan = [
    { name: 'lint', enabled: true },
    { name: 'typecheck', enabled: true },
    { name: 'build', enabled: mode === 'full' },
    { name: 'lighthouse', enabled: true },
  ];

  for (const gate of gatePlan) {
    const gateStartedAt = Date.now();
    if (!gate.enabled) {
      gates.push({ name: gate.name, status: 'skipped', duration_ms: 0 });
      checks.push({ name: gate.name, status: 'skipped', elapsed_ms: 0, timeout_ms: perGateTimeout });
      continue;
    }

    const command = resolveGateCommand(gate.name, scripts, resolvedConfig);
    if (!command && gate.name === 'lighthouse' && externalStateDir) {
      const lighthouseArgs = ['autorun', '--upload.target=filesystem', `--upload.outputDir=${path.join(externalStateDir, 'lhci')}`];
      const fallback = ['npx', '--no-install', 'lhci', ...lighthouseArgs];
      commandVersions[gate.name] = commandVersion(fallback, resolvedCwd, Math.min(2_000, perCommandTimeout), 1_024);
      commandVersions[gate.name].source = 'fallback';
      commandVersions[gate.name].command = fallback;
    }
    const actualCommand = command || (gate.name === 'lighthouse' && externalStateDir
      ? ['npx', '--no-install', 'lhci', 'autorun', '--upload.target=filesystem', `--upload.outputDir=${path.join(externalStateDir, 'lhci')}`]
      : null);
    if (!actualCommand) {
      gates.push({ name: gate.name, status: 'fail', duration_ms: 0 });
      const errorCode = gate.name === 'lighthouse' && !externalStateDir
        ? 'EXTERNAL_STATE_DIR_REQUIRED'
        : 'MISSING_COMMAND';
      checks.push({ name: gate.name, status: 'fail', elapsed_ms: 0, timeout_ms: perGateTimeout, error_code: errorCode });
      findings.push({
        id: `${gate.name}_${errorCode.toLowerCase()}`,
        gate: gate.name,
        severity: 'high',
        summary: gate.name === 'lighthouse' && !externalStateDir
          ? 'Lighthouse fallback requires an explicit external state directory.'
          : `No command configured for gate: ${gate.name}`,
        files: changedFiles,
        actual: 'missing',
        threshold: 'configured_command_required',
        status: 'fail',
      });
      errors.push({ code: errorCode, gate: gate.name });
      continue;
    }

    if (!commandVersions[gate.name]) {
      commandVersions[gate.name] = commandVersion(actualCommand, resolvedCwd, Math.min(2_000, perCommandTimeout), 1_024);
      commandVersions[gate.name].command = actualCommand;
    }
    const remainingMs = Math.max(1, perGateTimeout - (Date.now() - gateStartedAt));
    const timeoutMs = Math.min(perCommandTimeout, remainingMs);
    const result = runCommand(actualCommand, {
      cwd: resolvedCwd,
      timeoutMs,
      maxOutputBytes: outputLimit,
    });
    traces.push(result);
    const check = checkRecord(gate.name, result, timeoutMs);
    checks.push(check);
    const status = check.status;
    gates.push({ name: gate.name, status: status === 'pass' ? 'pass' : 'fail', duration_ms: result.duration_ms });

    if (status === 'fail') {
      const lighthouseFindings = gate.name === 'lighthouse'
        ? parseLighthouseFindings(resolvedCwd, externalStateDir, resolvedConfig.lighthouse?.thresholds)
        : [];
      findings.push(...(lighthouseFindings.length > 0 ? lighthouseFindings : [findingForExitCode(gate.name, result)]));
    }
    if (result.error_code || result.signal || result.timed_out) {
      errors.push({
        code: result.error_code || (result.timed_out ? 'TIMEOUT' : 'SIGNAL'),
        gate: gate.name,
        signal: result.signal || null,
      });
    }
  }

  const outputTruncated = traces.some((trace) => trace.output_truncated);
  const resultStatus = checks.some((check) => check.status === 'timeout')
    ? 'timeout'
    : checks.some((check) => ['missing', 'error'].includes(check.status))
      ? 'error'
      : findings.length > 0
        ? 'fail'
        : 'pass';
  const gateResult = buildGateResult({
    status: resultStatus,
    snapshotDigest: snapshot.snapshotDigest,
    checkedPaths: snapshot.checkedPaths,
    checks,
    findings,
    commandVersions,
    elapsedMs: Date.now() - startedAt,
    outputTruncated,
    errors,
    config_identity: identity,
    config_digest: identity.digest,
    config_version: identity.version,
    package_version: packageVersion(resolvedCwd),
    state_dir: externalStateDir,
  });

  return { gates, findings, traces, gateResult };
}
