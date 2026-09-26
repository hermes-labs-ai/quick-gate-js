import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const packageJson = JSON.parse(fs.readFileSync(new URL('../package.json', import.meta.url), 'utf8'));
const packageLock = JSON.parse(fs.readFileSync(new URL('../package-lock.json', import.meta.url), 'utf8'));
const codemeta = JSON.parse(fs.readFileSync(new URL('../codemeta.json', import.meta.url), 'utf8'));
const portablePlugin = JSON.parse(fs.readFileSync(new URL('../plugin.json', import.meta.url), 'utf8'));
const claudePlugin = JSON.parse(fs.readFileSync(new URL('../.claude-plugin/plugin.json', import.meta.url), 'utf8'));
const geminiExtension = JSON.parse(fs.readFileSync(new URL('../gemini-extension.json', import.meta.url), 'utf8'));
const citation = fs.readFileSync(new URL('../CITATION.cff', import.meta.url), 'utf8');
const skill = fs.readFileSync(new URL('../skills/quick-gate-js/SKILL.md', import.meta.url), 'utf8');
const RELEASE_VERSION = '0.3.2';



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





test('the prepared checkout version advances beyond both prior public surfaces', () => {
  assert.equal(packageJson.version, RELEASE_VERSION);
  assert.notEqual(packageJson.version, '0.2.3');
  assert.notEqual(packageJson.version, '0.3.1');
});
