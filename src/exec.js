import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const workerPath = path.join(path.dirname(fileURLToPath(import.meta.url)), 'command-worker.js');
export const DEFAULT_TIMEOUT_MS = 120_000;
export const DEFAULT_OUTPUT_LIMIT_BYTES = 64 * 1024;

function normalizeCommand(command, unsafeShell) {
  if (Array.isArray(command) && command.length > 0) {
    return { file: String(command[0]), args: command.slice(1).map(String), shell: false };
  }
  if (command && typeof command === 'object' && !Array.isArray(command)) {
    if (Array.isArray(command.args) && command.file) {
      const shell = Boolean(command.shell);
      if (shell && command.unsafeShell !== true && unsafeShell !== true) return null;
      return { file: String(command.file), args: command.args.map(String), shell };
    }
    if (typeof command.command === 'string') {
      return normalizeCommand(command.command, command.unsafeShell === true || unsafeShell === true);
    }
  }
  if (typeof command === 'string' && unsafeShell === true) {
    return { file: command, args: [], shell: true };
  }
  return null;
}

function commandLabel(command, spec) {
  if (typeof command === 'string') return command;
  if (Array.isArray(command)) return command.map(String).join(' ');
  return spec ? [spec.file, ...spec.args].join(' ') : String(command);
}

export function runCommand(command, options = {}) {
  const startedAt = Date.now();
  const cwd = options.cwd || process.cwd();
  const spec = normalizeCommand(command, options.unsafeShell === true);
  const label = commandLabel(command, spec);
  const timeoutMs = Math.max(1, Number(options.timeoutMs || DEFAULT_TIMEOUT_MS));
  const maxOutputBytes = Math.max(0, Number(options.maxOutputBytes || DEFAULT_OUTPUT_LIMIT_BYTES));

  if (!spec) {
    return {
      command: label,
      argv: null,
      cwd,
      started_at: new Date(startedAt).toISOString(),
      duration_ms: 0,
      exit_code: null,
      signal: null,
      error_code: 'UNSAFE_COMMAND_REQUIRES_ARGV',
      timed_out: false,
      output_truncated: false,
      stdout: '',
      stderr: 'Command strings are disabled by default; pass argv or unsafeShell: true.',
    };
  }

  const request = {
    file: spec.file,
    args: spec.args,
    shell: spec.shell,
    cwd,
    env: { ...process.env, ...(options.env || {}) },
    input: options.input,
    timeoutMs,
    maxOutputBytes,
  };
  const result = spawnSync(process.execPath, [workerPath], {
    cwd,
    env: { ...process.env, QUICK_GATE_COMMAND_REQUEST: JSON.stringify(request) },
    encoding: 'utf8',
    timeout: timeoutMs + 2_000,
    maxBuffer: Math.max(1024 * 1024, maxOutputBytes * 4),
  });

  let payload;
  try {
    payload = JSON.parse(String(result.stdout || '').trim());
  } catch {
    payload = {
      exit_code: null,
      signal: null,
      error_code: result.error?.code || 'COMMAND_WORKER_PROTOCOL_ERROR',
      timed_out: result.error?.code === 'ETIMEDOUT',
      output_truncated: false,
      stdout: '',
      stderr: String(result.stderr || result.error?.message || 'Command worker failed'),
      duration_ms: Date.now() - startedAt,
    };
  }

  return {
    command: label,
    argv: spec.shell ? null : [spec.file, ...spec.args],
    cwd,
    started_at: new Date(startedAt).toISOString(),
    duration_ms: Date.now() - startedAt,
    exit_code: payload.exit_code,
    signal: payload.signal,
    error_code: payload.error_code,
    timed_out: Boolean(payload.timed_out),
    output_truncated: Boolean(payload.output_truncated),
    stdout: payload.stdout || '',
    stderr: payload.stderr || '',
  };
}
