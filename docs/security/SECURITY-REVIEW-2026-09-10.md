Security review — 2026-09-10

Decision: not yet approved for client deployment. This source/configuration review, synthetic storage probe, regression suite and public dependency-advisory check are a first security pass, not a penetration test or certification. The client clarified that local company-controlled storage is allowed; company/user data must not be retained outside that boundary. No company repository, credential, conversation or private source was used for this review.

**Findings and disposition**

| Priority | Finding | Evidence and action |
| --- | --- | --- |
| High — fixed in code | Index permissions depended on process umask. A synthetic run at umask 022 produced a 0755 environment directory and 0644 SQLite database/WAL/SHM containing a source marker. Exposure depended on ancestor permissions and host ACLs. | `context_engine/core.py` now requires an owned, non-symlink environment directory, restricts it to 0700, creates the database as 0600 and tightens existing database/sidecar permissions. Non-regular or symlink index files are rejected. Regression checks cover new files, reopen and symlink refusal. Existing stores are tightened when opened by the updated engine; unopened old stores and backups are not migrated. |
| High — release gate | Third-party libraries have not received full vetting. Version pins alone are insufficient. | 89 package/version records queried against OSV: 80 npm development packages plus nine Python package/version records covering direct optional pins and the isolated navigation/development environment. Matches occurred for pip 21.2.4 and setuptools 58.0.4. Other queried versions returned no advisories at scan time. Some IDs are aliases of the same issue, not distinct vulnerabilities. Optional semantic/splitter transitive dependencies and native/model artifacts were not fully inventoried. |
| High — release gate | No centrally enforced company storage/egress policy. | State paths, VS Code global storage, generated workspaces, handoffs, managed checkouts and optional model caches can live at independently selected locations. A company-approved endpoint does not automatically make every directory, backup/sync destination or external coding-agent account approved. Require a managed storage root, approved process/provider paths and company egress controls before deployment. |
| Medium — open | Derived data has no complete cleanup lifecycle. | SQLite evidence/FTS, vectors, architecture/structure/history tables persist. Profile changes create new store identities; old stores can remain. Handoff files and saved packs have no demonstrated expiry/purge workflow. A six-month history query window is not a retention TTL. Define local retention and add inventory/delete-by-scope controls with WAL/checkpoint and backup considerations. Do not promise secure erasure on SSDs/backups. |
| Medium — open | Source exclusions are not secret detection. | `.env*`, ignored paths, symlinks, unsupported suffixes and files over 512 KB are excluded, but tracked JSON/YAML/Markdown/source can contain secrets. Add company-managed exclusions and explicit provider authorization; never describe these filters as DLP. Secret detection should be an additional vetted control, not an assurance that retrieved text is safe to export. |
| Medium — open | Process and parser trust boundaries need stronger deployment controls. | Shell-free argv is used, but configured gateway executables intentionally run code; child processes inherit environment, and native parser libraries process untrusted repository text. Git hooks/ext protocol restrictions help managed checkouts, but this is not an OS sandbox or domain allowlist. Review Git configuration/credential helpers, deny unapproved executables/destinations, constrain parser resources and use maintained runtimes. |
| Medium — open | Diagnostics and downstream clients can retain identifying information. | CLI/MCP results intentionally contain source paths, hashes and excerpts. Arbitrary OS exceptions may include paths; some extension failures are written to the output channel. Exported JSON, task terminals, editor recovery, coding-agent transcripts, crash dumps, OS swap and backups are outside the in-memory task ledger. Introduce fixed diagnostic codes and a reviewed local support-report schema; do not ship raw logs as telemetry. |

**Data inventory**

- Original repositories: company-selected local checkouts; remain source-owned.
- Engine state: SQLite source snippets, file/revision hashes, paths, FTS tokens, vectors, graph/structural facts, instructions and crawler metadata. Stored under the chosen state/environment scope; not encrypted by the engine.
- History: commit/PR descriptions, author names/logins/email, URLs and activity summaries. Local history includes identity data. Keep history off unless explicitly approved for the client use case.
- Managed Git: complete fetched checkout/object data plus source URL/ref and ownership markers.
- VS Code: profiles/workspace scope metadata, saved evidence packs and handoff JSON in extension/workspace storage; generated workspaces contain paths/configuration. Unnamed JSON editors and downstream agents can create additional copies.
- Models: optional local model cache; model content is third-party material, while derived vectors remain company data. The provided sentence-transformer adapter uses local-only loading and disables remote code trust. Injected company embedding adapters are a separate reviewed integration boundary.
- Task budget ledger: in-memory task IDs, counters and evidence IDs; cleared on server restart, capped at 128 tasks. It is not durable telemetry and cannot govern other clients' retention.

No automatic vendor telemetry uploader was found in the reviewed engine/extension sources. This does not prove zero network activity: Git/gh/gateways, external coding agents, model prefetch tooling, installation tooling and injected providers can use the network. External agent/provider retention must be assessed independently using the client's chosen account and agreement.

**Existing defenses confirmed**

Workspace trust guards, scoped manifests, source containment/symlink exclusions, selected-range hash checks, explicit inferred relationship labels, SQL parameter binding, capped regex worker runtime, shell-free extension process invocation, stderr suppression, nonce/CSP webview rendering and package allowlisting all provide useful protection. The VSIX packages engine Python and extension JS without npm runtime libraries or bundled Python dependency stacks. The npm lock contains integrity values for all 80 entries; CI uses SHA-pinned actions and `npm ci --ignore-scripts`.

Scope partitioning and chmod are not multi-user authorization or protection against malicious same-user code/admin access. macOS ACLs, device encryption, MDM controls, real account permissions and filesystem race resistance beyond the owned private directory were not independently verified.

**Dependency review record**

See [machine-readable inventory and advisory results](dependency-audit-2026-09-10.json). The lookup transmitted only public package ecosystem, name and version to OSV; no source contents, paths, company names or identities were sent. License strings are inventory evidence, not license approval; missing declarations remain unresolved.

The pip/setuptools findings concern installation/build tooling in the isolated development environment, not libraries bundled into the VSIX. They are still a supply-chain concern. Do not use that toolchain for client builds/installations until replacements have been reviewed and rescanned. No package was upgraded or installed during this pass. Advisory applicability needs triage against interpreter version and reachable installation operations. Example source records: [pip advisory](https://osv.dev/vulnerability/GHSA-4xh5-x5gv-qwph), [setuptools advisory](https://osv.dev/vulnerability/GHSA-cx63-2mw6-8hw5).

Required vetting checklist for every shipped/runtime/build dependency:

1. Inventory exact direct/transitive versions, origin, license, native components and model artifacts; generate a release SBOM from the actual build environment/artifact. Include Python, SQLite, Git, Node/VS Code and external provider integrations.
2. Review maintainer/source provenance, license obligations, install hooks/build execution, file/network access and vulnerability reachability. Parser wheels and model loaders need explicit review; a zero-advisory scan is not approval.
3. Pin transitive versions and artifact hashes for Python as well as npm. Use an approved artifact mirror/wheelhouse and reproducible offline installs. Resolve optional parser, embedding and splitter profiles separately; ship only approved profiles.
4. Record reviewer, approval scope, evidence, exceptions and expiry. Block release on unreviewed components or unresolved applicable high-severity issues. Recheck on dependency updates and before releases; do not upload a client's private dependency inventory to public scanners.

**Release sequence**

Ship the storage-permission fix after verification. Then complete dependency/toolchain vetting and enforce approved local storage/provider configuration. Implement the synthetic benchmark dashboard and fixed-schema export described in [the measurement plan](EFFICIENCY-MEASUREMENT-PLAN.md). Finish retention cleanup, diagnostic review and adversarial egress/storage tests before recommending the client use real company data. Local indexing permission is not permission to send content to an external provider.


Verification: the full quality gate passed with 81 Python tests run (two optional skips), all 22 extension tests, lint/format checks and deterministic retrieval evaluations. The rebuilt VSIX containing the permission fix was installed into the developer's existing local VS Code extension; reload is needed. No third-party dependency was installed or upgraded. This does not change the client release-gate decision.
