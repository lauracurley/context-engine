# Structural navigation

The engine caches syntax declarations, identifier occurrences, call sites and imports during indexing/crawling. Python uses its standard-library AST. JavaScript/JSX and TypeScript/TSX use optional [Tree-sitter Python bindings](https://github.com/tree-sitter/py-tree-sitter), with the [JavaScript](https://github.com/tree-sitter/tree-sitter-javascript) and [TypeScript](https://github.com/tree-sitter/tree-sitter-typescript) grammars. Source code is parsed, never imported or executed.

Install the pinned parsers into the Python environment that runs the engine, then reindex:

```sh
.venv/bin/python -m pip install -r requirements-navigation.txt
.venv/bin/python -m context_engine --manifest /path/team.json --state /path/state index
```

For an installed VSIX without the repository requirements file, the equivalent install is:

```sh
/path/to/venv/bin/python -m pip install tree-sitter==0.23.2 tree-sitter-javascript==0.23.1 tree-sitter-typescript==0.23.2 tree-sitter-kotlin==1.1.0
```

Set `contextEngine.pythonPath` to that interpreter in VS Code. Parsers are optional and are not bundled or downloaded automatically. Missing/incompatible parsers and syntax errors produce explicit coverage gaps, while lexical search remains available. The pins support the project's Python 3.9 baseline. Reindex after installing/changing parsers: their installed versions are part of the extraction cache identity.

## Retrieval

Use CLI `structure` or MCP `navigate_structure` with these modes:

| Mode | Inputs | Result |
| --- | --- | --- |
| `definitions` | Optional exact `symbol`, `source`, `path` | Function/class declarations and supported JS/TS/Kotlin named declarations |
| `references` | Exact `symbol`; optional source/path | Syntax identifier occurrences; Python loaded names/attributes |
| `callers` | Exact `symbol`; optional source/path | Parsed call sites and their syntactically enclosing declaration |
| `dependencies` | Source and indexed file path | Import evidence and in-source module-path candidates |
| `impact` | Source and indexed file path | One-hop candidate dependents: imports of that file and identifier/call matches to its declarations |

```sh
python3 -m context_engine --manifest /path/team.json --state /path/state structure \
  --mode=callers --symbol=run_queue --source=api --token-budget=8000
python3 -m context_engine --manifest /path/team.json --state /path/state structure \
  --mode=impact --source=api --path=queue.py --limit=50
```

Responses contain exact source/path/line/hash/revision citations. Read selected evidence using `read_code` with `expected_hash`, or CLI `read`. Results are limited to 30 items by default (maximum 100); the default whole-response ceiling is 4000 UTF-8 bytes, despite the legacy `token_budget` argument name. Check `budget.omitted_items`, `limit_omitted`, `coverage`, and `gaps`. Each file caches at most 4000 facts, with truncation counted. Unchanged files are reused and deleted/excluded files are removed at refresh. Stale indexes and extractor changes require reindexing.

VS Code offers **Structural navigation** in the sidebar and Command Palette. Workbench results provide **Definitions in file**, **Dependencies**, and **Impact candidates**. Definition cards also offer **References** and **Callers**. Preview/open citations and pin selected evidence with the existing task-pack actions. Pinned structural results become stale when the index generation changes, including changes in other files. Refreshing such a pin through the existing code-pin refresh replaces it with its current source excerpt; rerun navigation to pin a new structural result.

## Evidence strength and coverage

`classification: extracted` means the parser found the syntax. `resolution: declaration` identifies a declaration, not a resolved reference. References and calls carry `inferred` same-name target candidates (up to five, with omissions counted), or `unresolved` when no declaration candidate is available. Even one matching name is not proof of binding: shadowing, aliases, dynamic dispatch and runtime modification remain possible. No inferred candidate is labeled a resolved runtime call.

Python import path candidates assume a source-root module layout; JS/TS candidates follow relative filenames and index files. These are static hypotheses, not Python import execution or TypeScript/bundler resolution. Dependency matching stays within each source; cross-repository builds and project aliases are not resolved. Unfiltered definition/reference lookup can search all configured sources, but binding candidates remain source-local. Search imported aliases separately.

Python local assignment bindings, JavaScript destructuring/default exports, full overload/type resolution, language-server references, callback dataflow, transitive impact and dependency injection are not fully modeled. JS/TS references are syntactic identifier occurrences, including some declaration/type/import positions; they are not compiler-bound uses. The enclosing declaration is syntax context, not proof that its function executes the call (for example, Python decorators/default arguments). Unsupported files are counted rather than interpreted as having no dependencies. These results help select files to inspect; they do not certify change safety.

## Kotlin support (2026-09-10)

`.kt` and `.kts` use the optional [Kotlin Tree-sitter grammar](https://github.com/tree-sitter-grammars/tree-sitter-kotlin) pinned in `requirements-navigation.txt`. Indexing produces declaration-based chunks plus text windows and caches syntax facts for the existing `navigate_structure` MCP tool and VS Code structural navigation controls. Installing or changing parser versions invalidates both chunk and structural caches on reindex.

Supported syntax evidence includes named classes/interfaces/objects, functions (including suspend and extension functions), properties and primary-constructor properties, type aliases, packages, imports/aliases, identifier occurrences, and simple/member call sites. Citations preserve source line ranges and content hashes. Comments and literal string contents are excluded from structural facts; string interpolation is not analyzed. Malformed or grammar-unsupported files return explicit gaps and retain text retrieval. The parser is not a Kotlin compiler and can reject valid syntax it does not implement.

Import facts retain qualified package names and aliases, but Kotlin import-to-file resolution is not implemented: no filename is invented from a package name. Reference/caller/impact candidates use the same conservative source-local name matching as the existing languages. Overloads, extension receivers, inheritance, Gradle source sets, Kotlin/Java interop, reflection and dependency injection are not compiler-resolved. Constructor parameters without `val`/`var`, destructured declarations, and unnamed companion objects are not exposed as named definitions. These limits apply in all clients.

Configure the extension's `contextEngine.pythonPath` to an interpreter with the pinned parsers, restart the engine and reindex. No Kotlin plugin, JVM, build invocation, or source execution is required. The existing extension consumes the updated core without a separate Kotlin-specific UI.


Verification: the complete quality gate passed on macOS on 2026-09-10: 75 Python tests (two unrelated optional model/splitter tests skipped), 19 extension tests, Ruff/ESLint/format checks, and fixture evaluations. Real Kotlin parser tests cover declarations, imports/aliases, extension/suspend functions, Unicode/backtick identifiers, comment/string negatives, malformed/missing-parser fallback, `.kts` discovery, citations, and incremental edits/deletion. The rebuilt VSIX includes the Kotlin adapter; parser wheels remain optional external dependencies.
