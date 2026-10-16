'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { createKnowledgeEditor } = require('../src/knowledge-editor');
const { engineSpec, run } = require('../src/runtime');

test('guided knowledge lifecycle uses current evidence, explicit review and exact revision conflicts', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'knowledge-editor-'));
  try {
    const source = path.join(root, 'api');
    await fs.mkdir(source);
    const file = path.join(source, 'main.py');
    await fs.writeFile(file, 'def retry(): return 1\n');
    const manifest = path.join(root, 'scope.json');
    await fs.writeFile(
      manifest,
      JSON.stringify({
        schema_version: 1,
        environment: 'test',
        workspace: 'guided',
        sources: [{ id: 'api', path: source }],
      }),
    );
    const selected = { manifest },
      messages = [],
      documents = [],
      decisions = [];
    let approve = false;
    const result = async (_title, args) =>
      JSON.parse(
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
    const hooks = {
      storage: root,
      current: async () => selected,
      result,
      publish: async (value) => messages.push(value),
      showJson: async () => {},
    };
    const api = {
      ViewColumn: { Beside: 2 },
      workspace: {
        openTextDocument: async (doc) => {
          documents.push(doc);
          return doc;
        },
      },
      window: {
        showTextDocument: async () => {},
        showWarningMessage: async (_message, _options, label) => {
          decisions.push(label);
          return approve ? label : undefined;
        },
      },
    };
    const editor = createKnowledgeEditor(api, hooks);
    const send = (action, args = {}) => editor.handle({ action, ...args });
    await result('', ['index']);
    await send('knowledge');
    assert.equal(messages.at(-1).knowledge.total, 0);
    await send('knowledgeNew');
    await send('knowledgeFindFiles', { kind: 'procedure', source: 'api', query: 'main.py' });
    assert.equal(messages.at(-1).knowledgeFiles.length, 1);
    await send('knowledgeChooseFile', { index: 0 });
    const draft = messages.at(-1).knowledgeDraft;
    assert.match(draft.id, /^knowledge-/);
    await send('knowledgeEvidence', { draft: true, citation: 0 });
    assert.match(documents[0].content, /def retry/);
    const value = {
      title: '<img src=x onerror=alert(1)> Retry recovery',
      statement: 'Retry with the existing key.',
      rationale: 'Keeps duplicate requests idempotent.',
      exceptions: ['Manual migration is exempt.'],
      details: {
        prerequisites: ['Read the request key'],
        steps: ['Retry with that key'],
        diagnostics: [{ if: 'Already processed', then: 'Return the stored response' }],
        verification: ['Confirm exactly one result'],
        rollback: ['Stop if the key is unavailable'],
      },
    };
    await assert.rejects(
      send('knowledgeSave', { value: { ...value, status: 'approved' } }),
      /Open a knowledge draft/,
    );
    await send('knowledgeSave', { value });
    let record = messages.at(-1).knowledge.records[0];
    assert.equal(record.status, 'proposed');
    assert.equal(record.title, value.title);
    assert.deepEqual(await fs.readdir(path.join(root, 'drafts')), []);
    assert.equal(
      (await result('', ['knowledge', 'lookup', '--kind=procedure', '--source=api'])).items.length,
      0,
    );
    await send('knowledgeDecide', { index: 0, decision: 'approve' });
    assert.equal((await result('', ['knowledge', 'catalog'])).records[0].status, 'proposed');
    approve = true;
    await send('knowledgeDecide', { index: 0, decision: 'approve' });
    assert.equal(messages.at(-1).knowledge.records[0].status, 'approved');
    assert.equal(decisions.length, 2);
    await send('knowledgeEdit', { index: 0 });
    // Another window creates revision 2 while this editor still holds revision 1.
    const other = createKnowledgeEditor(api, hooks);
    await other.handle({ action: 'knowledge' });
    await other.handle({ action: 'knowledgeEdit', index: 0 });
    await other.handle({
      action: 'knowledgeSave',
      value: { statement: 'A concurrent replacement proposal.' },
    });
    await assert.rejects(
      send('knowledgeSave', { value: { statement: 'Must not overwrite revision 2.' } }),
      /Knowledge changed in another window/,
    );
    assert.equal((await result('', ['knowledge', 'catalog'])).records.length, 2);
    await fs.writeFile(file, 'def retry(): return 2\n');
    await send('knowledge');
    assert.ok(messages.at(-1).knowledge.records.every((row) => !row.fresh));
    await assert.rejects(send('knowledgeEvidence', { index: 0, citation: 0 }), /Evidence changed/);
    await result('', ['index']);
    await send('knowledge');
    const latest = messages.at(-1).knowledge.records.findIndex((row) => row.revision === 2);
    await send('knowledgeRefreshDraft', { index: latest });
    assert.match(messages.at(-1).knowledgeDraft.statement, /^DRAFT:/);
    await send('knowledgeSave', {
      value: { statement: 'Reviewed against the changed implementation.' },
    });
    record = messages.at(-1).knowledge.records.find((row) => row.revision === 3);
    assert.equal(record.status, 'proposed');
    assert.equal(record.fresh, true);
  } finally {
    await fs.rm(root, { recursive: true, force: true });
  }
});
