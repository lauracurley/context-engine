'use strict';
const api = acquireVsCodeApi();
let view = 'code',
  capabilities = { sources: [] },
  pending = false,
  dirtyDraft = false;
const labels = {
  practice: 'Practice',
  architecture: 'Architecture',
  convention: 'Convention',
  decision: 'Decision',
  procedure: 'Procedure',
};
const detailLabels = {
  examples: 'Examples',
  alternatives: 'Alternatives',
  tradeoffs: 'Tradeoffs',
  revisit_when: 'Revisit when',
  prerequisites: 'Prerequisites',
  steps: 'Steps',
  diagnostics: 'Diagnostics',
  verification: 'Verification',
  rollback: 'Rollback',
};
const $ = (id) => document.getElementById(id);
const send = (action, data = {}) => {
  if (pending) return;
  setBusy(true);
  api.postMessage({
    action,
    ...data,
    discardDraft: dirtyDraft && !['knowledgeSave', 'knowledgeEvidence'].includes(action),
  });
};
function setBusy(value) {
  pending = value;
  document.body.setAttribute('aria-busy', String(value));
  for (const el of document.querySelectorAll('button')) el.disabled = value;
}
const node = (tag, text, cls) => {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (cls) el.className = cls;
  return el;
};
const button = (label, action, data) => {
  const el = node('button', label);
  el.type = 'button';
  el.onclick = () => send(action, data);
  return el;
};
function field(parent, label, value = '', type = 'input') {
  const wrap = node('label', label),
    input = node(type);
  input.value = value;
  wrap.append(input);
  parent.append(wrap);
  return input;
}
function card(item, index) {
  const el = node('article');
  el.append(
    node('div', item.kind || view, 'tag'),
    node('h3', item.symbol || item.title || item.name || item.id || item.path || 'Evidence'),
  );
  const cite = item.citation || (item.path && item.hash ? item : null);
  if (cite)
    el.append(node('p', `${cite.source} / ${cite.path}:${(cite.lines || []).join('–')}`, 'meta'));
  if (item.applies_to) el.append(node('p', `Applies to: ${item.applies_to.join(', ')}`, 'meta'));
  if (item.classification) el.append(node('p', item.classification, 'warning'));
  if (item.from) el.append(node('p', `${item.from} → ${item.to}`));
  if (item.occurred_at || item.observed_at)
    el.append(node('p', `Recorded: ${item.occurred_at || item.observed_at}`, 'meta'));
  if (item.description || item.summary) el.append(node('p', item.description || item.summary));
  if (item.snippet || item.text) el.append(node('pre', item.snippet || item.text));
  if (item.symbols)
    el.append(node('p', item.symbols.map((s) => `${s.name} : ${s.line}`).join(' · ')));
  const actions = node('div', undefined, 'actions');
  if (cite)
    actions.append(
      button('Preview source', 'preview', { index }),
      button('Open source', 'openSource', { index }),
    );
  const more = node('details'),
    navigation = node('div', undefined, 'actions');
  more.append(node('summary', 'Explore related context'), navigation);
  if (cite)
    navigation.append(
      button('Applicable instructions', 'instructions', { index }),
      button('Definitions in file', 'structure', { index, mode: 'definitions' }),
      button('Dependencies', 'structure', { index, mode: 'dependencies' }),
      button('Graph neighbors', 'graph', { index }),
      button('Impact candidates', 'structure', { index, mode: 'impact' }),
    );
  if (item.expand || item.kind === 'module') actions.append(button('Expand', 'expand', { index }));
  if (item.kind === 'definition' || item.symbol)
    navigation.append(
      button('References', 'structure', { index, mode: 'references' }),
      button('Callers', 'structure', { index, mode: 'callers' }),
    );
  if (item.resolution)
    el.append(node('p', `${item.resolution}: ${item.reason || 'Syntax declaration'}`, 'meta'));
  if (item.owner) el.append(node('p', `Enclosing declaration: ${item.owner}`, 'meta'));
  actions.append(button('Pin to task pack', 'pin', { index }));
  el.append(actions);
  if (navigation.children.length) el.append(more);
  const details = node('details');
  details.append(node('summary', 'Evidence details'), node('pre', JSON.stringify(item, null, 2)));
  el.append(details);
  return el;
}
function renderArchitecture(data) {
  const result = data.result;
  const controls = node('div', undefined, 'architecture-controls');
  const label = node('label', 'Repository');
  const select = node('select');
  select.setAttribute('aria-label', 'Architecture repository');
  for (const source of capabilities.sources) {
    const option = node('option', source.id);
    option.value = source.id;
    select.append(option);
  }
  select.value = result.source || '';
  select.onchange = () => send('architecture', { source: select.value });
  label.append(select);
  controls.append(label);
  $('content').append(controls);
  if (result.state !== 'ready') {
    $('content').append(
      node('h2', 'Architecture is not ready yet'),
      node('p', (result.gaps || []).join(' ')),
      button('Refresh and load architecture', 'refreshCode', {
        returnView: 'architecture',
        source: result.source,
      }),
    );
    return;
  }
  const layout = node('div', undefined, 'architecture-reader');
  const contents = node('nav');
  contents.setAttribute('aria-label', 'Overview contents');
  const article = node('div', undefined, 'architecture-prose');
  const rendered = globalThis.architectureReader.render(result.markdown, result.links);
  // The shared renderer emits only escaped text and fixed, locally generated markup.
  const parser = new DOMParser();
  const insert = (target, markup) => {
    const parsed = parser.parseFromString(markup, 'text/html');
    target.append(...Array.from(parsed.body.childNodes));
  };
  insert(contents, rendered.nav);
  insert(article, rendered.content);
  for (const link of article.querySelectorAll('[data-source-index]'))
    link.onclick = () => send('openSource', { index: Number(link.dataset.sourceIndex) });
  layout.append(contents, article);
  $('content').append(layout);
  const details = node('details');
  details.append(
    node('summary', 'Supporting code structure'),
    node('p', 'Explore extracted modules and relationships to investigate the overview.'),
    button('Explore code structure', 'architectureEvidence'),
  );
  $('content').append(details);
}
function renderProfile(profile, schedule = {}) {
  const form = node('form'),
    grid = node('div', undefined, 'grid');
  form.append(
    node('h2', 'Workspace profile'),
    node(
      'p',
      'Refresh preferences preserve this scope, its knowledge and task packs. Changes to repositories or retrieval configuration create a separate scope after confirmation; the previous scope remains available through Select Manifest.',
    ),
  );
  const environment = field(grid, 'Client / environment', profile.environment),
    workspace = field(grid, 'Workspace', profile.workspace);
  form.append(grid);
  const sources = node('section');
  const sourceInputs = [];
  function add(source = { id: '', type: 'git', path: '' }) {
    const box = node('div', undefined, 'box'),
      row = node('div', undefined, 'grid');
    const id = field(row, 'Source ID', source.id),
      type = field(row, 'Type', '', 'select');
    for (const t of ['git', 'files', 'markdown', 'remote-git']) {
      const option = node('option', t);
      type.append(option);
    }
    type.value = source.type || 'git';
    const location = field(row, 'Local path / remote URL', source.path || source.url || ''),
      ref = field(row, 'Remote ref (e.g. refs/heads/main)', source.ref || '');
    box.append(row);
    const remove = node('button', 'Remove source');
    remove.type = 'button';
    const entry = { base: source, id, type, location, ref, removed: false };
    sourceInputs.push(entry);
    remove.onclick = () => {
      entry.removed = true;
      box.remove();
    };
    box.append(remove);
    sources.append(box);
  }
  for (const source of profile.sources) add(source);
  form.append(sources);
  const addButton = node('button', 'Add source');
  addButton.type = 'button';
  addButton.onclick = () => add();
  form.append(addButton);
  const exclude = field(
    form,
    'Excluded path patterns (one per line)',
    (profile.exclude || []).join('\n'),
    'textarea',
  );
  const scheduling = node('div', undefined, 'grid');
  const interval = field(
      scheduling,
      'Periodic code refresh interval (seconds)',
      schedule.interval || profile.crawler?.interval || 300,
    ),
    historyInterval = field(
      scheduling,
      'History refresh interval (seconds)',
      schedule.history_interval || profile.crawler?.history_interval || 21600,
    ),
    months = field(
      scheduling,
      'History window (months)',
      schedule.history_months || profile.crawler?.history_months || 6,
    );
  form.append(
    scheduling,
    node(
      'p',
      'These intervals control periodic refresh. The generated workspace watch task separately checks saved code every two seconds.',
      'meta',
    ),
  );
  historyInterval.parentElement.hidden = months.parentElement.hidden =
    capabilities.history === false;
  const gateway = field(
    form,
    'Company history adapter: absolute executable, then one argument per line (no credentials)',
    (profile.history?.gateway_command || []).join('\n'),
    'textarea',
  );
  gateway.parentElement.hidden = capabilities.history === false;
  const submit = node('button', 'Save profile');
  submit.type = 'submit';
  form.append(submit);
  form.onsubmit = (event) => {
    event.preventDefault();
    const value = {
      ...profile,
      environment: environment.value,
      workspace: workspace.value,
      sources: sourceInputs
        .filter((s) => !s.removed)
        .map((s) => {
          const source = { ...s.base, id: s.id.value, type: s.type.value };
          delete source.path;
          delete source.url;
          delete source.ref;
          if (s.type.value === 'remote-git')
            Object.assign(source, { url: s.location.value, ref: s.ref.value });
          else source.path = s.location.value;
          return source;
        }),
      exclude: exclude.value.split('\n').filter(Boolean),
      crawler: {
        ...profile.crawler,
        interval: Number(interval.value),
        history_interval: Number(historyInterval.value),
        history_months: Number(months.value),
      },
      history: { ...profile.history },
    };
    if (gateway.value.trim())
      value.history.gateway_command = gateway.value.split('\n').filter(Boolean);
    else delete value.history.gateway_command;
    send('saveProfile', { value });
  };
  $('content').append(form);
}
function renderPacks(data) {
  $('content').append(button('New task pack', 'newPack'));
  for (const pack of data.packs || []) {
    const el = node('article');
    el.append(
      node('h3', pack.task),
      node('p', `${pack.items.length} items · ${pack.updated_at}`, 'meta'),
      button('Open pack', 'selectPack', { id: pack.id }),
    );
    $('content').append(el);
  }
  if (!data.pack) return;
  const pack = data.pack;
  $('content').append(node('h2', `Active pack: ${pack.task}`));
  const actions = node('div', undefined, 'actions');
  for (const [label, action] of [
    ['Rename task', 'renamePack'],
    ['Check freshness', 'validatePack'],
    ['Refresh pinned evidence', 'refreshPack'],
    ['Preview handoff', 'exportPack'],
    ['Prepare IDE handoff', 'handoff'],
  ])
    actions.append(button(label, action));
  $('content').append(
    actions,
    node(
      'p',
      `${data.budget.used_bytes} / ${data.budget.limit} bytes · ${data.budget.value.omitted_items} omitted from handoff. This is not a model-token count.`,
      'meta',
    ),
    button('Change budget', 'packBudget'),
  );
  for (const entry of pack.items) {
    const el = node('article');
    el.append(
      node(
        'h3',
        entry.item.path || entry.item.name || entry.item.title || entry.item.id || entry.kind,
      ),
      node('p', entry.kind),
      button('Remove', 'removePin', { id: entry.id }),
    );
    $('content').append(el);
  }
}
function repositorySelect(parent, label, selected = '', all = false) {
  const select = field(parent, label, '', 'select');
  if (all) {
    const option = node('option', 'All repositories');
    option.value = '';
    select.append(option);
  }
  for (const source of capabilities.sources) {
    const option = node('option', source.id);
    option.value = source.id;
    select.append(option);
  }
  if (selected || all) select.value = selected;
  return select;
}
function details(parent, title, value) {
  const el = node('details');
  el.append(node('summary', title), node('pre', JSON.stringify(value, null, 2)));
  parent.append(el);
}
function renderReviewLearning(data) {
  const content = $('content');
  content.append(
    node('h2', 'Learn from GitHub reviews'),
    node(
      'p',
      'Gather PR discussions and commits through your company’s connected MCP gateway. Review the evidence, distill useful practices, then approve selected guidelines in Team knowledge.',
    ),
  );
  const actions = node('div', undefined, 'actions');
  actions.append(
    button('Prepare gateway prompt', 'reviewPrepare'),
    button('Open collected evidence', 'reviewBrowse'),
    button('Review proposed guidelines', 'knowledge'),
  );
  content.append(actions);
  content.append(
    node('h3', 'Three layers, one review trail'),
    node(
      'p',
      'Evidence preserves what was said and changed. The dossier gives you the detailed context. Guidelines keep the concise practice and exceptions for agents, with the longer rationale available to people. Nothing is approved automatically.',
    ),
  );
  const request = data.reviewRequest;
  if (request) {
    const card = node('article');
    card.append(
      node('h3', 'Ready for your connected agent'),
      node(
        'p',
        `${request.repository} · ${request.since.slice(0, 10)} to ${request.until.slice(0, 10)}`,
      ),
      node(
        'p',
        'Copy the prompt into your approved agent. It must use your existing gateway and stop if access is unavailable. We do not ask for a GitHub token or send the prompt for you.',
      ),
      button('Copy collection and distillation prompt', 'reviewCopyPrompt'),
      button('Import gateway result file', 'reviewImport'),
    );
    const detail = node('details');
    detail.append(node('summary', 'Inspect the agent request'));
    const text = node('pre', request.prompt);
    detail.append(text);
    card.append(detail);
    content.append(card);
  }
  const page = data.reviewPage;
  if (!page) {
    content.append(
      node(
        'p',
        'No dossier open. After your agent gathers evidence, open the collected results here. Proposed guidelines appear separately in Team knowledge.',
      ),
    );
    return;
  }
  content.append(
    node('h3', `Review dossier · ${page.repository}`),
    node(
      'p',
      `${page.total_events} observations · ${page.complete ? 'Gateway reports collection complete' : 'Partial collection — inspect the gaps'}`,
    ),
    node('p', page.freshness),
  );
  for (const gap of page.gaps) content.append(node('p', gap, 'warning'));
  const labels = {
    pr: 'Pull request',
    review: 'Submitted review',
    review_comment: 'Line review comment',
    issue_comment: 'PR discussion',
    commit: 'Commit',
    commit_comment: 'Commit discussion',
  };
  for (const event of page.items) {
    const card = node('article');
    card.append(
      node(
        'h3',
        `${labels[event.kind] || 'Observation'}${event.pull ? ' · PR ' + event.pull : ''}`,
      ),
      node(
        'p',
        `${event.author || 'Author unavailable'} · ${event.updated.slice(0, 10)}${event.path ? ' · ' + event.path : ''}`,
      ),
    );
    const body = node('pre', event.body || 'No text supplied.');
    card.append(body);
    if (event.url) card.append(node('p', 'Source: ' + event.url));
    if (event.commit) card.append(node('p', 'Commit: ' + event.commit));
    content.append(card);
  }
  const pages = node('div', undefined, 'actions');
  pages.append(button('First evidence page', 'reviewFirst'));
  if (page.next_offset !== null) pages.append(button('More evidence', 'reviewNext'));
  content.append(
    pages,
    node(
      'p',
      'Evidence may contain incorrect suggestions or conflicting views. Ask your agent to explain counterexamples and scope before proposing a guideline.',
    ),
  );
}

function renderHealth(data) {
  const status = data.health,
    host = data.hostHealth || {},
    content = $('content');
  content.append(
    node('h2', 'Workspace health'),
    node(
      'p',
      'This check reads the selected local repositories. It does not verify an agent account or a live MCP connection.',
    ),
  );
  const grid = node('div', undefined, 'grid');
  for (const [label, value] of [
    ['Index', `${status.state} · ${status.drift_files} changed files`],
    ['Backend release', status.runtime?.loaded?.release || 'Not reported by this backend'],
    ['Backend build', status.runtime?.loaded?.build_id || 'Not reported'],
    ['Index writer build', status.runtime?.index_writer?.build_id || 'Not recorded'],
    ['Backend compatibility', status.runtime?.state || 'Unknown; update the backend to check'],
    [
      'Backend recovery',
      status.runtime?.recovery ||
        'Stop older writers before upgrading; refresh and verify each connection afterward.',
    ],
    ['Code refresh', host.watcher || 'Not observed in this window'],
    ['Semantic retrieval', status.semantic?.state || 'Not configured'],
    [
      'Agent connection',
      host.ide || 'Start an agent in the generated Context Engine folder; verify MCP tools there',
    ],
  ]) {
    const box = node('article');
    box.append(node('h3', label), node('p', value));
    grid.append(box);
  }
  content.append(grid);
  const actions = node('div', undefined, 'actions');
  actions.append(
    button('Check again', 'health'),
    button('Refresh code', 'refreshCode', { returnView: 'health' }),
    button('Start code refresh', 'startWatcher'),
    button('Open Codex IDE workspace', 'openIde'),
  );
  if (host.canStop) actions.append(button('Stop code refresh', 'stopWatcher'));
  content.append(actions, node('h3', 'Indexed repositories'));
  for (const [id, source] of Object.entries(status.coverage || {})) {
    const el = node('article');
    el.append(
      node('h3', id),
      node('p', source.root, 'meta'),
      node('p', `${source.files} supported files · ${source.excluded} excluded`),
    );
    for (const error of source.errors || []) el.append(node('p', String(error), 'warning'));
    content.append(el);
  }
  content.append(
    node(
      'p',
      'Health, source paths, knowledge and diagnostics stay in client-controlled storage. No vendor telemetry is sent.',
      'meta',
    ),
  );
  details(content, 'Local diagnostic details', status);
}
function renderBrief(data) {
  const content = $('content'),
    form = node('form'),
    grid = node('div', undefined, 'grid');
  content.append(
    node('h2', 'Change context'),
    node(
      'p',
      'Collect current changed code, applicable reviewed guidance, related structure and possible tests before a coding or review task.',
    ),
  );
  const source = repositorySelect(grid, 'Git repository', data.briefSource),
    base = field(grid, 'Compare tracked files against', data.briefBase || 'HEAD');
  base.required = true;
  base.maxLength = 120;
  const submit = node('button', 'Prepare context');
  submit.type = 'submit';
  form.append(grid, submit);
  form.onsubmit = (event) => {
    event.preventDefault();
    send('prepareBrief', { source: source.value, base: base.value });
  };
  content.append(form);
  const brief = data.changeBrief;
  if (!brief) return;
  content.append(node('p', brief.coverage || (brief.gaps || []).join('; '), 'warning'));
  content.append(
    node(
      'p',
      `${brief.state} · ${brief.items.length} evidence items · ${brief.omitted_changed_paths || 0} changed paths omitted · ${brief.upstream_omissions || 0} upstream omissions · ${brief.budget.omitted_items} items outside byte budget`,
      'meta',
    ),
  );
  for (const gap of brief.gaps || []) content.append(node('p', gap, 'warning'));
  if (brief.state !== 'ready')
    content.append(button('Refresh code', 'refreshCode', { returnView: 'brief' }));
  else if (!brief.items.length)
    content.append(
      node(
        'p',
        'No current evidence for this comparison. Check the base and coverage limits above.',
      ),
    );
  else content.append(button('Add change context to task pack', 'pinBrief'));
  for (const item of brief.items) {
    const el = node('article');
    el.append(
      node('div', item.category.replaceAll('_', ' '), 'tag'),
      node('h3', item.title || item.path || item.name || item.id || 'Related evidence'),
      node('p', item.reason),
    );
    if (item.statement) el.append(node('p', item.statement));
    if (item.exceptions?.length)
      el.append(node('h3', 'Exceptions'), node('p', item.exceptions.join(' · ')));
    for (const [key, values] of Object.entries(item.details || {})) {
      el.append(node('h3', detailLabels[key] || key));
      const list = node('ol');
      for (const value of values)
        list.append(
          node('li', key === 'diagnostics' ? `If ${value.if}, then ${value.then}` : value),
        );
      el.append(list);
    }
    if (item.text) el.append(node('pre', item.text));
    if (item.source)
      el.append(
        node(
          'p',
          `${item.source} / ${item.path || item.prefix || '(repository)'} ${(item.lines || []).join('–')}`,
          'meta',
        ),
      );
    details(el, 'Citations and evidence details', item);
    content.append(el);
  }
}
function renderHandoff(data) {
  const content = $('content');
  content.append(
    node('h2', 'Ready for your approved IDE agent'),
    node(
      'p',
      'Open the generated workspace, start a conversation in its Context Engine folder, and paste this prompt. The agent reads the pack locally through your existing client-approved tool access.',
    ),
    node('pre', data.handoff.prompt),
  );
  const actions = node('div', undefined, 'actions');
  actions.append(
    button('Copy prompt', 'copyHandoff'),
    button('Open local pack', 'openHandoff'),
    button('Open Codex IDE workspace', 'openIde'),
    button('Back to task packs', 'packs'),
  );
  content.append(
    actions,
    node(
      'p',
      'Copying checks evidence freshness again. Your agent manages authentication and any model requests. Context Engine does not submit this prompt.',
      'meta',
    ),
  );
}
function supportingFiles(parent, row, index, draft = false) {
  parent.append(node('h3', 'Supporting evidence'));
  for (const [citation, cite] of (row.citations || []).entries())
    parent.append(
      button(`${cite.source} / ${cite.path}`, 'knowledgeEvidence', { index, citation, draft }),
    );
}
function renderKnowledge(data) {
  const content = $('content');
  content.append(
    node('h2', 'Team knowledge'),
    node(
      'p',
      'Reviewed practices, architecture, conventions, decisions and procedures. Proposals stay out of agent guidance until you approve them; changed evidence requires re-review.',
    ),
  );
  if (data.knowledgeNew) {
    const form = node('form'),
      grid = node('div', undefined, 'grid'),
      kind = field(grid, 'Knowledge type', '', 'select');
    for (const [value, label] of Object.entries(labels)) {
      const option = node('option', label);
      option.value = value;
      kind.append(option);
    }
    kind.value = data.fileKind || 'practice';
    const source = repositorySelect(grid, 'Repository', data.fileSource),
      query = field(grid, 'Supporting file name or fragment', data.fileQuery || '');
    const submit = node('button', 'Find supporting files');
    submit.type = 'submit';
    form.append(grid, submit);
    form.onsubmit = (event) => {
      event.preventDefault();
      send('knowledgeFindFiles', { kind: kind.value, source: source.value, query: query.value });
    };
    content.append(form, button('Back to knowledge', 'knowledge'));
    for (const [index, file] of (data.knowledgeFiles || []).entries()) {
      const el = node('article');
      el.append(
        node('h3', file.path),
        button('Use this evidence', 'knowledgeChooseFile', { index }),
      );
      content.append(el);
    }
    return;
  }
  if (data.knowledgeDraft) {
    const draft = data.knowledgeDraft,
      form = node('form');
    form.append(node('h3', `${labels[draft.kind]} proposal · ${draft.source}`));
    const title = field(form, 'Title', draft.title),
      statement = field(form, 'Guidance', draft.statement, 'textarea'),
      rationale = field(form, 'Why this applies', draft.rationale, 'textarea');
    title.required = statement.required = rationale.required = true;
    title.maxLength = 150;
    statement.maxLength = 1200;
    rationale.maxLength = 6000;
    const prefix = field(form, 'Applies under path (blank means entire repository)', draft.prefix),
      languages = field(
        form,
        'Languages (one per line; blank means all)',
        (draft.languages || []).join('\n'),
        'textarea',
      ),
      tasks = field(
        form,
        'Tasks (one per line; blank means all)',
        (draft.tasks || []).join('\n'),
        'textarea',
      ),
      exceptions = field(
        form,
        'Exceptions (one per line)',
        (draft.exceptions || []).join('\n'),
        'textarea',
      );
    const detailInputs = {};
    for (const [key, values] of Object.entries(draft.details || {})) {
      if (key === 'diagnostics') continue;
      detailInputs[key] = field(
        form,
        (detailLabels[key] || key) + ' (one per line, up to 12)',
        values.join('\n'),
        'textarea',
      );
      detailInputs[key].required = key !== 'revisit_when' && draft.kind !== 'convention';
    }
    const diagnosticRows = [];
    if (draft.kind === 'procedure') {
      form.append(node('h3', 'Diagnostic branches'));
      const branches = node('div');
      form.append(branches);
      function addBranch(value = {}) {
        if (diagnosticRows.length >= 12) return;
        const row = node('div', undefined, 'grid'),
          condition = field(row, 'If observed', value.if || ''),
          action = field(row, 'Then do', value.then || '');
        condition.maxLength = action.maxLength = 500;
        branches.append(row);
        diagnosticRows.push({ condition, action });
      }
      for (const value of draft.details.diagnostics?.length ? draft.details.diagnostics : [{}])
        addBranch(value);
      const add = node('button', 'Add diagnostic branch');
      add.type = 'button';
      add.onclick = () => addBranch();
      form.append(add);
    }
    supportingFiles(form, draft, undefined, true);
    const submit = node('button', 'Save proposal for review');
    submit.type = 'submit';
    form.append(submit, button('Cancel editing', 'knowledge'));
    const lines = (value) =>
      value
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean);
    form.onsubmit = (event) => {
      event.preventDefault();
      const structured = Object.fromEntries(
        Object.entries(detailInputs)
          .map(([key, input]) => [key, lines(input.value)])
          .filter(([, values]) => values.length),
      );
      if (draft.kind === 'procedure')
        structured.diagnostics = diagnosticRows
          .map(({ condition, action }) => ({
            if: condition.value.trim(),
            then: action.value.trim(),
          }))
          .filter((row) => row.if || row.then);
      send('knowledgeSave', {
        value: {
          title: title.value.trim(),
          statement: statement.value.trim(),
          rationale: rationale.value.trim(),
          prefix: prefix.value.trim(),
          languages: lines(languages.value),
          tasks: lines(tasks.value),
          exceptions: lines(exceptions.value),
          details: structured,
        },
      });
    };
    form.oninput = () => {
      if (!dirtyDraft) api.postMessage({ action: 'draftDirty' });
      dirtyDraft = true;
    };
    content.append(form);
    return;
  }
  const catalog = data.knowledge;
  if (!catalog) return;
  const form = node('form'),
    grid = node('div', undefined, 'grid');
  const source = repositorySelect(grid, 'Repository', data.knowledgeFilter?.source, true),
    query = field(grid, 'Filter title or guidance', data.knowledgeFilter?.query || '');
  const submit = node('button', 'Filter knowledge');
  submit.type = 'submit';
  form.append(grid, submit);
  form.onsubmit = (event) => {
    event.preventDefault();
    send('knowledgeFilter', { source: source.value, query: query.value, offset: 0 });
  };
  content.append(
    form,
    button('New knowledge proposal', 'knowledgeNew'),
    node('p', `${catalog.total} active revisions · code ${catalog.state}`, 'meta'),
  );
  if (!catalog.records.length)
    content.append(
      node(
        'p',
        'No approved or proposed knowledge matches. Create a proposal grounded in a current indexed file.',
      ),
    );
  for (const [index, record] of catalog.records.entries()) {
    const el = node('article');
    el.append(
      node('div', `${labels[record.kind]} · ${record.status} · revision ${record.revision}`, 'tag'),
      node('h3', record.title),
      node('p', record.statement),
      node('p', record.availability, record.fresh ? 'meta' : 'warning'),
      node(
        'p',
        `Scope: ${record.source}/${record.prefix || '(repository)'} · languages: ${(record.languages || []).join(', ') || 'all'} · tasks: ${(record.tasks || []).join(', ') || 'all'}`,
        'meta',
      ),
      node('h3', 'Rationale'),
      node('p', record.rationale),
    );
    if (record.exceptions?.length)
      el.append(node('h3', 'Exceptions'), node('p', record.exceptions.join(' · ')));
    for (const [key, values] of Object.entries(record.details || {})) {
      el.append(node('h3', detailLabels[key] || key));
      const list = node('ol');
      for (const value of values)
        list.append(
          node('li', key === 'diagnostics' ? `If ${value.if}, then ${value.then}` : value),
        );
      el.append(list);
    }
    supportingFiles(el, record, index);
    const actions = node('div', undefined, 'actions');
    if (!record.fresh && record.revision !== record.expected_revision)
      el.append(
        node('p', 'A newer proposal exists; use its latest revision for re-review.', 'warning'),
      );
    else if (!record.fresh)
      actions.append(button('Prepare re-review draft', 'knowledgeRefreshDraft', { index }));
    else actions.append(button('Edit replacement proposal', 'knowledgeEdit', { index }));
    if (record.status === 'proposed') {
      if (record.fresh && catalog.state === 'ready')
        actions.append(
          button('Approve proposal', 'knowledgeDecide', { index, decision: 'approve' }),
        );
      actions.append(button('Reject proposal', 'knowledgeDecide', { index, decision: 'reject' }));
    } else
      actions.append(button('Retire guidance', 'knowledgeDecide', { index, decision: 'retire' }));
    actions.append(button('Revision history', 'knowledgeHistory', { index }));
    el.append(actions);
    content.append(el);
  }
  if (catalog.offset > 0)
    content.append(
      button('Previous page', 'knowledgeFilter', {
        ...data.knowledgeFilter,
        offset: Math.max(0, catalog.offset - 100),
      }),
    );
  if (catalog.next_offset !== null)
    content.append(
      button('Next page', 'knowledgeFilter', {
        ...data.knowledgeFilter,
        offset: catalog.next_offset,
      }),
    );
}
for (const btn of document.querySelectorAll('nav button'))
  btn.onclick = () => send(btn.dataset.action);
$('back').onclick = () => send('back');
$('search').onsubmit = (event) => {
  event.preventDefault();
  send('search', {
    view,
    query: $('query').value,
    mode: $('mode').value,
    source: $('source').value,
    glob: $('glob').value,
    kind: $('kind').value,
  });
};
window.addEventListener('message', (event) => {
  const data = event.data;
  if (!data || typeof data.scope !== 'string' || (!data.type && !data.view)) return;
  if (data.type === 'idle') {
    setBusy(false);
    return;
  }
  if (data.type === 'busy') {
    setBusy(true);
    $('status').textContent = data.message;
    return;
  }
  if (data.type === 'error' || data.type === 'notice') {
    $('status').textContent = data.message;
    return;
  }
  $('scope').textContent = data.scope || 'No profile selected';
  if (data.capabilities) capabilities = data.capabilities;
  if (data.view) view = data.view;
  for (const btn of document.querySelectorAll('nav button')) {
    btn.setAttribute('aria-pressed', String(btn.dataset.action === view));
    btn.hidden = btn.dataset.action === 'history' && capabilities.history === false;
  }
  const previousSource = $('source').value;
  $('source').replaceChildren();
  for (const source of [{ id: '' }, ...capabilities.sources]) {
    const option = node('option', source.id || 'All repositories');
    option.value = source.id;
    $('source').append(option);
  }
  $('source').value = previousSource;
  for (const option of $('mode').options)
    option.hidden = ['semantic', 'hybrid'].includes(option.value) && !capabilities.semantic;
  if (['semantic', 'hybrid'].includes($('mode').value) && !capabilities.semantic)
    $('mode').value = 'auto';
  if (data.search) {
    $('query').value = data.search.query;
    $('mode').value = data.search.mode || 'auto';
    $('source').value = data.search.source || '';
    $('glob').value = data.search.glob || '';
  }
  dirtyDraft = false;
  $('content').replaceChildren();
  $('search').hidden = !['code', 'history'].includes(view);
  $('back').hidden = !data.canGoBack || !['code', 'architecture', 'history'].includes(view);
  $('history-filter').hidden = view !== 'history';
  $('mode-filter').hidden = $('path-filter').hidden = view === 'history';
  $('status').textContent = [
    data.result?.state,
    data.result?.ordering,
    data.result?.content_mode,
    ...(data.result?.gaps || []),
    data.result?.budget
      ? `${data.result.budget.used_bytes ?? data.result.budget.used ?? '?'} / ${data.result.budget.limit} bytes · ${data.result.budget.omitted_items || 0} omitted`
      : '',
    data.message,
  ]
    .filter(Boolean)
    .join(' · ');
  if (data.profile) renderProfile(data.profile, data.schedule);
  else if (view === 'architecture' && data.result?.reader) renderArchitecture(data);
  else if (view === 'packs') renderPacks(data);
  else if (view === 'reviewLearning') renderReviewLearning(data);
  else if (view === 'knowledge') renderKnowledge(data);
  else if (view === 'health') renderHealth(data);
  else if (view === 'brief') renderBrief(data);
  else if (view === 'handoff') renderHandoff(data);
  else {
    if (['stale', 'unindexed', 'degraded'].includes(data.result?.state))
      $('content').append(button('Refresh code and retry search', 'refreshCode'));
    for (const [index, item] of (data.result?.items || data.result?.evidence || []).entries())
      $('content').append(card(item, index));
    if (!data.result?.items?.length && !data.result?.evidence?.length)
      $('content').append(
        node(
          'p',
          view === 'code'
            ? 'Search this workspace by task, identifier or file name. Use Search options to narrow the repository or path.'
            : 'No evidence displayed. Check workspace health and the selected scope.',
        ),
      );
  }
  setBusy(pending);
});
send('ready');
