'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const Module = require('node:module');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { execFileSync } = require('node:child_process');
const runtime = require('../src/runtime');

async function harness(report, options = {}) {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'context-vscode-'));
  const handlers = new Map(),
    state = new Map();
  const calls = [],
    terminals = [],
    errors = [],
    info = [],
    docs = [],
    picks = [],
    inputs = [];
  let tree,
    taskEnd,
    launches = 0;
  const disposable = { dispose() {} };
  const statusBar = { show() {}, dispose() {} };
  const executed = [];
  let saved;
  const execution = {
    terminate() {
      taskEnd({ execution });
    },
  };
  const api = {
    workspace: {
      isTrusted: true,
      workspaceFolders: [{ name: 'api', uri: { fsPath: '/selected/api' } }],
      getConfiguration: () => ({ get: (key, fallback) => options.settings?.[key] ?? fallback }),
      onDidSaveTextDocument: (fn) => {
        saved = fn;
        return disposable;
      },
      onDidChangeConfiguration: () => disposable,
      openTextDocument: async (value) => {
        docs.push(value);
        return { ...value, getText: () => value.content };
      },
    },
    env: { remoteName: undefined, openExternal: async () => {} },
    Uri: { parse: (value) => value, file: (value) => ({ fsPath: value }) },
    StatusBarAlignment: { Left: 1 },
    ViewColumn: { One: 1 },
    EventEmitter: class {
      constructor() {
        this.event = () => disposable;
      }
      fire() {}
      dispose() {}
    },
    TreeItem: class {
      constructor(label) {
        this.label = label;
      }
    },
    ThemeIcon: class {},
    ProgressLocation: { Notification: 15 },
    TaskScope: { Workspace: 2 },
    ProcessExecution: class {
      constructor(executable, args) {
        this.executable = executable;
        this.args = args;
      }
    },
    Task: class {
      constructor(...args) {
        this.args = args;
      }
    },
    tasks: {
      executeTask: async (task) => {
        calls.push(task);
        launches++;
        return execution;
      },
      onDidEndTask: (fn) => {
        taskEnd = fn;
        return disposable;
      },
    },
    commands: {
      registerCommand: (name, fn) => {
        handlers.set(name, fn);
        return disposable;
      },
      executeCommand: async (...args) => {
        executed.push(args);
      },
    },
    window: {
      createWebviewPanel: (kind, title, column, options) => {
        const panel = {
          kind,
          title,
          column,
          options,
          webview: {
            cspSource: 'self',
            asWebviewUri: () => 'local.css',
            html: '',
            postMessage: async () => true,
            onDidReceiveMessage: (fn) => {
              panel.receive = fn;
              return disposable;
            },
          },
          reveal() {},
          onDidDispose: () => disposable,
          dispose() {},
        };
        docs.push(panel);
        return panel;
      },
      createStatusBarItem: () => statusBar,
      createOutputChannel: () => ({ appendLine() {}, dispose() {} }),
      registerTreeDataProvider: (_, value) => {
        tree = value;
        return disposable;
      },
      withProgress: async (_, fn) => fn({}, { onCancellationRequested: () => disposable }),
      showTextDocument: async () => {},
      showInformationMessage: async (msg) => {
        info.push(msg);
      },
      showErrorMessage: async (msg) => {
        errors.push(msg);
      },
      showQuickPick: async (options) => {
        const answer = picks.shift();
        return typeof answer === 'function' ? answer(options) : answer;
      },
      showInputBox: async () => inputs.shift(),
      showOpenDialog: async () => [{ fsPath: '/selected/team.json' }],
      createTerminal: (opts) => {
        const terminal = {
          ...opts,
          show() {},
          dispose() {
            this.closed = true;
          },
        };
        terminals.push(terminal);
        return terminal;
      },
      onDidCloseTerminal: (_fn) => disposable,
    },
  };
  const context = {
    globalStorageUri: { fsPath: dir },
    asAbsolutePath: (p) => path.join(options.extensionRoot || path.join(dir, 'extension'), p),
    subscriptions: [],
    workspaceState: {
      get: (key, fallback) => (state.has(key) ? state.get(key) : fallback),
      update: async (key, value) => {
        state.set(key, value);
      },
    },
  };
  const original = Module._load;
  Module._load = function (name, ...args) {
    if (name === 'vscode') return api;
    if (name === './controller')
      return {
        createWorkbench: () => ({
          open: async (...args) => {
            calls.push({ workbench: args });
          },
          dispose() {},
        }),
      };
    if (name === './runtime')
      return {
        ...runtime,
        run: async (spec) => {
          calls.push(spec);
          if (options.realRuntime) return runtime.run(spec);
          if (spec.args.includes('commonplace') && spec.args.includes('preview'))
            return JSON.stringify({
              preview_token: 'synthetic-token',
              changes: [{ record: { id: 'rule' } }],
              conflicts: [],
            });
          if (spec.args.includes('commonplace'))
            return JSON.stringify({
              repository: '',
              directory: '/company/commonplace',
              snapshot: '/company/commonplace/snapshot',
            });
          if (spec.args.includes('maintenance'))
            return JSON.stringify({
              items: [
                {
                  id: 'rule',
                  revision: 1,
                  title: 'Rule',
                  status: 'approved',
                  stale_evidence: false,
                },
              ],
            });
          if (spec.args.includes('refresh-draft'))
            return JSON.stringify({
              draft: { id: 'rule', statement: 'DRAFT: Inspect evidence' },
              expected_revision: 1,
              review_required: 'Review before approval',
            });
          if (spec.args.includes('reasoning-template'))
            return JSON.stringify({ markdown: '# Working reasoning note' });
          if (spec.args.includes('github-access'))
            return JSON.stringify({ repository: 'fixture/project' });
          if (spec.args.includes('wiki'))
            return JSON.stringify({ markdown: '# Wiki\nContent', diagram: [] });
          if (spec.args.includes('usage') && spec.args.includes('report'))
            return JSON.stringify(report);
          if (spec.args.includes('vscode'))
            return JSON.stringify({ workspace_file: '/generated/context.code-workspace' });
          if (spec.args.includes('-c') && options.setupError) throw new Error(options.setupError);
          if (spec.args.includes('-c'))
            return JSON.stringify({
              python: '/python',
              version: '3.9',
              kotlin: 'text fallback',
              gaps: ['Parser unavailable'],
            });
          return spec.args.includes('--version')
            ? '1.0.0'
            : JSON.stringify({
                environment: 'team',
                workspace: 'checkout',
                state: 'ready',
                coverage: { api: { root: '/selected/api' } },
              });
        },
      };
    return original.call(this, name, ...args);
  };
  try {
    delete require.cache[require.resolve('../src/extension')];
    require('../src/extension').activate(context);
  } finally {
    Module._load = original;
  }
  return {
    api,
    calls,
    terminals,
    errors,
    info,
    docs,
    picks,
    inputs,
    state,
    context,
    tree,
    statusBar,
    executed,
    save: () => saved(),
    launches: () => launches,
    command: (name) => handlers.get('contextEngine.' + name)(),
    cleanup: async () => {
      for (const d of context.subscriptions) d.dispose();
      await fs.rm(dir, { recursive: true, force: true });
    },
  };
}

test('untrusted workspace cannot start agents, index, or change scope; activation is passive', async () => {
  const h = await harness();
  try {
    assert.equal(h.calls.length, 0);
    h.api.workspace.isTrusted = false;
    await h.command('codexLogin');
    await h.command('refresh');
    await h.command('chooseManifest');
    assert.equal(h.calls.length, 0);
    assert.equal(h.terminals.length, 0);
    assert.equal(h.errors.length, 3);
  } finally {
    await h.cleanup();
  }
});

test('manual login uses native terminal argv and never marks an account connected', async () => {
  const h = await harness();
  try {
    await h.command('claudeLogin');
    await h.command('codexLogin');
    assert.deepEqual(
      h.terminals.map((t) => t.shellArgs),
      [['auth', 'login'], ['login']],
    );
    assert.equal(h.terminals[0].shellPath, 'claude');
    assert.equal(h.state.size, 0);
    assert.ok(h.info.every((s) => s.includes('verify')));
  } finally {
    await h.cleanup();
  }
});

test('manifest validation, scoped MCP launch, model persistence and crawler lifecycle', async () => {
  const h = await harness();
  try {
    await h.command('chooseManifest');
    assert.equal(h.state.get('scope').label, 'team / checkout');
    h.picks.push({ id: 'codex' });
    h.inputs.push('chosen-model');
    await h.command('model');
    await h.command('codexLaunch');
    await h.command('claudeLaunch');
    const codex = h.terminals[0];
    assert.equal(codex.cwd, '/selected/api');
    assert.equal(codex.shellArgs.at(-1), 'chosen-model');
    const claude = JSON.parse(h.terminals[1].shellArgs[1]);
    const server = Object.values(claude.mcpServers)[0];
    assert.ok(server.args.includes('/selected/team.json'));
    h.picks.push((options) => options[0]);
    await h.command('startCrawler');
    await h.command('startCrawler');
    assert.equal(h.launches(), 1);
    await h.command('toggleAdvanced');
    assert.ok(h.tree.getChildren().some((row) => row.label === 'Stop crawler'));
    await h.command('chooseManifest');
    assert.match(h.errors.at(-1), /Stop the crawler/);
    await h.command('stopCrawler');
    assert.ok(h.tree.getChildren().some((row) => row.label === 'Start crawler'));
  } finally {
    await h.cleanup();
  }
});

test('source selection includes only explicitly picked folders and preserves visibility', async () => {
  const h = await harness();
  try {
    h.api.workspace.workspaceFolders.push({
      name: 'scratch',
      uri: { fsPath: '/personal/scratch' },
    });
    h.picks.push(
      (options) => options[1],
      (options) => [options[1]],
    );
    h.inputs.push('notes');
    await h.command('createScope');
    const saved = JSON.parse(await fs.readFile(h.state.get('scope').manifest, 'utf8'));
    assert.equal(saved.environment, 'personal');
    assert.deepEqual(saved.sources, [{ id: 'repo_1', type: 'git', path: '/personal/scratch' }]);
    assert.equal(h.calls.filter((c) => c.args && c.args.includes('index')).length, 0);
  } finally {
    await h.cleanup();
  }
});

test('saved scopes can be reselected and flag-like searches remain query text', async () => {
  const h = await harness();
  try {
    await h.command('chooseManifest');
    h.state.set('scope', undefined);
    h.picks.push((options) => options[0]);
    await h.command('chooseManifest');
    assert.equal(h.state.get('scope').manifest, '/selected/team.json');
    h.inputs.push('--some-flag');
    await h.command('search');
    assert.deepEqual(h.calls.find((call) => call.workbench).workbench, ['code', '--some-flag']);
  } finally {
    await h.cleanup();
  }
});

test('instruction command keeps flag-like paths as values', async () => {
  const h = await harness();
  try {
    await h.command('chooseManifest');
    h.inputs.push('api', '--new.py');
    await h.command('instructions');
    const call = h.calls.find((entry) => entry.args?.includes('instructions'));
    assert.deepEqual(call.args.slice(-4), [
      'instructions',
      '--source=api',
      '--path=--new.py',
      '--token-budget=8000',
    ]);
    assert.equal(h.errors.length, 0);
  } finally {
    await h.cleanup();
  }
});

test('structural navigation keeps symbol input as an argument value', async () => {
  const h = await harness();
  try {
    await h.command('chooseManifest');
    h.picks.push((options) => options.find((item) => item === 'callers'));
    h.inputs.push('api', '--symbol');
    await h.command('structure');
    const call = h.calls.find((entry) => entry.args?.includes('structure'));
    assert.deepEqual(call.args.slice(-5), [
      'structure',
      '--mode=callers',
      '--source=api',
      '--token-budget=8000',
      '--symbol=--symbol',
    ]);
    assert.equal(h.errors.length, 0);
  } finally {
    await h.cleanup();
  }
});

test('Codex IDE route generates scoped workspace without CLI login or terminals', async () => {
  const h = await harness();
  try {
    const manifest = path.join(h.context.globalStorageUri.fsPath, 'team.json');
    await fs.writeFile(
      manifest,
      JSON.stringify({
        schema_version: 1,
        environment: 'test',
        workspace: 'ide',
        sources: [{ id: 'api', path: '/selected/api' }],
      }),
    );
    h.api.window.showOpenDialog = async () => [{ fsPath: manifest }];
    await h.command('chooseManifest');
    await h.command('codexIde');
    assert.equal(h.errors.length, 0);
    assert.equal(h.terminals.length, 0);
    assert.ok(h.calls.some((c) => c.args?.includes('vscode')));
    assert.deepEqual(h.executed.at(-1), [
      'vscode.openFolder',
      { fsPath: '/generated/context.code-workspace' },
      { forceNewWindow: true },
    ]);
    assert.match(h.statusBar.text, /ready/);
    h.save();
    assert.match(h.statusBar.text, /check after save/);
    await h.command('status');
    assert.match(h.statusBar.text, /ready/);
    h.api.workspace.isTrusted = false;
    const count = h.calls.length;
    await h.command('codexIde');
    await h.command('checkSetup');
    assert.equal(h.calls.length, count);
  } finally {
    await h.cleanup();
  }
});

test('setup diagnostics works before selecting a scope and does not install software', async () => {
  const h = await harness();
  try {
    h.picks.push({ action: 'settings' });
    await h.command('checkSetup');
    assert.equal(h.errors.length, 0);
    assert.equal(h.calls.length, 1);
    assert.equal(h.calls[0].args[0], '-c');
    assert.equal(h.terminals.length, 0);
    assert.deepEqual(h.executed.at(-1), [
      'workbench.action.openSettings',
      'contextEngine.pythonPath',
    ]);
  } finally {
    await h.cleanup();
  }
});

test('editor selection search uses the workbench and respects workspace trust', async () => {
  const h = await harness();
  try {
    h.api.window.activeTextEditor = {
      selection: { isEmpty: false },
      document: { getText: () => 'consumeTask' },
    };
    await h.command('searchSelection');
    assert.deepEqual(h.calls.at(-1).workbench, ['code', 'consumeTask']);
    h.api.workspace.isTrusted = false;
    const count = h.calls.length;
    await h.command('searchSelection');
    assert.equal(h.calls.length, count);
    h.api.workspace.isTrusted = true;
    h.api.window.activeTextEditor.selection.isEmpty = true;
    await h.command('searchSelection');
    assert.match(h.errors.at(-1), /Select an identifier/);
  } finally {
    await h.cleanup();
  }
});

test('usage reporting saves only reviewed bytes, refuses overwrite, and never enables collection implicitly', async () => {
  const report = {
    schema_version: 1,
    engine_release: require('../package.json').version,
    report_kind: 'product_usage_aggregate',
    period_days_bucket: '0',
    operations: {},
    token_usage: { availability: 'unavailable' },
  };
  const h = await harness(report);
  try {
    await h.command('chooseManifest');
    const target = path.join(h.context.globalStorageUri.fsPath, 'reviewed.json');
    h.api.window.showInformationMessage = async () => 'Save reviewed report';
    h.api.window.showSaveDialog = async () => ({ fsPath: target });
    h.picks.push({ action: 'report' });
    await h.command('usageReport');
    assert.equal(h.errors.length, 0);
    assert.equal(await fs.readFile(target, 'utf8'), h.docs.at(-1).content);
    assert.equal((await fs.stat(target)).mode & 0o077, 0);
    assert.ok(!h.calls.some((c) => c.args?.includes('enable')));
    h.picks.push({ action: 'report' });
    await h.command('usageReport');
    assert.match(h.errors.at(-1), /not overwritten/);
    h.api.workspace.openTextDocument = async () => ({ getText: () => 'COMPANY_SECRET' });
    h.picks.push({ action: 'report' });
    await h.command('usageReport');
    assert.match(h.errors.at(-1), /Preview changed/);
    h.api.window.showWarningMessage = async () => undefined;
    const before = h.calls.length;
    h.picks.push({ action: 'enable' });
    await h.command('usageReport');
    assert.equal(h.calls.length, before);
    h.api.window.showWarningMessage = async () => 'Continue';
    h.picks.push({ action: 'enable' });
    await h.command('usageReport');
    assert.ok(h.calls.at(-1).args.includes('enable'));
    h.api.workspace.isTrusted = false;
    const count = h.calls.length;
    await h.command('usageReport');
    assert.equal(h.calls.length, count);
  } finally {
    await h.cleanup();
  }
});

test('knowledge wiki uses a dedicated projection and trust blocks review commands', async () => {
  const h = await harness();
  try {
    await h.command('chooseManifest');
    h.picks.push('architecture', { id: 'api' });
    await h.command('knowledgeWiki');
    assert.ok(h.calls.at(-1).args.includes('wiki'));
    assert.ok(h.calls.at(-1).args.includes('--kind=architecture'));
    assert.equal(h.docs.at(-1).kind, 'contextKnowledgeWiki');
    assert.equal(h.docs.at(-1).options.enableScripts, false);
    h.api.workspace.isTrusted = false;
    const count = h.calls.length;
    await h.command('knowledgeReview');
    await h.command('knowledgePropose');
    assert.equal(h.calls.length, count);
  } finally {
    await h.cleanup();
  }
});

test('GitHub credential goes only to one fetch environment after permission check', async () => {
  const h = await harness();
  try {
    await h.command('chooseManifest');
    h.picks.push({ id: 'api' });
    h.inputs.push('12', 'SYNTHETIC_TOKEN');
    await h.command('githubReviews');
    const access = h.calls.findIndex((call) => call.args?.includes('github-access'));
    const fetch = h.calls.findIndex((call) => call.args?.includes('github-fetch'));
    assert.ok(access >= 0 && fetch > access);
    assert.equal(h.calls[fetch].env.CONTEXT_ENGINE_GITHUB_TOKEN, 'SYNTHETIC_TOKEN');
    assert.ok(!JSON.stringify(h.calls[fetch].args).includes('SYNTHETIC_TOKEN'));
    assert.ok(!JSON.stringify(h.docs).includes('SYNTHETIC_TOKEN'));
    assert.ok(!JSON.stringify(h.errors).includes('SYNTHETIC_TOKEN'));
    assert.notEqual(process.env.CONTEXT_ENGINE_GITHUB_TOKEN, 'SYNTHETIC_TOKEN');
    h.api.workspace.isTrusted = false;
    const count = h.calls.length;
    await h.command('githubReviews');
    assert.equal(h.calls.length, count);
  } finally {
    await h.cleanup();
  }
});

test('Commonplace mapping and local snapshot opening stay behind workspace trust', async () => {
  const h = await harness();
  try {
    await h.command('chooseManifest');
    h.picks.push('Configure team repository mapping');
    h.inputs.push('team/commonplace', '/company/commonplace');
    await h.command('commonplace');
    assert.deepEqual(h.calls.at(-1).args.slice(-4), [
      'commonplace',
      'configure',
      '--repository=team/commonplace',
      '--directory=/company/commonplace',
    ]);
    h.picks.push('Open local Commonplace');
    await h.command('commonplace');
    assert.deepEqual(h.executed.at(-1), [
      'revealFileInOS',
      { fsPath: '/company/commonplace/snapshot' },
    ]);
    h.api.workspace.isTrusted = false;
    const count = h.calls.length;
    await h.command('commonplace');
    assert.equal(h.calls.length, count);
  } finally {
    await h.cleanup();
  }
});

test('P1 preview precedes proposal import and change brief stays read-only and trusted', async () => {
  const h = await harness();
  try {
    await h.command('chooseManifest');
    h.picks.push('Preview and import edited records');
    h.api.window.showWarningMessage = async () => undefined;
    await h.command('commonplace');
    assert.ok(h.calls.at(-1).args.includes('preview'));
    h.picks.push('Preview and import edited records');
    h.api.window.showWarningMessage = async () => 'Import proposals';
    await h.command('commonplace');
    assert.ok(h.calls.at(-1).args.includes('import'));
    assert.ok(h.calls.at(-1).args.includes('--preview-token=synthetic-token'));
    await h.command('changeBrief');
    assert.deepEqual(h.calls.at(-1).workbench, ['brief']);
    h.api.workspace.isTrusted = false;
    const count = h.calls.length;
    await h.command('changeBrief');
    assert.equal(h.calls.length, count);
    assert.match(h.errors.at(-1), /Trust this workspace/);
  } finally {
    await h.cleanup();
  }
});

test('maintenance records exact-revision feedback and prepares unsaved drafts and Scratch notes', async () => {
  const h = await harness();
  try {
    await h.command('chooseManifest');
    h.picks.push({ id: 'api' }, (options) => options[0], 'wrong_scope');
    await h.command('knowledgeMaintenance');
    assert.deepEqual(h.calls.at(-1).args.slice(-5), [
      'knowledge',
      'feedback',
      '--id=rule',
      '--revision=1',
      '--outcome=wrong_scope',
    ]);
    h.picks.push({ id: 'api' }, (options) => options[0], 'Prepare re-review draft');
    await h.command('knowledgeMaintenance');
    assert.ok(h.calls.at(-1).args.includes('refresh-draft'));
    assert.ok(h.docs.some((d) => d.content?.includes('DRAFT: Inspect evidence')));
    await h.command('reasoningNote');
    assert.ok(
      h.docs.some((d) => d.language === 'markdown' && d.content === '# Working reasoning note'),
    );
    assert.deepEqual(h.errors, []);
    h.api.workspace.isTrusted = false;
    const count = h.calls.length;
    await h.command('knowledgeMaintenance');
    await h.command('reasoningNote');
    assert.equal(h.calls.length, count);
  } finally {
    await h.cleanup();
  }
});

test('everyday sidebar hides legacy flows, advanced toggle preserves access, and cancel is passive', async () => {
  const h = await harness();
  try {
    const commands = () => h.tree.getChildren().map((item) => item.command.command);
    assert.ok(commands().includes('contextEngine.getStarted'));
    assert.ok(!commands().includes('contextEngine.codexLogin'));
    assert.ok(!commands().includes('contextEngine.codexLaunch'));
    assert.equal(h.statusBar.command, 'contextEngine.getStarted');
    await h.command('toggleAdvanced');
    assert.ok(commands().includes('contextEngine.codexLogin'));
    await h.command('toggleAdvanced');
    assert.ok(!commands().includes('contextEngine.codexLogin'));
    await h.command('getStarted');
    assert.equal(h.calls.length, 0);
    assert.equal(h.terminals.length, 0);
  } finally {
    await h.cleanup();
  }
});

test('onboarding requires a scope and guides an existing configuration through refresh', async () => {
  const h = await harness();
  try {
    h.picks.push({ action: 'refresh' }, { action: 'done' });
    await h.command('getStarted');
    assert.match(h.info.at(-1), /Choose repository folders/);
    assert.equal(h.calls.length, 0);
    h.picks.push({ action: 'select' }, { action: 'refresh' }, { action: 'done' });
    await h.command('getStarted');
    assert.ok(h.calls.some((call) => call.args?.includes('index')));
    assert.ok(h.calls.some((call) => call.args?.includes('/selected/team.json')));
    assert.equal(h.terminals.length, 0);
    assert.deepEqual(h.errors, []);
  } finally {
    await h.cleanup();
  }
});

test('missing Python offers settings recovery without installing or starting a terminal', async () => {
  const h = await harness(undefined, { setupError: 'spawn missing-python ENOENT' });
  try {
    h.picks.push({ action: 'setup' }, { action: 'settings' }, { action: 'done' });
    await h.command('getStarted');
    assert.deepEqual(h.executed.at(-1), [
      'workbench.action.openSettings',
      'contextEngine.pythonPath',
    ]);
    assert.equal(h.calls.length, 1);
    assert.equal(h.terminals.length, 0);
    assert.deepEqual(h.errors, []);
  } finally {
    await h.cleanup();
  }
});

test('repository picker shows scoped roots and cancellation does not request a change brief', async () => {
  const h = await harness();
  try {
    await h.command('chooseManifest');
    h.picks.push((options) => {
      assert.deepEqual(options, [{ label: 'api', description: '/selected/api', id: 'api' }]);
      return undefined;
    });
    await h.command('changeBrief');
    assert.ok(!h.calls.some((call) => call.args?.includes('change-brief')));
    assert.deepEqual(h.errors, []);
  } finally {
    await h.cleanup();
  }
});

test('core-generated scopes share extension approvals with MCP and retain storage policy', async () => {
  const root = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'context-shared-state-')));
  const extensionRoot = path.resolve(__dirname, '..');
  const launcher = path.join(extensionRoot, 'backend/launch.py');
  let h;
  try {
    for (const source of ['api', 'personal']) {
      await fs.mkdir(path.join(root, source));
      await fs.writeFile(path.join(root, source, 'main.py'), `SCOPE = '${source}'\n`);
    }
    const generated = JSON.parse(
      await runtime.run({
        executable: 'python3',
        args: [
          launcher,
          'init',
          '--output',
          path.join(root, 'workspace'),
          '--environment',
          'test',
          '--repo',
          `api=${path.join(root, 'api')}`,
          '--personal-repo',
          `notes=${path.join(root, 'personal')}`,
        ],
      }),
    );
    const workspace = JSON.parse(await fs.readFile(generated.workspace_file, 'utf8'));
    const settings = Object.fromEntries(
      Object.entries(workspace.settings)
        .filter(([key]) => key.startsWith('contextEngine.'))
        .map(([key, value]) => [key.slice('contextEngine.'.length), value]),
    );
    const tasks = JSON.parse(
      await fs.readFile(path.join(root, 'workspace/.vscode/tasks.json'), 'utf8'),
    ).tasks;
    for (const task of tasks.filter((t) => t.label.endsWith(': index'))) {
      await runtime.run({ executable: task.command, args: task.args }, { cwd: task.options.cwd });
    }
    const team = tasks.find((t) => t.label === 'Context Engine team: index');
    const teamState = team.args[team.args.indexOf('--state') + 1];
    const call = async (args) =>
      JSON.parse(
        await runtime.run({
          executable: team.command,
          args: [launcher, ...team.args.slice(2, -1), ...args],
        }),
      );
    h = await harness(undefined, { settings, extensionRoot, realRuntime: true });
    await h.command('status');
    assert.equal(JSON.parse(h.docs.at(-1).content).state, 'ready');
    const draft = await call(['knowledge', 'template', '--source=api', '--path=main.py']);
    draft.id = 'shared-rule';
    draft.statement = 'Keep fixture changes covered.';
    const file = path.join(root, 'proposal.json');
    await fs.writeFile(file, JSON.stringify(draft));
    h.api.window.showOpenDialog = async () => [{ fsPath: file }];
    h.inputs.push('0');
    await h.command('knowledgePropose');
    h.picks.push((options) => options.find((item) => item.record.id === draft.id));
    h.api.window.showWarningMessage = async () => 'Approve';
    await h.command('knowledgeReview');
    assert.deepEqual(h.errors, []);
    // Use the generated MCP server configuration, independent of the extension's launcher.
    const config = await fs.readFile(path.join(root, 'workspace/.codex/config.toml'), 'utf8');
    const server = Object.fromEntries(
      config
        .split('[mcp_servers.context_engine_team]')[1]
        .split('[mcp_servers.context_engine_personal]')[0]
        .split('\n')
        .filter((line) => line.includes(' = '))
        .map((line) => {
          const at = line.indexOf(' = ');
          return [line.slice(0, at), JSON.parse(line.slice(at + 3))];
        }),
    );
    const requests = [
      { jsonrpc: '2.0', id: 1, method: 'initialize', params: {} },
      {
        jsonrpc: '2.0',
        id: 2,
        method: 'tools/call',
        params: {
          name: 'lookup_knowledge',
          arguments: { kind: 'practice', source: 'api', path: 'main.py', byte_budget: 8000 },
        },
      },
    ];
    const replies = execFileSync(server.command, server.args, {
      cwd: server.cwd,
      input: requests.map((r) => JSON.stringify(r)).join('\n') + '\n',
      encoding: 'utf8',
    })
      .trim()
      .split('\n')
      .map((line) => JSON.parse(line));
    assert.equal(JSON.parse(replies.at(-1).result.content[0].text).items[0].id, draft.id);
    assert.ok(h.calls.every((c) => c.args[c.args.indexOf('--state') + 1] === teamState));
    const personalManifest = path.join(root, 'workspace/personal.json');
    h.api.window.showOpenDialog = async () => [{ fsPath: personalManifest }];
    await h.command('chooseManifest');
    await h.command('status');
    assert.deepEqual(Object.keys(JSON.parse(h.docs.at(-1).content).coverage), ['notes']);
    assert.equal(
      h.calls.at(-1).args[h.calls.at(-1).args.indexOf('--state') + 1],
      settings.statePaths[personalManifest],
    );
    h.picks.push((options) => {
      assert.equal(options.length, 0);
      return undefined;
    });
    await h.command('knowledgeReview');
    assert.deepEqual(h.errors, []);

    const policy = path.join(root, 'policy.json');
    await fs.writeFile(
      policy,
      JSON.stringify({
        schema_version: 1,
        storage_roots: [path.join(root, 'workspace/state')],
        source_roots: [path.join(root, 'api'), path.join(root, 'personal')],
        allow_history: false,
        allow_remote_git: false,
        allow_embeddings: false,
      }),
      { mode: 0o600 },
    );
    settings.policyPath = policy;
    settings.statePaths[personalManifest] = path.join(root, 'unapproved');
    await h.command('status');
    assert.equal(h.errors.length, 1);
    await assert.rejects(fs.stat(path.join(root, 'unapproved')), { code: 'ENOENT' });
  } finally {
    if (h) await h.cleanup();
    await fs.rm(root, { recursive: true, force: true });
  }
});
