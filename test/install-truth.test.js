import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const readme = fs.readFileSync(new URL('../README.md', import.meta.url), 'utf8');
const packageJson = JSON.parse(fs.readFileSync(new URL('../package.json', import.meta.url), 'utf8'));
const packageLock = JSON.parse(fs.readFileSync(new URL('../package-lock.json', import.meta.url), 'utf8'));

test('README presents one canonical mode interface with a compatibility alias', () => {
  assert.match(readme, /--mode quick\|full/);
  assert.match(readme, /canary[\s\S]*backward-compatible alias/);
  assert.doesNotMatch(readme, /--mode canary\|full/);
  assert.doesNotMatch(readme, /Current public source/);
});

test('release package and lockfile versions agree', () => {
  assert.equal(packageJson.version, '0.3.0');
  assert.equal(packageLock.version, packageJson.version);
  assert.equal(packageLock.packages[''].version, packageJson.version);
});

test('README release matrix labels the three version surfaces with their true, distinct values', () => {
  assert.match(readme, /\| npm runtime \(published package\) \| \[`0\.2\.3`\]/);
  assert.match(readme, /\| repository source \(this checkout\) \| `0\.3\.0`/);
  assert.match(readme, /\| agent plugin \(GitHub release\) \| \[`v0\.3\.1`\]/);
  assert.match(readme, /releases\/tag\/v0\.2\.3/);
  assert.match(readme, /releases\/tag\/v0\.3\.1/);
});

test('README warns that the checkout version is not an installable npm package version', () => {
  assert.match(readme, /Do not run `npm install -g quick-gate@0\.3\.0`/);
  assert.match(readme, /npm does not provide that version/);
});

test('the checkout version documented in the README matches package.json, and neither collides with the npm or plugin release versions', () => {
  assert.equal(packageJson.version, '0.3.0');
  assert.notEqual(packageJson.version, '0.2.3');
  assert.notEqual(packageJson.version, '0.3.1');
});
