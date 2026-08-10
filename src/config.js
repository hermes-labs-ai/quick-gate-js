import path from 'node:path';
import { DEFAULT_POLICY } from './constants.js';
import { fileExists, readJsonFileSync } from './fs-utils.js';
import { configIdentity } from './contract.js';

const DEFAULT_CONFIG = {
  policy: { ...DEFAULT_POLICY, commandTimeoutMs: 120_000, gateTimeoutMs: 300_000, outputCapBytes: 64 * 1024 },
  commands: {},
  lighthouse: {
    thresholds: {
      performance: 0.8,
      accessibility: 0.8,
      'best-practices': 0.8,
      seo: 0.8,
    },
  },
  allowUnsafeShellCommands: false,
};

function withIdentity(config) {
  const identity = configIdentity(config);
  return {
    ...config,
    config_version: identity.version,
    config_digest: identity.digest,
  };
}

export function loadConfig(cwd = process.cwd()) {
  const configPath = path.join(cwd, 'quick-gate.config.json');
  if (!fileExists(configPath)) {
    return withIdentity({ ...DEFAULT_CONFIG, source: 'defaults' });
  }

  const userConfig = readJsonFileSync(configPath);
  return withIdentity({
    policy: { ...DEFAULT_CONFIG.policy, ...(userConfig.policy || {}) },
    commands: { ...(userConfig.commands || {}) },
    lighthouse: {
      ...DEFAULT_CONFIG.lighthouse,
      ...(userConfig.lighthouse || {}),
      thresholds: { ...DEFAULT_CONFIG.lighthouse.thresholds, ...(userConfig.lighthouse?.thresholds || {}) },
    },
    allowUnsafeShellCommands: userConfig.allowUnsafeShellCommands === true,
    source: configPath,
  });
}
