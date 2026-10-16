# Open-source feature comparison

Reviewed 2026-09-09 against project documentation, with local behavior verified separately. This is a capability comparison, not a benchmark against these projects.

The supplied [Medium article](https://medium.com/@wangxj03/semantic-code-search-010c22e7d267), also available on the [author's blog](https://wangxj03.github.io/posts/2024-09-24-code-search/), links to [wangxj03/ai-cookbook/code-search](https://github.com/wangxj03/ai-cookbook/tree/main/code-search). Its core flow is AST-aware chunks, embeddings, a Qdrant index carrying file/line metadata, semantic snippet search, and full-file retrieval through a FastAPI/browser application.

| Article/demo capability | Context Engine implementation | Gap or distinction |
| --- | --- | --- |
| AST/token chunking | Built-in Python AST; optional same author's `code-splitter==0.1.5` bindings, tested on real Rust input | Optional bindings cover four languages; other files use windows |
| Embedding ingestion and semantic search | Provider boundary, optional local cached model, persisted vectors; lexical and hybrid modes too | Different model; quality parity not established |
| File/line metadata with search results | Source, path, lines, hash, revision and method citations | Current-code freshness is explicitly checked |
| Fetch selected file content | `read_code` / CLI `read`, paginated ranges with optional expected hash | No dedicated REST full-file endpoint |
| Vector database | Scoped SQLite persistence and exact vector scoring | No Qdrant/ANN scaling |
| Search application | MCP and CLI | No browser search UI or FastAPI server |

This covers the principal agent workflow—index, search, inspect cited code—to a useful local degree. It does not establish equivalent scale, latency, or retrieval accuracy.

Other primary-source inspirations:

| Project | Relevant functionality | Adopted here / remaining gap |
| --- | --- | --- |
| [Aider repository maps](https://aider.chat/docs/repomap.html) | Symbols/signatures and graph-ranked compact repository context | Cited bounded architecture map, dependency-degree ranking and node expansion; no equivalent graph-ranking algorithm claimed |
| [Serena](https://github.com/oraios/serena) | Language-server-based symbol navigation and reference lookup | Symbol outlines and targeted reads; precise LSP references and refactoring remain absent |
| [Zoekt](https://github.com/sourcegraph/zoekt) | Trigram-based code search and indexed substring/regex queries | Literal/regex search, scope/path filters and periodic Git refresh; no trigram index, full query language, or throughput parity |
| [Code Search Please](https://github.com/pleaseai/code-search) | CLI/MCP retrieval, snippet controls, content filters and related-code discovery | Compact previews, location-only responses, content filters and similarity discovery; no adoption of its benchmark claims |
| [CocoIndex Code](https://github.com/cocoindex-io/cocoindex-code) | Incremental semantic code indexing with agent-facing search | Content-identity reuse and explicit/periodic refresh; no equivalent dependency-tracking framework |
| [code-splitter](https://github.com/wangxj03/code-splitter) | Structure-aware chunking with Python bindings | Optional pinned integration; missing dependency falls back visibly |

The next quality milestone should use representative, approved multi-repository tasks: compare compact and verbose retrieval for answer correctness, relevant-file recall, actual model tokens, and end-to-end latency. Include negative questions, changed/deleted code, unavailable sources, and multilingual navigation. Current public fixtures establish mechanics and payload savings only; existing semantic evaluations already expose ranking and abstention limitations.
