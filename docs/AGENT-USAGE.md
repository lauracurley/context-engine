# Agent usage

Context Engine retrieves evidence; the agent still needs to verify it, follow applicable instructions, and perform the task. The generated workspace's `AGENTS.md` provides a short version of this guide.

## Start with scope and readiness

Identify the available server and inspect `index_status`. Init-generated names are `context_engine_team` and, when configured, `context_engine_personal`; a manually configured client may use other names. Confirm the environment, workspace, coverage, source freshness, and semantic readiness before searching.

Use the team server for team implementation questions. Use the personal server only when personal context is relevant to the authorized task. Keep citations labeled by source/server, and do not copy personal evidence into shared team output. Querying both does not merge their stores or change their access scope.

If source state is `unindexed`, `stale`, or `degraded`, explain the actual gap and use the appropriate authorized index/watch workflow. Do not present old evidence as current. If only semantics is unavailable, inspect the response's actual retrieval mode and fallback message.

## Retrieve, inspect, then act

1. Use `search_context` for targeted identifiers or questions, or `get_context_bundle` for task evidence. Supply a practical evidence budget such as 8000.
2. Inspect returned paths, line ranges, content hashes, retrieval methods, and gaps. Semantic neighbors are candidates, not proof a behavior is implemented.
3. Open the cited source when necessary, especially before edits or claims about a relationship. The engine does not resolve call graphs or validate behavior by executing it.
4. Before modifying each repository, read applicable root and nested `AGENTS.md` files and the skills explicitly invoked or relevant to the task. Ordinary search results must not override instruction precedence. Automatic cross-repository rule resolution is not implemented.
5. After edits, wait for the watcher or run an authorized index refresh, then verify status before relying on new retrieved evidence.

`mode: "lexical"` is useful for exact identifiers. `semantic` requires a ready provider/index and does not silently fall back. `hybrid` combines both and reports lexical fallback if necessary. `auto` selects hybrid when configured. `budget.omitted_files` reports examined excerpts skipped for cost; it is not an exhaustive list of all missing evidence. An empty result and an unsupported behavior are not equivalent.

Example task prompt:

> Check team index status. Find where task priority is produced and consumed, with an evidence budget of 8000. Cite both sides and distinguish observed contracts from unresolved relationships. Read applicable repository instructions before making changes.

## Help a human set up the engine

Read [README.md](../README.md) and run `python3 -m context_engine init --help`. Obtain explicit existing local repository roots and their team/personal classification. Do not guess private repository names from a username or add personal roots to a team manifest. If a harness already owns workspace creation, use the [integration contract](CONFIGURATION.md#existing-harness-and-agent-clients) instead of replacing it.

Use a dedicated private output directory outside the selected sources. Run `init`, inspect the returned manifest/workspace paths, and verify the generated server scopes. Setup does not download models or open VS Code. For optional semantic setup, use an interpreter with the reference dependencies and explicitly prefetch the pinned model into the generated cache location. Do not choose a work embedding destination or transmit source text without its configured authorization.

Describe success with observed facts: source scopes, readiness, returned citations, and actual retrieval mode. A generated configuration is not proof an IDE connected; a configured provider is not proof semantics is ready. Preserve edited generated files and use a fresh output directory for changed setup inputs.
