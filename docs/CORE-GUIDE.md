# Portable core and integration guide

For developers and company workflow integrators. VS Code users can follow the [extension quickstart](../README.md#start-in-vs-code) without running these commands. The extension uses this same core; a second repository or service is unnecessary.

Run the examples from the Context Engine repository root. General core development supports Python 3.9+ and Git. The restricted client deployment uses a separately pinned macOS runtime: see [Client setup](CLIENT-SETUP.md). Optional dependency profiles are not automatically approved for that deployment.

## Try lexical retrieval

```sh
python3 -m context_engine --manifest examples/acme.json index
python3 -m context_engine --manifest examples/acme.json search 'task.requested priority' --token-budget 8000
```

This synthetic example needs no extra packages, model or API key. Results include cited source locations. The historical `--token-budget` name bounds response bytes, not actual model tokens; do not use it to claim measured token or currency savings.

## Generate local workspace configuration

Clone or mount repositories using the company's existing tools first:

```sh
python3 -m context_engine init \
  --environment my-team --workspace checkout \
  --repo api="$HOME/dev/api" --repo worker="$HOME/dev/worker" \
  --personal-repo scratch="$HOME/dev/scratch" \
  --output "$HOME/.local/share/context-engine/checkout"
```

Repeat `--repo NAME=PATH` and optionally `--personal-repo` for other sources. Use a dedicated output directory outside every source repository. Setup validates paths and rejects overlapping Team/Personal roots. It writes scoped manifests, a VS Code workspace, watch/index tasks, scoped MCP configuration and agent instructions. It does not clone repositories, install packages or alter source files. Newly created output directories are private; paths are machine-local.

Open the generated workspace and run/allow the matching watch tasks. Team and Personal servers retain separate indexes. Ask the agent for focused cited evidence; use index status when diagnosing freshness or coverage, rather than prepending a full inventory to every lookup.

The generated workspace carries each manifest's state directory in `contextEngine.statePaths`, so the VS Code extension and MCP share index readiness and reviewed knowledge. See [state and updates](CONFIGURATION.md#state-and-updates) when upgrading an older workspace or attaching an existing store.

Identical `init` calls are idempotent. Use a fresh output directory when changing repositories, mode or interpreter; setup refuses to overwrite edited generated files. Old scoped stores are retained until explicitly removed. See [configuration and harness integration](CONFIGURATION.md) and [agent usage](AGENT-USAGE.md).

## Integrate another workflow

Supply scoped manifests and run a code watcher per scope; register the core's `serve` MCP process in the client integration. `python3 -m context_engine --help` describes available commands. Retrieval tools return compact evidence; explicit history ingestion and maintenance commands write approved local state. Company repository provisioning, credentials, identity and remote authorization belong in replaceable integrations.

Use `overview` for cached architecture facts, `discover` for filtered search and `read` for selected ranges. Syntax navigation and observed relationships do not establish a compiler-resolved graph. [Architecture](ARCHITECTURE.md) explains the interfaces and limitations.

## Optional semantic reference adapter

This local model adapter is for separately reviewed development/experimentation, outside the restricted client profile. Install dependencies and explicitly download the public model only in an approved environment:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-semantic.txt
.venv/bin/python -m context_engine init \
  --environment my-team --workspace checkout \
  --repo api="$HOME/dev/api" --semantic \
  --output "$HOME/.local/share/context-engine/checkout-semantic"
.venv/bin/python prefetch_model.py \
  --cache-folder "$HOME/.local/share/context-engine/checkout-semantic/models"
```

The generated tasks capture this interpreter. After indexing, check `semantic.state: ready`. `auto` uses hybrid retrieval when configured; explicit modes are `lexical`, `semantic` and `hybrid`. Hybrid reports semantic failures and can fall back to lexical results. Similarity is not proof of a behavior. The reference adapter processes source text locally; a custom provider requires its own data-boundary review. See [semantic adapter details and measured limits](SEMANTIC-REFERENCE.md).

## Optional history and scheduled refresh

```sh
python3 -m context_engine --manifest /path/to/team.json --state /path/to/state/team ingest-history
python3 -m context_engine --manifest /path/to/team.json --state /path/to/state/team search-history 'task retries'
```

History ingestion is explicit, normally covering six calendar months; it uses configured adapters or authorized GitHub/local Git evidence and reports missing access. It is not part of the normal code watcher. The separate `crawl` command can schedule code and history collection; `--no-history` disables history. No daemon is installed automatically. These features can be disabled by deployment policy. See [history providers, coverage and retention](HISTORY.md).

Reviewed team practices and other knowledge use [Commonplace](COMMONPLACE.md), [local review workflows](LAUNCH-WORKFLOWS.md) and [maintenance](KNOWLEDGE-MAINTENANCE.md). Imported reviews are evidence/proposals, not automatically accepted rules.

## Verification and distribution

Use [Development and verification](DEVELOPMENT.md) for tool installation, linting, tests, benchmark gates and VSIX packaging. Those quality tools govern this product's repository; they are not rules installed into client repositories. Client toolchain discovery remains a planned feature.

Synthetic benchmarks measure fixture retrieval and serialized payload size, not production correctness or realized cost savings. Client data and generated artifacts stay in the approved local environment. Consult the [vendor boundary](security/VENDOR-DATA-BOUNDARY.md) and [release dependency review](security/RELEASE-DEPENDENCY-REVIEW.md) before distributing a client build.
