# Semantic retrieval reference implementation

Implemented 2026-09-09. The engine now supports a company-independent embedding interface, incremental vectors, and lexical/semantic/hybrid retrieval. The optional local adapter uses Sentence Transformers; companies can inject their own embedding API without changing discovery, evidence storage, or retrieval assembly.

## Run locally

The core and ordinary tests remain Python 3.9+ standard-library code. The optional reference adapter has its own dependencies. Create a virtual environment in a location appropriate for your machine:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-semantic.txt
.venv/bin/python prefetch_model.py --cache-folder .context-engine/models
.venv/bin/python -m context_engine --manifest examples/acme-semantic.json index
.venv/bin/python -m context_engine --manifest examples/acme-semantic.json search 'preserve urgency when processing queued work' --mode hybrid --token-budget 8000
```

Only the explicit prefetch step downloads model files. The adapter loads cached weights with `local_files_only=True`, `trust_remote_code=False`, and CPU inference. Source text is embedded locally; it is not sent to Hugging Face. The example uses a pinned MiniLM commit and a 384-dimensional output. It is a small general-purpose reference model, not a selected production code model. Install packages and prefetch in the approved environment before indexing; a missing model is reported rather than silently downloading it.

The manifest's optional `embeddings` object accepts `provider`, `model`, `revision`, `dimensions`, and `cache_folder`. Relative cache paths resolve against the manifest directory. The reference provider requires a 40-character model commit SHA. No embeddings configuration means the existing lexical-only behavior. The semantic example uses its own configuration-scoped store; it does not modify existing Acme/Harbor configurations.

To connect the example through MCP, use the optional environment's Python executable and `examples/acme-semantic.json` in the normal `serve` launch. Restart/reconnect the client to load changed Python code/tool schemas. The workspace generator can also be run with that interpreter and manifest, using a fresh output directory. Existing running MCP processes are not automatically upgraded or switched to semantic mode.

## Adapter contract

`context_engine.embeddings.EmbeddingProvider` requires:

- `identity: EmbeddingIdentity(provider, model, revision, dimensions, adapter_version)`.
- `embed_documents(texts)`: one vector for each input, in the same order.
- `embed_query(text)`: a query vector from the compatible vector space.

Inject the provider using `Engine(manifest, state, embedding_provider=provider)`. A company integration can construct that engine and call `context_engine.__main__.serve(engine)`, wrapping its internal API and credential lookup in the provider. The built-in manifest factory only recognizes the local reference adapter; it never imports arbitrary module names from source content. Company runtime/harness, authentication, API request/response format, retries, and deadlines remain adapter/deployment responsibilities. Calls are synchronous; this prototype does not enforce cancellation/deadlines for injected code.

Identity must change whenever the vector space or input preprocessing changes, even if an API model alias remains the same. Never put credentials in identity or exception messages. Generic provider failures are redacted; `EmbeddingError` messages are considered safe to surface. The core validates batch counts, dimensions, finite values, and nonzero norms and normalizes vectors before cosine scoring. Test doubles validate this contract but do not demonstrate semantic usefulness.

## Storage and freshness

Vectors live in an additive `vectors` table inside each existing scoped SQLite store. A key combines source/path, extraction method, embedding text, and input-template version; the provider namespace adds model/revision/dimension/adapter identity. The local adapter includes its Sentence Transformers package version. Embedding text is path, optional symbol, and excerpt. The reference model applies its model-specific token-length truncation; long code chunks may be only partially represented. This does not truncate the returned cited excerpt.

Indexing first updates lexical evidence, then embeds missing chunks in batches of at most 32. Unchanged chunks reuse vectors; changed/deleted chunk vectors are pruned, and a model identity change rebuilds its namespace. Invalid cached vectors are recomputed. A successful vector batch set and its semantic-generation metadata are committed atomically after a source-generation/freshness check. Failure leaves lexical retrieval available for fresh source content and prevents use of an incomplete semantic generation. No partial new vector batch is published.

The first slice does not keep a historical semantic snapshot active across source edits. It withholds semantic results until the current generation is complete. Provider computation is outside the SQLite write transaction. Concurrent changes are checked before publishing and after query embedding; as with the lexical prototype, filesystem edits can still race the final scan. There is no managed-service writer lease, crash-recovery supervisor, or multi-user ACL implementation yet.

## Search and status

CLI `search --mode` and MCP `search_context` / `get_context_bundle` accept `auto`, `lexical`, `semantic`, or `hybrid`.

- `auto`: hybrid when a provider is configured, otherwise lexical.
- `lexical`: existing BM25 behavior, with no query embedding call.
- `semantic`: exact cosine nearest-neighbor ranking; unavailable semantics returns no evidence plus a gap.
- `hybrid`: equal reciprocal-rank fusion, `1/(60 + rank)` per lane, followed by overlap suppression and budget assembly. Single-word literal identifiers are promoted ahead of nonliteral candidates. If semantics fails, fresh lexical evidence is returned with an explicit fallback notice.

`retrieval.requested` and `retrieval.used` identify the requested and actual mode. Semantic/hybrid results include retrieval-method signals and explain their rank convention; scores are not confidence. Existing evidence IDs, citations, budgets, and `budget.omitted_files` remain available. Source drift fails closed before any mode returns evidence.

Status reports source freshness separately from `semantic.state` (`disabled`, `pending`, `error`, `ready`), provider identity, chunk coverage, and the last indexing result. `capabilities.semantic_search` is true only for a fresh source snapshot and complete semantic generation. Readiness of stored vectors is not a guarantee that the provider will answer the next query; query failures are explicit. Index commands can complete lexical indexing while reporting a semantic error in their JSON output, so callers must inspect both states.

Exact vector scanning, JSON vector storage, repeated freshness scans, and batch accumulation in memory are correctness baselines for small corpora. They are not a scale claim. Deleted sources are pruned on indexing; deleting a manifest or abandoning an old store does not automatically purge that store.

## Verification and observed limits

```sh
python3 -m unittest discover -s tests -v
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 CONTEXT_ENGINE_MODEL_CACHE="$PWD/.context-engine/models" .venv/bin/python -m unittest discover -s tests -v
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python evaluate_semantic.py --cache-folder .context-engine/models --output /tmp/semantic-results.json
```

The optional model test runs actual embeddings and a fresh MCP subprocess. The synthetic six-source fixture and questions are in `evaluation/semantic-fixture.json`, with measured results in `evaluation/semantic-results-2026-09-09.json`. The fixture was authored before the first model run and was not used to tune fusion weights or a relevance threshold; it is not an independently blinded production benchmark.

| Validated smoke result | Lexical | Semantic | Hybrid |
| --- | --- | --- | --- |
| Expected file ranked first, positive questions | 5/8 | 8/8 | 6/8 |
| No result for unsupported questions | 2/2 | 0/2 | 0/2 |

The first cross-process evaluation exposed insertion-order sensitivity at equal ranks. Ranking now breaks ties by stable source/path/span identity, with a regression test across changed row IDs. The table records the post-fix run; all 22 tests passed including real-model MCP. All 12 vectors were reused on unchanged reindex (zero new embeddings). Semantic-only outperformed this initial hybrid ranking on the positive smoke cases. Neither semantic nor hybrid has a calibrated relevance cutoff; both return nearest neighbors for unsupported questions. **Do not treat a semantic match as proof that the behavior exists.** The reference is functional, but the negative-result regression means it has not met the earlier production-pilot acceptance gate. Preserve lexical mode and the published failures while evaluating improved ranking/abstention on a larger fresh corpus.

## Source references

The local adapter uses the documented [query/document encoding methods](https://www.sbert.net/docs/package_reference/sentence_transformer/model.html). Model identity and revision come from the [MiniLM model metadata](https://huggingface.co/api/models/sentence-transformers/all-MiniLM-L6-v2). No service-specific API is coupled to the engine core.
