# Client-test readiness — 0.6.0 alpha candidate

The restricted pilot is local macOS Apple Silicon, Python 3.13.15 and the pinned structural parsers. VS Code is the supported client interface; the portable Python/MCP core remains in the same repository. History, remote repository provisioning and embedding providers are disabled by an external deployment policy. There is no usage uploader.

## Release gates

| Gate | Engineering result | Remaining acceptance |
| --- | --- | --- |
| P1 dependencies | Hash-pinned wheel-only release profile; public advisory checks and license/provenance inventory; isolated modern Python/Node toolchain | Client approval of this exact dependency profile and editor/agent versions; refresh advisory checks at distribution |
| P2 security/deployment | External source/storage allowlists; private index/usage permissions; disabled history/remote/embedding features; local inventory and selected-index reset | Client-managed policy/settings, approved local storage and backup rules, approved agent account/provider policy and egress controls |
| P3 reviewed usage | Opt-in local aggregates, strict independent Python/JS validators, preview then exclusive private-file save, no uploader | Client reviews exported files before sending; agree recipient retention and handling |
| P4 onboarding | Packaged launcher tests and separate VS Code test-profile rehearsal | Actual fresh company-managed Mac, real account integration and human export review |
| P5 recovery | Stale/reindex checks, transactional selected-index reset, source preservation; isolated extension upgrade/rollback rehearsal | Full client runbook rehearsal; retain approved fallback and separately scoped state |
| P6 improvement | Validated read-only report analyzer; synthetic observation packet; benchmark gate correction and regression case | Laura reviews decision; real reports follow only after client vetting |

**Local maintainer approval is sufficient for this alpha.** An absent optional reviewer policy does not block local readiness. Shared SSO, hosted approval and employee monitoring are outside the product boundary and are not launch gates. Follow the [alpha acceptance checklist](../ALPHA-ACCEPTANCE.md) for the user journey.

These are engineering checks, not certification, legal license approval, or authorization to transfer company information. No physical fresh-Mac or client MDM approval is implied.

## Deployment

1. IT chooses company-controlled source and artifact roots outside source repositories. Approve local caches, packs, handoffs, editor state, backups and retention. Avoid personal sync folders. The policy is an application guard; OS/MDM controls must protect its file and the machine settings. A same-user operator can bypass an optional application policy by changing settings/environment.
2. Provision the approved Python profile. Use `requirements-release-macos-arm64.txt` with `pip install --require-hashes --only-binary=:all:` against approved artifacts (offline wheelhouse preferred). It includes developer tools for repeatability; none of the npm tools ships as a runtime dependency. Do not use the legacy development environment as the client release environment. Other Python/CPU profiles need separate verification.
3. Create an absolute policy file outside the source checkout, using `examples/client-policy.example.json`. Replace both example roots. Set permissions to 0600 or administrator-managed read access, with no group/world write. Keep all three feature permissions false. A client manifest must omit history and embeddings and use existing local sources only.
4. In VS Code machine settings set `contextEngine.pythonPath`, `contextEngine.storageRoot`, and `contextEngine.policyPath` to approved absolute paths. Restart after storage changes. This does not migrate or remove previous storage. Install the reviewed `dist/context-engine-0.6.0.vsix` via **Install from VSIX**.
5. Choose the manifest, refresh, and run **Client-test readiness**. All local checks should pass. The displayed inventory contains identifying paths: keep it local. Run **Run synthetic benchmark**; all cases and Kotlin must pass. Synthetic fixtures use a temporary directory under the first approved storage root, independently of the selected manifest.
6. Use the approved IDE integration. Managed pilot mode blocks the extension's terminal agent launch/account flows. Approve the editor/agent separately: retrieved company evidence intentionally goes to the selected agent. Context Engine does not control that agent's retention, account, telemetry or network behavior. Do not attach company evidence to product feedback.
7. Verify a saved-file change yields stale evidence, then refresh and retry. Test Kotlin navigation, graph relationships and bounded reads on authorized fixtures. Start with the synthetic fixture before adding company sources.
8. Optional: enable local usage aggregates, perform a few lookups, preview and save a report, have the client vet it, then send only the approved file through the agreed channel. No automatic transmission occurs. See [the metric registry](REVIEWED-USAGE.md).

## Recovery and rollback

Stop crawlers and agent processes before maintenance. **Local data inventory and reset** offers selected-index logical reset and separate selected pack/handoff deletion. Reset makes the index unindexed, clears usage and disables collection. Reindex rebuilds from preserved source files. Writer locking prevents competing writers; callers can retry after the lock is released.

A reset is not secure erasure. SQLite free pages/WAL, previous store generations, old manifest-scope artifacts, generated workspaces, saved report copies, VS Code documents/backups and source checkouts may remain. The inventory covers the selected engine state plus selected extension artifact locations, not every historical location. For complete offboarding, stop all processes, inventory every configured/previous artifact root, and have IT remove those roots and backups under its storage policy. Do not delete source checkouts as part of automatic reset.

Retain the previous reviewed VSIX. On a failed upgrade, disable the extension, stop agents/crawlers, install that VSIX explicitly, reload, and use a separate approved storage root followed by reindexing. Do not assume older versions understand newer policy/report settings or can safely reuse new state. Version 0.2.0 lacks the new policy/report protections, so it is an internal rollback rehearsal artifact, not automatically an approved company fallback. Prefer disabling the pilot until an approved corrected build is available.

## Security evidence and limits

- [Dependency review](RELEASE-DEPENDENCY-REVIEW.md), hashed Python requirements, npm lockfile and inventories define the reviewed profile. Zero advisory matches is a dated database result, not proof that packages contain no vulnerabilities.
- Native parsers execute in the engine process; package provenance and synthetic parser tests do not constitute a full source or memory-safety audit. Optional semantic/splitter dependency graphs remain outside this pilot.
- Company content still exists in local indexes/packs/handoffs by design. Usage statistics are a separate numeric store. No telemetry is attached to error messages or diagnostic inventories.
- Collection covers six compact retrieval operations, not all product activity. Crashes/cancellation can lose increments. It must not be used for billing or claims of actual token/currency savings.

## Verification checkpoint

Current candidate evidence is recorded in [alpha verification](../../evaluation/alpha-verification-2026-09-13.json). The earlier 0.3.x checkpoint remains in `evaluation/client-release-verification-2026-09-10.json` as historical evidence only. Developer tests and isolated editor rehearsals do not establish fresh client hardware, real account integration or client release approval.
