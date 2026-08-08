import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const readme = fs.readFileSync(new URL('../README.md', import.meta.url), 'utf8');
const packageJson = JSON.parse(fs.readFileSync(new URL('../package.json', import.meta.url), 'utf8'));
const packageLock = JSON.parse(fs.readFileSync(new URL('../package-lock.json', import.meta.url), 'utf8'));

test('README presents one canonical mode interface with a compatibility alias', () => {
  assert.match(readme, /npm install -g quick-gate@0\.2\.3/);
  assert.match(readme, /--mode quick\|full/);
  assert.match(readme, /canary[\s\S]*backward-compatible alias/);
  assert.doesNotMatch(readme, /--mode canary\|full/);
  assert.doesNotMatch(readme, /Current public source/);
});

test('release package and lockfile versions agree', () => {
  assert.equal(packageJson.version, '0.2.3');
  assert.equal(packageLock.version, packageJson.version);
  assert.equal(packageLock.packages[''].version, packageJson.version);
});
