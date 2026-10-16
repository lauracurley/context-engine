# Dogfooding Context Engine

We can use the engine to develop itself and consult the related Scratch notes. A local rehearsal on 2026-09-13 indexed both working trees, retrieved cited evidence across them, and exercised the generated MCP launch command. This is development dogfooding; it does not replace client-machine acceptance or prove improved agent task completion.

## Prepared workspace on this machine

The private setup is under `.context-engine/dogfood/` in this checkout, already excluded by Git and the engine's scanner:

- `manifest.json`: source `engine` is this repository; source `scratch` is the Scratch repository. The unrelated `projects/pet-food/` tree, generated evaluation JSON and the extension lockfile are excluded from this focused scope.
- `policy.json`: the two local source roots and this setup's storage root only; history, remote Git and embeddings are disabled.
- `state/`: a separate development index and knowledge store. Existing demo/client stores are untouched.
- `workspace/context-engine.code-workspace`: the reusable multi-folder IDE workspace, with a project-local MCP configuration and shared extension/MCP state paths.
- `context`: a small local command wrapper that selects the manifest, state, policy and prepared Python runtime.

From the engine repository:

```sh
.context-engine/dogfood/context index
.context-engine/dogfood/context discover 'vendor code prompts' --content docs --limit 6
.context-engine/dogfood/context discover schedule_preferences --source engine --mode literal
.context-engine/dogfood/context discover ranked-feature --source scratch --mode files
```

The local setup uses the live development checkout. It contains absolute machine paths and is not a distributable client configuration. The general `init` workflow in the [core guide](CORE-GUIDE.md) remains the starting point on another machine and requires an output directory outside the source repositories. This existing-manifest setup instead uses the engine's ignored local state directory.

## Use it from the IDE

Open the generated workspace in the known working VS Code installation, then start a conversation in its first **Context Engine** folder. The project `.codex/config.toml` must be loaded by a trusted project. Confirm `context_engine` and its `search_code`/`read_code` tools are connected; restart the MCP connection or IDE extension after configuration changes. Project-scoped STDIO servers are supported by the [official MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

No editor was launched and no existing agent configuration was changed during this rehearsal. The current conversation used the CLI and a local MCP protocol probe; a newly connected IDE conversation remains to be verified. Run the generated watch task for ongoing code refresh, or use the one-shot `index` command above. No watcher was left running by the rehearsal.

The prepared Python on this Mac requires `.context-engine/toolbin/python3` to set its framework paths. The local generated task commands, workspace Python setting and MCP command were adjusted to retain that wrapper. The generated MCP command was then tested without inherited `DYLD_*` variables. Regeneration with the current generic renderer would select the underlying `sys.executable`; preserve the wrapper until launcher configuration supports this case directly.

## Daily loop

1. Start with a real maintenance question. Retrieve the relevant implementation and its Scratch rationale, using source/path filters. Expand selected citations with `read_code` and `expected_hash`.
2. Resolve repository instructions before editing. Scratch text is working evidence; it does not automatically become approved Commonplace guidance.
3. Make the change and run its normal checks. Refresh the index after edits. Restart the MCP server after editing Python engine code so it loads the new implementation.
4. Use the change brief as bounded context and inspect its omissions alongside the actual Git diff. Use direct reads for new files outside its tracked-change coverage.
5. Record whether the evidence helped, query retries, missing files, stale-state recovery, and the actual task outcome in the Scratch dogfooding log. Promote a useful lesson as a proposal for explicit human review.

If an engine change breaks retrieval, use ordinary file/search tools to repair it. Keep this development state separate from release acceptance state; do not use it as an older-version rollback fixture.

## What the first rehearsal exposed

| Finding | Practical effect and follow-up |
| --- | --- |
| Initial index: 171 files, no scan/parser errors, about 0.97 seconds | One local observation on these small working trees; not a production latency guarantee. Subsequent documentation adds files. |
| One query returned the engine boundary document and the Scratch boundary decision | Cross-repository context is useful now, without a remote service or embedding model. |
| A broad priorities query missed the named ranked-opportunities document in its first five hits | Filename discovery found it immediately. Evaluate ranking on real tasks and improve guidance for choosing search modes. |
| `requirements-structure.txt` was absent from file discovery | The suffix allowlist excludes `.txt`; requirements and extensionless build files need deliberate coverage work. Use direct file reads meanwhile. |
| Prepared-runtime wrapper needed a local launch adjustment | Preserve launcher identity and add clean-environment launch verification to generic workspace generation. |
| Change brief reported substantial omissions against the current old Git base | Most new implementation files are untracked. It cannot be the complete review context; use the actual diff and direct reads. No staging or commits were performed. |
| Knowledge lookup returned no approved decisions | Indexing Markdown does not populate Commonplace. Curate a few durable practices through the normal human review flow. |

These observations make requirements-file coverage, launcher preservation and real-task retrieval evaluation useful next alpha priorities. Keep detailed results local. Our own personal/public-safe project scope does not justify adding employer/client repositories or sending their material to the vendor; agent/provider behavior remains a separate boundary.
