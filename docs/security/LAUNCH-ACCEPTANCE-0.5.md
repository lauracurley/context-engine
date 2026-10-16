# 0.5.0 launch acceptance

Historical 0.5.x checkpoint. Use [Alpha acceptance](../ALPHA-ACCEPTANCE.md) and [the current client-test runbook](CLIENT-TEST-READINESS.md) for 0.6.0.

**MVP scope update:** Shared authenticated approvals are not required. Local maintainer approval is sufficient, and an absent optional reviewer policy no longer blocks readiness. Commonplace is the configured team-repo concept, backed by local snapshots for now. See [Commonplace](../COMMONPLACE.md). This supersedes contrary shared-approval gates below.


This is a reviewable local release candidate. The remaining feature slices have been implemented for a single company-controlled local-store workflow. Production release still requires the client-owned acceptance below; no shared authenticated approval service is represented as implemented.

| Requirement | Implementation/evidence | Acceptance still needed |
| --- | --- | --- |
| Five human/agent knowledge layers | Practices, architecture, conventions, decisions and procedures; one canonical record, separate reader projections | Representative client-authored scenarios; inspect exceptions and procedure completeness |
| Review loop | Explicit per-PR GitHub GET transport, bounded atomic import, fingerprints, refinement drafts, human approval and source/provenance invalidation | Real approved repository/token, TLS/proxy and GitHub permissions; development used synthetic transport fixtures |
| Decision governance | Exact-revision supersession, cycles/conflicts blocked, history and current-successor lookup | Human semantic conflict review; declared conflicts are not automatic contradiction detection |
| Local roles/audit | Root-owned policy, OS UID checks, optional self-approval blocking and chained local events | IT-installed policy, MDM launch/settings controls; client confirms this local topology is sufficient |
| Shared authenticated review | Not implemented; private owner-only database is not a multi-user approval service | If required: client identity provider, hosting/storage, approver roles and service authorization design |
| Wiki experience | Script-disabled navigable webview, bounded static SVG map, no authored remote resources | Human usability/visual review on client editor/window sizes |
| Retrieval efficiency | Existing byte budgets plus whole-record knowledge packing, language/task/path filters, one-click synthetic checks for all layers | Client task success and approved usage feedback; no actual model token/currency claims |
| Privacy | All new knowledge/review/audit content stays in company-controlled state; separate numeric usage reports | Agree retention/backups/offboarding and human vetting of any transferred report |
| Dependencies/security | No new third-party libraries; existing frozen Python/Node package profiles; standard HTTPS for optional GitHub | Approve exact interpreter/editor/provider/token profile and refresh advisories before distribution |
| Fresh-Mac/account rehearsal | Isolated development-Mac tests are engineering evidence only | Fresh company-managed Mac, actual approved agent account and company source/storage selection |
| Recovery | Stale evidence withheld; re-fetch/revise/reapprove; additive schema and prior VSIX retained | Client maintenance/offboarding rehearsal; disable pilot or use separate state for older versions |

## Client-owned rehearsal

1. IT selects approved roots and installs both deployment and reviewer policy files; configure machine settings. Keep GitHub disabled until token/repository/egress approval. Do not weaken database owner-only permissions to simulate a multi-user service.
2. Install the candidate VSIX into a test profile. Run local readiness; a missing reviewer policy must remain action required. Run the synthetic benchmark and require all five knowledge layers and Kotlin/recovery checks to pass.
3. Create one real example of each knowledge kind on authorized sources. Verify draft invisibility, explicit review, narrow applicability, exceptions, complete procedure fields, supersession and deliberate retirement. Try stale citations and a declared conflict; approval/retrieval should fail closed as documented.
4. If authorized, fetch a single test PR with a read-scoped token. Verify duplicate imports, refinement and approval. Edit/remove a synthetic review and re-fetch to verify invalidation. Inspect local errors without sending them to the product vendor.
5. Exercise the human wiki and agent lookup for the same record. Confirm that rationale stays human-only, material constraints appear in structured guidance, and saved wiki projections are excluded from indexing.
6. Stop services and rehearse recovery/offboarding on disposable state. Index reset preserves curated knowledge; removing an entire approved state root and its backups is the complete offboarding procedure, not a claim of secure media erasure.
7. Enable optional numeric usage collection only after agreement. Preview/save a synthetic report and have a human vet it. Never attach wiki, audit, diagnostics, review bodies, tokens or manifests to product feedback.
8. Record client sign-off separately from software-generated checks. If shared approvals are required, keep launch blocked until that topology is implemented and tested.
