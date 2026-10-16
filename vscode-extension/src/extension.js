'use strict';
const vscode = require('vscode');
const path = require('node:path');
const fs = require('node:fs/promises');
const { randomUUID, createHash } = require('node:crypto');
const {
  PROVIDERS,
  provider,
  scopeId,
  stateDirectory,
  engineSpec,
  agentSpec,
  run,
} = require('./runtime');
const { scopeKey } = require('./packs');
const { createWorkbench } = require('./controller');
const { reviewedReport } = require('./usage-report');

function activate(context) {
  const output = vscode.window.createOutputChannel('Context Engine');
  const changed = new vscode.EventEmitter();
  const running = new Set();
  const terminals = new Set();
  let crawler;
  let disposed = false;
  const settings = () => vscode.workspace.getConfiguration('contextEngine', null);
  const storage = settings().get('storageRoot', '') || context.globalStorageUri.fsPath;
  const launcher = context.asAbsolutePath('backend/launch.py');
  const config = () => {
    const saved = context.workspaceState.get('scope');
    const manifest = settings().get('manifestPath', '');
    return saved || (manifest ? { manifest, label: path.basename(manifest) } : undefined);
  };
  let readiness = 'not checked',
    checkedAt;
  let setupState;
  let showAdvanced = false;
  const statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 10);
  statusBar.command = 'contextEngine.status';
  context.subscriptions.push(statusBar);
  const modelKey = (id) => `model.${config() ? scopeId(config().manifest) : 'default'}.${id}`;
  const selectedModel = (id) => context.workspaceState.get(modelKey(id), '');
  function guard() {
    if (!vscode.workspace.isTrusted)
      throw new Error('Trust this workspace before running Context Engine or an agent.');
    if (disposed) throw new Error('Extension has stopped');
    if (!path.isAbsolute(storage)) throw new Error('Storage root must be absolute');
  }
  async function privateDir(dir) {
    await fs.mkdir(dir, { recursive: true, mode: 0o700 });
  }
  function executable(id) {
    return settings().get(`${id}Path`, PROVIDERS[id].executable);
  }
  function spec(args = [], selected = config()) {
    if (!selected) throw new Error('Select a manifest or create a scope first.');
    const engine = engineSpec(
      settings().get('pythonPath', 'python3'),
      launcher,
      selected.manifest,
      stateDirectory(storage, selected.manifest, settings().get('statePaths', {})),
      args,
    );
    const policy = settings().get('policyPath', '');
    if (policy) engine.args.splice(1, 0, '--policy', policy);
    const reviewPolicy = settings().get('reviewPolicyPath', '');
    if (reviewPolicy) engine.args.splice(1, 0, '--review-policy', reviewPolicy);
    return engine;
  }
  async function result(title, args, selected) {
    guard();
    return vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title, cancellable: true },
      async (_, token) => {
        const value = JSON.parse(
          await run(spec(args, selected), { cwd: path.dirname(launcher), token }),
        );
        if (args[0] === 'status') {
          readiness = value.state || 'unknown';
          checkedAt = new Date().toLocaleTimeString();
          refreshView();
        } else if (['index', 'crawl'].includes(args[0])) {
          readiness = 'check status';
          refreshView();
        }
        return value;
      },
    );
  }
  async function openWiki(kind, source) {
    guard();
    const value = await result('Rendering human wiki', [
      'knowledge',
      'wiki',
      '--kind=' + kind,
      '--source=' + source,
    ]);
    const panel = vscode.window.createWebviewPanel(
      'contextKnowledgeWiki',
      'Company knowledge wiki',
      vscode.ViewColumn.One,
      {
        enableScripts: false,
        localResourceRoots: [vscode.Uri.file(context.asAbsolutePath('media'))],
      },
    );
    panel.webview.html = require('./wiki').html(
      panel.webview,
      context.asAbsolutePath(''),
      vscode,
      value,
    );
    context.subscriptions.push(panel);
  }
  async function showJson(value) {
    const doc = await vscode.workspace.openTextDocument({
      content: JSON.stringify(value, null, 2),
      language: 'json',
    });
    await vscode.window.showTextDocument(doc, { preview: true });
  }
  function refreshView() {
    statusBar.text = config()
      ? `$(database) Context: ${readiness}`
      : '$(database) Context: get started';
    statusBar.tooltip = config()
      ? `${config().label} — checked ${checkedAt || 'not yet'}; click for health and refresh controls`
      : 'Get started: check runtime and choose repositories';
    statusBar.command = config() ? 'contextEngine.workspaceHealth' : 'contextEngine.getStarted';
    statusBar.show();
    changed.fire(undefined);
  }
  async function checkSetup() {
    const script = [
      'import json, sqlite3, sys',
      'sys.path.insert(0, sys.argv[1])',
      'from context_engine.kotlin import extract, identity',
      'db = sqlite3.connect(":memory:")',
      'db.execute("CREATE VIRTUAL TABLE probe USING fts5(text)")',
      'kotlin = extract("fun probe() = 1\\n")',
      'print(json.dumps({"python": sys.executable, "version": sys.version.split()[0], "fts5": True, "kotlin": "ready" if not kotlin["gaps"] else "text fallback", "parser": identity(), "gaps": kotlin["gaps"]}))',
    ].join('\n');
    let setup;
    try {
      setup = JSON.parse(
        await run(
          {
            executable: settings().get('pythonPath', 'python3'),
            args: ['-c', script, path.dirname(launcher)],
          },
          { timeout: 15000 },
        ),
      );
    } catch (error) {
      setupState = undefined;
      const choice = await vscode.window.showQuickPick(
        [
          { label: 'Open Python interpreter setting', action: 'settings' },
          { label: 'Read runtime preparation guide', action: 'docs' },
        ],
        {
          title: 'Python setup could not run',
          placeHolder:
            'Use the Python executable prepared for your client. No installation was attempted.',
        },
      );
      output.appendLine('setup: ' + error.message);
      if (choice?.action === 'settings')
        await vscode.commands.executeCommand(
          'workbench.action.openSettings',
          'contextEngine.pythonPath',
        );
      if (choice?.action === 'docs') await setupGuide();
      return;
    }
    setupState = setup;
    const choice = await vscode.window.showQuickPick(
      [
        { label: `Python ${setup.version} · SQLite ready`, description: setup.python },
        {
          label: `Kotlin: ${setup.kotlin}`,
          description: setup.gaps.join('; ') || 'Syntax parser is available',
        },
        { label: 'Configure Python interpreter', action: 'settings' },
        { label: 'Read runtime preparation guide', action: 'docs' },
      ],
      { title: 'Context Engine setup' },
    );
    if (choice?.action === 'settings')
      await vscode.commands.executeCommand(
        'workbench.action.openSettings',
        'contextEngine.pythonPath',
      );
    if (choice?.action === 'docs') await setupGuide();
    return setup;
  }
  async function setupGuide() {
    const doc = await vscode.workspace.openTextDocument({
      language: 'markdown',
      content:
        '# Prepare the Context Engine runtime\n\nEmployees: use the Python executable supplied by your team and set Context Engine: Python Path in VS Code Settings. The VSIX includes engine code, not Python or parser packages. No terminal scripts are needed for daily use.\n\nRuntime preparer: the restricted macOS Apple Silicon pilot uses Python 3.13.15 and the pinned requirements-release-macos-arm64.txt profile. General development requires Python 3.9+ and Git; Kotlin navigation needs the approved Tree-sitter packages. Optional semantic/model packages are not part of the restricted pilot. See docs/security/CLIENT-TEST-READINESS.md and docs/DEVELOPMENT.md in the product repository.\n\nRun Check Python and Kotlin Setup afterward. A missing Kotlin parser permits text search but does not satisfy the Kotlin pilot requirement. Setup checks do not verify model sign-in or client release approval. After changing Python or updating the extension, open a new Codex IDE workspace to capture the new runtime. No packages are installed automatically.',
    });
    await vscode.window.showTextDocument(doc, { preview: true });
  }
  async function getStarted() {
    while (true) {
      const choice = await vscode.window.showQuickPick(
        [
          {
            label: '1. Check Python and Kotlin setup',
            detail: setupState
              ? `Last check: Python ${setupState.version}; Kotlin ${setupState.kotlin}`
              : 'Use your team-prepared runtime; nothing is installed automatically',
            action: 'setup',
          },
          {
            label: '2. Choose repository folders',
            detail: config()
              ? `Selected: ${config().label}`
              : 'Create a scope using folders already open in VS Code',
            action: 'create',
          },
          {
            label: 'Use an existing context configuration',
            detail: 'Select a team-supplied manifest or previously saved scope',
            action: 'select',
          },
          { label: '3. Refresh code', detail: `Last index check: ${readiness}`, action: 'refresh' },
          {
            label: '4. Open Codex IDE workspace',
            detail: 'Generates local integration files; sign in through the Codex extension',
            action: 'ide',
          },
          {
            label: 'Open Context Workbench',
            detail: 'Search and inspect cited evidence without starting an agent',
            action: 'workbench',
          },
          { label: 'Runtime preparation help', action: 'help' },
          { label: 'Done', action: 'done' },
        ],
        {
          title: 'Get started with Context Engine',
          placeHolder:
            'Choose a step; Escape closes this checklist. Checks are not continuous monitoring.',
        },
      );
      if (!choice || choice.action === 'done') return;
      if (choice.action === 'setup') await checkSetup();
      else if (choice.action === 'create') await createScope();
      else if (choice.action === 'select') await chooseManifest();
      else if (choice.action === 'help') await setupGuide();
      else if (!config())
        await vscode.window.showInformationMessage(
          'Choose repository folders or an existing configuration first.',
        );
      else if (choice.action === 'refresh') await actions.refresh();
      else if (choice.action === 'ide') {
        await codexIde();
        return;
      } else if (choice.action === 'workbench') {
        await workbench.open();
        return;
      }
    }
  }
  async function pickSource(title) {
    const status = await result('Reading repositories in this scope', ['status']);
    const entries = Object.entries(status.coverage || {});
    if (!entries.length)
      throw new Error(
        'No indexed repositories in this scope. Refresh code first; use Get Started to select repository folders.',
      );
    const selected = await vscode.window.showQuickPick(
      entries.map(([id, coverage]) => ({ label: id, description: coverage.root || '', id })),
      { title },
    );
    return selected?.id;
  }

  async function codexIde() {
    if (!config()) await chooseManifest();
    if (!config()) return;
    const selected = { ...config() };
    await result('Checking context scope', ['status'], selected);
    const identity = createHash('sha256')
      .update(await scopeKey(selected.manifest))
      .update(JSON.stringify(spec([], selected)))
      .update(require('../package.json').version)
      .digest('hex');
    const saved = context.workspaceState.get('ide.' + identity);
    const target =
      saved || path.join(storage, 'ide', scopeId(selected.manifest), identity.slice(0, 20));
    const generated = await result(
      'Preparing Codex IDE workspace',
      ['vscode', '--output', target, '--preserve-edits'],
      selected,
    );
    if (!generated.workspace_file || !path.isAbsolute(generated.workspace_file))
      throw new Error('Engine did not return a valid workspace file');
    await context.workspaceState.update('ide.' + identity, path.dirname(generated.workspace_file));
    await vscode.window.showInformationMessage(
      (generated.preserved_workspace
        ? 'Your edited workspace was preserved; a new copy was prepared. '
        : '') +
        'Opening a Codex IDE workspace. Start a new Codex conversation in the Context Engine folder. Allow the workspace watch task when prompted. Codex manages its own sign-in.',
    );
    await vscode.commands.executeCommand(
      'vscode.openFolder',
      vscode.Uri.file(generated.workspace_file),
      { forceNewWindow: true },
    );
  }
  async function storeScope(selected) {
    if (crawler) throw new Error('Stop the crawler before changing scope.');
    const status = await result('Validating Context Engine scope', ['status'], selected);
    selected.label = `${status.environment} / ${status.workspace}`;
    const scopes = context.workspaceState
      .get('scopes', [])
      .filter((item) => item.manifest !== selected.manifest);
    await context.workspaceState.update('scopes', [...scopes, selected]);
    await context.workspaceState.update('scope', selected);
    refreshView();
    vscode.window.showInformationMessage(
      `Selected ${selected.label}. Run Refresh Code to index it. Existing agent terminals retain their original scope.`,
    );
  }
  async function chooseManifest() {
    if (crawler) throw new Error('Stop the crawler before changing scope.');
    const scopes = context.workspaceState.get('scopes', []);
    if (scopes.length) {
      const choice = await vscode.window.showQuickPick(
        [
          ...scopes.map((scope) => ({ label: scope.label, description: scope.manifest, scope })),
          { label: 'Browse for another manifest' },
        ],
        { title: 'Choose a context scope' },
      );
      if (!choice) return;
      if (choice.scope) {
        await storeScope(choice.scope);
        return;
      }
    }
    const files = await vscode.window.showOpenDialog({
      canSelectMany: false,
      filters: { 'Context Engine manifest': ['json'] },
      openLabel: 'Use this manifest',
    });
    if (files && files[0]) await storeScope({ manifest: files[0].fsPath });
  }
  async function createScope() {
    const folders = vscode.workspace.workspaceFolders || [];
    if (!folders.length)
      throw new Error('Open the repository folders in a VS Code workspace first.');
    const scope = await vscode.window.showQuickPick(
      [
        {
          label: 'Team',
          value: 'team',
          description: 'Select only repositories approved for this team scope',
        },
        {
          label: 'Personal',
          value: 'personal',
          description: 'Keep personal code and Scratch in a separate scope',
        },
      ],
      { title: 'Choose context visibility' },
    );
    if (!scope) return;
    const selected = await vscode.window.showQuickPick(
      folders.map((f) => ({ label: f.name, description: f.uri.fsPath, folder: f })),
      { title: `Select ${scope.value} repositories only`, canPickMany: true },
    );
    if (!selected || !selected.length) return;
    const name = await vscode.window.showInputBox({
      title: 'Context workspace name',
      value: 'workspace',
      validateInput: (s) =>
        /^[a-zA-Z0-9_-]{1,80}$/.test(s)
          ? null
          : 'Use 1–80 letters, digits, underscores or hyphens.',
    });
    if (!name) return;
    const dir = path.join(storage, 'manifests');
    await privateDir(dir);
    const manifest = path.join(dir, `${scope.value}-${name}-${randomUUID()}.json`);
    const sources = selected.map((item, i) => ({
      id: `repo_${i + 1}`,
      type: 'git',
      path: item.folder.uri.fsPath,
    }));
    const value = { schema_version: 1, environment: scope.value, workspace: name, sources };
    await fs.writeFile(manifest, JSON.stringify(value, null, 2) + '\n', {
      flag: 'wx',
      mode: 0o600,
    });
    await storeScope({ manifest });
  }
  async function cwd() {
    const folders = vscode.workspace.workspaceFolders || [];
    if (!folders.length) throw new Error('Open a repository folder for the coding session.');
    if (folders.length === 1) return folders[0].uri.fsPath;
    const selected = await vscode.window.showQuickPick(
      folders.map((f) => ({ label: f.name, description: f.uri.fsPath, folder: f })),
      { title: 'Working repository for this agent session' },
    );
    return selected && selected.folder.uri.fsPath;
  }
  async function pickProvider() {
    const selected = await vscode.window.showQuickPick(
      Object.entries(PROVIDERS).map(([id, p]) => ({ label: p.label, id })),
      { title: 'Choose an agent' },
    );
    return selected && selected.id;
  }
  async function agent(action, id, prompt, expectedPackScope) {
    guard();
    if (settings().get('policyPath', ''))
      throw new Error(
        'Terminal agent flows are disabled in managed pilot mode. Use the approved IDE integration.',
      );
    id = id || (await pickProvider());
    if (!id) return;
    const p = provider(id);
    try {
      await run({ executable: executable(id), args: ['--version'] }, { timeout: 15000 });
    } catch (_) {
      const choice = await vscode.window.showErrorMessage(
        `${p.label} CLI was not found or could not run on this extension host. Install it or set its executable path.`,
        'Install instructions',
        'Settings',
      );
      if (choice === 'Install instructions')
        await vscode.env.openExternal(vscode.Uri.parse(p.install));
      if (choice === 'Settings')
        await vscode.commands.executeCommand('workbench.action.openSettings', 'contextEngine');
      return;
    }
    let workdir = storage;
    await privateDir(storage);
    let options;
    if (action === 'launch') {
      const engine = spec();
      workdir = await cwd();
      if (!workdir) return;
      options = {
        engine,
        serverName: `context_engine_${scopeId(config().manifest)}`,
        model: selectedModel(id),
        prompt,
      };
      // Fail early if the bundled backend or configured interpreter is unavailable.
      await result('Checking Context Engine', ['status']);
    }
    if (
      expectedPackScope &&
      (!config() || (await scopeKey(config().manifest)) !== expectedPackScope)
    )
      throw new Error(
        'Context profile changed during handoff. Reopen the pack in its original scope.',
      );
    const launch = agentSpec(id, executable(id), action, options);
    const terminal = vscode.window.createTerminal({
      name: `${p.label}: ${action}`,
      shellPath: launch.executable,
      shellArgs: launch.args,
      cwd: workdir,
      isTransient: true,
    });
    terminals.add(terminal);
    terminal.show();
    if (action === 'login')
      vscode.window.showInformationMessage(
        `Complete sign-in in ${p.label}'s terminal/browser. The CLI owns credentials; use Account Status to verify. This changes the CLI's active account on this host.`,
      );
  }
  async function model() {
    const id = await pickProvider();
    if (!id) return;
    const value = await vscode.window.showInputBox({
      title: `${provider(id).label} model`,
      prompt:
        'Enter a model ID supported by your account, or leave blank for the agent default. Availability is checked by the agent.',
      value: selectedModel(id),
      validateInput: (s) =>
        s.length <= 200 && !/[\r\n\0]/.test(s)
          ? null
          : 'Enter a single model ID (up to 200 characters).',
    });
    if (value !== undefined) {
      await context.workspaceState.update(modelKey(id), value.trim());
      refreshView();
    }
  }
  function observedWatchers() {
    return (vscode.tasks.taskExecutions || []).filter((execution) => {
      const args = execution.task.execution?.args || [];
      return (
        execution === crawler ||
        (args.includes(config()?.manifest) && (args.includes('watch') || args.includes('crawl')))
      );
    });
  }
  async function startCrawler(codeOnly = false) {
    if (crawler || (codeOnly && observedWatchers().length)) {
      vscode.window.showInformationMessage(
        'Code refresh is already running for this scope in this window.',
      );
      return;
    }
    const mode =
      codeOnly || settings().get('policyPath', '')
        ? { args: ['crawl', '--no-history'] }
        : await vscode.window.showQuickPick(
            [
              {
                label: 'Code and architecture',
                args: ['crawl', '--no-history'],
                description: 'Uses profile refresh preferences; no history collection',
              },
              {
                label: 'Code, architecture, and history',
                args: ['crawl'],
                description: 'Also refresh available history using profile preferences',
              },
            ],
            { title: 'Start periodic refresh' },
          );
    if (!mode) return;
    const command = spec(mode.args);
    const task = new vscode.Task(
      { type: 'context-engine', scope: scopeId(config().manifest) },
      vscode.TaskScope.Workspace,
      `Crawler: ${config().label}`,
      'Context Engine',
      new vscode.ProcessExecution(command.executable, command.args, {
        cwd: path.dirname(launcher),
      }),
      [],
    );
    task.isBackground = true;
    crawler = await vscode.tasks.executeTask(task);
    refreshView();
  }
  async function search() {
    const query = await vscode.window.showInputBox({
      title: 'Search context',
      prompt: 'Ask in English or enter a code identifier',
    });
    if (!query) return;
    await workbench.open('code', query);
  }
  async function read() {
    const source = await vscode.window.showInputBox({
      title: 'Read source',
      prompt: 'Source ID from a search citation',
    });
    if (!source) return;
    const file = await vscode.window.showInputBox({
      title: 'Read file',
      prompt: 'Source-relative path from the citation',
    });
    if (!file) return;
    const start = await vscode.window.showInputBox({
      title: 'Starting line',
      value: '1',
      validateInput: (s) => (/^[1-9][0-9]*$/.test(s) ? null : 'Enter a positive line number'),
    });
    if (!start) return;
    const value = await result('Reading cited code', ['read', source, file, '--line-start', start]);
    await showJson(value);
  }
  const workbench = createWorkbench(vscode, context, {
    storage,
    guard,
    config,
    result,
    storeScope,
    showJson,
    managed: () => Boolean(settings().get('policyPath', '')),
    codexIde,
    startWatcher: () => startCrawler(true),
    stopWatcher: async () => {
      for (const execution of observedWatchers()) execution.terminate();
      if (crawler && !observedWatchers().includes(crawler)) crawler.terminate();
    },
    health: () => ({
      watcher:
        crawler || observedWatchers().length
          ? 'Running in this window'
          : 'Not observed in this window; a watcher may run elsewhere',
      canStop: Boolean(crawler || observedWatchers().length),
      ide: 'Start in the generated Context Engine folder and verify its MCP tools',
      checkedAt,
    }),
    assertMutable: () => {
      if (crawler) throw new Error('Stop the crawler before editing a profile');
    },
  });
  context.subscriptions.push(workbench);
  const actions = {
    getStarted,
    toggleAdvanced: () => {
      showAdvanced = !showAdvanced;
      refreshView();
    },
    searchSelection: async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor || editor.selection.isEmpty)
        throw new Error('Select an identifier, error, or short passage in the editor first');
      const query = editor.document.getText(editor.selection);
      await workbench.open('code', query);
    },
    checkSetup,
    codexIde,
    workbench: () => workbench.open(),
    profiles: () => workbench.open('profile'),
    reviewLearning: () => workbench.open('reviewLearning'),
    taskPacks: () => workbench.open('packs'),
    workspaceHealth: () => workbench.open('health'),
    knowledgeHome: () => workbench.open('knowledge'),
    chooseManifest,
    createScope,
    status: async () => showJson(await result('Checking index', ['status'])),
    refresh: async () => {
      await result('Refreshing code and architecture', ['index']);
      await showJson(await result('Checking refreshed index', ['status']));
    },
    refreshAll: async () =>
      showJson(
        await result('Refreshing code and available history', ['crawl', '--once', '--force']),
      ),
    structure: async () => {
      const mode = await vscode.window.showQuickPick(
        ['definitions', 'references', 'callers', 'dependencies', 'impact'],
        { title: 'Structural navigation' },
      );
      if (!mode) return;
      const source = await vscode.window.showInputBox({
        title: 'Source ID',
        prompt: 'Source ID in the selected scope',
      });
      if (!source) return;
      const args = ['structure', `--mode=${mode}`, `--source=${source}`, '--token-budget=8000'];
      if (['dependencies', 'impact'].includes(mode)) {
        const file = await vscode.window.showInputBox({ title: 'Source-relative file path' });
        if (!file) return;
        args.push(`--path=${file}`);
      } else {
        const symbol = await vscode.window.showInputBox({
          title: 'Symbol name',
          prompt: 'Exact identifier; definitions may be left empty to browse',
        });
        if (symbol === undefined) return;
        args.push(`--symbol=${symbol}`);
      }
      await showJson(await result('Loading structural navigation', args));
    },
    instructions: async () => {
      const source = await vscode.window.showInputBox({
        title: 'Resolve instructions',
        prompt: 'Source ID in the selected scope',
      });
      if (!source) return;
      const file = await vscode.window.showInputBox({
        title: 'Task file',
        prompt: 'Source-relative file path (may be a new file)',
      });
      if (!file) return;
      await showJson(
        await result('Resolving repository instructions', [
          'instructions',
          `--source=${source}`,
          `--path=${file}`,
          '--token-budget=8000',
        ]),
      );
    },
    overview: () => workbench.open('architecture'),
    search,
    read,
    startCrawler,
    stopCrawler: async () => {
      if (crawler) crawler.terminate();
    },
    login: () => agent('login'),
    logout: () => agent('logout'),
    accountStatus: () => agent('status'),
    launchAgent: () => agent('launch'),
    model,
    codexLogin: () => agent('login', 'codex'),
    claudeLogin: () => agent('login', 'claude'),
    codexLaunch: () => agent('launch', 'codex'),
    claudeLaunch: () => agent('launch', 'claude'),
    changeBrief: () => workbench.open('brief'),
    knowledgeWiki: async () => {
      const kind = await vscode.window.showQuickPick(
        ['all', 'practice', 'architecture', 'convention', 'decision', 'procedure'],
        {
          title: 'Human wiki section',
        },
      );
      if (!kind) return;
      const source = await pickSource('Choose repository');
      if (!source) return;
      await openWiki(kind, source);
    },
    commonplace: async () => {
      const choice = await vscode.window.showQuickPick(
        [
          'Open local Commonplace',
          'Configure team repository mapping',
          'Preview and import edited records',
        ],
        { title: 'Commonplace — local team knowledge' },
      );
      if (!choice) return;
      if (choice === 'Preview and import edited records') {
        const files = await vscode.window.showOpenDialog({
          canSelectMany: false,
          filters: { JSON: ['json'] },
          title: 'Choose Commonplace edit.json',
        });
        if (!files?.length) return;
        const file = '--file=' + files[0].fsPath;
        const preview = await result('Previewing Commonplace changes', [
          'commonplace',
          'preview',
          file,
        ]);
        await showJson(preview);
        if (preview.conflicts.length || !preview.changes.length) return;
        const decision = await vscode.window.showWarningMessage(
          'Review the displayed before/after records. Import these changes as unapproved proposals?',
          { modal: true },
          'Import proposals',
        );
        if (decision !== 'Import proposals') return;
        await showJson(
          await result('Importing reviewed edit file as proposals', [
            'commonplace',
            'import',
            file,
            '--preview-token=' + preview.preview_token,
          ]),
        );
        return;
      }
      if (choice === 'Configure team repository mapping') {
        const current = await result('Reading Commonplace settings', ['commonplace', 'status']);
        const repository = await vscode.window.showInputBox({
          prompt: 'Team repository mapping (owner/repository). No clone or sync.',
          value: current.repository,
        });
        if (repository === undefined) return;
        const directory = await vscode.window.showInputBox({
          prompt: 'Company-controlled local placeholder directory (absolute)',
          value: current.directory,
        });
        if (!directory) return;
        await showJson(
          await result('Configuring Commonplace', [
            'commonplace',
            'configure',
            '--repository=' + repository,
            '--directory=' + directory,
          ]),
        );
        return;
      }
      const value = await result('Creating local Commonplace snapshot', [
        'commonplace',
        'materialize',
      ]);
      await vscode.commands.executeCommand('revealFileInOS', vscode.Uri.file(value.snapshot));
      vscode.window.showInformationMessage(
        'Commonplace snapshot created locally. SQLite records remain authoritative; files are not synced or imported automatically.',
      );
    },
    knowledgeDraft: async () => {
      const kind = await vscode.window.showQuickPick(
        ['practice', 'architecture', 'convention', 'decision', 'procedure'],
        { title: 'New knowledge draft' },
      );
      if (!kind) return;
      const source = await pickSource('Choose repository for this knowledge draft');
      const file = await vscode.window.showInputBox({
        prompt: 'Current indexed supporting file (source-relative)',
      });
      if (!source || !file) return;
      await showJson(
        await result('Preparing editable draft', [
          'knowledge',
          'template',
          '--kind=' + kind,
          '--source=' + source,
          '--path=' + file,
        ]),
      );
      vscode.window.showInformationMessage(
        'Edit the draft, save it in company-controlled storage, then Import knowledge proposal. DRAFT statements cannot be approved.',
      );
    },
    knowledgeHistory: async () => {
      const identity = await vscode.window.showInputBox({ prompt: 'Knowledge record ID' });
      if (identity)
        await showJson(
          await result('Loading decision/revision history', [
            'knowledge',
            'history',
            '--id=' + identity,
          ]),
        );
    },
    knowledgeAudit: async () =>
      showJson(await result('Checking local audit chain', ['knowledge', 'audit'])),
    githubReviews: async () => {
      const source = await pickSource('Choose repository');
      if (!source) return;
      const access = await result('Checking GitHub permission', [
        'knowledge',
        'github-access',
        '--source=' + source,
      ]);
      const pull = await vscode.window.showInputBox({
        prompt: 'Pull request number in ' + access.repository,
      });
      if (!pull || !/^[1-9][0-9]{0,8}$/.test(pull)) return;
      const token = await vscode.window.showInputBox({
        prompt: 'Approved GitHub token with Pull requests: read. Used for this request only.',
        password: true,
        ignoreFocusOut: true,
      });
      if (!token) return;
      const value = JSON.parse(
        await run(
          {
            ...spec(['knowledge', 'github-fetch', '--source=' + source, '--pull=' + pull]),
            env: { ...process.env, CONTEXT_ENGINE_GITHUB_TOKEN: token },
          },
          { timeout: 120000 },
        ),
      );
      await showJson(value);
    },
    githubCandidate: async () => {
      const source = await pickSource('Choose repository');
      if (!source) return;
      const batch = await result('Loading local review events', [
        'knowledge',
        'github-inbox',
        '--source=' + source,
      ]);
      const choice = await vscode.window.showQuickPick(
        batch.groups.map(({ event, distinct_pulls }) => ({
          label: `PR ${event.pull}: ${event.event_id}`,
          description: `${event.path || 'General review'} · ${distinct_pulls} distinct PR(s), exact text match`,
          event,
        })),
        { title: 'Choose a review to refine into a draft lesson' },
      );
      if (!choice) return;
      await showJson(choice.event);
      const file = await vscode.window.showInputBox({
        prompt: 'Indexed supporting file for the lesson',
        value: choice.event.path,
      });
      if (!file) return;
      const draft = await result('Preparing unapproved review lesson', [
        'knowledge',
        'github-candidate',
        '--event=' + choice.event.id,
        '--path=' + file,
      ]);
      const statement = await vscode.window.showInputBox({
        prompt: 'Refine the quoted suggestion into a reusable practice (keep DRAFT: if unresolved)',
        value: draft.statement,
      });
      if (!statement) return;
      const prefix = await vscode.window.showInputBox({
        prompt: 'Applicable source-relative file or directory; empty means the whole source',
        value: file,
      });
      if (prefix === undefined) return;
      const exception = await vscode.window.showInputBox({
        prompt: 'Known exception, if any. Leave empty only after considering applicability.',
        value: '',
      });
      if (exception === undefined) return;
      draft.statement = statement;
      draft.title = statement.replace(/^DRAFT:\s*/, '').slice(0, 120);
      draft.prefix = prefix;
      draft.exceptions = exception ? [exception] : [];
      await showJson(draft);
      vscode.window.showInformationMessage(
        'Review the full imported event, refine the draft into general guidance, then save and import it. Nothing is approved automatically.',
      );
    },
    knowledgePropose: async () => {
      const files = await vscode.window.showOpenDialog({
        canSelectMany: false,
        filters: { JSON: ['json'] },
        title: 'Import company-local knowledge proposal',
      });
      if (!files?.length) return;
      const revision = await vscode.window.showInputBox({
        prompt: 'Latest record revision (0 for a new ID)',
        value: '0',
      });
      if (revision === undefined) return;
      await showJson(
        await result('Creating proposal (not approved)', [
          'knowledge',
          'propose',
          '--file=' + files[0].fsPath,
          '--revision=' + revision,
        ]),
      );
    },
    reasoningNote: async () => {
      const value = await result('Preparing empty Scratch note', ['reasoning-template']);
      const doc = await vscode.workspace.openTextDocument({
        language: 'markdown',
        content: value.markdown,
      });
      await vscode.window.showTextDocument(doc);
      vscode.window.showInformationMessage(
        'Save this exploration note only in the appropriate company-controlled Scratch. Nothing has been saved or promoted to Commonplace.',
      );
    },
    knowledgeMaintenance: async () => {
      const source = await pickSource('Choose repository');
      if (!source) return;
      const queue = await result('Checking knowledge freshness and local feedback', [
        'knowledge',
        'maintenance',
        '--source=' + source,
      ]);
      await showJson(queue);
      const selected = await vscode.window.showQuickPick(
        queue.items.map((record) => ({
          label: record.title,
          description: `${record.id} r${record.revision} (${record.stale_evidence ? 'stale evidence' : record.status})`,
          record,
        })),
        { title: 'Choose a record to inspect; no automatic cleanup' },
      );
      if (!selected) return;
      const record = selected.record;
      const action = await vscode.window.showQuickPick(
        ['useful', 'wrong_scope', 'stale', 'redundant', 'Prepare re-review draft'],
        { title: 'Record a local observation or prepare a draft' },
      );
      if (!action) return;
      const args = [
        'knowledge',
        action === 'Prepare re-review draft' ? 'refresh-draft' : 'feedback',
        '--id=' + record.id,
        '--revision=' + record.revision,
      ];
      if (action !== 'Prepare re-review draft') args.push('--outcome=' + action);
      const value = await result('Maintaining local knowledge', args);
      await showJson(value.draft || value);
      if (value.draft)
        vscode.window.showInformationMessage(
          `Inspect changed evidence and refine this draft before importing at expected revision ${value.expected_revision}. ${value.review_required}`,
        );
    },
    knowledgeReview: async () => {
      const queue = await result('Loading local knowledge review', ['knowledge', 'queue']);
      const selected = await vscode.window.showQuickPick(
        queue.records
          .filter((r) => ['proposed', 'approved'].includes(r.status))
          .map((record) => ({
            label: record.title,
            description: `${record.id} r${record.revision} (${record.status})`,
            record,
          })),
        { title: 'Review scope, statement, rationale, evidence and conflicting guidance' },
      );
      if (!selected) return;
      const row = selected.record;
      await showJson(row);
      const action = await vscode.window.showWarningMessage(
        'Review this exact revision and supporting evidence. Approval replaces the prior approved revision of this ID. Resolve conflicting guidance before approving. This content stays company-local.',
        { modal: true },
        ...(row.status === 'proposed' ? ['Approve', 'Reject'] : ['Retire']),
      );
      if (!action) return;
      await showJson(
        await result('Recording human decision', [
          'knowledge',
          action.toLowerCase(),
          '--id=' + row.id,
          '--revision=' + row.revision,
        ]),
      );
    },
    benchmark: async () => {
      const args = [launcher];
      const policy = settings().get('policyPath', '');
      if (policy) args.push('--policy', policy);
      args.push('benchmark');
      await showJson(
        JSON.parse(
          await run(
            { executable: settings().get('pythonPath', 'python3'), args },
            { timeout: 120000 },
          ),
        ),
      );
    },
    clientReadiness: async () =>
      showJson(await result('Checking client readiness', ['local-data', 'readiness'])),
    localData: async () => {
      const value = await result('Inspecting local data', ['local-data', 'inventory']);
      const scope = await scopeKey(config().manifest);
      const artifacts = ['packs', 'handoffs'].map((kind) => path.join(storage, kind, scope));
      await showJson({ ...value, selectedExtensionArtifacts: artifacts });
      const choice = await vscode.window.showWarningMessage(
        'This inventory contains local paths. Do not send it as a usage report. Stop all agents and crawlers before resetting the current index.',
        { modal: true },
        'Reset current index',
        'Delete selected packs and handoffs',
      );
      if (choice === 'Delete selected packs and handoffs') {
        workbench.dispose();
        for (const folder of [storage, ...artifacts.map((f) => path.dirname(f))]) {
          const item = await fs.lstat(folder).catch((error) => {
            if (error.code !== 'ENOENT') throw error;
          });
          if (item?.isSymbolicLink()) throw new Error('Refusing symlink artifact ancestor');
        }
        for (const folder of artifacts) {
          const item = await fs.lstat(folder).catch((error) => {
            if (error.code !== 'ENOENT') throw error;
          });
          if (item?.isSymbolicLink()) throw new Error('Refusing symlink artifact directory');
          if (item) await fs.rm(folder, { recursive: true });
        }
      }
      if (choice === 'Reset current index') {
        if (crawler) throw new Error('Stop the crawler before resetting data');
        await showJson(await result('Resetting selected index', ['local-data', 'purge-index']));
      }
    },
    usageReport: async () => {
      const choice = await vscode.window.showQuickPick(
        [
          { label: 'Preview usage report', action: 'report' },
          { label: 'Enable local aggregate collection', action: 'enable' },
          { label: 'Pause local aggregate collection', action: 'disable' },
          { label: 'Clear usage aggregates and disable collection', action: 'clear' },
        ],
        { title: 'Content-free usage statistics — nothing is uploaded' },
      );
      if (!choice) return;
      if (choice.action !== 'report') {
        const ok = await vscode.window.showWarningMessage(
          'Only fixed operation counts, outcomes, timing buckets and byte totals are stored locally in a rolling 30-day window, pruned on next access. No prompts, code, paths or identities are recorded. This action changes local collection.',
          { modal: true },
          'Continue',
        );
        if (ok !== 'Continue') return;
        await result('Updating local statistics', ['usage', choice.action]);
        return;
      }
      const report = await result('Preparing usage report', ['usage', 'report']);
      const content = reviewedReport(report);
      const document = await vscode.workspace.openTextDocument({ content, language: 'json' });
      await vscode.window.showTextDocument(document, { preview: false });
      const save = await vscode.window.showInformationMessage(
        'Review this exact report before saving for internal vetting. Nothing is uploaded. Rolling reports may overlap; do not count repeated exports as independent usage.',
        'Save reviewed report',
      );
      if (save !== 'Save reviewed report') return;
      if (document.getText() !== content)
        throw new Error('Preview changed. Generate a fresh report before saving.');
      const target = await vscode.window.showSaveDialog({
        filters: { JSON: ['json'] },
        saveLabel: 'Save for client review',
      });
      if (target) {
        const stat = await fs.lstat(target.fsPath).catch((error) => {
          if (error.code !== 'ENOENT') throw error;
        });
        if (stat) throw new Error('Choose a new filename; existing files are not overwritten.');
        await fs.writeFile(target.fsPath, content, { flag: 'wx', mode: 0o600 });
      }
    },
    diagnostics: async () => {
      const versions = {};
      for (const [id, binary] of [
        ['python', settings().get('pythonPath', 'python3')],
        ...Object.keys(PROVIDERS).map((id) => [id, executable(id)]),
      ]) {
        try {
          versions[id] = (
            await run({ executable: binary, args: ['--version'] }, { timeout: 15000 })
          ).trim();
        } catch (_) {
          versions[id] = 'Unavailable; check executable path on this host';
        }
      }
      await showJson({
        remote: vscode.env.remoteName || 'local',
        scope: config() || null,
        versions,
        authentication: 'Not checked. Use Account Status in the official CLI.',
        openModels: 'Stretch goal; not implemented.',
      });
    },
  };
  const rows = () =>
    [
      ['Get started', 'getStarted', 'rocket'],
      [
        showAdvanced ? 'Show everyday actions' : 'Show advanced actions',
        'toggleAdvanced',
        'settings-gear',
      ],
      ['Check Python and Kotlin setup', 'checkSetup', 'checklist'],
      ['Open Codex IDE workspace', 'codexIde', 'window'],
      ['Context workbench', 'workbench', 'layout'],
      ['Wiki', 'knowledgeWiki', 'book'],
      ['Workspace health', 'workspaceHealth', 'pulse'],
      ['Team knowledge', 'knowledgeHome', 'book'],
      ['Learn from GitHub reviews', 'reviewLearning', 'repo-pull'],
      ['Edit workspace profile', 'profiles', 'settings-gear'],
      ['Task context packs', 'taskPacks', 'pin'],
      [
        config() ? `Scope: ${config().label}` : 'Select a context manifest',
        'chooseManifest',
        'folder-opened',
      ],
      ['Create scope from workspace folders', 'createScope', 'new-folder'],
      [`Index: ${readiness} (check now)`, 'status', 'pulse'],
      ['Refresh code', 'refresh', 'refresh'],
      ['Refresh code and history', 'refreshAll', 'history'],
      ['System overview', 'overview', 'type-hierarchy'],
      ['Prepare change context brief', 'changeBrief', 'git-compare'],
      ['Commonplace team knowledge', 'commonplace', 'repo'],
      ['New knowledge draft', 'knowledgeDraft', 'edit'],
      ['Knowledge revision history', 'knowledgeHistory', 'history'],
      ['Local review audit', 'knowledgeAudit', 'shield'],
      ['Fetch GitHub review candidates', 'githubReviews', 'repo-pull'],
      ['Refine imported review lesson', 'githubCandidate', 'lightbulb'],
      ['Import knowledge proposal', 'knowledgePropose', 'add'],
      ['Maintain local knowledge', 'knowledgeMaintenance', 'checklist'],
      ['New Scratch reasoning note', 'reasoningNote', 'note'],
      ['Review knowledge proposals', 'knowledgeReview', 'checklist'],
      ['Resolve repository instructions', 'instructions', 'book'],
      ['Structural navigation', 'structure', 'symbol-method'],
      ['Search code', 'search', 'search'],
      ['Read cited file', 'read', 'go-to-file'],
      [
        crawler ? 'Stop crawler' : 'Start crawler',
        crawler ? 'stopCrawler' : 'startCrawler',
        crawler ? 'debug-stop' : 'play',
      ],
      ['Sign in to OpenAI Codex', 'codexLogin', 'account'],
      ['Sign in to Claude Code', 'claudeLogin', 'account'],
      [
        `Codex terminal (legacy)${selectedModel('codex') ? ` (${selectedModel('codex')})` : ''}`,
        'codexLaunch',
        'terminal',
      ],
      [
        `Open Claude Code${selectedModel('claude') ? ` (${selectedModel('claude')})` : ''}`,
        'claudeLaunch',
        'terminal',
      ],
      ['Choose model', 'model', 'settings-gear'],
      ['Account status', 'accountStatus', 'verified'],
      ['Sign out', 'logout', 'sign-out'],
      ['Run synthetic benchmark', 'benchmark', 'beaker'],
      ['Client-test readiness', 'clientReadiness', 'checklist'],
      ['Usage report (review before sharing)', 'usageReport', 'graph'],
      ['Local data inventory and reset', 'localData', 'database'],
      ['Diagnostics', 'diagnostics', 'tools'],
    ]
      .filter(
        ([, action]) =>
          showAdvanced ||
          new Set([
            'getStarted',
            'toggleAdvanced',
            'workbench',
            'chooseManifest',
            'workspaceHealth',
            'knowledgeHome',
            'knowledgeWiki',
            'changeBrief',
            'taskPacks',
            'codexIde',
          ]).has(action),
      )
      .map(([label, action, icon]) => {
        const item = new vscode.TreeItem(label);
        item.command = { command: `contextEngine.${action}`, title: label };
        item.iconPath = new vscode.ThemeIcon(icon);
        return item;
      });
  context.subscriptions.push(
    output,
    changed,
    vscode.window.registerTreeDataProvider('contextEngine.home', {
      onDidChangeTreeData: changed.event,
      getTreeItem: (item) => item,
      getChildren: () => rows(),
    }),
  );
  refreshView();
  for (const [name, fn] of Object.entries(actions)) {
    context.subscriptions.push(
      vscode.commands.registerCommand(`contextEngine.${name}`, async () => {
        if (running.size) {
          await vscode.window.showInformationMessage(
            'Finish or cancel the current Context Engine action first.',
          );
          return;
        }
        try {
          guard();
          running.add(name);
          return await fn();
        } catch (error) {
          output.appendLine(`${name}: ${error.message}`);
          await vscode.window.showErrorMessage(`Context Engine: ${error.message}`);
        } finally {
          running.delete(name);
        }
      }),
    );
  }
  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument(() => {
      readiness = 'check after save';
      refreshView();
    }),
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration('contextEngine')) {
        readiness = 'not checked';
        setupState = undefined;
        refreshView();
      }
    }),
    vscode.tasks.onDidEndTask((event) => {
      if (event.execution === crawler) {
        crawler = undefined;
        refreshView();
      }
    }),
    vscode.window.onDidCloseTerminal((terminal) => terminals.delete(terminal)),
    {
      dispose() {
        disposed = true;
        if (crawler) crawler.terminate();
        for (const terminal of terminals) terminal.dispose();
      },
    },
  );
  return {
    openWiki,
    openProfile: async (uri) => {
      guard();
      if (!uri || typeof uri.fsPath !== 'string' || !path.isAbsolute(uri.fsPath))
        throw new Error('An absolute manifest URI is required');
      await storeScope({ manifest: uri.fsPath });
    },
  };
}
module.exports = { activate };
