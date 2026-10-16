'use strict';
const path = require('node:path');
const crypto = require('node:crypto');
const { execFile } = require('node:child_process');
// Only fixed engine validation messages can reach a notification. Never display arbitrary stderr.
const ENGINE_ERRORS = new Map([
  [
    'Knowledge changed; reload before proposing',
    'Knowledge changed in another window. Your draft is still open; copy your edits, reload knowledge and apply them to the latest revision.',
  ],
  [
    'Review revision/status changed; reload',
    'This review changed in another window. Reload team knowledge before deciding.',
  ],
  [
    'A newer proposal exists; review it first',
    'A newer proposal exists. Reload team knowledge and review the latest revision.',
  ],
  [
    'Choose the latest approved or proposed revision',
    'Select the latest proposal for re-review; an older revision cannot replace it.',
  ],
  [
    'Refine the draft before approval',
    'Replace the DRAFT statement with reviewed guidance before approval.',
  ],
  [
    'Supporting evidence is stale; refresh and revise the proposal',
    'Supporting evidence changed. Refresh code and prepare a re-review draft.',
  ],
  ['Refresh the code index first', 'Refresh code in Workspace Health, then try again.'],
  [
    'Supporting file missing; select replacement evidence manually',
    'A supporting file was removed. Create a replacement proposal grounded in a current file.',
  ],
  [
    'Invalid knowledge text length',
    'Enter a title (1–150 characters), guidance (1–1200) and rationale (1–6000). Your draft is still open.',
  ],
  [
    'Invalid applicability/exception list',
    'Use at most 12 entries per list: 64 characters per language/task and 500 per exception.',
  ],
  [
    'Complete the decision/procedure fields',
    'Complete every required decision or procedure field before saving.',
  ],
  ['Detail lists need 1..12 items', 'Each structured detail needs 1–12 entries.'],
  [
    'Diagnostic branches need bounded if/then text',
    'Complete both If and Then in each diagnostic branch, at most 500 characters each.',
  ],
  ['Invalid knowledge detail', 'Keep each structured detail between 1 and 500 characters.'],
  [
    'Knowledge record exceeds 24 KB; split it into bounded records',
    'Split this knowledge into smaller records; each record must fit within 24 KB.',
  ],
  [
    'Local Git comparison failed; select a checkout and valid commit',
    'Choose a Git checkout and an existing commit or branch as the comparison base.',
  ],
  ['Select a commit or branch ref', 'Enter a commit or branch name, such as HEAD or main.'],
]);

const PROVIDERS = Object.freeze({
  codex: {
    label: 'OpenAI Codex',
    executable: 'codex',
    login: ['login'],
    logout: ['logout'],
    status: ['login', 'status'],
    install: 'https://learn.chatgpt.com/docs/cli',
  },
  claude: {
    label: 'Anthropic Claude Code',
    executable: 'claude',
    login: ['auth', 'login'],
    logout: ['auth', 'logout'],
    status: ['auth', 'status'],
    install: 'https://code.claude.com/docs/en/setup',
  },
});
function provider(id) {
  if (!Object.hasOwn(PROVIDERS, id)) throw new Error('Unknown agent provider');
  return PROVIDERS[id];
}
function scopeId(manifest) {
  return crypto.createHash('sha256').update(path.resolve(manifest)).digest('hex').slice(0, 20);
}
function stateDirectory(storage, manifest, configured = {}) {
  if (!configured || typeof configured !== 'object' || Array.isArray(configured))
    throw new Error('State paths must map absolute manifest paths to absolute directories');
  const key = path.resolve(manifest);
  if (Object.hasOwn(configured, key)) {
    const state = configured[key];
    if (typeof state !== 'string' || !path.isAbsolute(state))
      throw new Error('The selected scope needs an absolute state directory');
    return state;
  }
  return path.join(storage, 'state', scopeId(manifest));
}
function engineSpec(python, launcher, manifest, state, args) {
  if (!path.isAbsolute(launcher) || !path.isAbsolute(manifest) || !path.isAbsolute(state))
    throw new Error('Engine paths must be absolute');
  return {
    executable: python,
    args: [launcher, '--manifest', manifest, '--state', state, ...args],
    engineErrors: true,
    env: { ...process.env, CONTEXT_ENGINE_PYTHON_LAUNCHER: python },
  };
}
function agentSpec(id, executable, action, { engine, serverName, model = '', prompt } = {}) {
  const p = provider(id);
  if (action !== 'launch') {
    if (!['login', 'logout', 'status'].includes(action)) throw new Error('Unknown agent action');
    return { executable, args: [...p[action]] };
  }
  if (!engine || !/^[a-zA-Z0-9_]+$/.test(serverName))
    throw new Error('A scoped MCP server is required');
  const args = [];
  if (id === 'codex') {
    // Values are TOML strings/arrays passed as individual argv entries, never shell text.
    for (const [key, value] of Object.entries({
      command: engine.executable,
      args: [...engine.args, 'serve'],
    })) {
      args.push('-c', `mcp_servers.${serverName}.${key}=${JSON.stringify(value)}`);
    }
  } else {
    args.push(
      '--mcp-config',
      JSON.stringify({
        mcpServers: {
          [serverName]: {
            type: 'stdio',
            command: engine.executable,
            args: [...engine.args, 'serve'],
          },
        },
      }),
    );
  }
  if (model) args.push('--model', model);
  if (prompt) args.push('--', prompt);
  return { executable, args };
}
function run(spec, { cwd, timeout = 120000, token } = {}) {
  return new Promise((resolve, reject) => {
    let cancel;
    let cancelled = false;
    const child = execFile(
      spec.executable,
      spec.args,
      {
        cwd,
        timeout,
        env: spec.env || process.env,
        maxBuffer: 16 * 1024 * 1024,
        windowsHide: true,
        shell: false,
      },
      (error, stdout, stderr) => {
        if (cancel) cancel.dispose();
        if (cancelled) return reject(new Error('Operation cancelled'));
        if (error) {
          const explanation = spec.engineErrors && ENGINE_ERRORS.get(stderr.trim());
          if (explanation) return reject(new Error(explanation));
          const reason =
            error.code === 'ENOENT'
              ? 'Executable not found. Set its path in Context Engine settings.'
              : error.killed
                ? 'Operation timed out. Inspect the configured source/provider and try a smaller refresh.'
                : `Process failed (${error.code || 'unknown'}). Run diagnostics or inspect the task terminal.`;
          // Never forward arbitrary process stderr into notifications (credentials may be present).
          return reject(new Error(reason));
        }
        resolve(stdout);
      },
    );
    if (token) {
      const stop = () => {
        cancelled = true;
        child.kill();
      };
      cancel = token.onCancellationRequested(stop);
      if (token.isCancellationRequested) stop();
    }
  });
}
module.exports = { PROVIDERS, provider, scopeId, stateDirectory, engineSpec, agentSpec, run };
