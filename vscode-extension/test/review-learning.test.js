'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { createReviewLearning } = require('../src/review-learning');
const { engineSpec, run } = require('../src/runtime');

test('gateway UI prepares an explicit prompt and reads a real local dossier without direct fetching', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'review-learning-'));
  try {
    await fs.mkdir(path.join(root, 'api'));
    await fs.writeFile(path.join(root, 'api/main.py'), 'def scoped(): return 1\n');
    const manifest = path.join(root, 'scope.json');
    await fs.writeFile(
      manifest,
      JSON.stringify({
        schema_version: 1,
        environment: 'test',
        workspace: 'review-learning',
        sources: [{ id: 'api', path: 'api', github: 'example/fictional' }],
      }),
    );
    const selected = { manifest },
      messages = [],
      calls = [],
      copied = [];
    let scoped = true,
      cancel = false;
    const current = async () => {
      if (!scoped) throw new Error('Workspace profile changed');
      return selected;
    };
    const result = async (_title, args) => {
      calls.push(args);
      return JSON.parse(
        await run(
          engineSpec(
            'python3',
            path.resolve(__dirname, '../backend/launch.py'),
            manifest,
            path.join(root, 'state'),
            args,
          ),
        ),
      );
    };
    const file = path.join(root, 'gateway.json');
    const api = {
      env: { clipboard: { writeText: async (text) => copied.push(text) } },
      window: {
        showQuickPick: async (items) => (cancel ? undefined : items[0]),
        showOpenDialog: async () => (cancel ? undefined : [{ fsPath: file }]),
      },
    };
    const editor = createReviewLearning(api, {
      current,
      result,
      publish: async (v) => messages.push(v),
    });
    await result('', ['index']);
    assert.equal(await editor.handle({ action: 'knowledge' }), false);
    assert.equal(await editor.handle({ action: 'reviewLearning' }), true);
    await editor.handle({ action: 'reviewPrepare' });
    const request = messages.at(-1).reviewRequest;
    assert.equal(request.repository, 'example/fictional');
    assert.equal(copied.length, 0, 'Preparation does not copy or send client scope');
    await editor.handle({ action: 'reviewCopyPrompt' });
    assert.equal(copied.length, 1);
    assert.match(copied[0], /already-connected MCP gateway/);
    assert.match(copied[0], /Do not approve/);
    const events = Array.from({ length: 7 }, (_, n) => ({
      kind: 'review_comment',
      id: String(n + 1),
      pull: 7,
      body: '<script>untrusted evidence</script>',
      path: 'main.py',
      author: 'reviewer',
      commit: '',
      updated: request.since,
      url: 'https://github.com/example/fictional/pull/7',
    }));
    await fs.writeFile(
      file,
      JSON.stringify({
        schema_version: 1,
        request_id: request.request_id,
        events,
        gaps: ['Thread resolution unavailable'],
        complete: false,
      }),
    );
    await editor.handle({ action: 'reviewImport' });
    assert.equal(messages.at(-1).reviewPage.total_events, 7);
    assert.equal(messages.at(-1).reviewPage.items.length, 5);
    assert.equal(messages.at(-1).reviewPage.complete, false);
    await editor.handle({ action: 'reviewNext' });
    assert.equal(messages.at(-1).reviewPage.items.length, 2);
    await assert.rejects(editor.handle({ action: 'reviewNext' }), /No further/);
    await editor.handle({ action: 'reviewFirst' });
    assert.equal(messages.at(-1).reviewPage.items.length, 5);
    await editor.handle({ action: 'reviewBrowse' });
    assert.equal(messages.at(-1).reviewPage.total_events, 7);
    cancel = true;
    const before = calls.length;
    await editor.handle({ action: 'reviewImport' });
    assert.equal(calls.length, before, 'Cancelled file dialog has no writes');
    scoped = false;
    await assert.rejects(editor.handle({ action: 'reviewCopyPrompt' }), /profile changed/);
    assert.equal(copied.length, 1);
    editor.reset();
    scoped = true;
    await assert.rejects(editor.handle({ action: 'reviewCopyPrompt' }), /Prepare/);
    await assert.rejects(editor.handle({ action: 'reviewApprove' }), /Unknown/);
    assert.ok(calls.every((args) => ['index', 'status', 'review-context'].includes(args[0])));
  } finally {
    await fs.rm(root, { recursive: true, force: true });
  }
});

test('gateway UI discards results after a scope change and rejects changed evidence pagination', async () => {
  let changed = false,
    inFlight = false,
    fingerprint = 'one';
  const messages = [],
    copied = [];
  const api = {
    env: { clipboard: { writeText: async (text) => copied.push(text) } },
    window: { showQuickPick: async (items) => items[0] },
  };
  const hooks = {
    current: async () => {
      if (changed) throw new Error('Scope changed');
      return {};
    },
    publish: async (v) => messages.push(v),
    result: async (_title, args) => {
      if (inFlight) changed = true;
      if (args[0] === 'status') return { coverage: { api: {} } };
      if (args[1] === 'request')
        return { source: 'api', request_id: 'one', since: 'start', until: 'end', prompt: 'scoped' };
      if (args[1] === 'catalog')
        return {
          collections: [
            { repository: 'fictional/repo', since: 'start', until: 'end', batch_id: 'batch' },
          ],
        };
      return { fingerprint, next_offset: 5, items: [] };
    },
  };
  const editor = createReviewLearning(api, hooks);
  inFlight = true;
  await assert.rejects(editor.handle({ action: 'reviewPrepare' }), /Scope changed/);
  assert.equal(messages.length, 0);
  assert.equal(copied.length, 0);
  inFlight = changed = false;
  await editor.handle({ action: 'reviewBrowse' });
  const before = messages.length;
  fingerprint = 'edited';
  await assert.rejects(editor.handle({ action: 'reviewNext' }), /Collection changed/);
  assert.equal(messages.length, before);
});
