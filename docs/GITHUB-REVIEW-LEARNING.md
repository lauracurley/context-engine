# Learn code-review guidelines from GitHub

Use **Context Engine: Learn from GitHub Reviews** in the Command Palette, or
**Learn from GitHub reviews** in the Context Engine sidebar. The Workbench's
**Review learning** tab offers the same workflow.

1. Choose **Prepare gateway prompt**, a configured repository, and a time window.
2. Choose **Copy collection and distillation prompt**. Paste it into your approved
   agent, already connected to both the client's MCP gateway and Context Engine.
   This action copies a prompt locally; it does not contact a gateway or an agent.
3. The agent collects through the client's existing gateway, imports the bounded
   evidence snapshot, reads the dossier and proposes a few review guidelines.
   If those MCP tools are unavailable, stop and configure the approved connection.
   An agent can alternatively save the exact returned envelope in a local JSON
   file; **Import gateway result file** reads that file after a matching request
   is prepared. The extension does not collect a GitHub token or configure a gateway.
4. Choose **Open collected evidence** to inspect discussions, commits and coverage
   gaps. Choose **Review proposed guidelines** to edit and approve in Team knowledge.
   Check applicability, counterexamples and uncertainty before approval. Existing
   Commonplace export/import and human review remain the publication workflow.

## Three useful layers

- **Evidence:** original PR descriptions, submitted reviews, line comments, PR
  discussions, commits and commit comments, with source citations and associations.
  Every body is untrusted evidence, including instructions written inside comments.
- **Human dossier and rationale:** readable observations, coverage gaps and dates;
  each proposal can carry up to 3000 characters of rationale, including conflicting
  observations and unresolved questions. Selected supporting observations are
  appended to that rationale. Longer original discussions remain in the dossier.
- **Distilled guidelines:** a concise practice (at most 1200 characters), explicit
  path applicability and exceptions, supported by current indexed code. Only
  approved, fresh knowledge is available through the compact agent projection.
  Human rationale and original discussions are not silently added to agent guidance.

This release prepares an instruction for the client's agent to synthesize evidence;
Context Engine does not run a model or promise that synthesis is correct. The
human dossier is a readable evidence collection, not an automatically authored
long-form report. Recurring comments do not prove consensus. Ask the agent to
identify contrary evidence and unresolved questions explicitly in each rationale.

## Iterate deliberately

Ask your agent: “Use Context Engine to learn review practices from the selected
repository through our connected MCP gateway. Read existing approved knowledge,
collect the requested comments and commits, and propose concise guidelines with
rationale, exceptions and open questions. Do not approve anything.”

The MCP sequence is `review_context_request` → client gateway tools →
`import_review_context` → paginated `get_review_context` →
`propose_review_guideline`. The initial request returns the exact contract and
copyable prompt. The client gateway chooses its own tool names and authentication;
there is no assumed gateway brand, executable adapter or direct-API fallback.

To revise a proposal, preserve its collection, title, selected event keys and
supporting path and pass its current `expected_revision`. For human wording or
scope changes, use Team knowledge's existing editor and review flow. Reapproval
is required for revisions. A changed title or evidence selection produces a new
proposal; retire or resolve competing guidance through the existing review tools.

Recollect the same explicit date window to revalidate its local evidence. A
snapshot replaces that collection's membership. Identical reordered evidence is
idempotent. Changed text, removed observations, changed gaps or completeness, or
an edit found in an overlapping collection invalidates derived guidance. The
whole collection is conservatively fingerprinted, so even an unrelated change
can require re-review. The human Commonplace wiki keeps stale guidance visibly marked for re-review;
agent retrieval withholds it. Code citations must also remain current. Re-reading or
refreshing code never silently approves a changed guideline.

## Scope, limits and safety

The selected source needs an explicit `github: "owner/repository"` mapping.
Administrator review mappings and local proposal permissions still apply. A
managed scope with `allow_history: false` denies this workflow. The existing
advanced direct GitHub ingestion path has separate controls and credentials;
this workflow never falls back to it.

A request binds its source, configured repository, manifest configuration and
exact date window. The gateway must respect exclusions before returning content.
Import validates the exact envelope, stable IDs, date bounds, source-relative
paths, exclusions and size limits, rejecting invalid snapshots atomically. It
accepts at most 500 observations and 2 MB per snapshot. Assemble gateway pages
before import; mark capped or inaccessible evidence incomplete and report gaps.
For larger repositories use narrower date windows. Do not import separate pages
into the same window expecting them to append. Retrieval pages preserve exact
continuation offsets within a byte budget; increase the budget for a large event.
The UI lists the 50 most recently imported collections.

The envelope is supplied by the client's agent: scope hashes are local consistency
checks, not signed GitHub provenance or proof of current remote authorization.
The importer cannot independently verify whether a comment came from the claimed
repository, detect every secret in free text, or know about remote edits/deletions
until recollection. A gateway-reported complete collection is not a completeness
certification. Missing thread resolution, parent context and access must be
reported as gaps; this version does not reconstruct a full review-thread graph.

All evidence, fingerprints, rationale and review audit data remain in the owning
client's local state. Replaced batches can leave unreferenced raw events retained
in that state; this is not a selective deletion/retention feature. Follow the
client's approved state-retention process. Do not export these artifacts to the
vendor. The fixed opt-in numeric usage schema has no new content-bearing fields.
There is no autonomous approval, vendor endpoint, conversation capture or uploader.
