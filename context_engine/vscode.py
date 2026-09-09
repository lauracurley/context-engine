"""Generate a dedicated local VS Code/Codex workspace without global edits."""
import json
from pathlib import Path
import sys


def render(engine, output=None):
    root = Path(__file__).resolve().parents[1]
    target = Path(output).resolve() if output else engine.store.parent / (engine.store.stem + "-vscode")
    target = target.resolve()
    command = str(Path(sys.executable).absolute())
    args = ["-m", "context_engine", "--manifest", str(engine.manifest), "--state", str(engine.state)]
    tasks = []
    for action in ("watch", "index", "status"):
        task = {"label": "Context Engine: " + action, "type": "process", "command": command,
                "args": args + [action], "options": {"cwd": str(root)}, "problemMatcher": [],
                "presentation": {"reveal": "silent", "panel": "dedicated"}}
        if action == "watch":
            task.update({"isBackground": True, "runOptions": {"runOn": "folderOpen", "instanceLimit": 1}})
        tasks.append(task)
    tasks.append({"label": "Context Engine: search", "type": "process", "command": command,
                  "args": args + ["search", "${input:contextQuery}", "--token-budget", "8000"],
                  "options": {"cwd": str(root)}, "problemMatcher": [], "presentation": {"reveal": "always", "panel": "dedicated"}})
    workspace = {"folders": [{"name": "Context Engine", "path": str(target)}] +
                 [{"name": sid, "path": source["root"]} for sid, source in engine.sources.items()],
                 "settings": {"terminal.integrated.cwd": str(target)},
                 "extensions": {"recommendations": ["openai.chatgpt"]}}
    q = lambda value: json.dumps(value, ensure_ascii=False)
    config = "\n".join(["# Generated Context Engine project configuration.",
                        "[mcp_servers.context_engine]", "command = " + q(command),
                        "args = " + q(args + ["serve"]), "cwd = " + q(str(root)), ""])
    readme = """# Context Engine workspace

Open `context-engine.code-workspace` in VS Code. The other Explorer folders are
the selected sources; this first folder holds the workspace's agent integration.

1. Trust this workspace if its sources are yours or approved.
2. Allow automatic tasks when VS Code prompts. Otherwise run **Tasks: Run Task →
   Context Engine: watch**. The watch terminal prints indexing coverage and updates.
3. Start a new Codex conversation with **Context Engine** as its working folder.
   Codex must trust this project to load `.codex/config.toml`. Restart the extension
   if configuration was added after the conversation started.
4. Ask: “Use Context Engine index_status, then find the implementation of a behavior
   across this workspace. Cite the returned paths and lines.”

Use **Tasks: Run Task** for index, status, and interactive search. Use **Tasks:
Terminate Task** to stop the watcher. Closing the window stops the task under
normal VS Code task lifecycle; opening another window can start another watcher.

MCP is scoped to the Context Engine working folder. Conversations rooted directly
in a sibling source folder may not load this configuration. The selected manifest
is fixed in the generated config, and retrieval cannot switch environments.

Generated paths are machine-local. Regenerate after moving the engine, Python,
manifest, or source directories. No global Codex configuration or source repository
files are changed. This directory is generated; modified files are preserved by
refusing regeneration over differing content. Choose another output directory to
generate a fresh workspace.
"""
    files = {"context-engine.code-workspace": json.dumps(workspace, indent=2) + "\n",
             ".vscode/tasks.json": json.dumps({"version": "2.0.0", "tasks": tasks,
                 "inputs": [{"id": "contextQuery", "type": "promptString", "description": "Search workspace context"}]}, indent=2) + "\n",
             ".codex/config.toml": config,
             "README.md": readme}
    return target, files


def save_files(target, files):
    # Preflight all files before writing anything; never overwrite user edits.
    for name, text in files.items():
        path = target / name
        if path.is_symlink() or any(p.is_symlink() for p in path.parents):
            raise ValueError("Refusing symlink output: " + str(path))
        if path.exists() and (not path.is_file() or path.read_text() != text):
            raise ValueError("Existing file differs; choose another --output: " + str(path))
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, text in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not path.exists():
            with path.open("x") as stream:
                stream.write(text)


def generate(engine, output=None):
    target, files = render(engine, output)
    save_files(target, files)
    return {"workspace_file": str(target / "context-engine.code-workspace"), "codex_project": str(target),
            "manifest": str(engine.manifest), "state": str(engine.state),
            "next": "Open workspace in VS Code; allow trusted automatic tasks; start Codex from the Context Engine folder"}
