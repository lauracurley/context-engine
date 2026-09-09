# Configuration and integration

Start with [the README's init command](../README.md#set-up-your-team-and-personal-repositories). This page covers manual configuration and company adapters.

## Source manifests

A server is bound to one manifest. There is no query parameter for changing its environment or sources.

```json
{
  "schema_version": 1,
  "environment": "my-company",
  "workspace": "checkout",
  "sources": [
    {"id": "api", "type": "git", "path": "../repos/api"},
    {"id": "worker", "type": "git", "path": "../repos/worker"}
  ],
  "exclude": ["private/*", "**/private/**"]
}
```

| Field | Meaning |
| --- | --- |
| `schema_version` | Must be `1` |
| `environment`, `workspace` | 1–80 letters, digits, underscores, or hyphens; explicit scope identifiers |
| `sources[].id` | Unique simple name within this manifest |
| `sources[].path` | Local directory; relative paths resolve against the manifest, not the shell working directory |
| `sources[].type` | `git` or `files` for supported content in an existing directory; `markdown` limits content to `.md` |
| `exclude` | Optional Python `fnmatch` patterns against source-relative paths |
| `embeddings` | Optional local reference provider configuration; see [the semantic guide](SEMANTIC-REFERENCE.md) |

`git` does not clone or fetch. Both `files` and `git` use Git-aware discovery when the directory is in a checkout. Git ignores apply to untracked files; tracked files are still eligible. Non-Git directories use traversal and built-in exclusions, not `.gitignore` parsing. Source roots may point to subdirectories of a checkout.

Supported extensions: Python, Kotlin, Java, TypeScript/TSX, JavaScript/JSX, HTML, CSS, YAML, JSON, Markdown, TOML, SQL, and GraphQL. Symlinks, build/vendor folders, `.env*`, binary or invalid UTF-8 content, files above 512 KB, and the chosen state directory are excluded. These rules are not a comprehensive secret detector. Use narrow source roots and explicit exclusions.

## Team versus personal configuration

`init` creates separate manifests, state directories, and MCP processes. Personal repositories can contain code or notes; the same supported-file rules apply. To index only Markdown, maintain a personal manifest with `type: "markdown"` manually. The setup command rejects overlap across scopes; direct manifests do not enforce that cross-manifest check, so integrations must validate their selections too.

The generated directory is per-developer configuration. Never distribute it as a shared team deployment: it names that developer's personal sources. A company harness should determine the authenticated user, provision their personal repository, and call `init --personal-repo` only in that user's private environment. The engine does not infer usernames, expand GitHub repository templates, or authorize access by itself.

For a team-only installation, omit `--personal-repo`. For a team service, implement authenticated access and storage controls before exposing MCP remotely. Current local separation is not multi-user authorization. Do not add personal sources to a team manifest or copy private evidence into shared derived artifacts.

## State and updates

`--state` chooses the store root; it defaults to `.context-engine` in the shell's current directory. Specify it explicitly in a harness. The store path includes environment, workspace, and a hash of resolved configuration. A change to source selection or embedding configuration starts a fresh store. Old stores are not automatically deleted.

`init` uses `<output>/state/team` and `<output>/state/personal`. The lexical and vector indexes remain scoped there. A common model-weight cache is safe for these two local scopes because model weights contain no repository content; source-derived embeddings are kept in their separate stores.

The foreground `watch` command indexes at startup and polls every two seconds by default. `--interval` controls polling. It does not install a background service, clone new revisions, or supervise a shared daemon. Existing source edits are detected, but source changes can race a final freshness scan. The platform should own managed startup/shutdown and single-writer coordination.

## Existing harness and agent clients

A company layer can use init to generate a local workspace, or retain its own VS Code workspace and use the generated launch values. Each server needs an executable, argument list, and working directory:

```text
command: /path/to/python
args: ["-m", "context_engine", "--manifest", "/path/to/team.json", "--state", "/path/to/state/team", "serve"]
cwd: /path/to/context-engine
```

Run the same command with `watch` instead of `serve` under the harness's lifecycle manager. Register a second server with the personal manifest/state only for its owner. In Codex TOML, give each server a distinct `[mcp_servers.NAME]` table. Preserve existing unrelated settings when integrating manually. The generated setup writes only its own dedicated directory and does not modify global agent configuration.

The reusable boundary is explicit local sources plus `EmbeddingProvider`. A company layer can resolve internal GitHub MCP results into checked-out/mounted directories, select personal repositories, supply approved credentials and an API-backed provider, and construct `Engine(manifest, state, embedding_provider=provider)`. Then expose that instance through the existing MCP `serve` function. Streaming remote repository ingestion, GitHub PR/history connectors, and remote authorization are not implemented in the local reference.

## Updating a generated workspace

Identical `init` inputs preserve existing files. Changed generated content is rejected before any files are written; there is no destructive overwrite option. Generate to a fresh directory when changing source selection, mode, or interpreter. A manually edited manifest can be used with explicit CLI/MCP commands; keep corresponding state paths and launch arguments consistent. Reconnect MCP processes after code or configuration changes.

Generated output and indexes are machine-local data. Keep them out of the engine source repository; `.context-engine/`, `.venv/`, and Python caches are ignored. The source repository contains public-safe examples and tests, not your work configuration or indexes.
