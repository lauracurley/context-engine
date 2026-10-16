# Launch workflows — 0.6.0 alpha candidate

All five knowledge types now use a shared local record and two reader-specific projections. This candidate adds conventions, decision relationships, operations, GitHub review candidates, local reviewer policy/audit and a navigable static wiki. It does not establish client IT approval, live GitHub access, or a shared authenticated approval service.

## Authoring and use

Use **Team knowledge** in the workbench for the everyday flow: browse/filter records, choose an indexed supporting file, fill in a guided proposal, inspect its source, and approve/reject/retire the exact revision. All five kinds have forms. Saving does not approve. A stale record can prepare a re-review draft after refresh; replacing citation hashes never validates the conclusion by itself. A statement beginning `DRAFT:` cannot be approved. Conflict errors preserve the open form so edits can be reapplied to the latest revision.

Use **Show advanced actions** for JSON import, review provenance, additional citations, cross-record relationships, local Commonplace snapshots, static wiki and audit. Imported records still become proposals. Revision/audit records are company-local data, never usage feedback. See the [alpha acceptance checklist](ALPHA-ACCEPTANCE.md) for the supported first session.

| Type | Structured material mirrored to agents and humans |
| --- | --- |
| practice / architecture | Existing reviewed statements, rationale for humans, scoped citations |
| convention | `languages`, `tasks`, `exceptions`, optional `details.examples` |
| decision | Required `details.alternatives` and `details.tradeoffs`; exact `supersedes` and `conflicts` references |
| procedure | Required `details.prerequisites`, `steps`, `diagnostics` (`if`/`then` objects), `verification`, `rollback` |

Language/task lists and exceptions are available on every type. Empty applicability lists mean unrestricted. Agent lookup accepts explicit `language` and `task`; common language names are inferred from file extensions when possible. Task-restricted guidance is omitted unless the task is supplied. Use `record_id` for a specific approved record, still subject to scope, applicability and freshness. Instructions/procedures are retrieved evidence, not authorization to run their actions.

Relations are arrays such as `[{"id":"previous-decision","revision":2}]`. Cross-record supersession requires an active approved exact revision with identical source, type, prefix, language and task applicability. It atomically replaces that revision; a different scope must be handled explicitly by a reviewer. Supersession cycles are rejected. Declared active conflicts block approval unless resolved by explicit supersession or retirement. Semantic contradictions that authors did not declare are not automatically detected; human review remains required.

Records are bounded to 24 KB. Agent responses pack complete records, including exceptions and procedure safety fields, or report them omitted; they never truncate a rule or omit only rollback steps. Increase the byte budget, target an ID, or split oversized records. Human rationale is excluded from agent lookup; material constraints belong in the canonical statement/structured fields, not only rationale.

**Human knowledge wiki** now opens a script-disabled webview with an internal table of contents and a bounded static architecture diagram. Choose All for a combined view or a section. Arrows are extracted/inferred relationships, not proof of runtime dependencies. Authored HTML and external links are displayed as text, and a restrictive CSP prevents remote resources. This is a local reader, not a hosted collaborative wiki. `.context-wiki` remains excluded from source indexing.

## GitHub review loop

1. IT approves GitHub access and the exact repository. Configure an explicit `sources[].github` owner/repository in the local manifest and the same mapping in the administrator review policy. Both source and repository must match; no discovery across an organization occurs.
2. **Fetch GitHub review candidates** checks local permission first, then asks for a PR number and a client-approved token with **Pull requests: read**. The token is password input, passed only to the short-lived fetch process environment, and never stored in application state, argv, reports or logs. The OS process owner can inspect process memory/environment; this is not secret isolation from the local user. Use short-lived, repository-restricted tokens. No tokens/accounts were accessed during development.
3. The importer issues only GET requests to `api.github.com`, using API version `2026-03-10`. It reads review summaries and review comments for that PR, at most ten pages of 100 per endpoint and 8 MiB per response. Redirects are refused, network/status failures are generic, and an incomplete fetch does not store a partial batch. There are no POST/PATCH/DELETE requests, no automatic retries or background polling.
4. Events are normalized and deduplicated by source/repository/event identity and content fingerprint. Raw diff hunks and token values are not stored. Review bodies, authors, commit references and paths **are company-local knowledge data**, not telemetry. On a successful complete re-fetch, removed events are removed locally; edited/removed provenance causes dependent guidance to be withheld. Remote freshness is only known as of the last manual fetch, not continuously verified.
5. **Refine imported review lesson** shows a full local event and opens a candidate template with its provenance plus a current indexed supporting citation. It deliberately leaves the statement as a draft for human generalization; no model extracts rules or automatically changes policy. The initial rationale can be shorter than a long comment; inspect the full event before editing. Save/import the refined proposal, then review and approve it through the normal workflow. Re-importing unchanged events does not create duplicate rules.

An internal operator can also import a bounded normalized event JSON array through `knowledge github-import --source ... --file ...`, subject to the same administrator permission. This is a company-local offline route; imported provenance is asserted by the operator, not authenticated by a live API call. Do not send review exports to the product vendor. For large histories, use explicit smaller batches/PRs rather than broad collection.

No additional third-party library or GitHub CLI dependency was introduced: the transport uses Python's standard HTTPS stack. Client acceptance must still validate token permissions, TLS/proxy setup and repository access on the managed Mac. GitHub Enterprise Server hosts are not enabled by the fixed github.com transport and require a separately approved host configuration.

Primary API references consulted: GitHub documents the list-review endpoint, read permission and pagination [here](https://docs.github.com/en/rest/pulls/reviews); review-comment endpoints are [here](https://docs.github.com/en/rest/pulls/comments). The implementation does not use their write endpoints.

## Local review governance

Set machine-scoped `contextEngine.reviewPolicyPath` to an absolute **root-owned, non-group/world-writable** policy file, outside repositories. IT can use `examples/review-policy.example.json`, replacing numeric OS user IDs, source IDs and repository mappings. Keep `allow_github` false until approved. Generated agent workspaces carry the policy path; no approval, import or audit tools are exposed over MCP.

The policy checks local process UID against author/reviewer lists and source scope. Audit events record UID, action, record/revision and UTC time, with a chained digest to detect accidental/telltale edits. This is **not** proof of a human click, tamper-proof auditing, or protection from an administrator/store owner who can rewrite the chain. An agent running as the same OS user has that user's process identity. MDM/file/launch controls must enforce the application's configuration; clearing an optional policy setting is not prevented by the library itself.

The supported alpha topology is one company-controlled private local store and its OS user. **Local maintainer review is sufficient; an absent optional review policy does not block readiness.** If the client chooses to install a policy, its configured author/reviewer rules apply. `separation_of_duties: true` requires a different reviewer, but the current private store does not provide a cross-employee approval service; readiness flags that unsupported topology. Shared SSO or approval hosting is outside this alpha and is not a prerequisite. Legacy proposals without an author cannot bypass an explicitly configured independent-review rule.

## Retention, recovery and release acceptance

Knowledge records, superseded revisions, audit events and imported review bodies remain in the company-controlled state root. Index reset preserves them; retiring a rule does not erase its history. For full offboarding, close the extension/agents, remove the approved state roots and their backups under client IT policy, and include saved drafts/wiki copies/editor backups. Usage reporting stays in a separate release-specific numeric store, disabled initially; none of the new content/identities enters it. No new metric categories or uploader were added.

The one-click synthetic benchmark now exercises proposal withholding, approval and both projections for all five types, as well as existing retrieval/Kotlin/stale-recovery checks. It uses only temporary invented data, disables ambient review policy inside that synthetic scope, and does not validate client permissions or make GitHub requests. Real token/role/provider/fresh-Mac tests remain separate acceptance tasks.

Retain the previously reviewed package as a separate artifact. Schema additions are additive, but old code does not understand new kinds/relationships/governance. Do not reopen the same state with an older build as a supported rollback; use a separate approved state root, or disable the pilot until a corrected release is available. No client deployment has been performed.
