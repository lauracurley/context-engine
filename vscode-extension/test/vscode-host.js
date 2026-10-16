'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const vscode = require('vscode');
const os = require('node:os');

async function run() {
  const extension = vscode.extensions.getExtension('context-engine-local.context-engine');
  assert.ok(extension, 'Extension is discoverable');
  await extension.activate();
  assert.equal(extension.isActive, true);
  const commands = await vscode.commands.getCommands(true);
  for (const command of extension.packageJSON.contributes.commands)
    assert.ok(commands.includes(command.command), command.command);
  await fs.access(path.join(extension.extensionPath, 'backend/launch.py'));
  await vscode.commands.executeCommand('workbench.view.extension.contextEngine');
  await vscode.commands.executeCommand('contextEngine.diagnostics');
  const report = vscode.workspace.textDocuments.find(
    (doc) => doc.languageId === 'json' && doc.getText().includes('"authentication"'),
  );
  assert.ok(report, 'Diagnostics opens a JSON document through the actual VS Code API');
  const value = JSON.parse(report.getText());
  assert.equal(value.authentication, 'Not checked. Use Account Status in the official CLI.');
  const fixture = await fs.mkdtemp(path.join(os.tmpdir(), 'context-workbench-host-'));
  try {
    await fs.mkdir(path.join(fixture, 'api'));
    await fs.writeFile(
      path.join(fixture, 'api/main.py'),
      'def queue_task():\n    return "TASK_READY"\n',
    );
    const manifest = path.join(fixture, 'client.json');
    await fs.writeFile(
      manifest,
      JSON.stringify({
        schema_version: 1,
        environment: 'fictional_client',
        workspace: 'demo',
        sources: [{ id: 'api', path: 'api' }],
      }),
    );
    await extension.exports.openProfile(vscode.Uri.file(manifest));
    await vscode.commands.executeCommand('contextEngine.refresh');
    await vscode.commands.executeCommand('contextEngine.clientReadiness');
    const readiness = vscode.workspace.textDocuments.find((doc) =>
      doc.getText().includes('"client_approval"'),
    );
    assert.ok(readiness, 'Readiness opens local diagnostics');
    const readinessValue = JSON.parse(readiness.getText());
    assert.equal(
      readinessValue.checks.review_governance,
      true,
      'Synthetic host has no administrator-installed review policy',
    );
    assert.ok(
      Object.entries(readinessValue.checks)
        .filter(([key]) => key !== 'review_governance')
        .every(([, value]) => value),
    );
    assert.equal(readinessValue.state, 'checks_passed');
    await vscode.commands.executeCommand('contextEngine.benchmark');
    const benchmark = vscode.workspace.textDocuments.find((doc) =>
      doc.getText().includes('"synthetic_benchmark"'),
    );
    assert.ok(benchmark, 'Synthetic benchmark opens results');
    assert.equal(JSON.parse(benchmark.getText()).passed, true);
    await extension.exports.openWiki('all', 'api');
    const wikiDeadline = Date.now() + 5000;
    while (
      !vscode.window.tabGroups.all.some((group) =>
        group.tabs.some((tab) => tab.label === 'Company knowledge wiki'),
      ) &&
      Date.now() < wikiDeadline
    )
      await new Promise((resolve) => setTimeout(resolve, 50));
    assert.ok(
      vscode.window.tabGroups.all.some((group) =>
        group.tabs.some((tab) => tab.label === 'Company knowledge wiki'),
      ),
      'Real human wiki webview opens',
    );
    await vscode.commands.executeCommand('contextEngine.reviewLearning');
    const reviewDeadline = Date.now() + 5000;
    while (
      !vscode.window.tabGroups.all.some((group) =>
        group.tabs.some((tab) => tab.label === 'Context Engine'),
      ) &&
      Date.now() < reviewDeadline
    )
      await new Promise((resolve) => setTimeout(resolve, 50));
    assert.ok(
      vscode.window.tabGroups.all.some((group) =>
        group.tabs.some((tab) => tab.label === 'Context Engine'),
      ),
      'Review learning command opens the native workbench',
    );
    await vscode.commands.executeCommand('contextEngine.profiles');
    const deadline = Date.now() + 5000;
    while (
      !vscode.window.tabGroups.all.some((group) =>
        group.tabs.some((tab) => tab.label === 'Context Engine'),
      ) &&
      Date.now() < deadline
    )
      await new Promise((resolve) => setTimeout(resolve, 50));
    assert.ok(
      vscode.window.tabGroups.all.some((group) =>
        group.tabs.some((tab) => tab.label === 'Context Engine'),
      ),
      'Workbench webview is open',
    );
    // Optional brief hold for visual inspection of the real webview.
    if (process.env.CONTEXT_ENGINE_VISUAL_CHECK === '1')
      await new Promise((resolve) => setTimeout(resolve, 45000));
    console.log(
      'Context Engine VS Code host smoke passed: activation, commands, sidebar, diagnostics, profile import, real indexing, workbench webview.',
    );
  } finally {
    await fs.rm(fixture, { recursive: true, force: true });
  }
}
module.exports = { run };
