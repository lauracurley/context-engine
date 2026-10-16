'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { version } = require('../package.json');
const { reviewedReport } = require('../src/usage-report');
test('report exporter rejects company content, arbitrary labels and invalid totals', () => {
  const report = {
    schema_version: 1,
    engine_release: version,
    report_kind: 'product_usage_aggregate',
    period_days_bucket: '0',
    operations: {},
    token_usage: { availability: 'unavailable' },
  };
  assert.equal(JSON.parse(reviewedReport(report)).schema_version, 1);
  assert.throws(() => reviewedReport({ ...report, prompt: 'COMPANY_SECRET' }), /unexpected/);
  assert.throws(() => reviewedReport({ ...report, operations: { COMPANY_NAME: {} } }), /Unknown/);
  const row = {
    calls: 1,
    outcomes: { success: 1, empty: 0, stale: 0, unavailable: 0, cancelled: 0, internal_error: 0 },
    duration_ms_bins: { le_100: 1, '101_500': 0, '501_2000': 0, gt_2000: 0 },
    emitted_payload_bytes: 100,
    duplicate_candidates_suppressed: 0,
  };
  report.operations.search_code = row;
  assert.ok(reviewedReport(report));
  row.duration_ms_bins.le_100 = 0;
  assert.throws(() => reviewedReport(report), /totals/);
  row.duration_ms_bins.le_100 = 1;
  row.emitted_payload_bytes = 'PRIVATE_CODE';
  assert.throws(() => reviewedReport(report), /counter/);
});
