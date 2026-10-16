"""Generate a dedicated local VS Code/Codex workspace without global edits."""

import json
import os
import shutil
import sys
from pathlib import Path
from uuid import uuid4


class WorkspaceConflict(ValueError):
    pass


def render(engine, output=None):
    root = Path(__file__).resolve().parents[1]
    target = (
        Path(output).resolve() if output else engine.store.parent / (engine.store.stem + "-vscode")
    )
    target = target.resolve()
    launcher = os.environ.get("CONTEXT_ENGINE_PYTHON_LAUNCHER", sys.executable)
    command = shutil.which(launcher)
    if not command:
        raise ValueError(
            "Configured Python launcher is unavailable; check CONTEXT_ENGINE_PYTHON_LAUNCHER"
        )
    command = str(Path(command).absolute())
    args = [
        "-m",
        "context_engine",
        "--manifest",
        str(engine.manifest),
        "--state",
        str(engine.state),
    ]
    from .policy import load, within

    policy = getattr(engine, "policy", None) or load()
    if policy:
        if not within(target, policy["storage_roots"]):
            raise ValueError("Generated workspace is outside approved storage roots")
        args.extend(["--policy", os.environ["CONTEXT_ENGINE_POLICY"]])
    if os.environ.get("CONTEXT_ENGINE_REVIEW_POLICY"):
        from .governance import policy as review_policy

        review_policy()
        args.extend(["--review-policy", os.environ["CONTEXT_ENGINE_REVIEW_POLICY"]])
    tasks = []
    for action in ("watch", "index", "status", "crawl", "overview"):
        task = {
            "label": "Context Engine: " + action,
            "type": "process",
            "command": command,
            "args": args + [action],
            "options": {"cwd": str(root)},
            "problemMatcher": [],
            "presentation": {"reveal": "silent", "panel": "dedicated"},
        }
        if action == "watch":
            task.update(
                {"isBackground": True, "runOptions": {"runOn": "folderOpen", "instanceLimit": 1}}
            )
        elif action == "crawl":
            task.update({"isBackground": True, "runOptions": {"instanceLimit": 1}})
        tasks.append(task)
    tasks.append(
        {
            "label": "Context Engine: search",
            "type": "process",
            "command": command,
            "args": args + ["search", "${input:contextQuery}", "--token-budget", "8000"],
            "options": {"cwd": str(root)},
            "problemMatcher": [],
            "presentation": {"reveal": "always", "panel": "dedicated"},
        }
    )
    workspace = {
        "folders": [{"name": "Context Engine", "path": str(target)}]
        + [{"name": sid, "path": source["root"]} for sid, source in engine.sources.items()],
        "settings": {
            "terminal.integrated.cwd": str(target),
            "contextEngine.manifestPath": str(engine.manifest),
            "contextEngine.pythonPath": command,
            "contextEngine.statePaths": {str(engine.manifest): str(engine.state)},
        },
        "extensions": {"recommendations": ["openai.chatgpt"]},
    }

    def q(value):
        return json.dumps(value, ensure_ascii=False)

    config = "\n".join(
        [
            "# Generated Context Engine project configuration.",
            "[mcp_servers.context_engine]",
            "command = " + q(command),
            "args = " + q(args + ["serve"]),
            "cwd = " + q(str(root)),
            "",
        ]
    )
    readme = """# Context Engine workspace

Open `context-engine.code-workspace` in VS Code. The other Explorer folders are
the selected sources; this first folder holds the workspace's agent integration.

1. Trust this workspace if its sources are yours or approved.
2. Allow automatic tasks when VS Code prompts. Otherwise run **Tasks: Run Task →
   Context Engine: watch**. The watch terminal prints indexing coverage and updates.
3. Start a new Codex conversation with **Context Engine** as its working folder.
   Codex must trust this project to load `.codex/config.toml`. Restart the extension
   if configuration was added after the conversation started.
4. Ask: “Use Context Engine search_code to find the implementation of a behavior
   across this workspace. Cite the returned paths and lines.”

Use **Tasks: Run Task** for index, status, and interactive search. Use **Tasks:
Terminate Task** to stop the watcher. Closing the window stops the task under
normal VS Code task lifecycle; opening another window can start another watcher.

The **overview** task returns a small cited system map. Start **crawl** manually
for periodic code, architecture, embedding and history refresh. It uses existing
credentials and reports partial access; it is not started automatically by setup.

MCP is scoped to the Context Engine working folder. Conversations rooted directly
in a sibling source folder may not load this configuration. The selected manifest
is fixed in the generated config, and retrieval cannot switch environments.

Generated paths are machine-local. Regenerate after moving the engine, Python,
manifest, or source directories. No global Codex configuration or source repository
files are changed. This directory is generated; modified files are preserved by
refusing regeneration over differing content. Choose another output directory to
generate a fresh workspace.
"""
    files = {
        "context-engine.code-workspace": json.dumps(workspace, indent=2) + "\n",
        ".vscode/tasks.json": json.dumps(
            {
                "version": "2.0.0",
                "tasks": tasks,
                "inputs": [
                    {
                        "id": "contextQuery",
                        "type": "promptString",
                        "description": "Search workspace context",
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        ".codex/config.toml": config,
        "README.md": readme,
    }
    return target, files


def save_files(target, files):
    # Preflight all files before writing anything; never overwrite user edits.
    for name, text in files.items():
        path = target / name
        if path.is_symlink() or any(p.is_symlink() for p in path.parents):
            raise ValueError("Refusing symlink output: " + str(path))
        if path.exists() and (not path.is_file() or path.read_text() != text):
            raise WorkspaceConflict("Existing file differs; choose another --output: " + str(path))
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, text in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not path.exists():
            with path.open("x") as stream:
                stream.write(text)


def generate(engine, output=None, preserve_edits=False):
    target, files = render(engine, output)
    previous = None
    try:
        save_files(target, files)
    except WorkspaceConflict:
        if not preserve_edits:
            raise
        previous = str(target / "context-engine.code-workspace")
        target, files = render(engine, target.with_name(target.name + "-" + uuid4().hex[:12]))
        save_files(target, files)
    return {
        "workspace_file": str(target / "context-engine.code-workspace"),
        "codex_project": str(target),
        "manifest": str(engine.manifest),
        "state": str(engine.state),
        "preserved_workspace": previous,
        "next": "Open workspace in VS Code; allow trusted automatic tasks; start Codex from the Context Engine folder",
    }
