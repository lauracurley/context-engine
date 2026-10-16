import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from context_engine.core import Engine
from context_engine.vscode import generate


class VSCodeTests(unittest.TestCase):
    def test_generated_commands_and_mcp_work_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="context workspace ") as temp:
            root = Path(temp)
            source = root / "source files"
            source.mkdir()
            (source / "main.py").write_text("def launch_rocket():\n    return 'LIFTOFF'\n")
            manifest = root / "workspace.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "environment": "test",
                        "workspace": "rocket",
                        "sources": [{"id": "code", "path": str(source)}],
                    }
                )
            )
            e = Engine(manifest, root / "state")
            try:
                generated = generate(e)
                folder = Path(generated["codex_project"])
                self.assertEqual(generated, generate(e))
                workspace = json.loads(Path(generated["workspace_file"]).read_text())
                self.assertEqual(workspace["folders"][1]["path"], str(source.resolve()))
                self.assertEqual(
                    workspace["settings"]["contextEngine.statePaths"],
                    {str(e.manifest): str(e.state)},
                )
                tasks = json.loads((folder / ".vscode/tasks.json").read_text())["tasks"]
                for action in ("index", "status"):
                    task = next(t for t in tasks if t["label"].endswith(action))
                    completed = subprocess.run(
                        [task["command"]] + task["args"],
                        cwd=task["options"]["cwd"],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    self.assertTrue(json.loads(completed.stdout))
                # Config strings use the JSON subset of TOML basic strings/arrays.
                config = dict(
                    line.split(" = ", 1)
                    for line in (folder / ".codex/config.toml").read_text().splitlines()
                    if " = " in line
                )
                launch = {key: json.loads(value) for key, value in config.items()}
                requests = [
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {"protocolVersion": "2025-11-25"},
                    },
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": "search_context", "arguments": {"query": "LIFTOFF"}},
                    },
                ]
                result = subprocess.run(
                    [launch["command"]] + launch["args"],
                    cwd=launch["cwd"],
                    input="\n".join(json.dumps(r) for r in requests) + "\n",
                    capture_output=True,
                    text=True,
                    check=True,
                )
                reply = json.loads(result.stdout.splitlines()[-1])
                self.assertTrue(json.loads(reply["result"]["content"][0]["text"])["items"])
                (folder / "README.md").write_text("My edits")
                with self.assertRaisesRegex(ValueError, "Existing file differs"):
                    generate(e)
                self.assertEqual((folder / "README.md").read_text(), "My edits")
                replacement = generate(e, preserve_edits=True)
                self.assertEqual(replacement["preserved_workspace"], generated["workspace_file"])
                self.assertNotEqual(replacement["codex_project"], generated["codex_project"])
                reopened = generate(e, replacement["codex_project"], preserve_edits=True)
                self.assertEqual(reopened["workspace_file"], replacement["workspace_file"])
                self.assertIsNone(reopened["preserved_workspace"])
                self.assertEqual((folder / "README.md").read_text(), "My edits")
            finally:
                e.close()


class LauncherTests(unittest.TestCase):
    def test_explicit_launcher_is_preserved(self):
        import os
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch

        from context_engine.vscode import render

        with tempfile.TemporaryDirectory(prefix="launcher with spaces ") as temp:
            root = Path(temp)
            wrapper = root / "python wrapper"
            # A standalone launcher supplies an otherwise absent initialization marker.
            wrapper.write_text(
                "#!"
                + sys.executable
                + "\nimport os, sys\nos.environ['WRAPPER_READY']='yes'\nos.execv(sys.executable, [sys.executable] + sys.argv[1:])\n"
            )
            wrapper.chmod(0o700)
            engine = SimpleNamespace(
                manifest=root / "manifest.json", state=root / "state", sources={}
            )
            with patch.dict(os.environ, {"CONTEXT_ENGINE_PYTHON_LAUNCHER": str(wrapper)}):
                _, files = render(engine, root / "workspace")
                workspace = json.loads(files["context-engine.code-workspace"])
                self.assertEqual(workspace["settings"]["contextEngine.pythonPath"], str(wrapper))
                tasks = json.loads(files[".vscode/tasks.json"])["tasks"]
                self.assertTrue(all(task["command"] == str(wrapper) for task in tasks))
                clean = {
                    k: v
                    for k, v in os.environ.items()
                    if k.startswith("DYLD_") or k in ("PATH", "SYSTEMROOT")
                }
                result = subprocess.run(
                    [tasks[0]["command"], "-c", "import os; print(os.environ['WRAPPER_READY'])"],
                    env=clean,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                self.assertEqual(result.stdout.strip(), "yes")
                self.assertIn(json.dumps(str(wrapper)), files[".codex/config.toml"])
            with patch.dict(os.environ, {"CONTEXT_ENGINE_PYTHON_LAUNCHER": str(root / "missing")}):
                with self.assertRaisesRegex(ValueError, "launcher is unavailable"):
                    render(engine, root / "workspace")
