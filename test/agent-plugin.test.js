import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const root = new URL('../', import.meta.url);
const readJson = (rel) => JSON.parse(fs.readFileSync(new URL(rel, root), 'utf8'));
const skillPath = 'skills/quick-gate-js/SKILL.md';

test('repository ships exactly one canonical SKILL.md', () => {
  const skills = fs.readdirSync(new URL('skills/', root), { recursive: true })
    .filter((p) => String(p).endsWith('SKILL.md'));
  assert.deepEqual(skills.map(String), ['quick-gate-js/SKILL.md']);
  const skill = fs.readFileSync(new URL(skillPath, root), 'utf8');
  assert.match(skill, /^---\nname: quick-gate-js\ndescription: /);
  assert.match(skill, /quick-gate@0\.2\.3/);
  assert.match(skill, /gate-result\/v1/);
});

test('all host manifests name the same root plugin', () => {
  const portable = readJson('plugin.json');
  const claude = readJson('.claude-plugin/plugin.json');
  const claudeMarket = readJson('.claude-plugin/marketplace.json');
  const codexMarket = readJson('.agents/plugins/marketplace.json');
  const gemini = readJson('gemini-extension.json');

  assert.equal(portable.$schema, 'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json');
  for (const manifest of [portable, claude, gemini]) {
    assert.equal(manifest.name, 'quick-gate-js');
    assert.equal(manifest.description, portable.description);
  }
  assert.equal(claude.version, portable.version);
  assert.equal(gemini.version, portable.version);
  assert.deepEqual(claudeMarket.plugins.map((p) => [p.name, p.source]), [['quick-gate-js', '.']]);
  assert.deepEqual(codexMarket.plugins.map((p) => [p.name, p.source.path]), [['quick-gate-js', './']]);
});
