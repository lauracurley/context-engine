import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from context_engine.budget import encode
from context_engine.core import Engine
from context_engine.structure import extract

PARSERS = all(
    importlib.util.find_spec(name)
    for name in ("tree_sitter", "tree_sitter_javascript", "tree_sitter_typescript")
)


class StructureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        (self.repo / "worker.py").write_text("def run(value):\n    return value\n")
        (self.repo / "api.py").write_text(
            'from worker import run\ndef handle():\n    return run(1)\n# run() is a comment\nmessage = "run()"\n'
        )
        (self.repo / "other.py").write_text("def run():\n    pass\n")
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "environment": "team",
                    "workspace": "nav",
                    "sources": [{"id": "repo", "path": str(self.repo)}],
                }
            )
        )
        self.engine = Engine(self.manifest, self.root / "state")
        self.engine.index()

    def tearDown(self):
        self.engine.close()
        self.tmp.cleanup()

    def test_definitions_callers_ambiguity_and_dependencies(self):
        result = self.engine.structure.query(symbol="run")
        self.assertEqual({i["path"] for i in result["items"]}, {"worker.py", "other.py"})
        calls = self.engine.structure.query(mode="callers", symbol="run")["items"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["owner"], "handle")
        self.assertEqual(calls[0]["lines"], [3, 3])
        self.assertEqual(calls[0]["resolution"], "inferred")
        self.assertEqual(len(calls[0]["target_candidates"]), 2)
        dependencies = self.engine.structure.query(
            mode="dependencies", source="repo", path="api.py"
        )["items"]
        self.assertEqual(dependencies[0]["target_paths"], ["worker.py"])
        impact = self.engine.structure.query(mode="impact", source="repo", path="worker.py")[
            "items"
        ]
        self.assertTrue(any(i["path"] == "api.py" and i["kind"] == "import" for i in impact))
        self.assertTrue(all(i["path"] != "worker.py" for i in impact))
        for item in calls:
            self.assertTrue(
                self.engine.navigation.read(
                    item["source"], item["path"], expected_hash=item["hash"]
                )["items"]
            )

    def test_incremental_delete_stale_and_exclusions(self):
        self.assertEqual(self.engine.index()["structure"]["changed"], 0)
        (self.repo / "worker.py").write_text("def renamed():\n    pass\n")
        self.assertEqual(self.engine.structure.query(symbol="run")["state"], "stale")
        self.assertEqual(self.engine.index()["structure"]["changed"], 1)
        (self.repo / "other.py").unlink()
        self.assertEqual(self.engine.index()["structure"]["deleted"], 1)
        self.assertFalse(self.engine.structure.query(symbol="run")["items"])
        self.engine.excludes.append("api.py")
        self.engine.index()
        self.assertFalse(self.engine.structure.query(mode="callers", symbol="run")["items"])

    def test_budget_validation_and_no_scope_escape(self):
        result = self.engine.structure.query(token_budget=1024)
        self.assertLessEqual(len(encode(result).encode()), 1024)
        self.assertEqual(result["budget"]["used_bytes"], len(encode(result).encode()))
        self.assertGreater(result["budget"]["omitted_items"], 0)
        for kwargs in (
            {"source": "private"},
            {"mode": "impact", "source": "repo", "path": "../private.py"},
            {"mode": "callers"},
            {"limit": True},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.engine.structure.query(**kwargs)

    def test_parse_failure_and_parser_absence(self):
        self.assertTrue(extract("broken.py", "def ???")["gaps"])
        with patch.dict(sys.modules, {"tree_sitter": None}):
            data = extract("a.js", "function go() {}")
            self.assertTrue(data["gaps"])
            self.assertFalse(data["facts"])
        (self.repo / "broken.py").write_text("def ???")
        self.engine.index()
        result = self.engine.structure.query()
        self.assertEqual(result["state"], "partial")
        self.assertEqual(result["coverage"]["parse_gap_files"], 1)

    @unittest.skipUnless(PARSERS, "Install requirements-navigation.txt for real JS/TS parsing")
    def test_real_javascript_typescript_tsx_and_strings(self):
        for suffix in ("js", "ts", "tsx"):
            data = extract(
                "app." + suffix,
                'import { run } from "./worker";\nexport function handle() { return run(); }\nconst arrow = () => run();\n// fake()\nconst text = "fake()";\n',
            )
            self.assertFalse(data["gaps"], data)
            calls = [f for f in data["facts"] if f["kind"] == "call"]
            self.assertEqual([f["name"] for f in calls], ["run", "run"])
            self.assertEqual([f["owner"] for f in calls], ["handle", "arrow"])
        self.assertTrue(extract("bad.ts", "export function {")["gaps"])
        (self.repo / "worker.ts").write_text("export function run(): number { return 1; }")
        (self.repo / "app.tsx").write_text(
            'import { run } from "./worker";\nexport const Widget = () => <div>{run()}</div>;'
        )
        self.engine.index()
        result = self.engine.structure.query(mode="dependencies", source="repo", path="app.tsx")
        self.assertEqual(result["items"][0]["target_paths"], ["worker.ts"])

    def test_cli_mcp(self):
        command = [
            sys.executable,
            "-m",
            "context_engine",
            "--manifest",
            str(self.manifest),
            "--state",
            str(self.root / "state"),
        ]
        result = subprocess.run(
            [*command, "structure", "--mode=callers", "--symbol=run"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(len(json.loads(result.stdout)["items"]), 1)
        requests = [
            {"jsonrpc": "2.0", "id": 0, "method": "initialize"},
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "navigate_structure",
                    "arguments": {"mode": "callers", "symbol": "run"},
                },
            },
        ]
        result = subprocess.run(
            [*command, "serve"],
            input="\n".join(map(json.dumps, requests)) + "\n",
            capture_output=True,
            text=True,
            check=True,
        )
        value = json.loads(result.stdout.splitlines()[-1])["result"]
        self.assertFalse(value["isError"])
        self.assertEqual(len(json.loads(value["content"][0]["text"])["items"]), 1)
