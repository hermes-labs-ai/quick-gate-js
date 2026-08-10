import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { executeSummarize } from '../src/summarize-command.js';

test('external summaries cite external evidence paths', () => {
  const cwd = fs.mkdtempSync(path.join(os.tmpdir(), 'quick-gate-summary-source-'));
  const outputDir = fs.mkdtempSync(path.join(os.tmpdir(), 'quick-gate-summary-output-'));
  const failuresPath = path.join(outputDir, 'failures.json');
  fs.writeFileSync(failuresPath, JSON.stringify({
    run_id: 'run-1',
    mode: 'quick',
    status: 'fail',
    findings: [{
      id: 'lint-1',
      gate: 'lint',
      summary: 'lint failed',
      actual: 1,
      threshold: 0,
      files: [],
    }],
  }));

  const result = executeSummarize({ input: failuresPath, cwd, outputDir });
  const markdown = fs.readFileSync(result.briefMdPath, 'utf8');

  assert.match(markdown, new RegExp(failuresPath.replaceAll(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  assert.match(markdown, new RegExp(path.join(outputDir, 'run-metadata.json').replaceAll(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  assert.doesNotMatch(markdown, /\.quick-gate\/failures\.json/);
});
