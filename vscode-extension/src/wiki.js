'use strict';
const { escape } = require('./workbench');
const path = require('node:path');
function diagram(items = []) {
  const nodes = items.filter((item) => item.kind === 'module').slice(0, 16);
  const positions = new Map(
    nodes.map((node, i) => [node.id, { x: 20 + (i % 3) * 250, y: 35 + Math.floor(i / 3) * 100 }]),
  );
  const edges = items
    .filter((item) => positions.has(item.from) && positions.has(item.to))
    .slice(0, 20);
  const lines = edges.map((edge) => {
    const a = positions.get(edge.from),
      b = positions.get(edge.to);
    return `<path d="M${a.x + 100},${a.y + 25} L${b.x + 100},${b.y + 25}" stroke="currentColor" fill="none" marker-end="url(#arrow)"><title>${escape(edge.relation)} (${escape(edge.classification || 'inferred')})</title></path>`;
  });
  const cards = nodes.map((node) => {
    const p = positions.get(node.id);
    return `<g><rect x="${p.x}" y="${p.y}" width="210" height="50" rx="6"/><text x="${p.x + 8}" y="${p.y + 30}">${escape(node.id.slice(-27))}</text><title>${escape(node.id)}</title></g>`;
  });
  return `<figure><figcaption>Static architecture map — arrows show extracted/inferred relationships, not runtime proof. ${nodes.length} modules / ${edges.length} relationships shown; use the overview for full detail.</figcaption><svg role="img" aria-label="Architecture module relationships" viewBox="0 0 770 ${Math.max(100, Math.ceil(nodes.length / 3) * 100)}"><defs><marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor"/></marker></defs>${lines.join('')}${cards.join('')}</svg></figure>`;
}
function html(webview, root, vscode, value) {
  const rendered = require('../media/reader').render(value.markdown);
  const css = webview.asWebviewUri(vscode.Uri.file(path.join(root, 'media/wiki.css')));
  return `<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource};"><link rel="stylesheet" href="${escape(css)}"></head><body><nav aria-label="Wiki contents">${rendered.nav}</nav><main>${rendered.content}${value.diagram?.length ? '<details><summary>Supporting code structure</summary>' + diagram(value.diagram) + '</details>' : ''}</main></body></html>`;
}
module.exports = { html, diagram };
