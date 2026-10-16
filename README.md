# Context Engine

**Cited company context for coding agents, directly in VS Code.** Search selected repositories, inspect architecture and code relationships, and maintain reviewed team knowledge in Commonplace. The portable engine runs locally and exposes compact retrieval through MCP.

## Start in VS Code

The client preview targets **macOS Apple Silicon**. Your team supplies the reviewed `context-engine-0.6.0.vsix` and a prepared Python runtime. The extension bundles the engine code, but **does not bundle Python or install parser packages**. Runtime preparation is a one-time team setup task; daily use does not require terminal scripts.

1. In VS Code, run **Extensions: Install from VSIX** and select the supplied package.
2. Open your repository folders. Trust the workspace when appropriate, then open **Context Engine** in the sidebar and select **Get started**.
3. Run **Check Python and Kotlin setup**. Set **Context Engine: Python Path** to the executable your team supplies. Missing Python offers a settings shortcut and runtime help; missing Kotlin parsing is reported explicitly.
4. Choose repository folders to create a **Team** or **Personal** scope, or select an existing team-supplied configuration. Only folders you select enter the new scope; no JSON editing is needed for this basic setup.
5. Select **Refresh code**, then **Open Codex IDE workspace**. Open the generated workspace and use your approved Codex extension account. This route does not require the Codex CLI or a terminal login.

The generated workspace includes integration files and a code watcher. Allow its automatic task when VS Code prompts, or start the matching watch task from **Tasks: Run Task**. Start conversations in the generated **Context Engine** folder so its project MCP configuration is loaded. **Workspace health** checks index freshness, coverage, semantic availability and refresh tasks observed in this window. It does not verify an agent account or live MCP connection. Opening the IDE workspace reuses unchanged integration files; runtime/configuration changes create a new workspace, and edited generated files are preserved.

Preparing the client installation? Read [Client setup](docs/CLIENT-SETUP.md). Developing the engine? Start with [Development and verification](docs/DEVELOPMENT.md). Using the core in another workflow? See the [portable core guide](docs/CORE-GUIDE.md).

## Everyday work

- **Context workbench:** search code, inspect cited evidence, and assemble bounded task context before handing it to an agent. You can use it without starting an agent.
- **Change context:** choose a repository and Git base, read changed code, applicable guidance and possible tests, then add the complete brief and its coverage limits to a task pack.
- **Team knowledge:** browse all five knowledge types, choose supporting source evidence, write a proposal in a guided form, and explicitly approve, reject or retire it. Stale records lead to re-review drafts. Agents receive only applicable approved current guidance.
- **Task packs:** prepare a local handoff, copy its prompt and use it in your approved IDE agent. Handoff rechecks citations and never invokes the legacy terminal launcher.
- **Workspace health:** check the selected repositories, refresh code, and start/stop code refresh observed in this window.
- **Commonplace team knowledge:** map a team repository to a local snapshot directory, then explicitly export or preview/import edits. Imported edits become proposals; they do not approve themselves. Repository synchronization is not automatic.
- **Maintain local knowledge:** inspect stale records, exact duplicates and feedback, and prepare drafts for human re-review.
- **New Scratch reasoning note:** start an empty working note. Scratch holds exploration; Commonplace holds curated team conclusions. No hidden model reasoning or conversation is captured.

Use **Show advanced actions** for Commonplace snapshots, static wiki, maintenance, Scratch notes, profiles, advanced imports/relationships, benchmarks, client readiness, reviewed usage reports, diagnostics, and legacy integrations. Every command remains available from the Command Palette. Legacy terminal flows are blocked under the managed pilot policy.

## Local company knowledge, no vendor collection

The client-local engine intentionally knows the selected company repositories and retains approved local indexes and derived knowledge. **The Context Engine vendor must not receive company code, prompts, repository references, indexes, or derived knowledge.** There is no usage-report uploader. Optional reports contain a fixed schema of aggregate statistics; users preview/save them and the client vets them before any manual sharing.

Your selected coding agent receives the evidence you use with it and has its own account and data policies. Context Engine's vendor boundary is separate from that agent's behavior. See the [vendor data boundary and repeatable check](docs/security/VENDOR-DATA-BOUNDARY.md).

## Scope and current limits

The extension and portable core live in one repository. Separate Team and Personal scopes have separate indexes; work-related Scratch still belongs in the company-controlled environment. Commonplace uses local maintainer review for this MVP, with no shared approval server.

Retrieval includes lexical search, bounded reads, structural navigation, cached architecture facts/relationships, and optional semantic/hybrid adapters. Kotlin navigation uses syntax parsing, not a compiler-resolved call graph. The restricted client profile excludes optional semantic models and several remote/history features. Response budgets bound serialized UTF-8 bytes; they are not measured model tokens or dollar savings.

This is the **0.6.0 alpha candidate**; follow the [alpha acceptance checklist](docs/ALPHA-ACCEPTANCE.md). Client runtime preparation, fresh-Mac testing, account integration and release approval remain explicit steps. Cross-record relationships, extra supporting citations and imported-review provenance still use advanced local JSON workflows. Guided drafts are held in the open panel; save a proposal before closing or reloading VS Code. Built-in synthetic benchmarks measure fixture behavior, not client task success.

Refresh timing saved through **Profile** preserves your current index, knowledge and packs. Repository/retrieval changes explicitly create a separate scope; the old scope remains selectable. Direct edits to a manifest still use configuration-specific store identities.

## Guides

- [Alpha acceptance and known limits](docs/ALPHA-ACCEPTANCE.md)
- [Dogfooding the engine and Scratch](docs/DOGFOODING.md)

- [Extension commands and troubleshooting](vscode-extension/README.md)
- [Client setup and handoff](docs/CLIENT-SETUP.md)
- [Portable core commands and integration](docs/CORE-GUIDE.md)
- [Development, tests and packaging](docs/DEVELOPMENT.md)
- [Commonplace](docs/COMMONPLACE.md), [knowledge workflows](docs/LAUNCH-WORKFLOWS.md), [maintenance](docs/KNOWLEDGE-MAINTENANCE.md)
- [Change briefs and reviewed lesson workflow](docs/P1-WORKFLOWS.md)
- [Client-test readiness and release gates](docs/security/CLIENT-TEST-READINESS.md), [dependency review](docs/security/RELEASE-DEPENDENCY-REVIEW.md)

### GitHub review learning through the client gateway

Use **Context Engine: Learn from GitHub Reviews** to prepare a scoped prompt for
your connected agent, read its collected evidence and review proposed guidelines.
See [the gateway review-learning guide](docs/GITHUB-REVIEW-LEARNING.md) for the
three output layers, Commonplace review loop and collection limits.
