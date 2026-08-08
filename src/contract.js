import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

export const GATE_RESULT_VERSION = 'gate-result/v1';

function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, canonicalize(value[key])]),
    );
  }
  return value;
}

export function stableStringify(value) {
  return JSON.stringify(canonicalize(value));
}

export function sha256(value) {
  const hash = crypto.createHash('sha256');
  hash.update(typeof value === 'string' || Buffer.isBuffer(value) ? value : stableStringify(value));
  return hash.digest('hex');
}

function safeRelativePath(cwd, rawPath) {
  const absolute = path.isAbsolute(rawPath) ? path.resolve(rawPath) : path.resolve(cwd, rawPath);
  const relative = path.relative(cwd, absolute);
  if (relative === '' || (!relative.startsWith(`..${path.sep}`) && relative !== '..' && !path.isAbsolute(relative))) {
    return relative || '.';
  }
  return null;
}

export function snapshotInput({ cwd, paths = [] }) {
  const checkedPaths = Array.from(new Set(paths.map(String)))
    .map((rawPath) => safeRelativePath(cwd, rawPath))
    .filter(Boolean)
    .sort();

  const entries = checkedPaths.map((relativePath) => {
    const fullPath = path.join(cwd, relativePath);
    try {
      const stat = fs.statSync(fullPath);
      if (!stat.isFile()) {
        return { path: relativePath, type: stat.isDirectory() ? 'directory' : 'other' };
      }
      return { path: relativePath, type: 'file', sha256: sha256(fs.readFileSync(fullPath)), size: stat.size };
    } catch (error) {
      return {
        path: relativePath,
        type: 'missing',
        error: error?.code || 'UNKNOWN',
      };
    }
  });

  return {
    checkedPaths,
    snapshotDigest: sha256({ checked_paths: checkedPaths, entries }),
    entries,
  };
}

export function configIdentity(config) {
  const normalized = {
    policy: config.policy || {},
    commands: config.commands || {},
    lighthouse: config.lighthouse || {},
  };
  return {
    version: 'config/v1',
    source: config.source === 'defaults' || !config.source ? (config.source || 'provided') : path.basename(String(config.source)),
    digest: sha256(normalized),
  };
}

export function packageVersion(cwd) {
  try {
    const pkg = JSON.parse(fs.readFileSync(path.join(cwd, 'package.json'), 'utf8'));
    return String(pkg.version || 'unknown');
  } catch {
    return 'unknown';
  }
}

export function buildGateResult({
  status,
  snapshotDigest,
  checkedPaths,
  checks,
  findings,
  commandVersions,
  elapsedMs,
  outputTruncated,
  errors = [],
  ...extensions
}) {
  return {
    schema: GATE_RESULT_VERSION,
    // Deprecated compatibility discriminator. Remove in the next breaking release.
    version: GATE_RESULT_VERSION,
    status,
    snapshot_digest: snapshotDigest,
    checked_paths: checkedPaths,
    checks,
    findings,
    command_versions: commandVersions,
    elapsed_ms: elapsedMs,
    output_truncated: Boolean(outputTruncated),
    errors,
    ...extensions,
  };
}
