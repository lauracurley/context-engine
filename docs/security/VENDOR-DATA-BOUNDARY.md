# Vendor data boundary

Agreed with Laura, 2026-09-11. This is the standing product privacy requirement. Invoke it with **“Run a vendor-boundary check.”**

## Contract

Context Engine deployed in a client's environment is supposed to know about that client's repositories and working context. The company developing/supplying Context Engine must not receive, retain, or gain access to that corporate knowledge through the product.

The permitted exception is explicitly reviewed, content-free product usage statistics, manually shared after client vetting under the metric registry. This does not permit corporate identifiers or knowledge to accompany the statistics.

| Boundary | Permitted behavior |
| --- | --- |
| Client-controlled environment | Read and retain selected source code, prompts/task material where required by local workflows, semantic indexes/embeddings, GitHub analysis, knowledge records, Scratch/Commonplace, citations, drafts and local diagnostics |
| Client-selected services | Explicit integrations with the client's GitHub, coding agent/model provider or other approved services. These are not inherently vendor collection; inspect actual routing, credentials and destinations |
| Context Engine vendor and its services | No client content, derived knowledge or corporate references. Only the agreed vetted content-free usage report may be received |

“Corporate references” includes repository names/URLs, organization names, source paths, branches, commit/content hashes, PR/comment identifiers, source-linked fingerprints and credentials. Hashing or anonymizing such references does not automatically make them acceptable. Prohibited derived knowledge includes architecture, review norms, decisions, generated summaries, retrieval results, vector indexes and embeddings. A payload need not contain raw code to cross this boundary.

No client content is to be sent to vendor-owned telemetry, crash reporting, support bundles, proxies, storage, model accounts or development assistants. A client-selected provider is not a loophole for a vendor-owned account or intermediary. Direct integration requests may carry the information required by that client workflow, but the vendor must not be a recipient or gain access through the route.

Permitted feedback is limited to the declared fixed-schema counts, outcomes, coarse timing buckets and byte totals, plus fixed product/schema versions and coarse report-period metadata. See [the metric registry](REVIEWED-USAGE.md). No automatic uploader is currently implemented. Do not broaden the schema or add free-text logs/support attachments under the label “usage statistics.”

## What this requirement does not mean

It does not mean that the local product must be unaware of company data, that all network activity is forbidden, or that every configured folder must be proven company-owned. For the small MVP trial, policing malicious employees, accidental manual file sharing, personal-folder selection, enterprise SSO or mandatory organizational access controls is outside this particular requirement. Do not turn a vendor-boundary check into new enterprise-governance launch gates. Existing explicitly configured controls still apply.

The client controls its devices, accounts, selected integrations and manual handling of files. We remain responsible for what our product and bundled dependencies collect, send, log or expose to us by design. We cannot establish the behavior of independently operated client services merely by inspecting our code.

## Repeatable check

When asked to run a vendor-boundary check:

1. Read this contract and the current usage registry. Identify the release/revision and changes since the last recorded check. Do not infer a pass from an older report or the phrase “local-first.”
2. Trace outbound paths and recipients: HTTP/SDK calls, subprocess integrations, model/embedding requests, updates, analytics, crash/error reporting, support exports and dependency defaults. Distinguish client-selected destinations from vendor-owned destinations. Check payloads, headers/query parameters, credentials and account ownership where observable.
3. Trace persistence and exports: local indexes, knowledge/review data, Scratch/Commonplace, logs, temporary files and feedback reports. Company-local storage is expected; the issue is whether any product path copies or exposes it to the vendor. A local diagnostic containing paths is not automatically a breach, but must not become a vendor support attachment.
4. Inspect the usage allowlist and its call sites. Confirm content-derived IDs, raw errors, prompts, retrieved evidence and provenance cannot enter reports. Run relevant privacy canary/schema tests using invented markers, not client data. Check actual dependency telemetry defaults when dependency behavior changes; a code-string search alone is insufficient.
5. Report **PASS for inspected paths**, **CONCERN**, or **UNKNOWN**, with scope, evidence/tests, changed data flows and anything not verified. If deployment credentials or a dependency/service cannot be checked, state that limitation. Do not claim zero possible disclosure or certification.
6. Record the checkpoint in Scratch. Fix product-owned violations within the authorized scope; do not silently expand collection or invent unrelated client-policing requirements.

A short check-in answer should be:

> Vendor boundary: [verdict, inspected release/scope]. Vendor receives: [none / only vetted aggregate reports / concern]. Changed flows: […]. Evidence: […]. Not verified: […].

Recheck whenever reporting, logging, crash handling, connectors, remote models/embeddings, dependencies, sync, hosting or support workflows change, and before client releases. This is a review protocol, not an implemented automatic certification command.

## Current context

The 0.5.1 implementation has company-local stores and Commonplace snapshots, a separate allowlisted usage report with explicit preview/save, and no product-usage uploader. This is the known design baseline, not a fresh comprehensive end-to-end audit of every dependency or deployment. A future check must verify the then-current implementation and route ownership rather than relying on this paragraph.
