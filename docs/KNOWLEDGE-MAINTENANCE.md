# Local knowledge maintenance and Scratch notes

Implemented 2026-09-11 as a deliberately small P2 slice. No runtime dependency, server, inference service, network call or vendor reporting field was added.

## Maintain local knowledge

In the VS Code sidebar, choose **Maintain local knowledge**, choose a repository and inspect the queue. It shows at most 100 approved/proposed revisions, with stale evidence first, then records with more negative observations. Older approved guidance remains visible when a replacement is proposed. The queue reports omitted records and index readiness separately.

Select a revision and choose **useful**, **wrong_scope**, **stale** or **redundant**. Counts attach to that exact revision; they do not carry forward to its replacement. They are manual observations, not unique voters, usage measurement or a consensus score. Existing local proposal authorization applies when an optional review policy is configured. Feedback never changes retrieval ranking, approval or content automatically.

Counters are company-local SQLite data in the existing scoped store, capped at one million per category/revision. They contain no free-text feedback or user identity, remain until the store is removed, and are not included in vendor usage reports, Commonplace snapshots or agent knowledge projections.

The queue groups exact statement/applicability/exception/detail/relationship matches of the same source and kind. At most 10 other IDs are shown per record. These are review candidates; different evidence or rationale may make separate records legitimate. This is not semantic overlap or contradiction detection. Use the existing proposal, supersession and retirement workflow to resolve redundancy after review. Nothing is automatically merged or deleted.

## Prepare re-review draft

Choose **Prepare re-review draft** for a latest approved/proposed revision after refreshing the source index. The action preserves the statement, rationale, applicability, exceptions and structured details, and updates citation hashes from current indexed files. It marks the statement `DRAFT:` and opens only the editable draft in an unsaved JSON document. The notification supplies the expected revision for the existing import-proposal workflow.

If a replacement was rejected, the active approved record can still seed a re-review draft. Use the notification's expected revision when importing: it includes rejected revisions in the history, so it can be newer than the content revision you selected. A newer live proposal must be reviewed or used as the draft source first.

Updated hashes do not establish that the conclusion is still true. Inspect the changed source and refine the statement and rationale before saving/importing; then approve separately. The original record and both wiki/agent projections remain unchanged until the normal review process completes. A newer revision invalidates the expected revision at proposal time.

Missing supporting files require manually selected replacement evidence. Changed or removed GitHub review provenance requires a new candidate from current review evidence, not automatic hash repair. If the DRAFT prefix would exceed the existing statement limit, shorten the statement manually; content is not silently truncated.

This is a maintenance aid for canonical records. It does not regenerate architectural prose, automatically repair decisions, or create a second authoritative wiki.

## New Scratch reasoning note

**New Scratch reasoning note** opens an empty, unsaved Markdown template with question/constraints, alternatives, experiments, observed evidence, uncertainties, tentative conclusion and reconsideration sections. It reads no prompts, selections, files or conversations. Save it deliberately in the appropriate company-controlled developer Scratch.

Exploration stays in Scratch. Use the existing knowledge-draft/import/review workflow to promote one reusable conclusion with team-accessible evidence, scope and exceptions. There is no automatic selected-note capture, transcript collection, team publication or live collaboration. Human wiki and compact agent projections remain generated from reviewed records.

## Portable entry points

The internal core commands mirror the VS Code actions:

- `knowledge maintenance --source api`
- `knowledge feedback --id rule --revision 1 --outcome useful`
- `knowledge refresh-draft --id rule --revision 1`
- `reasoning-template` (no manifest required)

The first three use the usual manifest/state arguments. `refresh-draft` returns an envelope containing `draft`, `expected_revision` and the review warning; save/import the `draft` object only. These human maintenance actions are not new agent MCP write tools and do not expand end-user CLI support commitments.

## Deferred opportunities

Precise Kotlin LSP navigation, history co-change analysis, new task-aware ranking, semantic reranking, generated wiki text and external requirement/incident adapters need more integration or evaluation. Existing syntax navigation, history search, query-aware overviews, local Markdown sources and reviewed knowledge remain available. ANN/quantization and autonomous multi-agent reviews are outside this MVP increment. See Scratch's P2/P3 decision record for the per-item disposition.


## Verification

The full quality gate passed: 105 Python tests (2 optional skips), all evaluation gates, lint/format and 30 extension tests against the rebuilt VSIX. [Build receipt](../evaluation/p2-verification-2026-09-11.json). No live client data, model inference or new native VS Code host test was used. The package was rebuilt, not installed or published.
