import fs from 'node:fs';
import path from 'node:path';
import { loadConfig } from './config.js';
import { runCommand } from './exec.js';
import { readJsonFileSync, writeJsonFileSync } from './fs-utils.js';
import { executeRun } from './run-command.js';
import { executeSummarize } from './summarize-command.js';
import { DEFAULT_POLICY, ESCALATION_CODES } from './constants.js';
import { getModelRoutingPolicy, runHintModel, runPatchModel } from './model-adapter.js';
import { runDeterministicPreFix } from './deterministic-prefix.js';
import { hasRsync, hasGit } from './env-check.js';

function diffSnapshot(cwd) {
  if (!hasGit()) return new Map();
  const diff = runCommand(
    ['git', 'diff', '--numstat', '--', '.', ':(exclude).quick-gate', ':(exclude).next', ':(exclude).lighthouseci', ':(exclude)node_modules', ':(exclude)tmp'],
    { cwd },
  );
  const map = new Map();
  if (diff.exit_code !== 0) {
    return map;
  }
  diff.stdout
    .split(/\r?\n/)
    .filter(Boolean)
    .forEach((row) => {
      const cols = row.split(/\t+/);
      if (cols.length < 3) return;
      const added = Number(cols[0]);
      const removed = Number(cols[1]);
      const file = cols.slice(2).join('\t');
      const value = (Number.isFinite(added) ? added : 0) + (Number.isFinite(removed) ? removed : 0);
      map.set(file, value);
    });
  return map;
}

function computePatchLines(beforeMap, afterMap) {
  const allFiles = new Set([...beforeMap.keys(), ...afterMap.keys()]);
  let total = 0;
  for (const file of allFiles) {
    const before = beforeMap.get(file) || 0;
    const after = afterMap.get(file) || 0;
    total += Math.abs(after - before);
  }
  return total;
}

function backupWorkspace(cwd, backupDir) {
  fs.mkdirSync(backupDir, { recursive: true });
  if (hasRsync()) {
    runCommand([
      'rsync', '-a', '--delete',
      '--exclude', '.git', '--exclude', 'node_modules', '--exclude', '.next', '--exclude', '.quick-gate',
      `${cwd}${path.sep}`, `${backupDir}${path.sep}`,
    ], { cwd });
  } else {
    copyWorkspaceEntries(cwd, backupDir);
  }
}

function restoreWorkspace(cwd, backupDir) {
  if (hasRsync()) {
    runCommand([
      'rsync', '-a', '--delete',
      '--exclude', '.git', '--exclude', 'node_modules', '--exclude', '.next', '--exclude', '.quick-gate',
      `${backupDir}${path.sep}`, `${cwd}${path.sep}`,
    ], { cwd });
  } else {
    copyWorkspaceEntries(backupDir, cwd);
  }
}

function copyWorkspaceEntries(source, destination) {
  const excluded = new Set(['.git', 'node_modules', '.next', '.quick-gate']);
  for (const name of fs.readdirSync(source)) {
    if (excluded.has(name)) continue;
    fs.cpSync(path.join(source, name), path.join(destination, name), {
      recursive: true,
      force: true,
    });
  }
}

function runRepairActions(cwd, failures, policy, deterministicOnly, stateDir) {
  const attempted = [];
  let currentFailures = failures;

  const deterministicActions = runDeterministicPreFix({ cwd, failures: currentFailures });
  if (deterministicActions.length > 0) {
    attempted.push(...deterministicActions);
    const rerunAfterDeterministic = executeRun({
      mode: currentFailures.mode,
      changedFiles: currentFailures.changed_files || [],
      cwd,
      artifactDir: stateDir,
    });
    currentFailures = readJsonFileSync(path.join(stateDir, 'failures.json'));
    executeSummarize({ input: path.join(stateDir, 'failures.json'), cwd, outputDir: stateDir });

    attempted.push({
      strategy: 'deterministic_prefix_rerun',
      status: rerunAfterDeterministic.status,
      findings_after_rerun: currentFailures.findings.length,
    });
  }

  // Empty findings can accompany evaluation errors such as a changed snapshot.
  // Only a fresh, passing rerun can establish that deterministic repair worked.
  if (deterministicActions.length > 0 && currentFailures.status === 'pass') {
    return {
      attempted,
      currentFailures,
      shortCircuitPass: true,
    };
  }

  if (deterministicOnly) {
    attempted.push({
      strategy: 'deterministic_only_mode',
      note: 'Model-assisted repair skipped (--deterministic-only or Ollama not available).',
    });
    return {
      attempted,
      currentFailures,
      shortCircuitPass: false,
    };
  }

  const hasTypecheckFailure = currentFailures.findings.some((f) => f.gate === 'typecheck');
  const hasBuildFailure = currentFailures.findings.some((f) => f.gate === 'build');
  const hasLighthouseFailure = currentFailures.findings.some((f) => f.gate === 'lighthouse');
  const hasLintFailure = currentFailures.findings.some((f) => f.gate === 'lint');

  if (hasTypecheckFailure || hasBuildFailure || hasLighthouseFailure) {
    attempted.push({
      strategy: 'requires_manual_or_model_patch',
      note: 'No deterministic local fixer implemented for typecheck/build/lighthouse in MVP.',
    });
  }

  const modelPatchAllowed = hasLintFailure || hasTypecheckFailure;
  if (!modelPatchAllowed) {
    attempted.push({
      strategy: 'skip_model_patch',
      reason: 'no_patchable_gate_in_findings',
      gates: Array.from(new Set(currentFailures.findings.map((f) => f.gate))),
    });
    return {
      attempted,
      currentFailures,
      shortCircuitPass: false,
    };
  }

  const modelPolicy = getModelRoutingPolicy();
  const hintResult = runHintModel({ cwd, failures: currentFailures, policy: modelPolicy });
  attempted.push(hintResult);

  const patchResult = runPatchModel({
    cwd,
    failures: currentFailures,
    policy: modelPolicy,
    maxPatchLines: policy.maxPatchLines,
  });
  attempted.push(patchResult);

  return {
    attempted,
    currentFailures,
    shortCircuitPass: false,
  };
}

export function executeRepair({ input, maxAttempts, deterministicOnly = false, cwd = process.cwd(), outputDir }) {
  const stateDir = path.resolve(outputDir || path.join(cwd, '.quick-gate'));
  if (outputDir) {
    const relativeState = path.relative(path.resolve(cwd), stateDir);
    const insideWorktree = relativeState === ''
      || (!relativeState.startsWith(`..${path.sep}`) && relativeState !== '..' && !path.isAbsolute(relativeState));
    if (insideWorktree) {
      throw new Error('repair --output-dir must be outside the project worktree');
    }
  }
  const config = loadConfig(cwd);
  const policy = {
    maxAttempts: Number(maxAttempts || config.policy.maxAttempts || DEFAULT_POLICY.maxAttempts),
    maxPatchLines: Number(config.policy.maxPatchLines || DEFAULT_POLICY.maxPatchLines),
    abortOnNoImprovement: Number(config.policy.abortOnNoImprovement || DEFAULT_POLICY.abortOnNoImprovement),
    timeCapMs: Number(config.policy.timeCapMs || DEFAULT_POLICY.timeCapMs),
  };

  let failures = readJsonFileSync(path.resolve(cwd, input));
  let previousCount = failures.findings.length;
  let noImprovement = 0;
  const started = Date.now();
  const attempts = [];

  for (let attempt = 1; attempt <= policy.maxAttempts; attempt += 1) {
    if (Date.now() - started > policy.timeCapMs) {
      const escalation = {
        status: 'escalated',
        reason_code: ESCALATION_CODES.UNKNOWN_BLOCKER,
        message: `Time cap reached (${policy.timeCapMs}ms).`,
      };
      writeJsonFileSync(path.join(stateDir, 'escalation.json'), escalation);
      return escalation;
    }

    const backupDir = path.join(stateDir, `backup-attempt-${attempt}`);
    backupWorkspace(cwd, backupDir);

    const preActionDiff = diffSnapshot(cwd);
    const repairResult = runRepairActions(cwd, failures, policy, deterministicOnly, stateDir);
    const repairActions = repairResult.attempted;
    const failuresForRerun = repairResult.currentFailures;
    const postActionDiff = diffSnapshot(cwd);
    const patchLines = computePatchLines(preActionDiff, postActionDiff);

    if (patchLines > policy.maxPatchLines) {
      restoreWorkspace(cwd, backupDir);
      const escalation = {
        status: 'escalated',
        reason_code: ESCALATION_CODES.PATCH_BUDGET_EXCEEDED,
        message: `Patch budget exceeded at attempt ${attempt}: ${patchLines} > ${policy.maxPatchLines}`,
        evidence: {
          attempt,
          patch_lines: patchLines,
          max_patch_lines: policy.maxPatchLines,
          pre_action_diff_files: preActionDiff.size,
          post_action_diff_files: postActionDiff.size,
        },
      };
      writeJsonFileSync(path.join(stateDir, 'escalation.json'), escalation);
      return escalation;
    }

    if (repairResult.shortCircuitPass) {
      attempts.push({
        attempt,
        patch_lines: patchLines,
        before_findings: previousCount,
        after_findings: 0,
        improved: true,
        worsened: false,
        status: 'pass',
        actions: repairActions,
      });
      const result = { status: 'pass', attempts };
      writeJsonFileSync(path.join(stateDir, 'repair-report.json'), result);
      return result;
    }

    const rerun = executeRun({
      mode: failuresForRerun.mode,
      changedFiles: failuresForRerun.changed_files || [],
      cwd,
      artifactDir: stateDir,
    });
    failures = readJsonFileSync(path.join(stateDir, 'failures.json'));
    executeSummarize({ input: path.join(stateDir, 'failures.json'), cwd, outputDir: stateDir });

    const currentCount = failures.findings.length;
    const improved = currentCount < previousCount;
    const worsened = currentCount > previousCount;

    attempts.push({
      attempt,
      patch_lines: patchLines,
      before_findings: previousCount,
      after_findings: currentCount,
      improved,
      worsened,
      status: rerun.status,
      actions: repairActions,
    });

    if (rerun.status === 'pass') {
      const result = { status: 'pass', attempts };
      writeJsonFileSync(path.join(stateDir, 'repair-report.json'), result);
      return result;
    }

    if (worsened) {
      restoreWorkspace(cwd, backupDir);
    }

    if (improved) {
      noImprovement = 0;
    } else {
      noImprovement += 1;
    }

    previousCount = currentCount;

    if (noImprovement >= policy.abortOnNoImprovement) {
      const escalation = {
        status: 'escalated',
        reason_code: ESCALATION_CODES.NO_IMPROVEMENT,
        message: `No measurable improvement for ${noImprovement} consecutive attempt(s).`,
        evidence: {
          attempts,
          latest_failures_path: path.join(stateDir, 'failures.json'),
          latest_metadata_path: path.join(stateDir, 'run-metadata.json'),
        },
      };
      writeJsonFileSync(path.join(stateDir, 'escalation.json'), escalation);
      return escalation;
    }
  }

  const escalation = {
    status: 'escalated',
    reason_code: ESCALATION_CODES.UNKNOWN_BLOCKER,
    message: `Attempts exhausted (${policy.maxAttempts}).`,
    evidence: {
      latest_failures_path: path.join(stateDir, 'failures.json'),
    },
  };
  writeJsonFileSync(path.join(stateDir, 'escalation.json'), escalation);
  return escalation;
}
