import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

export const GATE_RESULT_VERSION = 'gate-result/v1';
const SNAPSHOT_SKIP_DIRS = new Set(['.git', '.quick-gate', '.pygate', '__pycache__', '.venv', 'venv', 'node_modules']);

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
  const requestedPaths = Array.from(new Set(paths.map(String)))
    .map((rawPath) => safeRelativePath(cwd, rawPath))
    .filter(Boolean)
    .sort();

  const expandedPaths = new Set();
  for (const requestedPath of requestedPaths) {
    const fullPath = path.join(cwd, requestedPath);
    const files = filesForSnapshot(fullPath);
    for (const filePath of files.length > 0 ? files : [fullPath]) {
      const relativePath = safeRelativePath(cwd, filePath);
      if (relativePath) expandedPaths.add(relativePath);
    }
  }

  const entries = Array.from(expandedPaths).sort().map((relativePath) => {
    const fullPath = path.resolve(cwd, relativePath);
    try {
      const stat = fs.statSync(fullPath);
      if (!stat.isFile()) {
        return { path: relativePath, exists: false };
      }
      return { path: relativePath, exists: true, size: stat.size, sha256: sha256(fs.readFileSync(fullPath)) };
    } catch {
      return { path: relativePath, exists: false };
    }
  });
  const checkedPaths = entries.map((entry) => entry.path);

  return {
    checkedPaths,
    snapshotDigest: sha256(entries),
    entries,
  };
}

function filesForSnapshot(startPath) {
  try {
    const stat = fs.lstatSync(startPath);
    if (stat.isFile() || stat.isSymbolicLink()) return [startPath];
    if (!stat.isDirectory()) return [startPath];
  } catch {
    return [startPath];
  }
  const files = [];
  const visit = (directory) => {
    const children = fs.readdirSync(directory, { withFileTypes: true })
      .sort((left, right) => (left.name === right.name ? 0 : left.name < right.name ? -1 : 1));
    for (const child of children) {
      const childPath = path.join(directory, child.name);
      if (child.isDirectory()) {
        if (SNAPSHOT_SKIP_DIRS.has(child.name) || child.name.startsWith('.')) continue;
        visit(childPath);
      } else {
        files.push(childPath);
      }
    }
  };
  visit(startPath);
  return files;
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
