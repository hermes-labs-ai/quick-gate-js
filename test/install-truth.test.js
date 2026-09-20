import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const readme = fs.readFileSync(new URL('../README.md', import.meta.url), 'utf8');
const packageJson = JSON.parse(fs.readFileSync(new URL('../package.json', import.meta.url), 'utf8'));
const packageLock = JSON.parse(fs.readFileSync(new URL('../package-lock.json', import.meta.url), 'utf8'));
const codemeta = JSON.parse(fs.readFileSync(new URL('../codemeta.json', import.meta.url), 'utf8'));
const portablePlugin = JSON.parse(fs.readFileSync(new URL('../plugin.json', import.meta.url), 'utf8'));
const claudePlugin = JSON.parse(fs.readFileSync(new URL('../.claude-plugin/plugin.json', import.meta.url), 'utf8'));
const geminiExtension = JSON.parse(fs.readFileSync(new URL('../gemini-extension.json', import.meta.url), 'utf8'));
const citation = fs.readFileSync(new URL('../CITATION.cff', import.meta.url), 'utf8');
const skill = fs.readFileSync(new URL('../skills/quick-gate-js/SKILL.md', import.meta.url), 'utf8');
const RELEASE_VERSION = '0.3.2';

test('README presents one canonical mode interface with a compatibility alias', () => {
  assert.match(readme, /--mode quick\|full/);
  assert.match(readme, /canary[\s\S]*backward-compatible alias/);
  assert.doesNotMatch(readme, /--mode canary\|full/);
  assert.doesNotMatch(readme, /Current public source/);
});

test('release package, lockfile, citation, and plugin metadata agree', () => {
  assert.equal(packageJson.version, RELEASE_VERSION);
  assert.equal(packageLock.version, packageJson.version);
  assert.equal(packageLock.packages[''].version, packageJson.version);
  assert.equal(codemeta.version, packageJson.version);
  assert.match(citation, new RegExp(`^version: "${RELEASE_VERSION.replaceAll('.', '\\.')}"$`, 'm'));
  for (const manifest of [portablePlugin, claudePlugin, geminiExtension]) {
    assert.equal(manifest.version, packageJson.version);
  }
  assert.match(skill, /quick-gate@0\.3\.2/);
  assert.doesNotMatch(skill, /quick-gate@0\.2\.3/);
});

test('README distinguishes the prepared release from public pre-release state', () => {
  assert.match(readme, /\| npm runtime \| `0\.3\.2` release target; \[`0\.2\.3`\][^\n]+remains public until publication completes/);
  assert.match(readme, /\| repository source \(this checkout\) \| `0\.3\.2`/);
  assert.match(readme, /\| agent plugin \| `0\.3\.2` release target; \[`v0\.3\.1`\][^\n]+remains the latest tag until release/);
  assert.match(readme, /releases\/tag\/v0\.3\.1/);
});

test('README does not infer publication from source metadata', () => {
  assert.match(readme, /Source metadata prepares `0\.3\.2`; it does not prove that npm publication or a GitHub release happened/);
  assert.match(readme, /npm view quick-gate version/);
  assert.match(readme, /After publication, verify the `0\.3\.2` artifact/);
});

test('the prepared checkout version advances beyond both prior public surfaces', () => {
  assert.equal(packageJson.version, RELEASE_VERSION);
  assert.notEqual(packageJson.version, '0.2.3');
  assert.notEqual(packageJson.version, '0.3.1');
});
