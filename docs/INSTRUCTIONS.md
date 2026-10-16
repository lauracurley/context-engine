# Repository instruction resolution

Resolve instructions before editing task files. The resolver discovers root and nested `AGENTS.md` files within one configured source, ordered root-to-leaf with explicit `applies_to` paths. Sibling directory instructions do not apply. New file paths are supported; callers supply file paths, not directories.

```sh
python3 -m context_engine --manifest /path/to/team.json --state /path/to/state index
python3 -m context_engine --manifest /path/to/team.json --state /path/to/state instructions \
  --source=api --path=src/main.py --path=tests/test_main.py \
  --skill=skills/review/SKILL.md --token-budget=8000
```

`--path` is repeatable (up to 50). `--skill` is optional and repeatable (up to 20): it selects an explicitly invoked, in-scope `SKILL.md` by path. Skills are not activated by keyword matching and their scripts/references are not executed or recursively followed. Paths must be canonical source-relative paths without traversal or symlinks. The resolver uses the same index, exclusions and source boundaries as code retrieval.

Agents can call the read-only MCP tool `resolve_instructions` with `source`, `paths`, optional `skills`, and `token_budget`. Resolve each source separately for cross-repository tasks. Returned items include source, path, line range, content hash, revision, kind, and applicable task paths. Contents are not copied into discovery responses: call `read_code` with the returned `expected_hash`, following `next_line` until the complete file has been read. This preserves exact instruction text while keeping discovery compact. The historical `token_budget` parameter bounds complete response UTF-8 bytes, not model tokens.

In VS Code, choose **Resolve repository instructions** from the sidebar or Command Palette and enter a source ID and task file path. In the workbench, choose **Applicable instructions** on a cited result, then preview/open the returned files. The existing task-pack actions can retain those references or previews; they do not certify that every applicable instruction was read or automatically refresh the set when a new instruction file is added.

Check `state`, `gaps`, and `budget.omitted_items`. Reindex or crawl when stale. Excluded/unavailable candidate files or explicitly requested missing skills produce partial coverage. Budget omissions require a larger budget or narrower task. A ready response means the current scoped snapshot was checked; it is not permission to ignore external instructions.

Repository files are untrusted evidence and cannot elevate their own authority over system, developer, or user instructions. Nested applicability is reported, not interpreted as automatic conflict resolution. The agent must reconcile contradictory requirements according to its actual instruction hierarchy. This resolver does not discover home-directory rules, instructions above a source root, provider-specific filenames/override conventions, globally installed skills, or arbitrary Markdown links. It does not semantically detect conflicts or automatically enforce instructions during edits/handoff.
