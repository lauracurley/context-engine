'use strict';
const path = require('node:path');
const NAME = /^[a-zA-Z0-9_-]{1,80}$/;
const named = (value) => typeof value === 'string' && NAME.test(value);
function validateProfile(value, base) {
  const profile = structuredClone(value);
  if (profile.schema_version !== 1 || !named(profile.environment) || !named(profile.workspace))
    throw new Error(
      'Client and workspace names must use 1–80 letters, digits, underscores or hyphens',
    );
  if (!Array.isArray(profile.sources) || !profile.sources.length || profile.sources.length > 100)
    throw new Error('Select 1–100 sources');
  const ids = new Set();
  for (const source of profile.sources) {
    if (!named(source.id) || ids.has(source.id))
      throw new Error('Source IDs must be unique simple names');
    ids.add(source.id);
    if (source.type === 'remote-git') {
      if (typeof source.url !== 'string' || typeof source.ref !== 'string')
        throw new Error('Remote sources require URL and full ref');
      delete source.path;
    } else {
      if (
        !['git', 'files', 'markdown'].includes(source.type || 'git') ||
        typeof source.path !== 'string' ||
        !source.path.trim()
      )
        throw new Error('Each local source needs a path and supported type');
      source.path = path.resolve(base, source.path);
    }
  }
  if (
    !Array.isArray(profile.exclude || []) ||
    (profile.exclude || []).some((x) => typeof x !== 'string')
  )
    throw new Error('Exclusions must be path patterns');
  if (
    profile.history?.gateway_command &&
    (!Array.isArray(profile.history.gateway_command) ||
      !profile.history.gateway_command.length ||
      !path.isAbsolute(profile.history.gateway_command[0]) ||
      profile.history.gateway_command.some((x) => typeof x !== 'string'))
  )
    throw new Error('Gateway requires an absolute executable and argument strings');
  for (const [key, max] of [
    ['interval', 31536000],
    ['history_interval', 31536000],
    ['history_months', 120],
  ]) {
    const n = profile.crawler?.[key];
    if (n !== undefined && (!Number.isInteger(n) || n < 1 || n > max))
      throw new Error(`Invalid crawler ${key}`);
  }
  return profile;
}
function scopeContent(profile, base) {
  const value = validateProfile(profile, base);
  for (const source of value.sources) source.type ||= 'git';
  if (value.embeddings?.cache_folder)
    value.embeddings.cache_folder = path.resolve(base, value.embeddings.cache_folder);
  for (const key of ['interval', 'history_interval', 'history_months'])
    if (value.crawler) delete value.crawler[key];
  for (const key of ['crawler', 'history'])
    if (value[key] && !Object.keys(value[key]).length) delete value[key];
  if (!value.exclude?.length) delete value.exclude;
  const canonical = (v) =>
    Array.isArray(v)
      ? v.map(canonical)
      : v && typeof v === 'object'
        ? Object.fromEntries(
            Object.keys(v)
              .sort()
              .map((key) => [key, canonical(v[key])]),
          )
        : v;
  return JSON.stringify(canonical(value));
}
module.exports = { validateProfile, scopeContent };
