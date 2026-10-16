'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const os = require('node:os');
const fs = require('node:fs/promises');
const { execFileSync } = require('node:child_process');
const { agentSpec, engineSpec, scopeId, run } = require('../src/runtime');
const root = path.resolve(__dirname, '../..');

test('provider login/logout/status use official CLI arguments', () => {
  assert.deepEqual(agentSpec('codex', 'codex', 'login').args, ['login']);
  assert.deepEqual(agentSpec('claude', 'claude', 'login').args, ['auth', 'login']);
  assert.deepEqual(agentSpec('codex', 'codex', 'status').args, ['login', 'status']);
  assert.deepEqual(agentSpec('claude', 'claude', 'logout').args, ['auth', 'logout']);
  assert.throws(() => agentSpec('__proto__', 'anything', 'login'));
});

test('MCP launch preserves paths, model names and scope without shell interpolation', () => {
  const engine = engineSpec(
    '/path with space/python',
    '/backend/launch.py',
    '/repo/$(touch bad)/team.json',
    '/state/team',
    [],
  );
  const codex = agentSpec('codex', '/bin/codex', 'launch', {
    engine,
    serverName: 'context_engine_team',
    model: 'model; touch bad',
  });
  assert.equal(codex.args.at(-1), 'model; touch bad');
  assert.deepEqual(JSON.parse(codex.args[3].split('=').slice(1).join('=')), [
    ...engine.args,
    'serve',
  ]);
  const claude = agentSpec('claude', '/bin/claude', 'launch', {
    engine,
    serverName: 'context_engine_team',
  });
  const config = JSON.parse(claude.args[1]);
  assert.deepEqual(Object.keys(config.mcpServers), ['context_engine_team']);
  assert.deepEqual(config.mcpServers.context_engine_team.args, [...engine.args, 'serve']);
  assert.notEqual(scopeId('/team.json'), scopeId('/personal.json'));
  assert.throws(() => engineSpec('python', 'relative.py', '/manifest', '/state', []));
});

test('process execution treats hostile-looking argv literally and redacts stderr', async () => {
  const text = '$(echo secret); `whoami`\nsecond line';
  assert.equal(
    await run({
      executable: process.execPath,
      args: ['-e', 'process.stdout.write(process.argv[1])', text],
    }),
    text,
  );
  await assert.rejects(
    run({
      executable: process.execPath,
      args: ['-e', 'console.error("SECRET_SENTINEL"); process.exit(2)'],
    }),
    (error) => !error.message.includes('SECRET_SENTINEL'),
  );
  await assert.rejects(
    run(
      { executable: process.execPath, args: ['-e', 'setInterval(()=>{},1000)'] },
      { timeout: 30 },
    ),
    /timed out/,
  );
});

test('packaged backend indexes and retrieves real fixture through shipped launcher', async () => {
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'context-extension-'));
  try {
    const bundled = path.join(root, 'vscode-extension/backend/launch.py');
    const engine = engineSpec(
      'python3',
      bundled,
      path.join(root, 'examples/acme.json'),
      path.join(temp, 'state'),
      ['index'],
    );
    const indexed = JSON.parse(await run(engine));
    assert.ok(indexed.generation);
    const found = JSON.parse(
      await run({
        ...engine,
        args: [
          ...engine.args.slice(0, -1),
          'discover',
          'task.requested priority',
          '--token-budget',
          '8000',
        ],
      }),
    );
    assert.ok(found.items.length);
    const overview = JSON.parse(
      await run({ ...engine, args: [...engine.args.slice(0, -1), 'overview'] }),
    );
    assert.equal(overview.state, 'ready');
    assert.ok(overview.items.length);
  } finally {
    await fs.rm(temp, { recursive: true, force: true });
  }
});

test('VSIX includes backend and excludes source data and dependencies', () => {
  const check = execFileSync(
    'python3',
    [
      '-c',
      `import zipfile, json, xml.etree.ElementTree as E
version=json.load(open('vscode-extension/package.json'))['version']
z=zipfile.ZipFile('dist/context-engine-'+version+'.vsix')
n=z.namelist()
assert 'extension/backend/context_engine/core.py' in n
assert 'extension/backend/launch.py' in n
assert not any('/.context-engine/' in x or '/__pycache__/' in x or '/node_modules/' in x or '/examples/' in x or x.endswith('.sqlite') for x in n)
p=json.loads(z.read('extension/package.json'))
assert p['capabilities']['untrustedWorkspaces']['supported'] is False
E.fromstring(z.read('extension.vsixmanifest'))
E.fromstring(z.read('[Content_Types].xml'))
print('valid')`,
    ],
    { cwd: root, encoding: 'utf8' },
  );
  assert.equal(check.trim(), 'valid');
});

test('state directory overrides stay paired to a manifest and invalid overrides fail', () => {
  const { stateDirectory } = require('../src/runtime');
  const mapping = {
    '/core/team.json': '/core/state/team',
    '/core/personal.json': '/core/state/personal',
  };
  assert.equal(stateDirectory('/extension', '/core/team.json', mapping), '/core/state/team');
  assert.equal(
    stateDirectory('/extension', '/core/personal.json', mapping),
    '/core/state/personal',
  );
  assert.equal(
    stateDirectory('/extension', '/other.json', mapping),
    path.join('/extension', 'state', scopeId('/other.json')),
  );
  assert.throws(
    () => stateDirectory('/extension', '/core/team.json', { '/core/team.json': 'relative' }),
    /absolute state/,
  );
  assert.throws(() => stateDirectory('/extension', '/core/team.json', []), /State paths/);
});

test('workspace generation retains the configured runtime launcher', () => {
  const spec = engineSpec(
    '/runtime with spaces/python',
    '/backend/launch.py',
    '/repo/m.json',
    '/state',
    ['vscode'],
  );
  assert.equal(spec.env.CONTEXT_ENGINE_PYTHON_LAUNCHER, spec.executable);
  assert.equal(spec.env.PATH, process.env.PATH);
});
