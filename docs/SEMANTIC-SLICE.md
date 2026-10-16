# First semantic retrieval slice

Status: initial provider-independent foundation implemented, 2026-09-09. See [the runnable reference](SEMANTIC-REFERENCE.md) for setup, tests, real-model results, and remaining pilot gaps. The design below records the broader milestone. A provider interface, random vectors, or mocked embeddings do not complete this milestone.

## User acceptance

Open the existing developer workspace, allow its normal startup integration to run, and ask a behavior question across selected repositories without knowing identifiers. The agent retrieves relevant code with source paths, lines, current content identities, and an explicit budget. Exact identifiers/errors must remain useful. Personal Scratch is optional and private.

Use the [workspace integration contract](WORKSPACE-INTEGRATION.md) to attach to the harness. The engine can be built and tested independently of any company API or harness. A local reference adapter now supplies real embeddings; a company integration can later supply its approved API, authentication, and runtime configuration through the same interface. Do not substitute a different service or transmit code until the actual approved destination is configured.

## Implementation order

1. **Capture deployment inputs.** Confirm runtime resources, the available approved API/model and its authentication contract, mounted-repository selection, persistent storage, source scale, and languages. Add a sanitized harness adapter fixture with team repositories and a separate personal Scratch fixture.
2. **Build the embedding adapter and real provider integration.** Support document and query embedding separately. Each response identifies provider/model revision, dimension, normalization, and the input configuration. Validate vector shape, finite values, and nonzero norms; define batching, bounded retries, timeouts, and cancellation. Resolve credentials through the work environment. Default to no network until a provider is explicitly configured.
3. **Persist incremental vector generations.** Key vector entries by authorized store, source/path, content chunk identity, parser version, model revision, dimension, and input-template version. Index only changed chunks; invalidate deleted/moved chunks and changed providers. Keep an active complete generation while preparing the next, and never return an excerpt whose current hash differs from its evidence identity.
4. **Fuse lexical and semantic candidates.** Retrieve both independently within the same authorized corpus, deduplicate by chunk/content identity, use rank-based fusion rather than comparing raw BM25 and cosine scores, then suppress overlapping excerpts and assemble a budgeted bundle. Preserve an exact-identifier lane and expose which retrieval methods contributed. Baseline rank-fusion parameters remain explicit and are tuned only on a development set.
5. **Expose readiness and fallback.** Report lexical readiness and semantic readiness separately. A provider outage may allow an explicitly labeled lexical fallback for fresh content. Never report semantic search available solely because an adapter is installed or an index has some vectors. Source-level partial coverage, failures, budget omissions, and model-generation mismatch must be visible.
6. **Evaluate actual semantic usefulness.** Run lexical-only, semantic-only, and hybrid modes on the same corpus, queries, scopes, and budgets, plus literal file search. Publish per-case predictions and resource measurements. Complete the slice only with real embeddings from an approved provider and a documented gain on behavior questions.

For an initial small local corpus, exact vector similarity scoring can be a correctness baseline. Select an approximate-neighbor backend only after measuring vector count, memory, latency, and rebuild behavior in the target environment. Do not select infrastructure solely from the four-file demo. The existing SQLite evidence/index can remain the provenance source, but vector storage and generation metadata require their own schema/migration plan.

## Chunking and language scope

Retain Python AST chunks and explicit fallback windows initially, while measuring the dominant work languages. Add parser adapters for the work stack where whole-window retrieval fails. Embedding text should contain the path, symbol/signature when available, and the excerpt, with deterministic truncation and a recorded input-template version. Avoid embedding unrelated repositories or combining private notes with team documents in one chunk.

Semantic relevance is not structural proof. Retrieval must not claim it resolved a call graph or producer/consumer relationship. Architecture extraction is now implemented as a separate cited structural layer; instruction resolution remains outstanding. Both are distinct from semantic similarity. See [current architecture](ARCHITECTURE.md).

## Evaluation contract

The existing 16-question set is now a development/regression set: its author saw the fixtures and its failures are known. Preserve it unchanged. Build a fresh evaluation set with independently supplied public-safe code and relevance labels, or evaluate work code entirely inside the approved work environment. Do not copy work questions/code into personal Scratch.

Include multiple repositories, similar-but-wrong services, old/dead implementations, tests versus production code, configuration, docs, personal-only sentinels, unsupported behavior, and natural-language queries without shared identifiers. Separate exact-identifier, behavioral, cross-repository, and negative cases. Label expected files and useful line ranges before running the candidate configurations.

Measure file/span precision and recall at budget, rank, negative false-positive rate, cross-repository coverage, evidence completeness, initial indexing cost, incremental-edit cost, query latency, and memory. Record actual model tokens where available separately from the current evidence-byte proxy. Track task completion with representative agent tasks as a separate measure; retrieval recall alone is not task success.

Gates for the pilot:

- Hybrid improves behavior-question retrieval over lexical-only on the fresh set, with per-case evidence of the gain.
- Exact-identifier and negative cases do not regress without an explicit reviewed tradeoff.
- Source isolation, instruction scope, citations, stale-evidence withholding, deletion, and budget tests pass.
- Edit/reindex and provider-outage scenarios behave as documented.
- Indexing and query resource use fit the developer workspace's agreed limits. Set numeric latency/memory targets after learning those limits, before benchmarking the pilot.

## Follow-on milestones

After semantic retrieval works in the harness: scoped instruction loading plus a cited low-token architecture overview; then a periodic canonical team crawler; then opt-in GitHub/commit decision retrieval and bounded knowledge-holder analysis. Develop a shared service only with authenticated scope enforcement and personal-data isolation tests. The current workspace generator remains useful for demonstrations, not the production bring-up architecture.

Current implementation update: the local architecture map, periodic crawler, managed canonical Git sources, and opt-in history/activity ingestion are implemented. The milestone ordering above records the original design; company deployment, instruction resolution, and representative retrieval-quality acceptance remain incomplete.
