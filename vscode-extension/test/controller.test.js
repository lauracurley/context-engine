'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { createWorkbench } = require('../src/controller');
const { engineSpec, run } = require('../src/runtime');
const { PackStore } = require('../src/packs');
const { execFileSync } = require('node:child_process');

test('real engine workbench: search, pin, handoff, stale rejection, refresh and profile revision', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'workbench-'));
  try {
    const source = path.join(root, 'api');
    await fs.mkdir(source);
    await fs.writeFile(path.join(source, 'AGENTS.md'), 'Run relevant tests.\n');
    const file = path.join(source, 'main.py');
    await fs.writeFile(file, 'def run_queue():\n    return "QUEUE_SENTINEL"\n');
    await fs.writeFile(
      path.join(source, 'README.md'),
      '# Queue architecture\n\nThe queue accepts work. Read [the handler](main.py).\n',
    );
    const git = (...args) => execFileSync('git', ['-C', source, ...args], { stdio: 'pipe' });
    git('init', '-q');
    git('add', '.');
    git(
      '-c',
      'user.name=Synthetic',
      '-c',
      'user.email=synthetic@example.invalid',
      'commit',
      '-qm',
      'fixture',
    );
    const manifest = path.join(root, 'team.json');
    await fs.writeFile(
      manifest,
      JSON.stringify({
        schema_version: 1,
        environment: 'client_a',
        workspace: 'checkout',
        sources: [{ id: 'api', path: 'api' }],
      }),
    );
    const policy = path.join(root, 'policy.json');
    await fs.writeFile(
      policy,
      JSON.stringify({
        schema_version: 1,
        storage_roots: [root],
        source_roots: [root],
        allow_history: false,
        allow_remote_git: false,
        allow_embeddings: false,
      }),
      { mode: 0o600 },
    );
    let selection = { manifest, label: 'client_a / checkout' },
      receive,
      onDispose;
    const lifecycle = [];
    const messages = [],
      prompts = [],
      opened = [],
      inputs = ['Explain queue processing'];
    const context = {
      globalStorageUri: { fsPath: path.join(root, 'storage') },
      asAbsolutePath: (p) => path.resolve(__dirname, '..', p),
      subscriptions: [],
    };
    const api = {
      ViewColumn: { One: 1, Beside: 2 },
      env: { clipboard: { writeText: async (text) => prompts.push(text) } },
      Uri: { file: (value) => value },
      Range: class {
        constructor(start, _startColumn, end, _endColumn) {
          this.start = start;
          this.end = end;
        }
      },
      Selection: class {},
      workspace: {
        openTextDocument: async (file) => ({ file, text: await fs.readFile(file, 'utf8') }),
      },
      window: {
        showTextDocument: async (doc) => ({ revealRange: (range) => opened.push({ doc, range }) }),
        showInputBox: async () => inputs.shift(),
        showWarningMessage: async (_text, _options, action) => action,
        createWebviewPanel: () => ({
          webview: {
            cspSource: 'vscode-resource:',
            asWebviewUri: (value) => value,
            postMessage: async (message) => {
              lifecycle.push(message.type);
              if (!['busy', 'idle'].includes(message.type)) messages.push(message);
            },
            onDidReceiveMessage: (fn) => {
              receive = fn;
              return { dispose() {} };
            },
          },
          reveal() {},
          dispose() {
            onDispose();
          },
          onDidDispose: (fn) => {
            onDispose = fn;
            return { dispose() {} };
          },
        }),
      },
    };
    const result = async (_, args, selected = selection) =>
      JSON.parse(
        await run(
          engineSpec(
            'python3',
            path.resolve(__dirname, '../backend/launch.py'),
            selected.manifest,
            path.join(root, 'state'),
            ['--policy', policy, ...args],
          ),
        ),
      );
    const workbench = createWorkbench(api, context, {
      guard() {},
      config: () => selection,
      result,
      assertMutable() {},
      storeScope: async (value) => {
        await result('', ['status'], value);
        selection = { ...value, label: 'client_b / checkout' };
      },
      showJson: async (value) => prompts.push(value),
      agent: async () => {
        throw new Error('Managed handoff must not launch a terminal');
      },
      managed: () => true,
    });
    await result('', ['index']);
    await workbench.open('code');
    await receive({ action: 'architecture', source: 'api' });
    const guide = messages.at(-1).result;
    assert.equal(guide.reader, true);
    assert.match(guide.markdown, /The queue accepts work/);
    const handler = guide.items.findIndex((item) => item.path === 'main.py');
    await receive({ action: 'openSource', index: handler });
    assert.equal(opened.at(-1).doc.file, await fs.realpath(file));
    await receive({ action: 'search', query: 'main.py', mode: 'files', view: 'code' });
    const fileLocation = messages.at(-1).result.items[0];
    assert.equal(fileLocation.lines, undefined);
    await receive({ action: 'pin', index: 0 });
    let pack = messages.at(-1).pack;
    assert.match(pack.items[0].item.text, /QUEUE_SENTINEL/);
    assert.deepEqual(pack.items[0].item.lines, [1, 2]);
    // Old versions could persist a filename pin without any line range.
    const store = new PackStore(path.join(context.globalStorageUri.fsPath, 'packs'), pack.scope);
    pack = await store.load(pack.id);
    pack.items[0].item = fileLocation;
    await store.save(pack);
    await receive({ action: 'selectPack', id: pack.id });
    await receive({ action: 'validatePack' });
    assert.match(messages.at(-1).message, /Code citations are current/);
    await receive({ action: 'refreshPack' });
    assert.match(messages.at(-1).pack.items[0].item.text, /QUEUE_SENTINEL/);
    await receive({ action: 'removePin', id: messages.at(-1).pack.items[0].id });
    await receive({ action: 'search', query: 'main.py', mode: 'files', view: 'code' });
    await receive({ action: 'openSource', index: 0 });
    assert.equal(opened.at(-1).doc.file, await fs.realpath(file));
    assert.equal(opened.at(-1).range.start, 0);
    assert.equal(opened.at(-1).range.end, 1);
    await receive({ action: 'preview', index: 0 });
    assert.match(messages.at(-1).result.items[0].text, /QUEUE_SENTINEL/);
    await receive({ action: 'search', query: 'main.py', mode: 'files', view: 'code' });
    const originalCode = await fs.readFile(file, 'utf8');
    await fs.writeFile(file, 'def changed(): return 2\n');
    await result('', ['index']);
    await receive({ action: 'preview', index: 0 });
    assert.match(messages.at(-1).message, /Expected content hash changed/);
    await receive({ action: 'pin', index: 0 });
    assert.match(messages.at(-1).message, /stale/);
    await receive({ action: 'packs' });
    assert.equal(messages.at(-1).pack.items.length, 0);
    await fs.writeFile(file, originalCode);
    await result('', ['index']);
    await workbench.open('code', 'QUEUE_SENTINEL');
    await receive({ action: 'ready' });
    assert.equal(messages.at(-1).result.items[0].path, 'main.py');
    assert.equal(messages.at(-1).search.query, 'QUEUE_SENTINEL');
    await workbench.open('code', '--not-a-command');
    assert.equal(messages.at(-1).result.items.length, 0);
    await receive({ action: 'back' });
    assert.equal(messages.at(-1).search.query, 'QUEUE_SENTINEL');
    assert.equal(messages.at(-1).result.items[0].path, 'main.py');
    await assert.rejects(workbench.open('code', 'x'.repeat(4001)), /4000/);
    await receive({ action: 'search', query: 'QUEUE_SENTINEL', mode: 'lexical', view: 'code' });
    assert.equal(messages.at(-1).result.items[0].path, 'main.py');
    await receive({ action: 'structure', mode: 'definitions', index: 0 });
    assert.equal(messages.at(-1).result.items[0].name, 'run_queue');
    assert.equal(messages.at(-1).result.items[0].resolution, 'declaration');
    await receive({ action: 'structure', mode: 'callers', index: 0 });
    assert.equal(messages.at(-1).result.items.length, 0);
    await receive({ action: 'search', query: 'QUEUE_SENTINEL', mode: 'lexical', view: 'code' });
    await receive({ action: 'graph', index: 0 });
    assert.equal(messages.at(-1).result.retrieval, 'graph');
    assert.equal(messages.at(-1).result.hops, 1);
    await receive({ action: 'search', query: 'QUEUE_SENTINEL', mode: 'lexical', view: 'code' });
    await receive({ action: 'instructions', index: 0 });
    assert.equal(messages.at(-1).result.items[0].path, 'AGENTS.md');
    assert.deepEqual(messages.at(-1).result.items[0].applies_to, ['main.py']);
    await receive({ action: 'preview', index: 0 });
    assert.match(messages.at(-1).result.items[0].text, /Run relevant tests/);
    await receive({ action: 'search', query: 'QUEUE_SENTINEL', mode: 'lexical', view: 'code' });
    await receive({ action: 'pin', index: 0 });
    assert.equal(messages.at(-1).pack.items.length, 1);
    await receive({ action: 'handoff' });
    assert.equal(prompts.length, 0);
    assert.equal(messages.at(-1).view, 'handoff');
    assert.match(messages.at(-1).handoff.prompt, /task context pack/);
    assert.ok((await fs.stat(messages.at(-1).handoff.file)).isFile());
    await receive({ action: 'copyHandoff' });
    assert.match(prompts[0], /task context pack/);
    await receive({ action: 'history' });
    assert.match(messages.at(-1).message, /managed deployment/);
    await fs.writeFile(file, 'def run_queue():\n    return "CHANGED_QUEUE"\n');
    await receive({ action: 'search', query: 'CHANGED_QUEUE', view: 'code', mode: 'lexical' });
    assert.equal(messages.at(-1).result.state, 'stale');
    await receive({ action: 'handoff' });
    assert.equal(prompts.length, 1);
    assert.match(messages.at(-1).message, /stale/);
    await receive({ action: 'copyHandoff' });
    assert.equal(prompts.length, 1);
    assert.match(messages.at(-1).message, /stale|changed/);
    await receive({ action: 'refreshCode' });
    assert.equal(messages.at(-1).result.state, 'ready');
    assert.equal(messages.at(-1).search.query, 'CHANGED_QUEUE');
    assert.equal(messages.at(-1).result.items[0].path, 'main.py');
    await receive({ action: 'refreshPack' });
    assert.match(messages.at(-1).pack.items[0].item.text, /CHANGED_QUEUE/);
    await receive({ action: 'exportPack' });
    assert.equal(prompts.length, 2);
    await receive({ action: 'prepareBrief', source: 'api', base: 'HEAD' });
    assert.equal(messages.at(-1).changeBrief.state, 'ready');
    assert.ok(messages.at(-1).changeBrief.items.some((row) => row.category === 'changed_code'));
    await receive({ action: 'pinBrief' });
    assert.ok(messages.at(-1).pack.items.some((row) => row.kind === 'brief'));
    await receive({ action: 'handoff' });
    assert.equal(messages.at(-1).view, 'handoff');
    await receive({ action: 'search', query: 'CHANGED_QUEUE', mode: 'lexical', view: 'code' });
    await receive({ action: 'structure', mode: 'definitions', index: 0 });
    await receive({ action: 'pin', index: 0 });
    await fs.writeFile(
      path.join(source, 'consumer.py'),
      'from main import run_queue\nrun_queue()\n',
    );
    await result('', ['index']);
    await receive({ action: 'handoff' });
    assert.equal(prompts.length, 2);
    assert.match(messages.at(-1).message, /Derived structure changed/);
    const profile = JSON.parse(await fs.readFile(manifest, 'utf8'));
    const originalManifest = await fs.readFile(manifest, 'utf8');
    profile.crawler = { interval: 90, history_interval: 7200, history_months: 3 };
    await receive({ action: 'saveProfile', value: profile });
    assert.equal(selection.manifest, manifest);
    assert.equal(await fs.readFile(manifest, 'utf8'), originalManifest);
    assert.equal((await result('', ['schedule'])).config.interval, 90);
    await receive({ action: 'packs' });
    assert.ok(messages.at(-1).packs.some((row) => row.id === pack.id));
    assert.equal(lifecycle.at(-1), 'idle');
    profile.environment = 'client_b';
    await receive({ action: 'saveProfile', value: profile });
    assert.notEqual(selection.manifest, manifest);
    const saved = JSON.parse(await fs.readFile(selection.manifest, 'utf8'));
    assert.equal(saved.sources[0].path, source);
    assert.equal(JSON.parse(await fs.readFile(manifest, 'utf8')).environment, 'client_a');
    await receive({ action: 'packs' });
    assert.equal(messages.at(-1).packs.length, 0);
    // A manifest edited outside the workbench cannot reuse a pack or source selection.
    await fs.writeFile(selection.manifest, JSON.stringify({ ...saved, environment: 'client_c' }));
    await receive({ action: 'handoff' });
    assert.match(messages.at(-1).message, /profile changed/);
    workbench.dispose();
  } finally {
    await fs.rm(root, { recursive: true, force: true });
  }
});
