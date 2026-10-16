'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const { randomUUID } = require('node:crypto');

const KINDS = ['practice', 'architecture', 'convention', 'decision', 'procedure'];
const EDITABLE = [
  'title',
  'statement',
  'rationale',
  'prefix',
  'languages',
  'tasks',
  'exceptions',
  'details',
];

function createKnowledgeEditor(vscode, hooks) {
  let records = [],
    files = [],
    draft,
    expectedRevision = 0,
    fileKind,
    fileSource;
  let filter = { source: '', query: '', offset: 0 };
  const run = async (title, args) => hooks.result(title, args, await hooks.current());
  const emit = (value) => hooks.publish({ view: 'knowledge', ...value });
  async function open(message) {
    const value = await run('Loading reviewed team knowledge', [
      'knowledge',
      'catalog',
      '--source=' + filter.source,
      '--query=' + filter.query,
      '--offset=' + filter.offset,
    ]);
    records = value.records;
    draft = undefined;
    await emit({ knowledge: value, knowledgeFilter: filter, message });
  }
  function recordAt(index) {
    if (!Number.isInteger(index) || !records[index])
      throw new Error('Reload knowledge and select a current record.');
    return records[index];
  }
  async function handle(message) {
    const action = message.action;
    if (!action.startsWith('knowledge')) return false;
    if (action === 'knowledge') await open();
    else if (action === 'knowledgeFilter') {
      if (
        typeof message.source !== 'string' ||
        typeof message.query !== 'string' ||
        message.query.length > 1000 ||
        !Number.isInteger(message.offset) ||
        message.offset < 0
      )
        throw new Error('Invalid knowledge filter');
      filter = { source: message.source, query: message.query, offset: message.offset };
      await open();
    } else if (action === 'knowledgeNew') {
      draft = undefined;
      files = [];
      await emit({ knowledgeNew: true });
    } else if (action === 'knowledgeFindFiles') {
      if (
        !KINDS.includes(message.kind) ||
        typeof message.source !== 'string' ||
        !message.source ||
        typeof message.query !== 'string' ||
        message.query.length > 1000
      )
        throw new Error('Choose a knowledge type, repository and file filter.');
      fileKind = message.kind;
      fileSource = message.source;
      const value = await run('Finding supporting files', [
        'discover',
        '--mode=files',
        '--source=' + fileSource,
        '--limit=50',
        '--byte-budget=32000',
        '--',
        message.query,
      ]);
      files = value.state === 'ready' ? value.items : [];
      await emit({
        knowledgeNew: true,
        knowledgeFiles: files,
        fileKind,
        fileSource,
        fileQuery: message.query,
        message: files.length
          ? 'Choose a supporting file. Narrow the filter if it is not in the first 50 results.'
          : 'No indexed files match. Refresh code or change the file filter.',
      });
    } else if (action === 'knowledgeChooseFile') {
      if (!Number.isInteger(message.index) || !files[message.index])
        throw new Error('Search for supporting files again.');
      const file = files[message.index];
      draft = await run('Preparing knowledge draft', [
        'knowledge',
        'template',
        '--kind=' + fileKind,
        '--source=' + fileSource,
        '--path=' + file.path,
      ]);
      draft.id = 'knowledge-' + randomUUID();
      draft.title = draft.statement = draft.rationale = '';
      for (const key of Object.keys(draft.details || {})) draft.details[key] = [];
      expectedRevision = 0;
      await emit({
        knowledgeDraft: draft,
        message:
          'Draft only. Saving creates a proposal; a separate review makes it available to agents.',
      });
    } else if (action === 'knowledgeEdit' || action === 'knowledgeRefreshDraft') {
      const row = recordAt(message.index);
      if (action === 'knowledgeRefreshDraft') {
        const result = await run('Preparing re-review draft', [
          'knowledge',
          'refresh-draft',
          '--id=' + row.id,
          '--revision=' + row.revision,
        ]);
        draft = result.draft;
        expectedRevision = result.expected_revision;
      } else {
        draft = Object.fromEntries(
          Object.entries(row).filter(
            ([key]) =>
              !['revision', 'status', 'fresh', 'availability', 'expected_revision'].includes(key),
          ),
        );
        expectedRevision = row.expected_revision;
        const defaults = {
          convention: { examples: [] },
          decision: { alternatives: [], tradeoffs: [], revisit_when: [] },
          procedure: {
            prerequisites: [],
            steps: [],
            diagnostics: [],
            verification: [],
            rollback: [],
          },
        };
        draft.details = { ...defaults[draft.kind], ...draft.details };
      }
      await emit({
        knowledgeDraft: draft,
        message:
          action === 'knowledgeRefreshDraft'
            ? 'Evidence hashes were updated. Inspect current source and refine the DRAFT statement; new hashes do not validate the conclusion.'
            : 'Edit a replacement proposal. The approved revision stays active until the replacement is reviewed.',
      });
    } else if (action === 'knowledgeSave') {
      if (
        !draft ||
        !message.value ||
        typeof message.value !== 'object' ||
        Object.keys(message.value).some((key) => !EDITABLE.includes(key))
      )
        throw new Error('Open a knowledge draft before saving.');
      const value = { ...draft, ...message.value };
      const selected = await hooks.current();
      const directory = path.join(hooks.storage, 'drafts');
      await fs.mkdir(directory, { recursive: true, mode: 0o700 });
      const file = path.join(directory, randomUUID() + '.json');
      await fs.writeFile(file, JSON.stringify(value), { flag: 'wx', mode: 0o600 });
      try {
        await hooks.result(
          'Saving unapproved proposal',
          ['knowledge', 'propose', '--file=' + file, '--revision=' + expectedRevision],
          selected,
        );
      } finally {
        await fs.rm(file, { force: true });
      }
      await open(
        'Proposal saved. Review its statement, scope, exceptions and supporting evidence before approval.',
      );
    } else if (action === 'knowledgeDecide') {
      const row = recordAt(message.index);
      if (!['approve', 'reject', 'retire'].includes(message.decision))
        throw new Error('Invalid review action');
      const label = { approve: 'Approve', reject: 'Reject', retire: 'Retire' }[message.decision];
      const choice = await vscode.window.showWarningMessage(
        `${label} “${row.title}” revision ${row.revision}? Review its scope, exceptions and evidence. Approval replaces prior approved guidance for this record.`,
        { modal: true },
        label,
      );
      if (choice === label) {
        await run('Recording human review', [
          'knowledge',
          message.decision,
          '--id=' + row.id,
          '--revision=' + row.revision,
        ]);
        await open(`${label} decision recorded.`);
      }
    } else if (action === 'knowledgeEvidence') {
      const row = message.draft ? draft : recordAt(message.index);
      const citation = row?.citations?.[message.citation];
      if (!citation) throw new Error('Choose supporting evidence.');
      // Verify cited identity, and keep raw paths out of webview-controlled filesystem actions.
      const value = await run('Reading knowledge evidence', [
        'read',
        citation.source,
        citation.path,
        '--expected-hash=' + citation.hash,
        '--byte-budget=32000',
      ]);
      if (value.state !== 'ready' || !value.items.length)
        throw new Error(
          'Evidence changed or is unavailable. Refresh code and prepare a re-review draft.',
        );
      const doc = await vscode.workspace.openTextDocument({
        language: 'plaintext',
        content: `${citation.source} / ${citation.path}\n\n${value.items[0].text}\n\n${value.next_line ? 'Excerpt ends here; inspect the source for the remaining lines.' : ''}`,
      });
      await vscode.window.showTextDocument(doc, {
        preview: true,
        viewColumn: vscode.ViewColumn.Beside,
      });
    } else if (action === 'knowledgeHistory') {
      const row = recordAt(message.index);
      await hooks.showJson(
        await run('Loading revision history', ['knowledge', 'history', '--id=' + row.id]),
      );
    } else throw new Error('Unknown knowledge action');
    return true;
  }
  return {
    handle,
    reset() {
      records = [];
      files = [];
      draft = undefined;
      filter = { source: '', query: '', offset: 0 };
    },
  };
}
module.exports = { createKnowledgeEditor };
