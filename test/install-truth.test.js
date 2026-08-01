import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const readme = fs.readFileSync(new URL('../README.md', import.meta.url), 'utf8');

test('README distinguishes the npm release from the newer source CLI', () => {
  assert.match(readme, /npm install -g quick-gate@0\.2\.1/);
  assert.match(readme, /npm release[\s\S]*--mode canary/);
  assert.match(readme, /github:hermes-labs-ai\/quick-gate-js/);
  assert.match(readme, /public source[\s\S]*--mode quick/);
  assert.doesNotMatch(readme, /npm install -g quick-gate\s*\n/);
});
