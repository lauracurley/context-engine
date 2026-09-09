# Development and verification

Run from the repository root. The standard suite uses Python's standard library and temporary fixtures/stores:

```sh
python3 -m unittest discover -s tests -v
python3 evaluate.py
python3 evaluate_retrieval.py --output /tmp/retrieval-results.json
```

The real-model test is opt-in and skipped without `CONTEXT_ENGINE_MODEL_CACHE`. After following the semantic setup in the README:

```sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 CONTEXT_ENGINE_MODEL_CACHE="$HOME/.local/share/context-engine/checkout-semantic/models" .venv/bin/python -m unittest discover -s tests -v
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python evaluate_semantic.py --cache-folder "$HOME/.local/share/context-engine/checkout-semantic/models" --output /tmp/semantic-results.json
```

Tests cover indexing, scope isolation, source changes/deletion, parser fallback, budgets, MCP, semantic caching/failures, stable ranking ties, and generated workspace setup. Setup tests run the generated task commands and both MCP servers, including a personal-only sentinel that must not appear in team results. Model tests use real cached vectors and a fresh MCP subprocess.

`evaluate.py` is a five-case smoke gate. The [16-question lexical comparison](../evaluation/README.md) and [semantic reference comparison](SEMANTIC-REFERENCE.md#verification-and-observed-limits) publish imperfect results, rather than treating completion of an evaluation as passing a quality gate. The corpora are tiny public-safe synthetic fixtures. Do not describe their scores as production quality or task completion.

The reusable code lives in `context_engine/`. `setup.py` scaffolds private workspace configuration; `vscode.py` renders launch files; `embeddings.py` defines the provider boundary; `semantic.py` manages vectors and ranking; `core.py` owns scoped discovery/evidence; `__main__.py` provides CLI and MCP entry points. Company-specific credentials, repository provisioning, identity mapping, and remote authorization belong outside this core.

Keep real work configurations, indexes, model weights, virtual environments, and credentials out of source control. Commit public-safe code, fixtures, tests, and documentation. The repository currently uses additive SQLite tables and configuration-scoped stores; there is no general schema migration framework or production daemon supervisor.
