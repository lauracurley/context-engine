# Alpha acceptance — 0.6.0

This candidate focuses on the daily loop: get a local workspace ready, find context, curate reviewed guidance, prepare change context, and hand a bounded pack to an approved IDE agent. The package, verification results and limitations are recorded in [alpha verification](../evaluation/alpha-verification-2026-09-13.json). Start with invented repositories in a separate VS Code profile; the client then runs the same journey on its approved machine and account.

## First session

| Step | Expected behavior |
| --- | --- |
| Install and set up | Install the supplied VSIX, select the prepared Python runtime, choose explicit source folders, and complete Get Started. No software or account is installed automatically. |
| Check health | Workspace Health shows the selected scope, coverage, current index state, semantic availability and refresh tasks observed in this window. Refresh code there; start/stop code refresh if needed. An account or live MCP connection is not claimed verified. |
| Find context | Search by behavior, identifier or filename. Choose repositories from the filter, preview/open a cited source, explore structure and use Back to evidence. Unavailable semantic/history controls are hidden. |
| Review knowledge | Team knowledge → New knowledge proposal → type/repository/supporting file. Fill in the form, including exceptions and procedure/decision details. Saving creates a proposal. Inspect source and approve separately; verify approved guidance is available through the scoped agent lookup. |
| Handle drift | Edit a supporting fixture and check again. Retrieval/handoff with stale code is withheld. Refresh code, prepare a re-review draft, inspect the changed source and refine its DRAFT statement. The old conclusion is never silently refreshed into approval. |
| Handle concurrent edits | Open two views/windows of a record. Save a replacement in one, then try saving the older draft. It must report a conflict and preserve the open form rather than overwrite newer knowledge. |
| Prepare change context | In a Git fixture, change a tracked file. Choose the repository and base in Change context. Read the changed snippets, applicable guidance, possible tests and coverage limits; pin the brief to a task pack. |
| Hand off in managed mode | Add cited evidence to a task pack, Prepare IDE handoff, inspect/open the local pack and Copy prompt. No terminal agent launch or automatic submission occurs. Paste into the approved agent in the generated Context Engine folder; verify MCP tools and current citations there. |
| Preserve continuity | Stop refresh. Change only timing in Profile and save. The selected manifest, reviewed knowledge and packs must remain. Change repository/retrieval scope separately and confirm its new index; the old scope must remain available in Select Manifest. |
| Reopen and recover | Reopen the IDE workspace twice: unchanged integration files are reused. Edit a generated fixture file and reopen: edits must remain in the prior copy. Check source-change rejection, refresh/retry and selected-index reset before testing rollback with a separate state root. |

For guided authoring, each new record starts with one indexed supporting file. Advanced local JSON workflows retain additional citations, exact cross-record relationships and imported-review provenance. Unsaved form edits are protected when navigating views, but are not durable across closing/reloading VS Code; save a proposal before doing so. Large evidence previews are bounded excerpts; inspect the full file where needed.

## Acceptance observations

The client keeps task descriptions, source paths, prompt/pack contents, authored knowledge, screenshots and diagnostics in its own environment. During the first session, record local time to first cited result, where setup or terminology required help, whether the right evidence was found, whether the agent actually used it, and whether the task outcome was correct. These observations are not collected or uploaded by the extension.

A useful alpha result is a tester completing the loop without developer repair, with stale/partial evidence visibly handled and no unexpected loss of scope data. Automated synthetic success is a regression signal; it does not establish downstream agent quality, token savings or real-repository latency. Keep product claims tied to client-local observations. Optional vendor feedback remains restricted to the existing fixed aggregate report after client review; do not attach raw session material.

## Supported boundary and remaining work

- The vendor receives no code, prompts, repository identifiers, indexes, knowledge, diagnostics or approval records. No uploader, new metric categories, proxy or remote service was introduced. Model calls and account settings belong to the client's approved agent/provider.
- This is a prepared-runtime macOS Apple Silicon alpha. Python, Git and approved parser packages are supplied by the team. Fresh client-machine setup and real approved-agent/MCP use remain acceptance steps.
- The native smoke test passed on VS Code 1.137.0. An additional 1.87.2 installation crashed during startup before the host-test checkpoint; its compatibility remains unverified. Use the explicit tested installation for the initial rehearsal, and validate the client's chosen editor version separately. This smoke result does not establish general editor stability.
- Health is a fresh local check and editor task observation, not continuous account/service monitoring. The generated project MCP configuration requires the conversation to start in the Context Engine folder.
- Schedule edits preserve current data through Profile or the `schedule` CLI. Direct manifest edits, changed source scope and model/retrieval configuration still select configuration-specific stores. Previous stores remain; automatic merging and cross-scope knowledge migration are not implemented.
- Commonplace snapshot export/import is explicit and local. There is no automatic Git synchronization or shared approval service. Local maintainer approval is the supported topology.
- Change briefs cover tracked working-tree changes against a Git base, with explicit path/hunk/budget omissions. Untracked/deleted/excluded paths are not current evidence. Test candidates and graph relationships are qualified inferences, not review verdicts or proven coverage.
- Compiler-resolved cross-language relationships, broader file-type coverage, measured real-task relevance, advanced guided relationship/citation editing and automatic draft recovery remain follow-up work. They are not represented as complete by this release.

The runtime/dependency and client storage/account checks in [Client setup](CLIENT-SETUP.md) still apply. Do not reuse newer state with an older package as a supported rollback; preserve the previous package and use separate state, or disable the alpha until corrected.
