# Context Engine for VS Code

Search selected local repositories, give agents compact cited evidence, and maintain reviewed team knowledge. The extension includes the portable engine code and runs it locally.

## Get started

1. Install the supplied `context-engine-0.6.0.vsix` using **Extensions: Install from VSIX**.
2. Open your repository folders and trust the workspace as appropriate.
3. Open the **Context Engine** sidebar and select **Get started**.
4. Check Python/Kotlin setup. Use **Context Engine: Python Path** to select the executable prepared by your team.
5. Choose repository folders for a Team or Personal scope, or select an existing configuration. Refresh code.
6. Open the generated **Codex IDE workspace** and use your approved Codex extension account. Allow its code-watch task when prompted, or run it through **Tasks: Run Task**.

**Daily work does not require Python scripts or the Codex CLI.** Your team must still prepare Python, Git and approved parser packages; these are not bundled or automatically installed. The client preview targets macOS Apple Silicon with the pinned Python 3.13.15 profile. General core development supports other profiles, which require separate client verification.

Get Started is a resumable checklist of explicit actions, not an automatic installer. Health reports the latest explicit check and refresh tasks observed in this window, not remote process liveness or agent authentication. Start Codex in the generated Context Engine folder. Reopen the IDE workspace after runtime/backend changes; unchanged files are reused and user edits are preserved.

## Everyday actions

| Action | Purpose |
| --- | --- |
| Context workbench | Search with repository pickers, inspect citations and related context, go back to earlier evidence |
| Wiki | Open the human-readable repository wiki directly from the main sidebar |
| Architecture | Read the repository overview, follow the request walkthrough, and open supporting code |
| Team knowledge | Browse, draft, review and retire all five knowledge types; prepare stale-evidence re-review drafts |
| Prepare change context brief | Read tracked change context and coverage limits; add it to a task pack |
| Task context packs | Pin evidence, check/refresh citations and prepare a local IDE prompt handoff |
| Workspace health | Check freshness and coverage; refresh code; observe and start/stop this window's refresh tasks |
| Open Codex IDE workspace | Reuse unchanged integration files or preserve edits while preparing a fresh copy |

Use **Show advanced actions** for profile edits, local Commonplace snapshots, maintenance, Scratch notes, JSON import, cross-record relationships, structural tools, benchmarks, diagnostics and legacy integrations. Every command remains available from the Command Palette. Managed deployments disable legacy terminal agent/account flows; the local IDE handoff works without them. History and semantic controls follow the engine's reported capabilities.

In **Team knowledge**, choose a type, repository and supporting file. Fill in guidance, rationale, applicability, exceptions and structured details. Saving creates a proposal; approval is a separate confirmation. The source preview validates the cited hash. Changed files require refresh and re-review. Conflicting edits from another window do not overwrite newer proposals. Unsaved form edits are protected when navigating within the workbench or opening another workbench view; save a proposal before closing/reloading the editor. New guided drafts start with one supporting file; advanced imports support additional citations and relationships.

In **Task packs**, select **Prepare IDE handoff**, inspect the prompt, and copy it into your approved agent in the generated **Context Engine** folder. Copying checks evidence again. Context Engine writes the pack locally and does not submit the prompt or launch an agent terminal. Whole items must fit the byte budget; increase it or remove pins when necessary.

In **Profile**, refresh timing changes preserve the manifest, index, knowledge and packs. Repository/retrieval changes explain the new scope before saving; use **Select Manifest** to recover the previous scope. Stop refresh before profile edits. Direct external manifest edits still select configuration-specific stores; automatic merging/migration is not implemented.

Filename search results support preview and opening the source. Pinning a filename expands a bounded, hash-checked excerpt; previously saved filename pins can be validated and refreshed too. Files with no readable excerpt cannot become code evidence.

Core-generated workspaces use `contextEngine.statePaths` to share each scope's store with the extension. For older workspaces whose sidebar and agent show different knowledge, follow the [existing-store setup](../docs/CONFIGURATION.md#state-and-updates); stores are not merged automatically.

Commonplace import creates proposals after preview; local maintainer review is required. It does not synchronize Git repositories. Some advanced editing still uses JSON documents.

## Troubleshooting

| Symptom | Next action |
| --- | --- |
| Python setup cannot run | Use the offered interpreter-setting shortcut or runtime help; ask your team for the prepared executable |
| Kotlin reports text fallback | Have the runtime preparer supply approved parser packages; text search alone does not satisfy Kotlin pilot readiness |
| No scope selected | Use Get Started to choose open folders or an existing configuration |
| Empty or stale results | Open Workspace Health, refresh code and check source coverage and refresh tasks |
| Agent tools missing | Open the generated workspace, check workspace/project trust and reconnect the agent; regenerate after runtime/backend changes |
| Advanced commands missing from sidebar | Select Show advanced actions or use the Command Palette |
| Legacy diagnostics report missing CLI tools | These CLI tools are not required for the Codex IDE route; use Python/Kotlin setup and client readiness for engine checks |
| Managed policy rejects an action | Check the configured client profile with its preparer; restricted features are intentionally unavailable |

Activation does not install software, index repositories, collect usage or start an agent. Workbench works without an agent account. Context Engine does not verify model sign-in or certify client release approval.

## Data and feedback

Indexes, selected context, wiki and diagnostic data stay in company-controlled local storage. The vendor must not receive company content or repository references. Optional usage reports use a fixed aggregate schema, explicit enablement, preview and local save; there is no uploader. The client vets any saved report before manually sharing it. Your coding agent has separate account and data policies for the evidence you send it.

## Further reading

- [Alpha acceptance and known limits](../docs/ALPHA-ACCEPTANCE.md)

- [Product overview](../README.md)
- [Client runtime preparation](../docs/CLIENT-SETUP.md)
- [Portable core guide](../docs/CORE-GUIDE.md)
- [Development and packaging](../docs/DEVELOPMENT.md)
- [Vendor data boundary](../docs/security/VENDOR-DATA-BOUNDARY.md)
- [Client-test gates](../docs/security/CLIENT-TEST-READINESS.md)

## Reading architecture

Architecture opens a reading view for the selected repository, with a table of contents and hash-checked source links. It prefers `docs/ARCHITECTURE-OVERVIEW.md`, then a root overview, an architecture document, or the root README. Repository text is displayed as documentation, not promoted to approved team knowledge. Without documentation, the view provides a limited reading path from source descriptions and explicitly identifies missing design explanations. Extracted module and relationship cards are available under **Supporting code structure**.

The Context Engine sidebar now also has a **Context workbench** toolbar action
(book icon). You can always run **Context Engine: Open Context Workbench** from the
Command Palette if the Activity Bar icon is hidden. In the Workbench, the first
keyboard link skips navigation to results. Runtime wrappers configured with
`contextEngine.pythonPath` are retained when generating new agent workspaces.

In 0.6.1, **Workspace Health** shows the loaded backend release/build and the index
writer build. A mismatch requires coordinating writers and refreshing with the
intended backend. Check `index_status` through the actual MCP connection too;
the sidebar cannot verify another process. See the implementation repository's
`docs/BACKEND-UPGRADES.md` for the deliberate upgrade sequence.
