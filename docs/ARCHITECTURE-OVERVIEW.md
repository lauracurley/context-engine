# How Context Engine fits together

Context Engine helps a coding agent find the right parts of a repository and lets people maintain guidance that the agent can trust. It runs next to your code. A VS Code extension provides the human interface; a Python engine indexes selected files, checks whether evidence is current, and serves it through a command line or MCP connection.

The central idea is that an answer should lead back to source. A search result carries a file location and content hash. The agent can then read that location and detect whether the file has changed since it was found.

## Follow one search through the system

Imagine asking an agent, “Where does this project validate a task pack?”

1. The agent calls MCP search with the question and, when useful, a repository or path filter. A person can run the same sort of search from the workbench. The two interfaces reach the same local engine.
2. The engine searches the selected scope. It returns a bounded set of excerpts and source references, along with freshness and coverage information. It does not load every repository file into the conversation.
3. The agent follows a promising reference with a hash-checked read. That expands the relevant code so the agent can explain it or prepare a change. If the source changed, the engine reports that the evidence needs refreshing.
4. When the task requires more context, the agent can ask for definitions, references, related modules, or applicable reviewed knowledge. Each lookup answers a narrower question.

Start with [the CLI and MCP entry points](../context_engine/__main__.py), then follow a request into [search and bounded reads](../context_engine/navigation.py). [The engine](../context_engine/core.py) supplies the configured sources, database, indexing, and freshness checks underneath them.

## The main components and their responsibilities

### The editor is the human interface

[The extension entry point](../vscode-extension/src/extension.js) registers commands, selects a workspace profile, and opens views. [The workbench controller](../vscode-extension/src/controller.js) handles actions such as searching, reading a source, and preparing a handoff. [The browser view](../vscode-extension/media/workbench.js) displays the results.

The extension invokes the Python backend through [its runtime adapter](../vscode-extension/src/runtime.js). This keeps the retrieval engine usable from other interfaces as well as VS Code.

### The index connects selected files to current evidence

[The engine](../context_engine/core.py) scans configured repositories, applies exclusions, and keeps a SQLite store for the scope. Indexing updates the derived data when files change. [Chunking](../context_engine/chunking.py) supplies excerpts; [navigation](../context_engine/navigation.py) turns indexed evidence into filtered searches and bounded reads.

[The crawler](../context_engine/crawler.py) provides scheduled refresh work. [Writer locking](../context_engine/locking.py) coordinates processes that update the same store. A successful refresh describes the snapshot that was observed; it does not guarantee that a checkout will stay unchanged afterward.

### Structure helps you follow the code

[Architecture extraction](../context_engine/architecture.py) records module descriptions, declarations, imports, and other structural signals. [Structural navigation](../context_engine/structure.py) supports more focused questions about definitions and relationships, with language-specific support such as [Kotlin parsing](../context_engine/kotlin.py).

These are evidence for exploration. An import tells you that one file refers to another; it does not tell you why a component exists or prove the order of a running request. The Architecture reading view uses repository documentation to explain those larger ideas and leaves extracted records available for investigation.

### Reviewed knowledge carries team intent

Source code can show what happens, but it often cannot explain why a team chose a design. [Knowledge](../context_engine/knowledge.py) stores proposed and approved practices, decisions, and other guidance with supporting citations. Approval and current evidence determine what is eligible for agent retrieval.

[Commonplace](../context_engine/commonplace.py) supports local repository snapshots of that knowledge. A repository document and an approved knowledge record are different things: showing a document in Architecture does not approve it as team guidance.

### Packs preserve a selection for a handoff

[Task packs](../vscode-extension/src/packs.js) save selected evidence locally. The controller checks that evidence before exporting a pack or preparing a handoff. Packs help people retain a deliberate selection across tasks; agents can also retrieve context directly through MCP without someone collecting pins first.

## Where the boundaries are

A manifest chooses the source repositories and retrieval settings. Different scopes have separate stores. [Deployment policy](../context_engine/policy.py) constrains capabilities and locations; [workspace setup](../context_engine/setup.py) and [IDE configuration](../context_engine/vscode.py) connect the engine to the chosen environment.

Optional capabilities add to this core. [Historical retrieval](../context_engine/history.py) supplies past activity. [Semantic search](../context_engine/semantic.py) uses the provider boundary in [embeddings](../context_engine/embeddings.py). Their availability depends on configuration and policy. In the development dogfooding scope, history, remote Git, and embedding providers are disabled.

The coding agent is a separate consumer of the engine. Its model account, conversation, and decisions are outside this repository's local index. Context Engine supplies evidence; it does not replace the agent or approve the agent's changes.

## Where to make a change

- **Search returns the wrong files:** start in navigation and core; use [retrieval tests](../tests/test_retrieval_efficiency.py) to check filtering, ranking, and response coverage.
- **A reference or relationship is wrong:** start in architecture or structure; use [architecture tests](../tests/test_architecture.py) and [structure tests](../tests/test_structure.py).
- **The interface is confusing:** start in the workbench view and controller; [controller tests](../vscode-extension/test/controller.test.js) exercise the real backend interaction.
- **Guidance appears before approval or after its evidence changes:** start in knowledge; [knowledge tests](../tests/test_knowledge.py) cover review and freshness behavior.
- **Architecture needs a better explanation:** edit this guide. [The human overview builder](../context_engine/human_architecture.py) selects the repository guide and resolves its code references; it does not invent undocumented design decisions.

## Continue reading

For command syntax, scheduled crawling, and extracted graph details, see [Architecture and retrieval reference](ARCHITECTURE.md). For running checks and packaging the extension, see [Development and verification](DEVELOPMENT.md).
