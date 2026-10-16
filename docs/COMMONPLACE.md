# Commonplace — MVP

**Local P2 maintenance — 2026-09-11:** [Knowledge feedback, cleanup queue, re-review drafts and empty Scratch reasoning notes](KNOWLEDGE-MAINTENANCE.md). Explicit human review remains required; no shared service or automatic wiki growth.

**2026-09-11 update:** [Validated local edit/import workflow](P1-WORKFLOWS.md#commonplace-editing-and-review) is implemented. Snapshots now include `edit.json`; explicit preview/import creates unapproved proposals. The snapshot description below remains accurate for `records.json` and `wiki/`. No automatic synchronization or approval transfer.

Commonplace is the team's shared knowledge home, complementary to a developer's personal Scratch. In this MVP it is a local placeholder directory with an optional team-repository mapping. No Git clone, fetch, commit, push, pull or network synchronization occurs.

In the sidebar, choose **Commonplace team knowledge → Configure team repository mapping**. Enter `owner/repository` (or leave it empty) and a company-controlled absolute local directory. Then choose **Open local Commonplace** to create and reveal a new snapshot containing:

- `README.md`: mapping, boundaries and usage instructions.
- `records.json`: canonical-record snapshot, including proposal/revision statuses.
- `wiki/<source>/<section>.md`: human views for all five knowledge types.

Snapshots use separate private directories and never overwrite repository files. The engine's reviewed SQLite records remain authoritative for now. Editing a snapshot does not update approval or agent lookup; use the existing draft/import/review workflow. Agents continue using compact lookup tools rather than wiki files. A future Commonplace repo adapter can load portable records through an explicit validation/review workflow; automatic import and shared approval are not part of this local workflow. Explicit edit-file preview/import is available as described above.

Settings are local to the selected engine scope and persisted beside its index. Configuration does not modify the selected source manifest or its index identity. Alternatively, a new manifest can declare:

```json
"commonplace": {
  "repository": "your-company/commonplace",
  "directory": "/absolute/company-controlled/commonplace"
}
```

A saved local mapping takes precedence. Changing a manifest can select a new scoped store, so prefer the sidebar for an existing scope. Local files contain company knowledge and must never enter product usage feedback. Choose a directory outside indexed sources (or an excluded `.context-wiki`/`.context-engine` directory). Configured deployment storage allowlists still apply. These snapshots have no automatic retention cleanup; include them in company offboarding and backup rules.

The internal portable-core commands are `commonplace status`, `commonplace configure --repository owner/repo --directory /absolute/path`, and `commonplace materialize`, with the usual global manifest/state arguments. User-facing operation remains in VS Code.

## MVP approval scope

Draft → local maintainer approval → human wiki and compact agent view is sufficient. SSO, central approval services, cross-employee authorization and separation of duties are not launch requirements. Missing optional reviewer policy no longer blocks the local workflow's readiness check. Explicitly configured advanced policies are still enforced; GitHub network access retains its separate permission gate. Normal client storage/dependency/provider approvals remain applicable.
