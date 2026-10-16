# Reviewed usage report v1

The [vendor data boundary](VENDOR-DATA-BOUNDARY.md) is the standing contract. The current 0.5.1 release uses the same metric allowlist with its own release label; earlier release notes/examples below are historical.


0.5.0: the six-operation metric registry remains unchanged; accepted release is 0.5.0, in its own initially disabled aggregate directory. Knowledge, review imports and audit identities are excluded. Previous-release examples below remain historical.

0.4.0 note: the metric registry is unchanged, but the accepted engine release is now 0.4.0. Aggregates use a release-specific directory and start disabled after this upgrade. The original 0.3.0 examples/evidence below remain historical; use the matching release for intake. Knowledge content and lookup counts are not added to this registry.

Collection is disabled by default. The VS Code sidebar offers enable, pause, clear/disable, and preview/save. There is no upload endpoint or network client. Local aggregates are scoped to an index. The Preview action shows the exact validated JSON saved after review, refuses a changed preview and refuses overwriting an existing target. A new report is mode 0600. The client chooses the destination and vets the file before manually transferring it.

## Allowed fields

| Field | Meaning |
| --- | --- |
| `schema_version` / `engine_release` / `report_kind` | Fixed accepted values: 1 / 0.3.0 / product_usage_aggregate |
| `period_days_bucket` | 0, 1–7, or 8–30 calendar days since oldest retained active day; not session duration |
| `operations` | Only search_code, read_code, get_system_overview, find_related, navigate_structure, resolve_instructions |
| `calls` | Completed observed operation attempts, including handled internal failures |
| `outcomes` | Fixed counters: success, empty, stale, unavailable, cancelled, internal_error |
| `duration_ms_bins` | Counts at ≤100, 101–500, 501–2000, >2000 ms |
| `emitted_payload_bytes` | Sum of encoded compact result JSON bytes, excluding MCP envelopes; zero for internal failures |
| `duplicate_candidates_suppressed` | Sum of the compact response's already_seen count; not cache hits or unique users |
| `token_usage.availability` | Always unavailable; bytes are not actual model tokens or money |

Both validators reject unknown fields/labels, arbitrary release strings, invalid numbers and inconsistent totals. Inputs are bounded to 64 KiB, integers to 10^12. The Python importer also rejects duplicate JSON keys. No prompts, snippets, paths, source names, architecture, content hashes, identifiers, precise timestamps, OS identity, free-text errors or installation IDs are exported. The collector receives only fixed enums and integers, not request/result objects.

Success means ready/unchanged with returned items; empty means ready/unchanged without items. Thus intentional duplicate suppression can count as empty. It does not measure answer quality. Other non-ready states map to unavailable except stale. Cancelled is reserved; process termination generally produces no observation. Timing measures the operation, excluding interpreter/engine startup and UI time. Only six compact core operations are instrumented in MCP and their internal CLI routes; legacy broad search, indexing and other UI activity are not usage counts.

Local day partitions and opt-in state live in `aggregates.json` below the private index scope. They contain only the same numeric rows plus dates used for retention. A rolling 30-day window is pruned on the next record/configure/preview access; there is no background eraser when the application is closed. Writes are locked across processes and atomically replaced. After a crash, orphan temporary aggregate files are removed on the next locked access. Clear writes an empty disabled state. Failures to persist statistics do not break retrieval, so counts can be incomplete.

Reports are overlapping rolling snapshots. They contain no deduplication identity: do not sum repeated reports or infer unique users. The review recipient must separately track accepted files/overlap, avoid keeping rejected payloads or diagnostic text, and agree a retention limit (proposed: delete received reports within 90 days). No recipient service or automatic retention scheduler is implemented. Saved report copies and editor backups follow client storage rules, not the aggregate window.

## Improvement intake

After client vetting, an operator can run:

```sh
python3 scripts/improvement_cycle.py /approved/reviewed.json --output /approved/new-decision.json
```

The script validates without uploading, rejects an existing output, and emits at most three fixed hypotheses with denominators. At least 20 calls and a 10% outcome rate are required by the current heuristic. These thresholds are product triage choices, not statistical significance. It does not edit code, expand collection, install packages or trigger releases. See [cycle 001](../../evaluation/IMPROVEMENT-CYCLE-001.md).
