Efficiency measurement without company or user data — implementation plan

We currently have built-in developer benchmarks (`evaluate.py`, `evaluate_context.py`, `evaluate_efficiency.py`, plus retrieval/semantic evaluators) and optional MCP response-budget accounting. CI runs the deterministic core evaluations. We do not yet have a one-click client benchmark, a client-facing efficiency dashboard, actual model-token instrumentation or an automated privacy-reviewed export. The client should not need to assemble logs or describe results manually.

The client allows local company-controlled storage. Keep normal source indexes local under that policy; do not add a vendor telemetry collector. This document is a plan, not an implemented telemetry feature.

**Two separate measurement paths**

1. Shareable synthetic benchmark: bundle a fixed, versioned, public/synthetic multi-service fixture, including Kotlin, distractors, duplicate identifiers, inferred relationships, stale updates and missing answers. It must never inspect the user's open workspace, repository manifests, Git history, chat transcripts or provider logs. Run locally from a fresh isolated fixture directory, with network denied and embeddings disabled unless an approved model is already present. Discard synthetic scratch state after completion. Synthetic tests are the only recommended source of externally shareable reports under the current requirement.
2. Optional live local view: compute coarse totals in memory inside the company-controlled process—response bytes, tool-call counts, retries, latency buckets, cache hits and omitted/reused evidence counts. Accept numeric values and fixed enums only. Do not pass queries, tool argument/result objects, task IDs, paths or exceptions to the measurement component. Keep this view off by default, local, nonpersistent and nonexportable. Clear it on close/restart. These numbers are still derived from company activity, so they are not claimed to be anonymous or suitable for external collection.

This separates shareable product benchmarks from actual-workload observations. We cannot prove real company task success or dollar savings using synthetic results alone. Central collection of real workload aggregates would require a separate explicit policy decision and privacy review; neither hashing identities nor dropping names makes that collection automatically acceptable.

**Client workflow to build**

Add a Workbench **Run private benchmark** action with a clear “synthetic fixtures only; nothing uploaded” description. No extra dependency installation or provider login is needed for the deterministic benchmark. Show correctness and cost side by side:

- Expected evidence found and citations valid; missing/ambiguous cases handled correctly.
- Compact response bytes, tool-call count, duplicate evidence and omissions.
- Median/p95 local latency with warm/cold runs labeled separately.
- Graph quality on relational tasks and overhead on ordinary identifier tasks.
- Total index/build work for the fixture, so retrieval savings do not hide setup cost.

Offer **Preview synthetic report** and **Save synthetic report**, not “send logs.” Generate the report from an allowlisted measurement object, validate it again at export, and reject extra properties. Use a generic filename and no automatic upload. The client can share this exact report through an approved channel without writing a narrative. No backend endpoint, analytics SDK or unique installation ID is required.

**Export contract**

Allow only schema version, released engine version, fixed fixture-suite version, fixed benchmark-case enum, success boolean, iteration count and bounded numeric measurements (bytes, calls, omissions, recall/precision, rounded latency). Include fixed enum `measurement_kind: synthetic` and explicit `token_measurement: unavailable` unless an approved numeric token counter was used. Do not serialize raw tool results to construct the report.

Exclude company/workspace/source names, file paths, URLs, Git refs, hashes of source or configuration, embeddings, snippets, queries, generated answers, instructions, history, task/session IDs, account/device identifiers, hostnames, IP addresses, usernames, exact timestamps, free-text feedback, stack traces, environment variables and arbitrary model/provider strings. Product version and synthetic fixture identifiers must be released constants rather than commit hashes from a private fork. Latency may reflect the device; do not claim it provides formal anonymity.

**Actual tokens and quality**

Keep byte measurements explicitly labeled; never multiply them by a fixed bytes-to-token ratio and call the result savings. If the approved client exposes numeric usage counters through a supported integration, a separate local adapter may read only those counters. Do not scrape stored conversations or proxy raw prompts to obtain usage. Account for tool schemas/instructions, all follow-up reads, retries, input/output tokens, cache treatment and indexing/embedding work. Mark unavailable fields unavailable. Do not attribute the entire conversation's token usage causally to this engine.

For optional synthetic model evaluation, compare paired tasks with and without the engine using the same approved model/settings and task inputs. Keep outputs transient and grade against deterministic assertions where possible. Record successes and failures, not only favorable runs; repeated trials are needed for stochastic agents. Network/model use must be explicitly configured and is outside the offline default. Actual company task quality remains a local client assessment unless separately authorized.

**Implementation stages and acceptance gates**

| Stage | Deliverable | Acceptance |
| --- | --- | --- |
| 1 | Versioned synthetic fixture + pure standard-library benchmark result/schema module | Run without an open project; no company directory enumeration; fixed expected evidence sets; deterministic correctness checks; repeated timing runs reported honestly. |
| 2 | Workbench action, readable dashboard and previewable JSON export | Client completes benchmark/report in one action; export contains only approved fields and synthetic enums; no arbitrary strings; cancellation clears transient fixture state. |
| 3 | Optional in-memory live counters | Numeric-only input API; no persistent files or network; no stable IDs; reset on close; explicit local-only labeling; no export route. |
| 4 | Release CI security/privacy gate and dependency approval record | Synthetic sentinel tests detect content/path/identity leakage; network-denied tests pass; OS file-write inspection covers crash/cancel paths; SBOM and approved dependencies accompany the artifact. |
| 5 | Optional approved numeric model-usage adapter | No transcript access; unsupported providers show “unavailable”; paired synthetic trials preserve quality and account for whole-task cost. |

Test privacy structurally: seed fake company names, usernames, emails, paths, credentials and source canaries into a test workspace; prove the synthetic runner does not read that workspace and the exporter cannot represent those values. Test query/result/exception objects rejected at the metric API, unknown JSON fields rejected, symlink workspace tricks, crash/cancel cleanup, and absence of network requests. A test that merely greps one exported report for known words is insufficient.

Suggested implementation order: dependency/storage release gates first, then stages 1–2 together. Add live measurement only after its retention and field contract is reviewed. The existing request budget ledger is a useful enforcement feature but must not be repurposed into exported telemetry: its task IDs and evidence hashes are not approved report fields.

This data-minimization approach is consistent with OWASP guidance to exclude sensitive values from logs; it goes further here by excluding raw logging from efficiency reports altogether. See [OWASP logging guidance](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
