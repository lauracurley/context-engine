Retrieval and context cost audit — 2026-09-10

The engine has a credible foundation for economical retrieval, but it does not yet establish lower end-to-end agent cost. Compact discovery, targeted reads, source identity checks, local indexing and optional semantic retrieval are useful building blocks. The next priority should be retrieval efficiency and evaluation before adding more tool surface.

This is an assessment and proposed implementation sequence. Runtime behavior was not changed by this audit.

**What exists today**

| Capability | Assessment |
| --- | --- |
| Progressive disclosure | Overview → compact discovery → selected source ranges exists. Overview supports ETags; reads support expected hashes and continuation. Agents should enter at the appropriate level rather than always traverse all levels. |
| Hierarchy | The overview groups repositories and file modules. Structural tools expose declarations, references and callers separately. There is no unified subsystem → file → symbol hierarchy or retrieval planner. |
| Graph | SQLite stores source-local import links and inferred cross-source shared-event-literal links. Overview can expand immediate neighbors. Ordinary search does not use this graph. |
| Related evidence | `find_related` searches using nearby source text and labels results content similarity. It does not traverse dependencies. |
| Structural evidence | Python, JS/TS and Kotlin parsing provides useful facts. Caller/reference candidates use names and source scope; they are not compiler-bound relationships. Kotlin import-to-file resolution remains missing. Symbol search uses the architecture extractor rather than the structural index. |
| Budget control | Compact responses budget their whole JSON payload, excluding MCP framing. Despite the parameter name `token_budget`, the unit is UTF-8 bytes. Legacy search budgets evidence only and includes a verbose status response outside that ceiling. |
| Handoff | VS Code task packs enforce a byte ceiling and deduplicate identical pinned items. They do not merge overlapping ranges or provide a cumulative MCP conversation budget. |

Relevant implementation: [navigation](../context_engine/navigation.py), [architecture](../context_engine/architecture.py), [structure](../context_engine/structure.py), [packing](../context_engine/budget.py), [task packs](../vscode-extension/src/packs.js).

**Measurements**

Ran `evaluate_context.py` with the existing isolated Python environment. The fixture is two tiny Python modules from `examples/acme.json`. Values below are complete compact-serialized JSON payload bytes, not model tokens. Legacy search uses a 32,000-byte evidence ceiling and compact search an 8,000-byte whole-payload ceiling; neither ceiling was saturated.

| Query | Legacy response | Compact response | Location-only response | Compact reduction |
| --- | ---: | ---: | ---: | ---: |
| task.requested priority | 4,702 | 1,587 | 959 | 66.2% |
| UNKNOWN_TEMPLATE | 3,756 | 1,019 | 719 | 72.9% |
| COMPLETED | 3,677 | 886 | 725 | 75.9% |

All three variants returned the same files. This does not establish equivalent answer quality: a location-only response may need an additional read. Overview returned 1,713 bytes and cited the shared event relationship; an unchanged conditional overview returned 408 bytes. The existing smoke evaluator passed.

A separate temporary-fixture probe wrapped `Engine.scan` with a call counter after indexing. For the lexical `UNKNOWN_TEMPLATE` lookup:

| Operation | Payload bytes | Full source scans |
| --- | ---: | ---: |
| index_status | 2,374 | 1 |
| get_system_overview | 1,713 | 2 |
| search_code | 1,019 | 3 |
| All three sequentially | 5,106 | 6 |

Direct search therefore returned about one fifth of the bytes for this case. Repeated scans affect local latency and I/O, not directly the model's billed token count. The current MCP catalog has 13 tools and serializes to 8,876 bytes; client tool loading and caching determine how much of that reaches the model. No authenticated model calls or dollar-cost measurements were performed.

**Recommended sequence**

1. Fix routing and accounting first. Align generated guidance, MCP instructions and agent docs around query intent. Use a known location directly with `read_code`; exact identifiers with structural definitions or literal/file search; unfamiliar architecture with overview; conceptual questions with compact lexical/hybrid search. Inspect full status for diagnosis, not as a mandatory prelude to every retrieval, since compact retrieval already reports freshness. Keep repository instructions available before edits. Make legacy tools optional/deprecated for new integrations and give all evidence responses the same whole-payload contract. Preserve backward compatibility while introducing an explicit byte-budget name; report model-token estimates separately when calibrated.

2. Consolidate retrieval behind one internal candidate pipeline. Compact search currently invokes legacy search with a fixed intermediate budget before compacting again. Retrieve lightweight candidates, rank and deduplicate them, then fetch selected snippets and pack once. Use the structural index for symbol lookup, including Kotlin. Share freshness work within a request while retaining a final change check; later consider watcher invalidation with periodic reconciliation and explicit handling of unsaved editor buffers. Scope SQL reads before decoding all facts/vectors. These changes primarily improve latency, recall under a budget, and consistency.

3. Add bounded graph expansion for relational questions. Start with the best few evidence anchors and allow one hop with an explicit small neighbor budget. Filter by scope and relation, rank neighbors against the question, and include a cited reason for each link. Expand imports/callers for dependency questions and shared contracts for cross-service questions; do not append neighbors to every search. Store direction and resolution confidence only where extraction supports them. Keep inferred event/name matches distinguishable from resolved relationships. SQLite adjacency indexes are sufficient for the next slice; a separate graph database is not currently justified by measured scale.

4. Unify the hierarchy without preloading it. Aim for workspace → repository → configured package/subsystem → file → symbol → source range. Derive cheap summaries from manifests, paths, declarations and curated architecture docs first. Use source hashes/generations to invalidate cached summaries and cite their inputs. Consider generated summaries only after evaluating their indexing cost and retrieval benefit. Keep instruction scope and history as distinct retrievable evidence, not mandatory attachments to every code answer.

5. Budget across the task, not just the response. Let callers supply already-seen evidence identities and a remaining budget. Deduplicate by source identity and overlapping ranges, preserve citations, expose omissions with a way to retrieve more, and reserve room for useful excerpts rather than filling the budget with metadata. Prefer useful evidence per byte, with repository diversity when the task requires multiple services. Extend the existing task-pack behavior through the portable core so VS Code and MCP share the same policy. A server budget can limit its outputs; only client usage telemetry can establish total conversation cost.

**Acceptance criteria before claiming savings**

Expand the existing retrieval evaluations with frozen, human-checked tasks: exact Kotlin definitions, ambiguous symbols, cross-service event flow, dependency/impact questions, documentation rationale, missing answers, and stale files. Include larger multi-repository fixtures. Compare the current compact baseline, routing changes, and routing plus graph expansion at equal budgets.

Measure evidence recall and citation correctness, successful task completion, total response bytes, actual input/output tokens where the client exposes them, repeated evidence, tool-call count, latency, and indexing/embedding cost. Track cached versus uncached model input where available. Require task quality to remain stable before accepting a byte reduction; graph expansion should earn its added budget through relational-task improvements. Report ordinary identifier lookups separately from architecture tasks so aggregate savings cannot hide regressions.

The recommended next implementation slice is items 1–2 plus the expanded baseline evaluation, followed by bounded graph expansion. This work belongs in the existing portable core, with extension controls for displaying and choosing budgets; it does not require a second repository.


**First implementation increment — 2026-09-10**

Implemented intent-based routing in generated workspace guidance, MCP instructions and agent docs. Compact search now shares ranked candidates with legacy search without inheriting its response packing or intermediate byte cutoff. It clips snippets once and checks freshness before and after retrieval; lexical discovery now performs two full scans rather than three. Symbol discovery uses scoped structural facts, including qualified Kotlin declarations, and reports parser gaps.

The six compact MCP tools accept `byte_budget`; `token_budget` remains a compatibility alias and supplying both is rejected. Their command-line equivalents accept `--byte-budget` as an alias, allowing existing extension/backend calls to continue working. Legacy response contracts remain unchanged in this increment.

The evaluator now compares discovery plus source reading, checking identical nonempty source evidence. On the demo, direct discovery/read returns 1,628 bytes across two calls versus 5,715 bytes across four calls with status/overview preludes (about 72% fewer response bytes). This compares two routes on the updated engine, not old/new model billing. Graph expansion, a unified subsystem hierarchy, cumulative task budgets and actual client token telemetry remain future work.


**Local efficiency track completed — 2026-09-10**

The follow-up adds explicit one-hop graph retrieval (indexed SQLite adjacency), Workbench graph navigation, directory-by-directory overview expansion, caller-supplied discovery exclusions and optional server-scoped cumulative MCP task ledgers. Default search remains unexpanded. Task accounting includes its own metadata and refuses evidence once the remaining allowance cannot support a response. Discovery reuse does not block selected source reads; changed content hashes produce new evidence identities.

The quality gate now includes `evaluate_efficiency.py`: the acme fixture plus 100 unrelated files, checking a scoped identifier, a cross-service event contract, an absent dependency and a missing identifier at fixed response budgets. All four expected evidence sets pass; the shared-event response uses 1,150 bytes. Tests also exercise import direction, stale rejection, nested directory expansion, repeated discovery, task lifecycle and exact MCP payload accounting. Existing Kotlin and ambiguous structural-navigation checks remain in the suite.

This completes the local implementation slice, not an end-to-end billing claim. Path groups are not generated business subsystem summaries; syntax and graph links remain inferred. The in-memory MCP task ledger and saved VS Code handoff packs have separate lifecycles. Compiler-bound Kotlin imports, graph recall beyond currently extracted edges, ANN indexing and paid-model task evaluation remain outside this completed slice. Broader optimizations should be justified by representative client quality/latency/usage measurements rather than added automatically.
