'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { PackStore, scopeKey, pin, assemble, bytes } = require('../src/packs');
const { validateProfile } = require('../src/profiles');
const { html } = require('../src/workbench');

test('pack storage separates clients and invalidates changed manifest content', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'packs-'));
  try {
    const manifest = path.join(dir, 'team.json');
    await fs.writeFile(manifest, '{"client":"one"}');
    const first = await scopeKey(manifest),
      store = new PackStore(dir, first),
      pack = store.create('Explain queue retries');
    pin(
      pack,
      'code',
      { source: 'api', path: 'tasks.py', hash: 'abc', lines: [1, 3], text: 'CLIENT_ONE_SENTINEL' },
      'generation',
    );
    await store.save(pack);
    assert.equal((await store.list()).length, 1);
    await fs.writeFile(manifest, '{"client":"two"}');
    const second = new PackStore(dir, await scopeKey(manifest));
    assert.deepEqual(await second.list(), []);
    await assert.rejects(second.save(pack), /scope mismatch/);
    await assert.rejects(store.load('../escape'), /Invalid pack ID/);
    assert.equal((await fs.stat(store.file(pack.id))).mode & 0o777, 0o600);
  } finally {
    await fs.rm(dir, { recursive: true, force: true });
  }
});

test('stale saves cannot overwrite pack edits from another window', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'packs-'));
  try {
    const store = new PackStore(dir, 'a'.repeat(64)),
      pack = store.create('Task');
    await store.save(pack);
    const stale = await store.load(pack.id);
    pack.task = 'New task';
    await store.save(pack);
    stale.task = 'Lost update';
    await assert.rejects(store.save(stale), /another window/);
    assert.equal((await store.load(pack.id)).task, 'New task');
  } finally {
    await fs.rm(dir, { recursive: true, force: true });
  }
});

test('packs deduplicate exact pins and fit the entire handoff JSON budget', () => {
  const store = new PackStore('/tmp/test', 'b'.repeat(64)),
    pack = store.create('English task');
  const item = { source: 'api', path: 'file.py', hash: 'hash', lines: [1, 2], text: 'evidence' };
  pin(pack, 'code', item, 'g');
  pin(pack, 'code', item, 'g');
  assert.equal(pack.items.length, 1);
  for (let i = 0; i < 12; i++)
    pin(pack, 'code', { ...item, path: i + '.py', text: '文'.repeat(100) }, 'g');
  const result = assemble(pack, 1024);
  assert.ok(bytes(result.value) <= 1024);
  assert.equal(result.used_bytes, bytes(result.value));
  assert.ok(result.value.omitted_items > 0);
  assert.throws(() => assemble(pack, 10), /budget/);
});

test('profile revisions rebase local roots, retain adapters, and reject invalid inputs', () => {
  const original = {
    schema_version: 1,
    environment: 'client_a',
    workspace: 'feature',
    sources: [{ id: 'api', path: '../api' }],
    embeddings: { provider: 'sentence-transformers', model: 'existing' },
  };
  const copied = validateProfile(original, '/client/config');
  assert.equal(copied.sources[0].path, '/client/api');
  assert.equal(original.sources[0].path, '../api');
  assert.deepEqual(copied.embeddings, original.embeddings);
  for (const change of [
    { environment: undefined },
    { sources: [] },
    {
      sources: [
        { id: 'api', path: '/a' },
        { id: 'api', path: '/b' },
      ],
    },
    { crawler: { interval: -1 } },
    { history: { gateway_command: ['relative.sh'] } },
  ])
    assert.throws(() => validateProfile({ ...original, ...change }, '/client'));
});

test('webview shell disallows inline content and remote scripts', () => {
  const page = html(
    { cspSource: 'vscode-resource:', asWebviewUri: (value) => value },
    '/extension',
    { Uri: { file: (value) => value } },
  );
  assert.match(page, /default-src 'none'/);
  assert.match(page, /script-src 'nonce-/);
  assert.ok(!page.includes('unsafe-inline'));
  assert.ok(!page.includes('https://'));
  assert.match(page, /lang="en"/);
});
