# History ingestion

History collection is opt-in. CLI and MCP call the same `History.ingest` and `History.search` implementation. It stores normalized PRs and commits, full retained messages/descriptions, searchable text, and per-event contribution/review signals in the manifest-scoped SQLite database. It does not invoke a model or send source text to an embedding provider.

An explicitly started [crawler](ARCHITECTURE.md) can also collect history periodically (six-hour default), rebuilding activity summaries. No history collection is triggered by the code watcher. Agent-only gateway tools cannot run unattended: configure the executable bridge for scheduled company-gateway collection, or import agent-fetched batches manually.

## Commands and dates

From the Context Engine checkout:

```sh
python3 -m context_engine --manifest /path/to/team.json --state /path/to/state/team ingest-history
python3 -m context_engine --manifest /path/to/team.json --state /path/to/state/team ingest-history --months 3
python3 -m context_engine --manifest /path/to/team.json --state /path/to/state/team ingest-history --since 2026-01-01 --until 2026-07-01
python3 -m context_engine --manifest /path/to/team.json --state /path/to/state/team search-history 'retry delivery' --token-budget 8000
python3 -m context_engine --manifest /path/to/team.json --state /path/to/state/team search-history 'retry delivery' --kind holder --source api
python3 -m context_engine --manifest /path/to/team.json --state /path/to/state/team history-request
```

The default window ends now and starts six **calendar months** earlier, clamping the day for shorter months. `--since` overrides the starting month calculation. Dates without a timezone use UTC; a date alone means midnight at the start of that date, including for `--until`. Boundaries are inclusive. Search defaults to the last collection's window; supplying search dates selects a custom window over retained records.

| Provider | Behavior |
| --- | --- |
| `auto` | Configured gateway if present, otherwise GitHub; always supplements with local Git |
| `github` | Existing `gh` authentication for github.com plus local Git |
| `git` | Local reachable commits only; no network/fetch |
| `gateway` | Configured executable or supplied normalized `data`/`--input`, plus local Git |
| `import` | Required normalized `data`/`--input`, plus local Git |

There are no credential prompts or login changes. The GitHub adapter uses authenticated, read-only [`gh api` requests](https://cli.github.com/manual/gh_api). A configured gateway is not bypassed with direct GitHub requests when it fails. Missing tools, timeouts, access failures, truncation, and invalid records are reported while preserving accessible results. Collection can take time for large repositories because file and review endpoints are paginated per event. `--max-pages` defaults to 100 per endpoint (100 records/page); local Git is capped at 10,000 commits per source per run. Narrow the time window when necessary.

GitHub repository scope comes from an explicit `sources[].github: "owner/repository"`, or from an origin URL on github.com when the selected source is the **repository root**. Nested local roots only collect their own local path history unless the manifest explicitly selects a whole remote repository. Enterprise GitHub and company-specific identities/API routing belong in the gateway adapter.

## Company gateway contract

The engine does not assume a particular company's MCP names, transport, or credentials. There are two supported bridges:

- **Agent bridge:** `history_request` returns the fixed scope, dates and field contract. The agent queries its connected company MCP gateway, then supplies the resulting envelope to `ingest_history(provider="gateway", data=...)`, using the request's exact dates.
- **Command bridge:** the manifest configures an executable adapter that talks to the company's gateway. Context Engine sends one request JSON object to stdin and reads one response JSON object from stdout. Diagnostics belong on stderr; nonzero exits and the 60-second process timeout produce a coverage gap. The adapter should return partial results within that deadline; use narrower windows/batches for slower gateways. No shell interpolation is used. Command paths should be absolute; execution inherits the engine's working directory and environment. Only configure trusted adapters.

Example manifest additions:

```json
{
  "sources": [{"id": "api", "path": "../api", "github": "company/api"}],
  "history": {
    "gateway_command": ["/absolute/path/company-history-adapter", "--format", "context-engine-v1"]
  }
}
```

This is a fragment to merge into the existing manifest. The executable is supplied by the company integration, not bundled here. `history-request` prints the full request; it includes `schema_version`, `environment`, `workspace`, `since`, `until`, and `sources` containing configured source IDs and resolved repositories. Adapters return:

```json
{
  "schema_version": 1,
  "records": [{
    "source": "api",
    "kind": "pr",
    "id": "123",
    "occurred_at": "2026-06-15T12:30:00Z",
    "title": "Deduplicate task retries",
    "body": "Description and rationale from the original PR.",
    "author": "github:alice",
    "files": ["src/tasks.py"],
    "reviewers": ["github:bob"],
    "url": "https://github.com/company/api/pull/123"
  }],
  "gaps": ["Commit endpoint unavailable; PR descriptions, files and submitted reviewers collected"]
}
```

For commits, use `kind: "commit"`, a full hexadecimal SHA as `id`, the committer date as `occurred_at`, the commit message in `body`, and an empty reviewers array. PRs use current `updated_at`. Use `github:login` for known accounts and `git:Name <email>` for unmatched Git authors. Include submitted reviewers, not requested reviewers. Empty/missing file lists are labeled unavailable in activity summaries. Unknown sources, invalid IDs, unsafe file paths and oversized fields are rejected and reported. Records outside the requested window are skipped. Include an explicit `gaps` array, even if empty; completeness of external results is not independently verified. Limit envelopes to 100,000 records and split larger collections into batches with the same explicit dates.

Import an envelope from disk:

```sh
python3 -m context_engine --manifest /path/to/team.json --state /path/to/state/team ingest-history \
  --provider import --input /path/to/history.json --since 2026-01-01 --until 2026-07-01
```

## Compaction and agent retrieval

Events upsert by source, kind and original ID. Unchanged documents do not rebuild the text/activity indexes. Older PR snapshots cannot replace newer ones. A local-only fallback cannot overwrite a richer remote snapshot. Repeated snapshots with the same timestamp merge available file/reviewer evidence; overlapping imports do not multiply contributions.

`search_history` / `search-history` use SQLite FTS5 over titles, messages, identities and file paths, returning at most 50 items with a conservative serialized-byte evidence budget. Excerpts are deterministic, bounded to 1,200 body characters near a query term, with up to 30 file paths and 20 reviewers. Omission counts, original IDs/URLs, content hashes, provider and observation time accompany citations. Full normalized documents remain in SQLite. This is lexical historical retrieval; semantic code retrieval remains independent.

`kind: "holder"` aggregates matching retained events by source, identity and parent directory. Authored PRs, reviewed PRs and commits have separate counts; multiple files in the same area and repeated reviews of one PR count once for that role. Results include the latest matching event date (`last_event_at`) and up to five supporting event citations. Counts cover matching events in the selected window, not every contribution by that person. Git authors and GitHub identities are not heuristically merged. PR reviewers are attributed to the PR's updated-at window; this is not a time series of individual review actions. Counts are candidate knowledge-holder signals, not ownership, expertise, authority, availability or performance ratings.

## Coverage and retained snapshots

Local Git covers commits reachable through local refs affecting the selected root, without fetching. Shallow history is reported; merge file lists may be empty. Git's date-limited traversal can omit unusual histories with non-monotonic commit timestamps. GitHub commits cover the default branch; PRs of all states are paginated by most recent update. See the official [commit API](https://docs.github.com/en/rest/commits/commits) and [pull request API](https://docs.github.com/en/rest/pulls/pulls). GitHub file lists have API caps; cap hits are reported. PR descriptions, changed paths and submitted reviewer identities are collected; review text, issue discussion comments, diffs and linked documents are not collected by this adapter.

These are historical snapshots, not as-of reconstructions: a PR changed after an old requested window may no longer match it. Refreshes do not automatically purge deleted remote events, revoked access, old windows, or renamed identities. Historical searches label this limitation and expose the latest collection report. A partial result is not evidence of no activity. Successful imports may still have partial status because local/remote scope and adapter completeness are limited. Repeated gaps are deduplicated and at most 20 samples per source/provider are returned, with omission counts.

History uses the same environment/workspace/configuration isolation as the code index. Explicit path exclusions and built-in private/build path rules filter changed paths; events known to touch only excluded files are skipped. Messages can describe multiple paths, and unavailable file lists cannot establish path coverage. These filters are not a secret scanner. Use approved, narrow scopes and keep state private. Code index/watch never collect or delete history; collection reports persist separately. To remove retained history, stop processes using the store and remove the scoped SQLite database and its WAL/SHM companions, then rebuild the desired code/history scope. There is no shared-service authorization or automatic retention policy in this local prototype.
