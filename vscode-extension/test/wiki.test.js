'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { html } = require('../src/wiki');
test('wiki navigation and diagrams never execute authored markup or load remote content', () => {
  const value = html(
    { cspSource: 'local', asWebviewUri: () => 'local.css' },
    '/extension',
    { Uri: { file: (x) => x } },
    {
      markdown:
        '# Team wiki\n## rule\n<img src="https://evil.test" onerror="evil()">\n[link](https://evil.test)\n## rule',
      diagram: [{ kind: 'module', id: '<script>evil()</script>' }],
    },
  );
  assert.ok(value.includes("default-src 'none'"));
  assert.ok(value.includes('href="#rule-1"'));
  assert.ok(value.includes('href="#rule-2"'));
  assert.ok(!value.includes('<script>'));
  assert.ok(!value.includes('<img'));
  assert.ok(!value.includes('href="https://evil.test"'));
  assert.ok(value.includes('aria-label="Architecture module relationships"'));
});

test('architecture reader renders prose and only host-mapped source links', () => {
  const { render } = require('../media/reader');
  const value = render(
    '# Overview\n\nA **local index** answers requests.\nWrapped prose.\n\n## Follow a request\n1. [Read the handler](source-0)\n2. `validate` checks it.\n\n[unsafe](javascript:evil)\n<img onerror="evil()">\n```js\n<script>evil()</script>\n```',
    { 'source-0': 2 },
  );
  assert.match(value.content, /<strong>local index<\/strong>/);
  assert.match(value.content, /requests\. Wrapped prose\.<\/p>/);
  assert.match(value.content, /<ol><li>/);
  assert.match(value.content, /data-source-index="2"/);
  assert.ok(!value.content.includes('javascript:'));
  assert.ok(!value.content.includes('<img'));
  assert.ok(!value.content.includes('<script>'));
  assert.match(value.nav, /Follow a request/);
});

test('wiki tables render safely and fenced tables remain code', () => {
  const { render } = require('../media/reader');
  const value = render(
    '# Operations\n\n| Symptom | Action |\n| --- | --- |\n| <img src=x> | **Refresh** |\n\n```\n| A | B |\n| --- | --- |\n```',
  );
  assert.match(value.content, /<table><thead>/);
  assert.match(value.content, /<th scope="col">Symptom/);
  assert.match(value.content, /<strong>Refresh<\/strong>/);
  assert.ok(!value.content.includes('<img'));
  assert.equal((value.content.match(/<table>/g) || []).length, 1);
});
