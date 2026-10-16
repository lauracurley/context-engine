# Development and verification

For engine contributors. Employees start with the [VS Code quickstart](../README.md#start-in-vs-code); company integrators use the [portable core guide](CORE-GUIDE.md). Runtime preparers follow [Client setup](CLIENT-SETUP.md).

Run from the repository root. For the complete quality gate, install Python 3.9+ and Node.js 24 LTS (development tooling requires Node 22.13+):

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci --ignore-scripts --prefix vscode-extension
.venv/bin/python scripts/check.py
```

The command checks Ruff lint/format, Python tests, smoke and compact-context evaluations, ESLint, Prettier, and extension tests against a freshly packaged VSIX. It installs nothing and writes evaluation output to a temporary directory. Use `scripts/check.py --fix` with the same Python interpreter to apply safe lint fixes and formatting before checking. Review the diff afterward.

Ruff enforces Python correctness, import order, common bug patterns, and selected unsafe subprocess rules. ESLint checks JavaScript correctness and prohibits explicit `shell: true`, dynamic evaluation, and direct HTML insertion in checked source. These targeted checks complement tests and review; they are not a complete security analysis. Prettier formats extension JavaScript, CSS, and configuration. Python fixtures under `examples/`, recorded evaluations, generated backend files, and dependencies are excluded from formatting. Runtime dependencies remain unchanged; quality tools are development dependencies pinned in `requirements-dev.txt` and `vscode-extension/package-lock.json`.

The GitHub Actions quality workflow runs on pull requests and pushes to `main`, covering Linux with Python 3.9/3.12 and macOS with Python 3.12, using Node 24. Weekly Dependabot updates cover the development tools and pinned Actions. Repository administrators can make the quality jobs required in branch protection; the workflow alone does not enable that policy.

The Python-only suite uses the standard library and temporary fixtures/stores:

```sh
python3 -m unittest discover -s tests -v
python3 evaluate.py
python3 evaluate_retrieval.py --output /tmp/retrieval-results.json
```

The real-model test is opt-in and skipped without `CONTEXT_ENGINE_MODEL_CACHE`. After following the optional semantic setup in the [portable core guide](CORE-GUIDE.md#optional-semantic-reference-adapter):

```sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 CONTEXT_ENGINE_MODEL_CACHE="$HOME/.local/share/context-engine/checkout-semantic/models" .venv/bin/python -m unittest discover -s tests -v
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python evaluate_semantic.py --cache-folder "$HOME/.local/share/context-engine/checkout-semantic/models" --output /tmp/semantic-results.json
```

Tests cover indexing, scope isolation, source changes/deletion, parser fallback, budgets, MCP, semantic caching/failures, stable ranking ties, and generated workspace setup. Setup tests run the generated task commands and both MCP servers, including a personal-only sentinel that must not appear in team results. Model tests use real cached vectors and a fresh MCP subprocess.

`evaluate.py` is a five-case smoke gate. The [16-question lexical comparison](../evaluation/README.md) and [semantic reference comparison](SEMANTIC-REFERENCE.md#verification-and-observed-limits) publish imperfect results, rather than treating completion of an evaluation as passing a quality gate. The corpora are tiny public-safe synthetic fixtures. Do not describe their scores as production quality or task completion.

The reusable code lives in `context_engine/`. `setup.py` scaffolds private workspace configuration; `vscode.py` renders launch files; `embeddings.py` defines the provider boundary; `semantic.py` manages vectors and ranking; `core.py` owns scoped discovery/evidence; `__main__.py` provides CLI and MCP entry points. Company-specific credentials, repository provisioning, identity mapping, and remote authorization belong outside this core.

Keep real work configurations, indexes, model weights, virtual environments, and credentials out of source control. Commit public-safe code, fixtures, tests, and documentation. The repository currently uses additive SQLite tables and configuration-scoped stores; there is no general schema migration framework or production daemon supervisor.

## Architecture and retrieval checks

`architecture.py` caches facts/edges; `navigation.py` implements compact search and reads; `budget.py` bounds serialized tool text; `crawler.py` checkpoints scheduled jobs; `locking.py` coordinates writers; `managed.py` owns explicit remote snapshots; `chunking.py` integrates optional structural splitting. `history.py` and `history_providers.py` maintain normalized historical evidence and adapter boundaries.

The standard suite now covers crawler cadence/restart/backoff, cross-process writer contention, canonical Git updates without changing developer working trees, architecture freshness/citations, filters, regex timeout, MCP wire budgets, hash-checked reads, and history scope/partial coverage. Install `requirements-structure.txt` into a temporary environment to enable the real Rust splitter integration test. The standard suite skips that test and the cached-model test when their dependencies are absent.

Run `python3 evaluate_context.py --output /tmp/context-results.json` for compact-versus-legacy response byte measurements and overview/ETag checks. [Recorded results](../evaluation/context-results-2026-09-09.json) preserve selected files on three synthetic queries; they do not measure actual model tokens or downstream answer quality.

## VS Code extension

The JavaScript extension has no runtime npm dependencies and lives in `vscode-extension/`. After installing development dependencies above, run `npm run verify --prefix vscode-extension`; its test step automatically rebuilds the VSIX and bundled backend. The tests exercise the shipped Python launcher as well as CLI argument handling, trust gates, scope selection, terminal creation, and crawler lifecycle. Packaging creates `dist/context-engine-0.6.1.vsix` and the ignored development `backend/` directory. Rebuild after changing engine or extension code.

`vscode-extension/test/vscode-host.js` exports a VS Code extension-host smoke suite: pass it through `--extensionTestsPath` alongside `--extensionDevelopmentPath` and isolated temporary user-data/extensions directories. It verifies real activation, command registration, sidebar access, the bundled launcher, and diagnostics. It does not log in to provider accounts or claim end-to-end model inference.

Select one explicit editor installation for the host test and record its version from the app's package metadata before launching. Do not automatically try other copies from Downloads or mounted installers. A separate profile isolates test data, but a crashed test application can still display a system crash dialog. If launch fails, stop and inspect the local test logs and OS crash report before retrying; the CLI returning zero alone is not a passing host test. Record failures alongside successful runs and keep raw diagnostics local. The 0.6.0 verification includes a passing 1.137.0 host test and a 1.87.2 startup crash; see [alpha verification](../evaluation/alpha-verification-2026-09-13.json).

Instruction resolver tests cover nested applicability, explicitly invoked skills, new file paths, stale evidence, excluded/symlink instructions, response budgets, and CLI/MCP calls. Extension tests exercise the instruction command and real-backend workbench discovery/preview.

Install `requirements-navigation.txt` into the test interpreter to exercise real JavaScript/TypeScript/TSX and Kotlin structural parsing. CI installs these optional parsers; the dependency-free suite skips that integration when absent. Structural tests cover incremental caching/deletion, ambiguity, comment/string negatives, syntax failures, missing parsers, scope/budgets, and CLI/MCP. Workbench tests verify navigation and stale structural pack rejection.

## Repeated improvement checkpoints

Use [the Ralph loop](RALPH-LOOP.md) for bounded, agent-driven improvement passes.
Run `python3 scripts/ralph_checkpoint.py` in this development checkout to execute
all existing quality gates and bind the outcome to before/after source hashes.
Untracked source is included. A failed, unavailable, timed-out or changed-source
run cannot be a passing checkpoint. Logs and records remain in ignored,
owner-private `.context-engine/ralph/`; they are local diagnostics and must never
be sent as vendor usage reports. The runner installs nothing and does not commit,
reset, launch agents or approve knowledge. POSIX process groups contain timed-out
checks; Windows users should use the ordinary quality command until equivalent
process-tree containment is implemented. A checkpoint is evidence, not a backup.

Backend upgrade acceptance is documented in [BACKEND-UPGRADES.md](BACKEND-UPGRADES.md).
`tests/test_runtime_identity.py` simulates legacy/foreign index writers without
source drift and a real Python process whose backend files are replaced while
loaded. Packaging must preserve the engine build identity across source and bundle.
