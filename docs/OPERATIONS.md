# Run, refresh and recover

Use the same manifest and state directory in the IDE, CLI and MCP configuration. A different state path can make existing reviewed knowledge appear missing.

## Start with workspace health

Open Workspace Health to inspect the selected scope and index. Confirm the intended repositories before refreshing. General installation and generated-workspace instructions are in the [portable core guide](CORE-GUIDE.md); machine-specific dogfooding instructions are in [Dogfooding](DOGFOODING.md).

## Refresh changed code

1. Save the source changes.
2. Run Refresh Code, or the prepared workspace's index command.
3. Reopen the affected reading or retrieval view and confirm the index is current.
4. If Python engine code changed, reconnect MCP. If extension code or its bundled backend changed, rebuild and reload the installed extension.

Refresh Code and History also collects configured history. Use the code-only action when history is outside the authorized scope. Refreshing evidence does not reapprove stale knowledge.

## Diagnose common problems

- **The view says stale:** refresh, then reopen it. If files keep changing, wait for the writer to finish before retrying.
- **A known file is missing:** check source roots, exclusions, supported file types and parser coverage. A search miss is not proof that the file or behavior is absent.
- **Reviewed guidance is missing:** confirm the source, state mapping, applicability conditions and approval status. Changed cited evidence requires review again.
- **The engine still behaves like the previous version:** reconnect the MCP process after Python edits; rebuilding alone does not reload a running process.
- **A generated workspace no longer matches configuration:** generate to a fresh directory or use the documented preserve-edits workflow. Keep the existing state mapping if you intend to retain knowledge.

## Verify recovery

Confirm Workspace Health, repeat the original query with a narrow source/path filter, and open a cited file. For implementation changes, run the checks in [Development and verification](DEVELOPMENT.md). Record any remaining omissions rather than treating a successful refresh as proof of a complete result.

## Preserve local state

Keep the previous generated workspace when changing launch configuration. There is no general schema migration framework or production daemon supervisor. Do not use a live development store as an older-version rollback fixture. Review the local data inventory before resetting anything.

See [Configuration and integration](CONFIGURATION.md) for state identity, launch commands and generated-workspace updates, and [Knowledge maintenance](KNOWLEDGE-MAINTENANCE.md) for stale guidance.
