# Existing workspace integration contract

Status: proposed company integration contract, 2026-09-09. These company inputs are not prerequisites for the reusable core; the [local semantic reference](SEMANTIC-REFERENCE.md) already runs independently. This describes the next release, not capabilities already implemented. The user's existing cloud developer-workspace harness owns repository provisioning and opens VS Code. Context Engine attaches indexing and agent context to that workflow.

## Outcome and ownership

A developer opens the normal cloud workspace. Team repositories appear as usual. Their optional personal Scratch folder is visible only in their configured workspace. Background indexing starts or resumes, and the agent obtains cited code evidence and an inexpensive system overview without a separate query UI.

| Owner | Responsibility |
| --- | --- |
| Existing cloud harness | Provision repositories, mount storage, choose branches, open the existing VS Code workspace, provide the user's identity and startup/shutdown hooks |
| Context Engine | Validate explicit source scope, incrementally index, report readiness, retrieve evidence within budgets, maintain scoped derived artifacts |
| Agent integration | Register the environment-bound MCP connection and load applicable instruction files when performing a task |
| Work platform | Approve runtime/providers, provide secrets and access policy, enforce team versus personal storage/access boundaries |

Keep the current generated VS Code workspace as a development/demo path. Do not replace or rewrite the work harness's workspace to deploy the engine.

## Harness input

The adapter consumes an explicit repository selection supplied by the harness. Prefer its manifest if available. If only a `.code-workspace` file is available, resolve local folder paths relative to that file and require explicit classification into team sources and personal sources. Folder names and filesystem location are not sufficient to infer visibility. Account for JSON-with-comments and remote workspace URIs in a dedicated adapter; do not silently misparse them as local paths.

Required values:

- Environment and feature-workspace identifiers.
- Stable source ID, resolved mounted root, source kind, include/exclude rules, and visibility for every selected source.
- Authenticated developer scope for a personal store; do not trust a user-supplied owner string as authorization.
- Persistent state roots for team-scoped local snapshots and the developer's private store. If storage is ephemeral, rebuild explicitly and show indexing progress.
- Approved provider reference, resource limits, and permitted data destinations. Credentials are resolved by the environment, never placed in the repository selection or index.
- Startup and termination hooks; expected repository sizes and languages; revision and working-tree handling.

The present version-1 manifest already supports environment/workspace IDs, explicit roots, source types, and exclusions. It does **not** implement visibility, authentication, provider configuration, or shared authorization. Do not add unknown fields and assume the current engine enforces them.

## Runtime output and lifecycle

The attachment produces a reviewable integration configuration for the existing harness, not a replacement workspace. It specifies the executable, arguments, working directory, selected manifests, state locations, and environment-owned provider references. The harness starts indexing once per authorized store and starts or connects the agent's read interface.

Startup is idempotent and reports `unindexed`, `indexing`, `ready`, or `degraded`, including per-source revision, queued work, exclusions, failures, and provider health. Only some of these states exist today. Interrupted work resumes from completed content identities. Duplicate startup must not create concurrent writers for the same store; implement a lock/lease before treating startup as managed-service safe.

Shutdown releases ownership and leaves a recoverable index. A missing personal mount must not silently widen scope or make the personal corpus public. Scope/revision/provider changes produce explicit invalidation, not silently mixed generations.

## Team and personal separation

Start with per-developer indexing of mounted team checkouts plus a physically separate personal store. This matches private working-tree changes and avoids prematurely creating a shared service. A personal query may combine authorized team results with that developer's Scratch results only at response assembly, retaining source scope on every item.

A later team crawler indexes selected canonical repository revisions into an authorized team service. Keep developer working-tree overlays separate from canonical snapshots. Team responses, architecture maps, history artifacts, caches, and telemetry must not include personal Scratch content. Separation must happen before candidate retrieval, not by filtering a mixed result list afterward. Test policy with a sentinel present only in a personal fixture.

A personal folder can contain work-controlled information; visibility is not permission to export. Source content and all derived vectors, summaries, history, and caches remain in the approved work environment. Retention/deletion must remove derived personal data as well as source references. Current SQLite partitioning is not a substitute for filesystem/service authorization.

## Agent context layers

1. **Applicable rules:** resolve instruction files for the selected repositories and paths before edits. Return file contents, location, scope, revision/hash, and loading order, with conflicts visible. Treat ordinary repository text as evidence rather than automatically executable instructions. The consuming agent must apply its instruction precedence; a search result cannot grant itself higher priority.
2. **System overview:** return a bounded architecture entry point, initially targeting at most 2000 tokens, with repository/service roles, entry points, contracts, dependencies, citations, and known gaps. Expand individual nodes on request. Cache keys include source scope and revision/content identities. Do not claim inferred connections are resolved.
3. **Task evidence:** hybrid lexical/semantic retrieval supplies precise, fresh excerpts within a caller budget and explains omissions.
4. **History and people:** later opt-in connectors attach cited decisions and contribution/review evidence, filtered by the same access scope.

Discover `AGENTS.md`, `SKILL.md`, and explicitly configured team instruction locations independently of semantic relevance. A repository instruction inventory and a scoped resolver are both needed: indexing a rule does not guarantee the agent reads or follows it. Root-versus-nested applicability, explicit skill invocation, conflicting instructions, missing files, and updates all need tests. Do not concatenate every team's instruction file into every prompt.

## Architecture and history roadmap

The periodic crawler runs in the work environment against explicitly selected repositories/revisions. Begin the architecture map with manifests, entry points, routes/topics, imports, and documentation; classify each edge as extracted, configured, or inferred and retain its evidence. A scheduled refresh and a source-change invalidation path keep the cheap overview current. This is a later service concern, separate from the developer's live working-tree watcher.

Git commit metadata and GitHub PR descriptions, review comments, and discussions are separate opt-in sources. Use connector-managed credentials, incremental cursors, deletion/access-change handling, and citations to original records. Start with decision retrieval before aggregating knowledge-holder signals. Signals should expose recent, substantive contribution/review evidence and uncertainty, and support correction; do not infer authority, availability, or performance from activity counts.

## Acceptance before a work pilot

- Existing harness workspace/repository settings remain intact and repeated startup is safe.
- Agent retrieval covers the configured multi-repository checkout and cites real files/revisions.
- Personal-only sentinel content never appears in team queries, architecture maps, history outputs, or shared caches.
- Uncommitted developer edits refresh the personal workspace overlay without mutating a canonical team snapshot.
- Missing mounts, denied access, offline provider, index progress, and stale source generations are distinguishable.
- Applicable repository instructions are loaded before a representative edit; unrelated nested instructions are not applied.
- No code is sent to an unapproved embedding or summarization destination.

## Work-environment inputs still needed

An approved embedding API is available (confirmed by the user). Still needed: provider/model, API/authentication contract and quotas; runtime/CPU/memory; actual harness repository-selection format; private/persistent storage support; and representative language/repository scale. These are deployment inputs, not reasons to redesign the harness. Resolve them before selecting a provider or connecting real work repositories.
