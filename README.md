# Context Engine

**Give coding agents cited context across your repositories.** Context Engine reads your selected local checkouts, keeps a search index current, and lets an agent find relevant code through MCP. You can also search from the terminal. Team code and your personal Scratch repository can appear in one VS Code window while remaining in separate indexes and MCP servers.

This is a working local prototype: lexical, semantic, and hybrid retrieval are implemented. Architecture overviews, automatic team-rule resolution, GitHub PR analysis, and knowledge-holder analysis are planned. Company-specific repository provisioning, identity, and API access belong in replaceable integrations.

## Try it in two minutes

From a checkout of this repository, with **Python 3.9+ and Git** installed:

```sh
python3 -m context_engine --manifest examples/acme.json index
python3 -m context_engine --manifest examples/acme.json search 'task.requested priority' --token-budget 8000
```

Expect cited results from `api/tasks.py` and `worker/consumer.py`. This demo uses lexical search and needs no extra packages, model, or API key. [Enable semantic search](#enable-semantic-search) when you are ready.

## Set up your team and personal repositories

Clone or mount your repositories first, using Git or your existing workspace harness. Then run this from the Context Engine checkout, replacing the example paths:

```sh
python3 -m context_engine init \
  --environment my-team \
  --workspace checkout \
  --repo api="$HOME/dev/api" \
  --repo worker="$HOME/dev/worker" \
  --personal-repo scratch="$HOME/dev/scratch" \
  --output "$HOME/.local/share/context-engine/checkout"
```

Repeat `--repo NAME=PATH` for team repositories; repeat or omit `--personal-repo` as needed. Paths can contain spaces. Use a dedicated output directory outside every source repository. The command validates local paths and rejects overlapping team/personal roots before writing files.

`init` creates:

| File | Purpose |
| --- | --- |
| `team.json` | Only your selected team repositories |
| `personal.json` | Only your personal repositories, when supplied |
| `context-engine.code-workspace` | VS Code folders for the engine integration and selected sources |
| `.vscode/tasks.json` | Watch, index, status, and search tasks for each scope |
| `.codex/config.toml` | Separate `context_engine_team` and optional `context_engine_personal` MCP servers |
| `AGENTS.md` | Retrieval, citation, scope, and repository-instruction guidance for agents |
| `README.md` | Instructions specific to the generated workspace |

It does not clone repositories, install packages, download models, launch VS Code, or change source files. New output directories are created with owner-only access. Keep an existing output directory private yourself. Generated paths are machine-local; keep this directory in your personal developer environment rather than sharing it with the team.

## Open it and start working

1. Open the generated `context-engine.code-workspace` in VS Code using **File → Open Workspace from File**.
2. Trust your selected workspace and allow automatic tasks if prompted. Otherwise run **Tasks: Run Task → Context Engine team: watch**, plus **Context Engine personal: watch** if configured.
3. Start Codex with **Context Engine** as its working folder. The project must be trusted for its `.codex/config.toml` to load. Reconnect/restart the client after changing configuration or engine code. [Official Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
4. Ask: **“Check the team index status, then find the implementation of [behavior]. Cite files and lines, and explain any gaps.”**

To use your notes, ask the agent to query the personal server too. It can combine authorized evidence in its answer; the engine does not merge the indexes. Keep personal evidence out of shared team deliverables.

The **watch** task indexes once, then refreshes saved changes. **status** shows freshness and semantic readiness; **index** refreshes once; **search** prompts for a terminal query. **Tasks: Terminate Task** stops a watcher. Closing its window normally stops the foreground task. The index persists in `state/team` and, if configured, `state/personal` beneath the generated directory.

For a terminal-only workflow, use the generated manifest:

```sh
python3 -m context_engine --manifest "$HOME/.local/share/context-engine/checkout/team.json" \
  --state "$HOME/.local/share/context-engine/checkout/state/team" watch
```

Run `search` or `status` in another terminal with the same manifest and state arguments. Global options (`--manifest`, `--state`) precede the command. `python3 -m context_engine init --help` and `python3 -m context_engine --help` list the options.

## Enable semantic search

The optional reference adapter embeds locally using cached model weights. Create an isolated environment and explicitly download the public model:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-semantic.txt
.venv/bin/python -m context_engine init \
  --environment my-team --workspace checkout \
  --repo api="$HOME/dev/api" --repo worker="$HOME/dev/worker" \
  --personal-repo scratch="$HOME/dev/scratch" \
  --semantic \
  --output "$HOME/.local/share/context-engine/checkout-semantic"
.venv/bin/python prefetch_model.py --cache-folder "$HOME/.local/share/context-engine/checkout-semantic/models"
```

The generated manifests point at the prefetched `models` directory. Open the new workspace after prefetch finishes. The generated tasks capture the interpreter used to run `init`, so use `.venv/bin/python` for this setup. No JSON editing is required.

Once indexed, check `semantic.state: ready`. `auto` uses hybrid retrieval when embeddings are configured; `--mode lexical`, `semantic`, or `hybrid` selects a mode explicitly. Semantic failure is reported, with lexical fallback in hybrid mode. Source text is processed locally by this reference adapter; it is not uploaded during model download. [Adapter details, measured results, and limitations](docs/SEMANTIC-REFERENCE.md)

## Change configuration or integrate an existing harness

Rerunning an identical `init` command is idempotent. To change repositories, mode, or interpreter, create a fresh output directory and open it. Setup refuses to overwrite edited generated files. Advanced users can edit manifests and maintain their launch configuration manually; source scope changes start a new index, and old stores are retained until you remove them.

Already have a harness? Keep its launcher. Supply local source manifests, start a watcher per scope, and register a read-only MCP `serve` process for each. The company layer can resolve GitHub repos and the current user's personal repo before invoking setup, or consume the same manifest/server interfaces directly. An internal embedding API implements `EmbeddingProvider`; it does not require rewriting the engine.

- [Configuration and existing-harness integration](docs/CONFIGURATION.md)
- [Agent usage guide](docs/AGENT-USAGE.md)
- [Semantic provider interface](docs/SEMANTIC-REFERENCE.md)

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| MCP tools missing | Use the generated **Context Engine** working folder, trust the project, and reconnect the client. Confirm `.codex/config.toml` names the expected interpreter and manifest. |
| `unindexed` or `stale` | Start the matching **watch** task or run **index**. Retrieval deliberately withholds stale source evidence. |
| Sources ready, semantic pending/error | Check `semantic.last_index`, install the optional dependencies into the captured interpreter, prefetch the pinned model into the configured cache, then run **index**. |
| Personal results missing | Query `context_engine_personal`; they are intentionally absent from the team server. |
| “Existing file differs” | Preserve your edits and generate into a new directory. There is no overwrite flag. |
| “Source directory does not exist” | Clone/mount the checkout first. `init` accepts local directories, not GitHub URLs. |
| Irrelevant semantic matches | Inspect the cited code; similarity is not proof a behavior exists. Try lexical mode for exact identifiers. The prototype has no calibrated semantic rejection threshold. |

## Limits and development

This is single-user software, not a shared service or multi-user authorization layer. Separate stores do not replace company access controls. Code, personal notes, vectors, and derived data belong in their approved environment. Scans honor supported-file and exclusion rules; they are not a secret scanner. Read [configuration details](docs/CONFIGURATION.md) before attaching a broad directory.

Python has AST excerpts; other supported languages use text windows. There is no resolved call graph. Evidence budgets use serialized UTF-8 bytes as a conservative token estimate, not actual model tokens. Exact vector scanning and polling suit small local corpora; source edits can race scans. Semantic/hybrid modes still return nearest neighbors for unsupported questions.

```sh
python3 -m unittest discover -s tests -v
python3 evaluate.py
```

[Development and evaluation](docs/DEVELOPMENT.md) explains optional real-model tests and the small published benchmarks. The intended license remains Apache-2.0, pending a license file and distribution-rights review; this commit is a local checkpoint, not a public release.
