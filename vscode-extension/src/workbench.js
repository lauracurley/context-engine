'use strict';
const { randomBytes } = require('node:crypto');
const path = require('node:path');
const escape = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );
function html(webview, root, vscode) {
  const nonce = randomBytes(18).toString('base64');
  const uri = (file) => webview.asWebviewUri(vscode.Uri.file(path.join(root, 'media', file)));
  return `<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource}; script-src 'nonce-${nonce}';"><link rel="stylesheet" href="${escape(uri('workbench.css'))}"></head><body>
  <a class="skip-link" href="#content">Skip to results</a><header><span class="eyebrow">CONTEXT ENGINE</span><h1>Context workbench</h1><p id="scope">Select a workspace profile to begin.</p></header>
  <nav aria-label="Views"><button data-action="code">Code</button><button data-action="architecture">Architecture</button><button data-action="knowledge">Team knowledge</button><button data-action="reviewLearning">Review learning</button><button data-action="brief">Change context</button><button data-action="packs">Task packs</button><button data-action="history">History</button><button data-action="health">Health</button><button data-action="profile">Profile</button></nav>
  <button id="back" type="button" hidden>Back to evidence</button>
  <form id="search"><label for="query">Find context</label><div class="searchbar"><input id="query" maxlength="4000" placeholder="Ask in English or enter an identifier"><button type="submit">Search</button></div><details><summary>Search options</summary><div class="filters"><label id="mode-filter">Mode<select id="mode"><option value="auto">Automatic</option><option value="lexical">Keywords</option><option value="semantic">Semantic</option><option value="hybrid">Hybrid</option><option value="literal">Exact text</option><option value="regex">Regular expression</option><option value="symbols">Symbols</option><option value="files">Files</option></select></label><label>Repository<select id="source"></select></label><label id="path-filter">Path pattern<input id="glob" placeholder="e.g. **/*.py"></label><label id="history-filter">History kind<select id="kind"><option>all</option><option>pr</option><option>commit</option><option>holder</option></select></label></div></details></form>
  <div id="status" role="status" aria-live="polite"></div><section id="content" tabindex="-1" aria-label="Context results"></section>
  <script nonce="${nonce}" src="${escape(uri('reader.js'))}"></script>
  <script nonce="${nonce}" src="${escape(uri('workbench.js'))}"></script></body></html>`;
}
module.exports = { html, escape };
