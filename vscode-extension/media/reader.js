/* A deliberately small text-only Markdown renderer, shared by both reading views. */
/* global module */
'use strict';
(function (root) {
  const escape = (value) =>
    String(value).replace(
      /[&<>"']/g,
      (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
    );
  function inline(text, links = {}) {
    const pattern = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))/g;
    let output = '',
      last = 0;
    for (const match of text.matchAll(pattern)) {
      output += escape(text.slice(last, match.index));
      const token = match[0];
      if (token.startsWith('`')) output += `<code>${escape(token.slice(1, -1))}</code>`;
      else if (token.startsWith('**')) output += `<strong>${escape(token.slice(2, -2))}</strong>`;
      else {
        const [, label, key] = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
        const index = Object.hasOwn(links, key) ? links[key] : undefined;
        output +=
          Number.isInteger(index) && index >= 0
            ? `<button type="button" class="source-link" data-source-index="${index}">${escape(label)}</button>`
            : escape(label);
      }
      last = match.index + token.length;
    }
    return output + escape(text.slice(last));
  }
  function render(markdown, links = {}) {
    const nav = [],
      body = [],
      used = new Map();
    let paragraph = [],
      list = null,
      fence = null,
      code = [];
    const flush = () => {
      if (paragraph.length) body.push(`<p>${inline(paragraph.join(' '), links)}</p>`);
      paragraph = [];
      if (list) body.push(`</${list}>`);
      list = null;
    };
    const lines = markdown.split('\n');
    const cells = (line) =>
      line
        .trim()
        .replace(/^\|/, '')
        .replace(/\|$/, '')
        .split('|')
        .map((cell) => cell.trim());
    for (let lineIndex = 0; lineIndex < lines.length; lineIndex++) {
      const line = lines[lineIndex];
      if (/^\s*```/.test(line)) {
        flush();
        if (fence !== null) {
          body.push(`<pre><code>${escape(code.join('\n'))}</code></pre>`);
          fence = null;
          code = [];
        } else fence = line;
        continue;
      }
      if (fence !== null) {
        code.push(line);
        continue;
      }
      if (
        line.includes('|') &&
        lineIndex + 1 < lines.length &&
        cells(lines[lineIndex + 1]).length > 1 &&
        cells(lines[lineIndex + 1]).every((cell) => /^:?-{3,}:?$/.test(cell))
      ) {
        flush();
        const headers = cells(line);
        body.push(
          '<div class="table-scroll"><table><thead><tr>' +
            headers.map((cell) => `<th scope="col">${inline(cell, links)}</th>`).join('') +
            '</tr></thead><tbody>',
        );
        lineIndex += 1;
        while (
          lineIndex + 1 < lines.length &&
          lines[lineIndex + 1].includes('|') &&
          lines[lineIndex + 1].trim()
        ) {
          const row = cells(lines[++lineIndex]);
          body.push(
            '<tr>' +
              headers.map((_, index) => `<td>${inline(row[index] || '', links)}</td>`).join('') +
              '</tr>',
          );
        }
        body.push('</tbody></table></div>');
        continue;
      }
      const heading = /^(#{1,6})\s+(.+)$/.exec(line);
      const bullet = /^\s*(?:([-*])|\d+\.)\s+(.+)$/.exec(line);
      if (heading) {
        flush();
        const level = heading[1].length,
          title = heading[2];
        const base = title.toLowerCase().replace(/[^a-z0-9_-]+/g, '-');
        const count = (used.get(base) || 0) + 1;
        used.set(base, count);
        const id = `${base}-${count}`;
        if (level <= 2) nav.push(`<a href="#${id}">${escape(title)}</a>`);
        body.push(`<h${level} id="${id}">${inline(title, links)}</h${level}>`);
      } else if (bullet) {
        const tag = bullet[1] ? 'ul' : 'ol';
        if (list !== tag) {
          flush();
          body.push(`<${tag}>`);
          list = tag;
        }
        body.push(`<li>${inline(bullet[2], links)}</li>`);
      } else if (!line.trim()) flush();
      else {
        if (list) flush();
        paragraph.push(line.trim());
      }
    }
    flush();
    if (fence !== null) body.push(`<pre><code>${escape(code.join('\n'))}</code></pre>`);
    return { content: body.join(''), nav: nav.join('') };
  }
  if (typeof module !== 'undefined') module.exports = { render };
  else root.architectureReader = { render };
})(globalThis);
