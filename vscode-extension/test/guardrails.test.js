'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { ESLint } = require('eslint');

test('lint rejects shell interpolation, dynamic evaluation, and unsafe evidence rendering', async () => {
  const eslint = new ESLint();
  for (const source of [
    'const options = { shell: true }; void options;',
    'eval("untrusted");',
    'document.body.innerHTML = location.hash;',
    'document.body.insertAdjacentHTML("beforeend", location.hash);',
  ]) {
    const [result] = await eslint.lintText(source, { filePath: 'media/guardrail-probe.js' });
    assert.ok(result.errorCount > 0, source);
    assert.ok(
      result.messages.some((message) =>
        ['no-restricted-syntax', 'no-eval'].includes(message.ruleId),
      ),
      source,
    );
  }
  const [safe] = await eslint.lintText('document.body.textContent = location.hash;', {
    filePath: 'media/guardrail-probe.js',
  });
  assert.equal(safe.errorCount, 0);
});
