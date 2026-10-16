# Human wiki and agent knowledge — initial 0.4.0 implementation

The remaining local-workflow slices are implemented in 0.5.0; see [the current workflow guide](LAUNCH-WORKFLOWS.md) and [acceptance gates](security/LAUNCH-ACCEPTANCE-0.5.md). The backlog below is historical.

Review practices and architecture now share company-local, versioned records. Humans read an on-demand Markdown wiki with rationale and evidence. Agents use `lookup_knowledge`, which returns only approved, applicable statements, scope, revision and citations within a whole-response byte budget. It omits human explanations. The architecture wiki also renders the existing extracted system map, shared with `get_system_overview`; inferred links remain labeled as inferred.

## Author and review

1. Index authorized local sources. Supporting evidence must be an indexed file with its current content hash. For a manually captured review lesson, put the approved review note in a company-controlled source; no GitHub ingestion or comment-to-rule automation is implemented in this slice.
2. Prepare a JSON proposal using the shape below. Use a stable ID for one practice/decision. `prefix` is an exact file or directory subtree; empty means the entire specified source. Supply each repository's scope separately. `statement` is the concise canonical guidance; `rationale` explains it for humans. Do not create two independently authored versions of the statement.
3. In the sidebar choose **Import knowledge proposal** and the latest revision (0 for a new ID). This creates an immutable proposed revision and does not change agent guidance.
4. Choose **Review knowledge proposals**. Inspect the statement, rationale, scope and cited evidence and check for conflicts with other approved records. Approve or reject explicitly. Approval fails if evidence changed, the index is not ready, or a newer proposal exists. Approving a replacement supersedes the previous approved revision of that ID. A pending/rejected revision leaves the old approved record active. Retire an approved record to withdraw it.
5. Choose **Human knowledge wiki**, section and source ID. Both curated sections are rendered on demand. Agents retrieve practices with `lookup_knowledge(kind="practice", source="api", path="src/file.kt")`, and architecture decisions with `kind="architecture"`. Use `get_system_overview` for the structural map and bounded graph tools for relationships.

```json
{
  "id": "regression-coverage",
  "kind": "practice",
  "source": "api",
  "prefix": "src",
  "title": "Regression coverage for fixes",
  "statement": "Add regression coverage for each behavior-changing bug fix.",
  "rationale": "Explain the team's approved reasoning, examples and exceptions here.",
  "citations": [{"source": "api", "path": "docs/review-practices.md", "hash": "REPLACE_WITH_CURRENT_64_CHARACTER_FILE_HASH"}]
}
```

For architecture records use `kind: "architecture"`, e.g. a boundary/ownership decision with supporting design or source citations. Exact fields are validated; IDs are lowercase letters/digits/underscore/hyphen, and text/citation counts are bounded. Human review decides whether evidence actually supports a claim; a matching hash only establishes file freshness, not truth. No semantic conflict detector is claimed. Conflicting records under different IDs require human resolution, and the agent response says so.

## Storage, retrieval and lifecycle

Records live in the selected private SQLite store, separate from source search tables and usage aggregates. Approved retrieval uses a status/kind/source expression index, filters scope/query, checks evidence freshness, and packs complete records without cutting a rule mid-sentence. Omitted records and stale counts are explicit. A rule that does not fit the budget is omitted, not silently truncated. MCP task byte accounting applies. Propose/approve/reject/retire are not MCP tools; those operations are local UI/operator actions, not an identity-enforced approval system.

The wiki is an unsaved Markdown document, never automatically written to indexed sources. If saving a local wiki copy, use the reserved `.context-wiki` directory, which the scanner excludes. Generated MCP instructions direct agents to compact knowledge tools, not wiki prose. Copies saved elsewhere can still be indexed; exclusion is not a filesystem access-control boundary.

A changed/deleted/excluded supporting file withholds the record from agent retrieval and marks it stale in the human wiki. Reindexing alone cannot reapprove an obsolete citation: create a new proposal with updated evidence. Index reset preserves curated knowledge and its review history, while withholding it until evidence is indexed and current again. For complete removal, follow the client offboarding procedure for the whole approved state root. Changing manifest scope may select a different store; no automatic cross-company migration is performed.

The schema is additive. Keep 0.3.0 and 0.4.0 artifacts separately; earlier releases ignore the new knowledge table. Do not treat rollback as an approved client deployment without repeating release checks. The 0.4.0 usage aggregate directory is release-specific and starts disabled, preventing old measurements from being relabeled. Older aggregate directories remain subject to the documented local cleanup process. Knowledge content never enters usage reports; the new lookup operation is not instrumented in the existing six-operation metric registry.

## Launch backlog

These first two slices do not complete the requested launch scope. Remaining paired layers: broader team conventions, decision records with explicit supersession relationships, and operational/troubleshooting procedures. Also remaining: GitHub review ingestion with provenance and candidate extraction; reviewer identity/permissions where required; richer conflict review; wiki navigation/diagrams beyond the current readable structural summary; independent company acceptance. Add these deliberately without automatic promotion of comments or exports of company knowledge.
