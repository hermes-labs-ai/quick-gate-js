import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { runCommand } from './exec.js';
import { loadConfig } from './config.js';
import { nowIso, writeJsonFileSync } from './fs-utils.js';
import { runDeterministicGates } from './gates.js';
import {
  GATE_RESULT_FILE,
} from './constants.js';
import { validateAgainstSchema } from './schema.js';
import { hasGit } from './env-check.js';

function gitInfo(cwd) {
  if (!hasGit()) return { repo: undefined, branch: undefined };
  const repoResult = runCommand(['git', 'config', '--get', 'remote.origin.url'], { cwd });
  const branchResult = runCommand(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], { cwd });
  return {
    repo: repoResult.exit_code === 0 ? repoResult.stdout.trim() : undefined,
    branch: branchResult.exit_code === 0 ? branchResult.stdout.trim() : undefined,
  };
}

export function executeRun({ mode, changedFiles, cwd = process.cwd(), artifactDir, outputDir, expectedSnapshotDigest }) {
  const runId = `run_${new Date().toISOString().replace(/[-:.TZ]/g, '').slice(0, 14)}_${randomUUID().slice(0, 8)}`;
  const startedAt = Date.now();
  const config = loadConfig(cwd);
  const resolvedArtifactDir = artifactDir || outputDir;

  const gateExecution = runDeterministicGates({
    mode,
    cwd,
    config,
    changedFiles,
    stateDir: resolvedArtifactDir,
    expectedSnapshotDigest,
  });
  const { gateResult } = gateExecution;
  const status = gateResult.status === 'pass' ? 'pass' : 'fail';
  const git = gitInfo(cwd);

  const failuresPayload = {
    version: '1.0.0',
    run_id: runId,
    mode,
    status,
    timestamp: nowIso(),
    repo: git.repo,
    branch: git.branch,
    changed_files: changedFiles,
    gates: gateExecution.gates,
    findings: gateExecution.findings,
    inferred_hints: gateExecution.findings.map((finding) => ({
      finding_id: finding.id,
      hint: `Start with the deterministic gate failure in ${finding.gate} and inspect command output in run-metadata traces.`,
      confidence: 'low',
    })),
  };

  const validation = validateAgainstSchema('failures.schema.json', failuresPayload);
  if (!validation.valid) {
    throw new Error(`failures.json schema validation failed: ${JSON.stringify(validation.errors, null, 2)}`);
  }

  const metadataPayload = {
    run_id: runId,
    mode,
    started_at: new Date(startedAt).toISOString(),
    completed_at: nowIso(),
    duration_ms: Date.now() - startedAt,
    config_source: config.source === 'defaults' ? 'defaults' : path.basename(String(config.source || 'provided')),
    command_traces: gateExecution.traces,
    gate_result_version: gateResult.version,
    artifact_dir: resolvedArtifactDir,
  };

  const gateValidation = validateAgainstSchema('gate-result-v1.schema.json', gateResult);
  if (!gateValidation.valid) {
    throw new Error(`gate-result/v1 schema validation failed: ${JSON.stringify(gateValidation.errors, null, 2)}`);
  }

  const artifacts = resolvedArtifactDir
    ? {
      failuresPath: path.join(resolvedArtifactDir, 'failures.json'),
      metadataPath: path.join(resolvedArtifactDir, 'run-metadata.json'),
      gateResultPath: path.join(resolvedArtifactDir, GATE_RESULT_FILE),
    }
    : undefined;
  if (artifacts) {
    writeJsonFileSync(artifacts.failuresPath, failuresPayload);
    writeJsonFileSync(artifacts.metadataPath, metadataPayload);
    writeJsonFileSync(artifacts.gateResultPath, gateResult);
  }

  return {
    status,
    gateResult,
    artifacts,
    runId,
  };
}
