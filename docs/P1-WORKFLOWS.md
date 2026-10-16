# P1 workflows: local retrieval and maintained knowledge

Implemented 2026-09-11. These increments add no runtime dependencies, remote model calls, uploads or automatic Git synchronization. The VS Code sidebar and portable core share the same behavior.

## Representative evidence evaluation

**Run synthetic benchmark** now includes `p1-evidence-1`. For development, `python3 evaluate_p1.py --output /tmp/p1.json` runs the same expanded evaluation, and `scripts/check.py` includes it in the quality gate.

The generated corpus has 120 distractors, Python and ambiguous Kotlin symbols, two indexed repositories and a third excluded source. It compares literal discovery or a manual three-tool change sequence with compact retrieval at equal sequence byte budgets. Cases cover identifiers, cross-repository contracts, missing answers, scope isolation, Kotlin ambiguity and a change requiring an approved practice's exception. Additional checks cover real A→B→A Git branch switches, stale code/guidance, refresh recovery and deletion.

Output contains fixed synthetic case names, evidence-task pass/fail, current citation checks, calls, complete response bytes, three-run p50/p95, cold/warm/branch indexing times, cache computation counts, SQLite store size and Python traced peak memory. Three-run p95 is just the largest sample; native allocations are not measured. No model is invoked: actual tokens and model task completion are explicitly unavailable. These fixtures provide regression evidence, not independent production validation. The development/held-out labels separate task compositions; after public use the challenge cases are regression cases, not a permanently unseen dataset.

A missing Kotlin parser fails its case; run with the approved navigation dependencies to verify it. The benchmark creates a closed synthetic scope and never evaluates or exports the selected company repository. Synthetic results are distinct from the strict client usage-report schema.

## Change context brief

Choose **Prepare change context brief**, then the source ID and a commit/branch (default `HEAD`). The engine compares that commit with tracked working-tree content, including staged changes. It never stages, commits or posts anything. Untracked files are excluded. Deleted/excluded files have no current evidence and count as omitted paths.

The result includes current source around changed hunks, enclosing chunk symbols, inferred test snippets mentioning those symbols, applicable approved guidance for the review task, and classified one-hop graph evidence. Each category explains its selection. Guidance retains exceptions and structured decision details; human rationale and wiki prose remain outside the agent projection. No caller/compiler completeness or review verdict is implied.

Limits: 12 current indexed changed paths, 3 hunks per path, up to 8 enclosing chunk symbols per hunk, 2 test snippets per selected symbol (up to 8 symbols per path for test lookup), 3 graph neighbors per path, bounded Git output and a 15-second timeout per Git operation. Results report skipped paths, known upstream omissions and final packing omissions. Candidate scans are capped; those counts do not enumerate every potentially relevant item in the repository. At small budgets whole items may be omitted; this is not proof that all rules were delivered. Refresh stale sources before trying again. No automatic refresh or source collection occurs.

Portable entry points: internal `change-brief --source api --base HEAD --byte-budget 6000`; read-only MCP `get_change_brief` with source/base and the normal byte/task-budget options. The core remains usable independently of VS Code. This does not establish end-user CLI support as a new client workflow.

## Assisted review-lesson inbox

**Refine imported review lesson** groups imported events with exactly matching whitespace-normalized text and path. It shows distinct PR counts, not a vote or authority score; repeated comments in one PR count once. At most 100 groups are shown. This is deterministic grouping, not semantic duplicate detection or automatic consensus.

The draft selects a sentence containing a review-guidance cue when available. It remains marked `DRAFT:`. The UI asks the maintainer to refine the statement, choose applicability and consider an exception. It preserves the selected event's provenance and indexed supporting citation. Save/import the draft through the existing proposal command, then approve separately. A group does not create multiple provenance guarantees: the selected event is the draft's origin, and its edit/removal invalidates that origin as before.

No model extracts policy. A quoted suggestion is untrusted review evidence, not an approved rule. Rationale belongs to human review, while the agent gets the concise approved statement. Decision templates also include an optional `details.revisit_when` list; older decision records remain valid.

## Commonplace editing and review

**Open local Commonplace** now creates `edit.json` alongside the existing `records.json` history snapshot and wiki. `edit.json` contains the latest revision of each record in entries with `base` and editable `record` fields. Keep `base` unchanged; edit only the record. For a new ID, add an entry with `base: null`. Omitted entries do not delete existing knowledge. Do not edit status/revision into a record; those are controlled by review.

Choose **Preview and import edited records**, select `edit.json`, inspect the displayed before/after changes, and confirm import as proposals. Preview compares every base against current local knowledge. The import token covers both the complete file and the current record state, and is checked again under the writer lock. Divergence or a changed file requires a new preview. Validation and authorization precede a single transaction, so a failing batch does not partially import. Limits are 2 MiB and 100 entries per import.

Import never approves, retires or deletes guidance. Existing approved revisions remain active until a new proposal passes the existing review/freshness checks. Review provenance must already exist locally; importing a file does not fetch its PR evidence. SQLite remains the local authority and generated views derive from its records. A separate checkout can import explicitly rebased new proposals after validating source mappings; this is not an automatic merge or cross-user approval transfer.

Use an already-local company repository if desired. Git branches/PR review can surround this file workflow, but cloning, committing, pushing, pulling and shared authenticated approval remain outside this increment. Scratch exploration and transcripts are not automatically imported into Commonplace.

## Bounded chunk artifact reuse

Parsing now caches successful chunk artifacts within the existing scoped SQLite store. Keys include source/path, content hash, complete chunker identity and an artifact-format version. Retrieval indexes still contain only the current scoped files; a cache hit never admits another branch's evidence. Optional parser errors are not cached. Semantic vectors retain their existing provider fingerprint and current-content pruning; this increment does not add cross-branch vector retention or an ANN dependency.

The chunk cache retains at most 16 MiB of serialized artifact payload and expires entries unused for 30 days, pruning during indexing. SQLite overhead/free pages can make the database larger than that payload cap. Previous branch content can remain in this client-local cache until pruning; deleting the scoped store removes it. No shared vendor cache exists. Parsing format changes must bump the artifact version. Index metadata reports hits and computations, including zero computations on an unchanged refresh.


## Verification checkpoint

The quality gate passed on Python 3.13.15 and Node 24.21.0, including the 100-test Python suite (two optional skips), all evaluation gates, and 29 extension tests. The final focused P1 suite passed 10 tests, including the added symbol/test-candidate check. See [synthetic measurements](../evaluation/p1-evidence-2026-09-11.json) and [build receipt](../evaluation/p1-verification-2026-09-11.json). No live corporate data, GitHub access, model inference or new native VS Code host run was involved. The local VSIX was rebuilt, not installed or published.
