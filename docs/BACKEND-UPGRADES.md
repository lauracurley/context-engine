# Backend upgrades and reconnects

An extension window, generated watcher and MCP server can each load a different
backend. Upgrading files does not replace Python code already loaded in a process.
Use Workspace Health to inspect **Backend release**, **Backend build**, **Index
writer build**, compatibility and recovery. MCP users can call `index_status`
through that connection and compare `runtime.loaded` with the intended build.
A healthy extension check cannot establish that the agent's MCP process is current.

The 0.6.1 candidate records the writer's engine-source build ID with each index.
A missing or different writer ID makes current retrieval stale even if source
files have not changed. Updated processes refuse writes if their backend files
change on disk; restart them to load the replacement. The build ID is independent
of installation path, but it is not a signature or proof of publisher authenticity.
It covers engine Python files, not the interpreter, dependencies or extension JS.
Build IDs and detailed health remain local diagnostics, outside usage exports.

## Deliberate upgrade sequence

1. Finish the active task and preserve edits. Identify all writers for the scope,
   including other windows and external terminals. Health's **Stop code refresh**
   control stops only tasks observed in this window; it does not stop other hosts.
2. Stop the identified refresh tasks through their owning window or terminal.
   Stop an MCP writer through the host's supported lifecycle controls when needed.
   Never infer that all writers stopped merely because one window reports none.
3. Install the reviewed extension candidate and update any standalone engine
   launchers to the same intended build. Keep configured wrappers, policy paths,
   manifests and state paths. Do not delete the index or migrate reviewed knowledge.
4. Use the host's supported reload/reconnect mechanism at a task boundary. If the
   host offers no verified reconnect action, start a new supported session and
   check it; this extension does not kill arbitrary processes or invent a restart
   command. Installation and active-window reload remain deliberate user actions.
5. Refresh **code only**, then check Health. Through each MCP connection call
   `index_status`; compare loaded and writer build IDs and require `current`.
   Run a hash-checked read. Restart the intended watcher and recheck after its
   refresh. If identities alternate, locate the remaining older writer.

Pre-0.6.1 processes cannot adopt the new fence retroactively. They can still write
old metadata, and their own readers do not check build IDs. Updated readers detect
that downgrade and withhold evidence; coordinated retirement of those processes
is still required. There is no claim of cross-process supervision, automatic
migration, rollback or universal protection from an unmodified old executable.

Stores, approved source scope and knowledge are preserved. Usage opt-in is
release-scoped; the new release starts with reporting disabled. No client data,
paths, code or build diagnostics are uploaded by this workflow.

Public host references (checked 2026-09-15): VS Code documents
[Restart Extensions after updates](https://code.visualstudio.com/docs/configure/extensions/extension-marketplace)
and [persistent terminal reconnection after reload](https://code.visualstudio.com/docs/terminal/advanced).
Consequently, restarting extensions or reloading a window alone is not evidence
that a terminal watcher restarted. Keep the explicit stop/restart and identity
check steps above. For remote work, verify the
[actual extension host](https://code.visualstudio.com/api/advanced-topics/remote-extensions).
