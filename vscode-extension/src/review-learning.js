'use strict';

function createReviewLearning(vscode, hooks) {
  let request,
    collection,
    page,
    collections = [];
  const run = async (title, args) => {
    const value = await hooks.result(title, ['review-context', ...args], await hooks.current());
    await hooks.current();
    return value;
  };
  const emit = (value = {}) =>
    hooks.publish({
      view: 'reviewLearning',
      reviewRequest: request,
      reviewPage: page,
      reviewCollections: collections,
      ...value,
    });
  async function chooseSource() {
    const status = await hooks.result(
      'Reading selected repositories',
      ['status'],
      await hooks.current(),
    );
    const choice = await vscode.window.showQuickPick(
      Object.keys(status.coverage || {}).map((source) => ({ label: source, source })),
      { title: 'Repository to learn review practices from' },
    );
    return choice?.source;
  }
  async function handle(message) {
    if (!message.action.startsWith('review')) return false;
    if (message.action === 'reviewLearning') {
      await hooks.current();
      await emit();
      return true;
    }
    if (message.action === 'reviewPrepare') {
      const source = await chooseSource();
      if (!source) return true;
      const period = await vscode.window.showQuickPick(
        [
          { label: 'Last month', months: 1 },
          { label: 'Last three months', months: 3 },
          { label: 'Last six months', months: 6 },
        ],
        { title: 'Review learning period' },
      );
      if (!period) return true;
      request = await run('Preparing a client-gateway request', [
        'request',
        '--source=' + source,
        '--months=' + period.months,
      ]);
      page = undefined;
      await emit();
    } else if (message.action === 'reviewCopyPrompt') {
      if (!request) throw new Error('Prepare a collection request first.');
      const now = await run('Checking the collection scope', [
        'request',
        '--source=' + request.source,
        '--since=' + request.since,
        '--until=' + request.until,
      ]);
      if (now.request_id !== request.request_id)
        throw new Error('Scope changed. Prepare the request again.');
      await hooks.current();
      await vscode.env.clipboard.writeText(request.prompt);
      await emit({
        message:
          'Prompt copied. Paste it into your approved agent connected to the client gateway. No prompt has been sent.',
      });
    } else if (message.action === 'reviewImport') {
      if (!request) throw new Error('Prepare the matching collection request first.');
      const files = await vscode.window.showOpenDialog({
        canSelectMany: false,
        filters: { 'Gateway review JSON': ['json'] },
        title: 'Import evidence returned by your client gateway',
      });
      if (!files?.length) return true;
      const receipt = await run('Importing local review evidence', [
        'import',
        '--source=' + request.source,
        '--since=' + request.since,
        '--until=' + request.until,
        '--file=' + files[0].fsPath,
      ]);
      collection = receipt.batch_id;
      page = await run('Reading the review dossier', ['get', '--batch-id=' + collection]);
      await emit();
    } else if (message.action === 'reviewBrowse') {
      const source = await chooseSource();
      if (!source) return true;
      const catalog = await run('Finding local review collections', [
        'catalog',
        '--source=' + source,
      ]);
      collections = catalog.collections;
      const choice = await vscode.window.showQuickPick(
        collections.map((item) => ({
          label: `${item.repository} · ${item.since.slice(0, 10)} to ${item.until.slice(0, 10)}`,
          id: item.batch_id,
        })),
        { title: 'Choose a collected review dossier' },
      );
      if (!choice) return true;
      collection = choice.id;
      page = await run('Reading the review dossier', ['get', '--batch-id=' + collection]);
      await emit();
    } else if (message.action === 'reviewNext' || message.action === 'reviewFirst') {
      if (!collection || !page) throw new Error('Open a collection first.');
      const offset = message.action === 'reviewFirst' ? 0 : page.next_offset;
      if (!Number.isInteger(offset)) throw new Error('No further evidence page.');
      const next = await run('Reading review evidence', [
        'get',
        '--batch-id=' + collection,
        '--offset=' + offset,
      ]);
      if (next.fingerprint !== page.fingerprint)
        throw new Error('Collection changed. Reopen it before continuing.');
      page = next;
      await emit();
    } else throw new Error('Unknown review-learning action');
    return true;
  }
  return {
    handle,
    reset() {
      request = collection = page = undefined;
      collections = [];
    },
  };
}
module.exports = { createReviewLearning };
