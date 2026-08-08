import { spawn } from 'node:child_process';

const request = JSON.parse(process.env.QUICK_GATE_COMMAND_REQUEST || '{}');
const outputLimit = Number(request.maxOutputBytes || 64 * 1024);
const timeoutMs = Number(request.timeoutMs || 120_000);
const startedAt = Date.now();

function capture(limit) {
  let chunks = [];
  let size = 0;
  let truncated = false;
  return {
    append(chunk) {
      if (truncated) return;
      const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(String(chunk));
      const remaining = limit - size;
      if (buffer.length > remaining) {
        if (remaining > 0) chunks.push(buffer.subarray(0, remaining));
        size = limit;
        truncated = true;
        return;
      }
      chunks.push(buffer);
      size += buffer.length;
    },
    value() {
      const text = Buffer.concat(chunks).toString('utf8');
      return truncated ? `${text}\n...[truncated]` : text;
    },
    get truncated() {
      return truncated;
    },
  };
}

function terminateProcessTree(child, signal) {
  if (process.platform !== 'win32' && child.pid) {
    try {
      process.kill(-child.pid, signal);
      return;
    } catch {
      // The group may have already exited; try the direct child below.
    }
  }
  try {
    child.kill(signal);
  } catch {
    // The child may have already exited.
  }
}

const stdout = capture(outputLimit);
const stderr = capture(outputLimit);
let timedOut = false;
let timeoutKillTimer;
let finished = false;

let child;
try {
  child = spawn(request.file, request.args || [], {
    cwd: request.cwd,
    env: request.env,
    shell: Boolean(request.shell),
    detached: process.platform !== 'win32',
    stdio: ['pipe', 'pipe', 'pipe'],
  });
} catch (error) {
  process.stdout.write(JSON.stringify({
    exit_code: null,
    signal: null,
    error_code: error?.code || 'SPAWN_ERROR',
    timed_out: false,
    stdout: '',
    stderr: '',
    output_truncated: false,
    duration_ms: Date.now() - startedAt,
  }));
  process.exit(0);
}

if (request.input !== undefined && request.input !== null) child.stdin.end(String(request.input));
else child.stdin.end();
child.stdout.on('data', (chunk) => stdout.append(chunk));
child.stderr.on('data', (chunk) => stderr.append(chunk));
child.on('error', (error) => {
  if (finished) return;
  finished = true;
  clearTimeout(timer);
  process.stdout.write(JSON.stringify({
    exit_code: null,
    signal: null,
    error_code: error?.code || 'SPAWN_ERROR',
    timed_out: timedOut,
    stdout: stdout.value(),
    stderr: stderr.value(),
    output_truncated: stdout.truncated || stderr.truncated,
    duration_ms: Date.now() - startedAt,
  }));
  process.exit(0);
});

const timer = setTimeout(() => {
  timedOut = true;
  terminateProcessTree(child, 'SIGTERM');
  timeoutKillTimer = setTimeout(() => terminateProcessTree(child, 'SIGKILL'), 250);
}, timeoutMs);

child.on('close', (code, signal) => {
  if (finished) return;
  finished = true;
  clearTimeout(timer);
  if (timeoutKillTimer) clearTimeout(timeoutKillTimer);
  process.stdout.write(JSON.stringify({
    exit_code: typeof code === 'number' ? code : null,
    signal: signal || null,
    error_code: null,
    timed_out: timedOut,
    stdout: stdout.value(),
    stderr: stderr.value(),
    output_truncated: stdout.truncated || stderr.truncated,
    duration_ms: Date.now() - startedAt,
  }));
});
