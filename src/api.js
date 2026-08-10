import { loadConfig } from './config.js';
import { runDeterministicGates } from './gates.js';

/**
 * Evaluate the configured gates without writing Quick Gate artifacts.
 * The underlying project commands remain responsible for their own behavior;
 * Quick Gate does not repair files, install packages, or mutate the environment.
 */
export function evaluateGates({ mode = 'quick', cwd = process.cwd(), changedFiles = [], config, ...options } = {}) {
  const resolvedConfig = config || loadConfig(cwd);
  return runDeterministicGates({ mode, cwd, changedFiles, config: resolvedConfig, ...options });
}

export { runCommand } from './exec.js';
