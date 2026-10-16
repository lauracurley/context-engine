'use strict';
const { version } = require('../package.json');
const operations = new Set([
  'search_code',
  'read_code',
  'get_system_overview',
  'find_related',
  'navigate_structure',
  'resolve_instructions',
]);
function exact(value, keys) {
  if (
    !value ||
    typeof value !== 'object' ||
    Array.isArray(value) ||
    Object.keys(value).sort().join(',') !== [...keys].sort().join(',')
  )
    throw new Error('Usage report contains unexpected fields');
}
function integer(value) {
  if (!Number.isSafeInteger(value) || value < 0 || value > 1e12)
    throw new Error('Invalid usage counter');
}
function reviewedReport(report) {
  exact(report, [
    'schema_version',
    'engine_release',
    'report_kind',
    'period_days_bucket',
    'operations',
    'token_usage',
  ]);
  if (
    report.schema_version !== 1 ||
    report.engine_release !== version ||
    report.report_kind !== 'product_usage_aggregate' ||
    !['0', '1-7', '8-30'].includes(report.period_days_bucket)
  )
    throw new Error('Unsupported usage report');
  exact(report.token_usage, ['availability']);
  if (report.token_usage.availability !== 'unavailable')
    throw new Error('Unsupported token measurement');
  if (
    !report.operations ||
    typeof report.operations !== 'object' ||
    Array.isArray(report.operations)
  )
    throw new Error('Invalid operations');
  for (const [op, row] of Object.entries(report.operations)) {
    if (!operations.has(op)) throw new Error('Unknown usage operation');
    exact(row, [
      'calls',
      'outcomes',
      'duration_ms_bins',
      'emitted_payload_bytes',
      'duplicate_candidates_suppressed',
    ]);
    for (const key of ['calls', 'emitted_payload_bytes', 'duplicate_candidates_suppressed'])
      integer(row[key]);
    for (const [key, labels] of [
      ['outcomes', ['success', 'empty', 'stale', 'unavailable', 'cancelled', 'internal_error']],
      ['duration_ms_bins', ['le_100', '101_500', '501_2000', 'gt_2000']],
    ]) {
      exact(row[key], labels);
      for (const value of Object.values(row[key])) integer(value);
      if (Object.values(row[key]).reduce((a, b) => a + b, 0) !== row.calls)
        throw new Error('Inconsistent usage totals');
    }
  }
  const text = JSON.stringify(report, null, 2) + '\n';
  if (Buffer.byteLength(text) > 65536) throw new Error('Usage report exceeds 64 KB');
  return text;
}
module.exports = { reviewedReport };
