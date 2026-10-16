'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const { PackStore, scopeKey, citations, pin, assemble } = require('./packs');
const { validateProfile, scopeContent } = require('./profiles');
const { createKnowledgeEditor } = require('./knowledge-editor');
const { createReviewLearning } = require('./review-learning');
const { html } = require('./workbench');

function createWorkbench(vscode, context, hooks) {
  let panel,
    key,
    selection,
    data,
    evidenceKind = 'code',
    activePack,
    busy = false;
  let budget = 12000,
    initialView = 'code';
  let initialQuery, lastSearch, dataSearch;
  let capabilities,
    lastBrief,
    handoff,
    dirtyDraft = false;
  const back = [];
  const storage = hooks.storage || context.globalStorageUri.fsPath;
  async function current() {
    hooks.guard();
    const selected = hooks.config();
    if (!selected) throw new Error('Select or create a workspace profile first');
    const now = await scopeKey(selected.manifest);
    if (key && now !== key)
      throw new Error('Workspace profile changed. Reopen the workbench to use its new scope.');
    return selected;
  }
  const store = () => new PackStore(path.join(storage, 'packs'), key);
  async function publish(value) {
    if (value.view) dirtyDraft = false;
    if (panel)
      await panel.webview.postMessage({
        scope: selection.label,
        capabilities,
        canGoBack: back.length > 0,
        ...value,
      });
  }
  async function present(kind, result) {
    if (data) {
      back.push({ kind: evidenceKind, result: data, search: dataSearch });
      if (back.length > 20) back.shift();
    }
    evidenceKind = kind;
    data = result;
    dataSearch = kind === 'code' ? lastSearch : undefined;
    await publish({
      view: kind === 'code' ? 'code' : kind,
      result,
      search: dataSearch,
    });
  }
  function itemAt(index) {
    if (!Number.isInteger(index) || index < 0 || index >= (data?.items || []).length)
      throw new Error('Evidence selection is no longer available');
    return data.items[index];
  }
  async function readCitation(cite, strict = true, expand = false) {
    if (!cite || !cite.source || !cite.path || !cite.hash)
      throw new Error('This evidence has no readable code citation');
    // Filename discovery (including old saved pins) names a whole file.
    // Expand it through the same bounded, hash-checked read as a code location.
    const lines = cite.lines === undefined ? [1, 80] : cite.lines;
    if (
      !Array.isArray(lines) ||
      lines.length !== 2 ||
      !lines.every(Number.isInteger) ||
      lines[0] < 1 ||
      lines[1] < lines[0]
    )
      throw new Error('This evidence has no readable code citation');
    const start = expand ? Math.max(1, lines[0] - 5) : lines[0];
    const end = expand ? start + 79 : Math.min(lines[1], start + 199);
    const args = [
      'read',
      cite.source,
      cite.path,
      '--line-start',
      String(start),
      '--line-end',
      String(end),
      '--token-budget',
      '32000',
    ];
    if (strict) args.push('--expected-hash', cite.hash);
    return hooks.result('Reading cited source', args, selection);
  }
  async function verify(pack) {
    const gaps = [];
    const status = await hooks.result('Checking pack freshness', ['status'], selection);
    for (const entry of pack.items) {
      if (entry.kind === 'brief') {
        const value = await readBrief(entry.item.source, entry.item.base, entry.item.byteBudget);
        if (value.state !== 'ready' || JSON.stringify(value) !== JSON.stringify(entry.item.brief))
          gaps.push('Change context has changed; refresh the brief in this pack.');
        continue;
      }
      if (entry.kind === 'history') continue; // Retained, dated snapshots, not claims of current code or remote access.
      if (status.state !== 'ready') {
        gaps.push(`${entry.id.slice(0, 8)}: code index is ${status.state}`);
        continue;
      }
      if (
        (entry.kind === 'architecture' || entry.item.resolution) &&
        entry.generation !== status.index?.generation
      ) {
        gaps.push('Derived structure changed; refresh or remove the pinned item');
        continue;
      }
      for (const cite of citations(entry.item)) {
        const read = await readCitation(cite);
        if (read.state !== 'ready' || !read.items?.length)
          gaps.push(`${cite.source}/${cite.path}: changed or unavailable`);
      }
    }
    await current();
    return [...new Set(gaps)];
  }
  async function showPacks(message) {
    const packs = await store().list();
    if (activePack) activePack = await store().load(activePack.id);
    await publish({
      view: 'packs',
      packs,
      pack: activePack,
      budget: activePack ? assemble(activePack, budget) : undefined,
      message,
    });
  }
  async function newPack() {
    const task = await vscode.window.showInputBox({
      title: 'Task for this context pack',
      prompt: 'Describe the task in English',
      validateInput: (s) => (s.trim() && s.length <= 4000 ? null : 'Enter 1–4000 characters'),
    });
    if (!task) return;
    activePack = store().create(task);
    await store().save(activePack);
    await showPacks();
  }
  async function needPack() {
    if (!activePack) await newPack();
    if (!activePack) throw new Error('Create or select a task pack first');
    return activePack;
  }
  async function loadProfile() {
    const profile = JSON.parse(await fs.readFile(selection.manifest, 'utf8'));
    const schedule = await hooks.result('Reading refresh preferences', ['schedule'], selection);
    await publish({ view: 'profile', profile, schedule: schedule.config });
  }
  const reviewLearning = createReviewLearning(vscode, { ...hooks, current, publish });
  const knowledge = createKnowledgeEditor(vscode, { ...hooks, storage, current, publish });
  async function loadCapabilities() {
    const status = await hooks.result('Checking selected repositories', ['status'], selection);
    capabilities = {
      sources: Object.entries(status.coverage || {}).map(([id, row]) => ({
        id,
        root: row.root,
        files: row.files,
        excluded: row.excluded,
        errors: row.errors,
      })),
      semantic: status.capabilities?.semantic_search === true,
      history: status.capabilities?.history_retrieval ?? !hooks.managed?.(),
      state: status.state,
    };
    return status;
  }
  const readBrief = (source, base, byteBudget = 8000) =>
    hooks.result(
      'Preparing change context',
      ['change-brief', '--source=' + source, '--base=' + base, '--byte-budget=' + byteBudget],
      selection,
    );
  async function handle(message) {
    if (!message || typeof message.action !== 'string' || JSON.stringify(message).length > 100000)
      throw new Error('Invalid workbench action');
    await current();
    const action = message.action;
    if (
      message.discardDraft === true ||
      (dirtyDraft && !['knowledgeSave', 'knowledgeEvidence'].includes(action))
    ) {
      const choice = await vscode.window.showWarningMessage(
        'Discard the unsaved knowledge edits in this form?',
        { modal: true },
        'Discard edits',
      );
      if (choice !== 'Discard edits')
        return publish({ type: 'notice', message: 'Your draft is still open.' });
    }
    if (!capabilities) await loadCapabilities();
    if (
      (action === 'history' || (action === 'search' && message.view === 'history')) &&
      !capabilities.history
    )
      throw new Error('History retrieval is unavailable in this managed deployment.');
    if (await reviewLearning.handle(message)) return;
    if (await knowledge.handle(message)) return;
    if (action === 'back') {
      const previous = back.pop();
      if (previous) {
        evidenceKind = previous.kind;
        data = previous.result;
        dataSearch = previous.search;
        if (dataSearch) lastSearch = dataSearch;
        await publish({ view: evidenceKind, result: data, search: dataSearch });
      }
      return;
    }
    if (action === 'health') {
      const status = await loadCapabilities();
      return publish({ view: 'health', health: status, hostHealth: hooks.health?.() });
    }
    if (action === 'startWatcher') {
      await hooks.startWatcher();
      return handle({ action: 'health' });
    }
    if (action === 'stopWatcher') {
      await hooks.stopWatcher();
      return publish({
        type: 'notice',
        message: 'Stopping code refresh in this window. Check again to confirm it ended.',
      });
    }
    if (action === 'openIde') return hooks.codexIde();
    if (action === 'brief') return publish({ view: 'brief', briefForm: true });
    if (action === 'prepareBrief') {
      if (
        !capabilities.sources.some((s) => s.id === message.source) ||
        typeof message.base !== 'string'
      )
        throw new Error('Choose a repository and Git base.');
      const result = await readBrief(message.source, message.base);
      lastBrief = {
        source: message.source,
        base: result.base_revision || message.base,
        byteBudget: 8000,
        brief: result,
        title: 'Change context for ' + message.source,
      };
      return publish({
        view: 'brief',
        briefForm: true,
        briefSource: message.source,
        briefBase: message.base,
        changeBrief: result,
      });
    }
    if (action === 'pinBrief') {
      if (!lastBrief || lastBrief.brief.state !== 'ready' || !lastBrief.brief.items.length)
        throw new Error('Prepare a current change brief first.');
      const pack = await needPack();
      pin(pack, 'brief', lastBrief, lastBrief.brief.generation);
      await store().save(pack);
      return showPacks('Change context added. Reported coverage limits travel with the brief.');
    }
    if (action === 'copyHandoff' || action === 'openHandoff') {
      if (!handoff) throw new Error('Prepare a handoff first.');
      const gaps = await verify(handoff.pack);
      if (gaps.length) throw new Error(gaps.join('; '));
      if (action === 'copyHandoff') {
        await vscode.env.clipboard.writeText(handoff.prompt);
        return publish({
          view: 'handoff',
          handoff,
          message:
            'Prompt copied. Paste it into your approved agent in the generated Context Engine workspace.',
        });
      }
      const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(handoff.file));
      return vscode.window.showTextDocument(doc, {
        preview: true,
        viewColumn: vscode.ViewColumn.Beside,
      });
    }
    if (action === 'ready')
      return handle(
        initialQuery !== undefined
          ? { action: 'search', view: 'code', query: initialQuery }
          : { action: initialView },
      );
    if (action === 'refreshCode') {
      await hooks.result('Refreshing selected code', ['index'], selection);
      await current();
      await loadCapabilities();
      if (['health', 'brief', 'architecture'].includes(message.returnView))
        return handle({ action: message.returnView, source: message.source });
      return handle(lastSearch || { action: 'code' });
    }
    if (action === 'code')
      return present('code', { items: [], state: 'Search the selected workspace' });
    if (action === 'profile') return loadProfile();
    if (action === 'architecture') {
      const source = message.source || capabilities?.sources?.[0]?.id;
      if (!source)
        return present('architecture', {
          reader: true,
          items: [],
          state: 'unindexed',
          gaps: ['Select a repository and refresh code first.'],
        });
      if (!capabilities.sources.some((entry) => entry.id === source))
        throw new Error('Select a repository in this workspace');
      return present(
        'architecture',
        await hooks.result(
          'Reading repository architecture',
          ['knowledge', 'wiki', '--kind=architecture', '--source=' + source],
          selection,
        ),
      );
    }
    if (action === 'architectureEvidence')
      return present(
        'architecture',
        await hooks.result(
          'Loading supporting structure',
          ['overview', '--token-budget', '12000'],
          selection,
        ),
      );
    if (action === 'history')
      return present(
        'history',
        await hooks.result(
          'Loading history',
          ['search-history', '', '--token-budget', '12000'],
          selection,
        ),
      );
    if (action === 'search') {
      if (typeof message.query !== 'string' || message.query.length > 4000)
        throw new Error('Query must be at most 4000 characters');
      const args = [];
      if (message.view === 'history') {
        if (!['all', 'pr', 'commit', 'holder'].includes(message.kind))
          throw new Error('Invalid history kind');
        args.push('search-history', '--kind', message.kind, '--token-budget', '12000');
      } else args.push('discover', '--mode', message.mode || 'auto', '--token-budget', '12000');
      for (const [field, flag] of [
        ['source', '--source'],
        ['glob', '--path-glob'],
      ]) {
        if (message[field]) {
          if (typeof message[field] !== 'string' || message[field].length > 4000)
            throw new Error('Invalid search filter');
          if (field !== 'glob' || message.view !== 'history') args.push(flag, message[field]);
        }
      }
      args.push('--', message.query);
      if (message.view !== 'history')
        lastSearch = {
          action: 'search',
          view: 'code',
          query: message.query,
          mode: message.mode || 'auto',
          source: message.source || '',
          glob: message.glob || '',
        };
      return present(
        message.view === 'history' ? 'history' : 'code',
        await hooks.result('Finding context', args, selection),
      );
    }
    if (action === 'expand') {
      const item = itemAt(message.index);
      return present(
        'architecture',
        await hooks.result(
          'Expanding architecture',
          ['overview', '--node', item.expand || item.id, '--token-budget', '12000'],
          selection,
        ),
      );
    }
    if (action === 'graph') {
      const cite = citations(itemAt(message.index))[0];
      if (!cite) throw new Error('Select evidence with a source citation');
      return present(
        'architecture',
        await hooks.result(
          'Finding graph neighbors',
          [
            'related',
            '--mode=graph',
            '--limit=5',
            '--byte-budget=8000',
            '--',
            cite.source,
            cite.path,
          ],
          selection,
        ),
      );
    }
    if (action === 'structure') {
      const item = itemAt(message.index),
        cite = citations(item)[0];
      if (!cite) throw new Error('Select evidence with a source citation');
      const mode = message.mode;
      if (!['definitions', 'references', 'callers', 'dependencies', 'impact'].includes(mode))
        throw new Error('Unknown navigation mode');
      const args = [
        'structure',
        `--mode=${mode}`,
        `--source=${cite.source}`,
        '--token-budget=12000',
      ];
      if (['references', 'callers'].includes(mode)) {
        const symbol = item.name || item.symbol;
        if (!symbol)
          throw new Error('Find a definition first or use Structural Navigation from the sidebar');
        args.push(`--symbol=${symbol}`);
      } else args.push(`--path=${cite.path}`);
      return present('code', await hooks.result('Loading structural navigation', args, selection));
    }
    if (action === 'instructions') {
      const cite = citations(itemAt(message.index))[0];
      if (!cite) throw new Error('Select evidence with a source file citation');
      return present(
        'code',
        await hooks.result(
          'Resolving repository instructions',
          [
            'instructions',
            `--source=${cite.source}`,
            `--path=${cite.path}`,
            '--token-budget=12000',
          ],
          selection,
        ),
      );
    }
    if (action === 'preview' || action === 'openSource') {
      const item = itemAt(message.index),
        cite = citations(item)[0];
      const result = await readCitation(cite, true, action === 'preview');
      if (result.state !== 'ready' || !result.items.length)
        throw new Error((result.gaps || ['Source is unavailable']).join('; '));
      if (action === 'preview') return present('code', result);
      const status = await hooks.result('Checking source location', ['status'], selection);
      // Paths come from the host-validated manifest; webview messages never supply filesystem paths.
      const profile = JSON.parse(await fs.readFile(selection.manifest, 'utf8'));
      const source = profile.sources.find((s) => s.id === cite.source);
      if (!source?.path) return present('code', result); // Managed source paths stay internal; preview is sufficient.
      const root = await fs.realpath(path.resolve(path.dirname(selection.manifest), source.path));
      const file = await fs.realpath(path.resolve(root, cite.path));
      const relative = path.relative(root, file);
      if (
        relative === '..' ||
        relative.startsWith('..' + path.sep) ||
        path.isAbsolute(relative) ||
        status.state !== 'ready'
      )
        throw new Error('Citation is outside the current source');
      const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(file));
      const editor = await vscode.window.showTextDocument(doc, { preview: true });
      const lines = result.items[0].lines;
      const range = new vscode.Range(lines[0] - 1, 0, lines[1] - 1, 0);
      editor.selection = new vscode.Selection(range.start, range.end);
      editor.revealRange(range);
      return;
    }
    if (action === 'saveProfile') {
      hooks.assertMutable();
      // Preserve integrations unsupported by this editor and resolve relative paths before moving a copy.
      const profile = validateProfile(message.value, path.dirname(selection.manifest));
      const original = JSON.parse(await fs.readFile(selection.manifest, 'utf8'));
      if (
        scopeContent(profile, path.dirname(selection.manifest)) ===
        scopeContent(original, path.dirname(selection.manifest))
      ) {
        const args = ['schedule'];
        for (const field of ['interval', 'history_interval', 'history_months'])
          if (profile.crawler?.[field] !== undefined)
            args.push('--' + field.replaceAll('_', '-') + '=' + profile.crawler[field]);
        await hooks.result('Saving refresh preferences', args, selection);
        await loadProfile();
        return publish({
          type: 'notice',
          message:
            'Preferences saved. Your index, reviewed knowledge and task packs are preserved.',
        });
      }
      const choice = await vscode.window.showWarningMessage(
        'This changes repository scope or retrieval configuration and creates a separate index and task-pack space. Your previous scope and reviewed knowledge remain available through Select Manifest.',
        { modal: true },
        'Create new scope',
      );
      if (choice !== 'Create new scope') return;
      if (profile.embeddings?.cache_folder)
        profile.embeddings.cache_folder = path.resolve(
          path.dirname(selection.manifest),
          profile.embeddings.cache_folder,
        );
      const dir = path.join(storage, 'manifests');
      await fs.mkdir(dir, { recursive: true, mode: 0o700 });
      const manifest = path.join(
        dir,
        `${profile.environment}-${profile.workspace}-${randomUUID()}.json`,
      );
      await fs.writeFile(manifest, JSON.stringify(profile, null, 2), { flag: 'wx', mode: 0o600 });
      try {
        await hooks.storeScope({ manifest });
      } catch (e) {
        await fs.unlink(manifest);
        throw e;
      }
      panel.dispose();
      panel = undefined;
      key = undefined;
      activePack = undefined;
      return open('profile', undefined, true);
    }
    if (action === 'packs') return showPacks();
    if (action === 'newPack') return newPack();
    if (action === 'selectPack') {
      activePack = await store().load(message.id);
      return showPacks();
    }
    if (action === 'pin') {
      let item = itemAt(message.index),
        generation = data.generation;
      const kind = evidenceKind;
      if (kind !== 'history' && data.state !== 'ready')
        throw new Error('Only fresh evidence can be pinned');
      if (kind === 'code' && !item.lines) {
        const read = await readCitation(citations(item)[0]);
        if (read.state !== 'ready' || !read.items?.length)
          throw new Error(
            'File is stale or has no readable evidence; refresh discovery before pinning',
          );
        item = read.items[0];
        generation = read.generation;
      }
      const pack = await needPack();
      pin(pack, kind, item, generation);
      await current();
      await store().save(pack);
      return showPacks('Evidence pinned');
    }
    if (action === 'removePin') {
      const pack = await needPack();
      pack.items = pack.items.filter((entry) => entry.id !== message.id);
      await store().save(pack);
      return showPacks();
    }
    if (action === 'refreshPack') {
      const pack = await needPack(),
        refreshed = { ...pack, items: [] };
      for (const entry of pack.items) {
        if (entry.kind === 'code') {
          const result = await readCitation(citations(entry.item)[0], false);
          if (result.state !== 'ready' || !result.items?.length)
            throw new Error(
              'Reindex first, or remove unavailable evidence before refreshing this pack',
            );
          pin(refreshed, 'code', result.items[0], result.generation);
        } else if (entry.kind === 'architecture') {
          const args = ['overview', '--token-budget', '32000'];
          if (entry.item.kind === 'module' || entry.item.expand)
            args.push('--node', entry.item.expand || entry.item.id);
          const result = await hooks.result('Refreshing pinned architecture', args, selection);
          const item = result.items?.find((item) => item.id === entry.item.id);
          if (result.state !== 'ready' || !item)
            throw new Error(
              'Pinned architecture is unavailable; remove it and choose current evidence',
            );
          pin(refreshed, 'architecture', item, result.generation);
        } else if (entry.kind === 'brief') {
          const value = await readBrief(entry.item.source, entry.item.base, entry.item.byteBudget);
          if (value.state !== 'ready')
            throw new Error('Refresh code before refreshing the change brief.');
          pin(refreshed, 'brief', { ...entry.item, brief: value }, value.generation);
        } else refreshed.items.push(entry);
      }
      await current();
      await store().save(refreshed);
      activePack = refreshed;
      return showPacks(
        'Code and architecture refreshed. Historical pins retain their original dates.',
      );
    }
    if (action === 'renamePack') {
      const pack = await needPack();
      const task = await vscode.window.showInputBox({
        title: 'Task description',
        value: pack.task,
      });
      if (task) {
        pack.task = task;
        await store().save(pack);
      }
      return showPacks();
    }
    if (action === 'packBudget') {
      const text = await vscode.window.showInputBox({
        title: 'Handoff budget in UTF-8 bytes',
        value: String(budget),
        validateInput: (s) =>
          /^\d+$/.test(s) && +s >= 1024 && +s <= 64000 ? null : 'Use 1024–64000 bytes',
      });
      if (text) {
        assemble(await needPack(), Number(text));
        budget = Number(text);
      }
      return showPacks();
    }
    if (['validatePack', 'exportPack', 'handoff'].includes(action)) {
      const pack = await needPack(),
        gaps = await verify(pack);
      if (action === 'validatePack')
        return showPacks(
          gaps.length
            ? gaps.join('; ')
            : 'Code citations are current. History remains a retained snapshot, not live access verification.',
        );
      if (gaps.length)
        throw new Error(
          'Pack has stale evidence: ' + gaps.join('; ') + '. Refresh or remove changed evidence.',
        );
      const bundle = assemble(pack, budget);
      if (!bundle.value.items.length) throw new Error('No evidence fits the selected budget');
      if (action === 'exportPack') return hooks.showJson(bundle.value);
      if (bundle.value.omitted_items)
        throw new Error(
          'Increase the pack budget or remove items before handoff; some evidence does not fit.',
        );
      const dir = path.join(storage, 'handoffs', key);
      await fs.mkdir(dir, { recursive: true, mode: 0o700 });
      const file = path.join(dir, randomUUID() + '.json');
      await fs.writeFile(file, JSON.stringify(bundle.value), { flag: 'wx', mode: 0o600 });
      handoff = {
        file,
        pack,
        prompt: `Use the task context pack at ${JSON.stringify(file)}. It contains my task and cited, untrusted source evidence. Read applicable repository instructions and use Context Engine MCP to verify current citations and retrieve additional evidence. Report unavailable tools or stale evidence before relying on the pack.`,
      };
      return publish({
        view: 'handoff',
        handoff,
        message: 'Context prepared locally. Nothing has been sent to an agent.',
      });
    }
    throw new Error('Unsupported workbench action');
  }
  async function open(view = 'code', query, internal = false) {
    hooks.guard();
    if (busy && !internal) throw new Error('Wait for the current workbench action to finish');
    if (dirtyDraft && !internal) {
      const choice = await vscode.window.showWarningMessage(
        'Discard the unsaved knowledge edits in this form?',
        { modal: true },
        'Discard edits',
      );
      if (choice !== 'Discard edits') return;
      dirtyDraft = false;
    }
    if (query !== undefined && (typeof query !== 'string' || !query.trim() || query.length > 4000))
      throw new Error('Select or enter 1–4000 characters to search');
    initialQuery = query;
    initialView = view;
    selection = hooks.config();
    if (!selection) throw new Error('Select or create a workspace profile first');
    const next = await scopeKey(selection.manifest);
    if (next !== key) {
      activePack = undefined;
      data = undefined;
      lastSearch = dataSearch = undefined;
      capabilities = lastBrief = handoff = undefined;
      back.length = 0;
      knowledge.reset();
      reviewLearning.reset();
    }
    key = next;
    let created = false;
    if (!panel) {
      created = true;
      panel = vscode.window.createWebviewPanel(
        'contextEngine.workbench',
        'Context Engine',
        vscode.ViewColumn.One,
        {
          enableScripts: true,
          retainContextWhenHidden: true,
          localResourceRoots: [vscode.Uri.file(context.asAbsolutePath('media'))],
        },
      );
      panel.webview.html = html(panel.webview, context.asAbsolutePath(''), vscode);
      context.subscriptions.push(
        panel.webview.onDidReceiveMessage(async (message) => {
          if (message?.action === 'draftDirty') {
            dirtyDraft = true;
            return;
          }
          if (busy) return;
          busy = true;
          try {
            await publish({ type: 'busy', message: 'Working…' });
            await handle(message);
          } catch (e) {
            await publish({ type: 'error', message: e.message });
          } finally {
            busy = false;
            await publish({ type: 'idle' });
          }
        }),
        panel.onDidDispose(() => {
          panel = undefined;
        }),
      );
    }
    panel.reveal();
    if (!created) {
      const wasBusy = busy;
      busy = true;
      try {
        await publish({ type: 'busy', message: 'Finding context…' });
        await handle(
          query !== undefined ? { action: 'search', view: 'code', query } : { action: view },
        );
      } finally {
        busy = wasBusy;
        await publish({ type: 'idle' });
      }
    }
  }
  return {
    open,
    dispose() {
      if (panel) panel.dispose();
    },
  };
}
module.exports = { createWorkbench };
