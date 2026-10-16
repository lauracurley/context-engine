import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from context_engine.core import Engine

ROOT = Path(__file__).resolve().parents[1]


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / "examples", self.root / "examples")
        self.engines = []

    def tearDown(self):
        for engine in self.engines:
            engine.close()
        self.tmp.cleanup()

    def engine(self, name="acme"):
        engine = Engine(self.root / "examples" / (name + ".json"), self.root / "state")
        self.engines.append(engine)
        return engine

    def test_malformed_manifests_fail_before_creating_state(self):
        valid = {
            "schema_version": 1,
            "environment": "client",
            "workspace": "test",
            "sources": [{"id": "api", "path": "examples/acme/api"}],
        }
        invalid = [None, [], "text", dict(valid, schema_version=True)]
        invalid += [dict(valid, sources=[source]) for source in [None, [], "api"]]
        invalid += [
            dict(valid, sources=[{"id": "api", "path": value}])
            for value in [None, 1, [], "", "   "]
        ]
        invalid.append(dict(valid, sources=[{"id": "api"}]))
        manifest = self.root / "invalid.json"
        for value in invalid:
            with self.subTest(value=value):
                manifest.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    Engine(manifest, self.root / "invalid-state")
                self.assertFalse((self.root / "invalid-state").exists())

    def test_two_environments_and_budget(self):
        a, b = self.engine(), self.engine("harbor")
        a.index()
        b.index()
        found = a.search("task.requested priority", token_budget=8000)
        self.assertEqual({i["source"] for i in found["items"]}, {"api", "worker"})
        self.assertTrue(all(i["hash"] and i["evidence_id"] for i in found["items"]))
        self.assertEqual(b.search("UNKNOWN_TEMPLATE")["items"], [])
        self.assertEqual(a.search("parcelCode")["items"], [])
        self.assertTrue(b.search("parcelCode", token_budget=8000)["items"])
        self.assertLessEqual(found["budget"]["used_estimated_tokens"], 8000)
        self.assertEqual(a.search("task", token_budget=1)["items"], [])

    def test_budget_omissions_and_no_match_are_distinct(self):
        e = self.engine()
        e.index()
        full = e.search("task.requested priority", token_budget=8000)
        first = full["items"][0]
        cost = len(json.dumps(first, ensure_ascii=False).encode("utf-8"))
        partial = e.search("task.requested priority", token_budget=cost)
        self.assertEqual(partial["items"], [first])
        self.assertEqual(
            partial["budget"]["omitted_files"], [{"source": "api", "path": "tasks.py"}]
        )
        self.assertTrue(any("Evidence budget omitted" in gap for gap in partial["gaps"]))
        self.assertLessEqual(partial["budget"]["used_estimated_tokens"], cost)
        tiny = e.search("task.requested priority", token_budget=1)
        self.assertEqual(
            tiny["budget"]["omitted_files"],
            [{"source": "api", "path": "tasks.py"}, {"source": "worker", "path": "consumer.py"}],
        )
        self.assertIn("No matching evidence fits the budget", tiny["gaps"])
        missing = e.search("absentsentinel20260909", token_budget=1)
        self.assertEqual(missing["budget"]["omitted_files"], [])
        self.assertIn("No matching evidence", missing["gaps"])
        self.assertEqual(full["budget"]["omitted_files"], [])
        # Item limits are not budget omissions.
        self.assertEqual(
            e.search("task.requested priority", limit=1, token_budget=8000)["budget"][
                "omitted_files"
            ],
            [],
        )
        # A selected AST excerpt covers an overlapping, oversized file window.
        api = e.search("UNKNOWN_TEMPLATE", token_budget=8000)["items"][0]
        budget = len(json.dumps(api, ensure_ascii=False).encode("utf-8"))
        self.assertEqual(
            e.search("UNKNOWN_TEMPLATE", token_budget=budget)["budget"]["omitted_files"], []
        )

    def test_incremental_edit_delete_and_unavailable(self):
        e = self.engine()
        self.assertEqual(e.status()["state"], "unindexed")
        e.index()
        path = self.root / "examples/acme/api/tasks.py"
        path.write_text(path.read_text() + '\nRETRY_SENTINEL = "retry"\n')
        self.assertEqual(e.status()["state"], "stale")
        self.assertEqual(e.search("task")["items"], [])
        result = e.index()
        self.assertEqual((result["changed"], result["unchanged"]), (1, 1))
        self.assertTrue(e.search("RETRY_SENTINEL")["items"])
        path.unlink()
        self.assertEqual(e.index()["deleted"], 1)
        self.assertEqual(e.search("RETRY_SENTINEL")["items"], [])
        shutil.rmtree(self.root / "examples/acme/worker")
        self.assertEqual(e.status()["state"], "degraded")
        self.assertEqual(e.search("task")["items"], [])

    def test_exclusions_symlinks_and_parser_error_persistence(self):
        root = self.root / "examples/acme/api"
        (root / ".env.py").write_text("SECRET_SENTINEL = 1")
        (root / "escape.py").symlink_to(ROOT / "context_engine/core.py")
        (root / "broken.py").write_text("def broken(:\n pass")
        e = self.engine()
        self.assertTrue(e.index()["parser_errors"])
        self.assertTrue(e.index()["parser_errors"])
        self.assertEqual(e.search("SECRET_SENTINEL")["items"], [])
        self.assertEqual(e.search("sqlite3")["items"], [])

    def test_git_ignore_and_revision_drift(self):
        root = self.root / "examples/acme/api"

        def run(*args):
            return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)

        run("init")
        (root / ".gitignore").write_text("hidden.py\n")
        (root / "hidden.py").write_text("IGNORE_SENTINEL = 1")
        run("add", ".")
        run(
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-m",
            "fixture",
        )
        e = self.engine()
        e.index()
        self.assertEqual(e.search("IGNORE_SENTINEL")["items"], [])
        self.assertTrue(e.search("UNKNOWN_TEMPLATE")["items"][0]["revision"])
        run(
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "--allow-empty",
            "-m",
            "revision",
        )
        self.assertEqual(e.status()["state"], "stale")
        self.assertEqual(e.index()["changed"], 0)
        self.assertEqual(e.status()["state"], "ready")

    def test_manifest_scope_change_uses_fresh_store(self):
        a = self.engine()
        a.index()
        manifest = self.root / "examples/acme.json"
        config = json.loads(manifest.read_text())
        config["sources"] = config["sources"][:1]
        manifest.write_text(json.dumps(config))
        b = self.engine()
        self.assertNotEqual(a.store, b.store)
        self.assertEqual(b.status()["state"], "unindexed")
        b.index()
        self.assertTrue(all(i["source"] == "api" for i in b.search("consume_task")["items"]))
        self.assertEqual(b.search("UNKNOWN_EVENT")["items"], [])

    def test_mcp_subprocess(self):
        e = self.engine()
        e.index()
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "search_context", "arguments": {"query": "UNKNOWN_TEMPLATE"}},
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "search_context",
                    "arguments": {"query": "task", "workspace": "other"},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "get_context_bundle",
                    "arguments": {"task": "task.requested priority", "token_budget": 1},
                },
            },
        ]
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "context_engine",
                "--manifest",
                str(e.manifest),
                "--state",
                str(e.state),
                "serve",
            ],
            input="\n".join(json.dumps(r) for r in requests) + "\n",
            text=True,
            capture_output=True,
            cwd=ROOT,
            check=True,
        )
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(responses), 5)
        self.assertEqual(
            {t["name"] for t in responses[1]["result"]["tools"]},
            {
                "search_context",
                "get_context_bundle",
                "index_status",
                "history_request",
                "ingest_history",
                "search_history",
                "get_system_overview",
                "search_code",
                "read_code",
                "find_related",
                "resolve_instructions",
                "navigate_structure",
                "lookup_knowledge",
                "get_change_brief",
                "refresh_context",
                "review_context_request",
                "import_review_context",
                "get_review_context",
                "propose_review_guideline",
            },
        )
        self.assertTrue(json.loads(responses[2]["result"]["content"][0]["text"])["items"])
        self.assertTrue(responses[3]["result"]["isError"])
        tiny = json.loads(responses[4]["result"]["content"][0]["text"])
        self.assertEqual({f["source"] for f in tiny["budget"]["omitted_files"]}, {"api", "worker"})
        self.assertEqual(tiny["items"], [])

    def test_demo_contract(self):
        def module(path):
            spec = importlib.util.spec_from_file_location("fixture", ROOT / path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod

        api = module("examples/acme/api/tasks.py")
        worker = module("examples/acme/worker/consumer.py")
        queue = []
        api.create_task("invoice", 3, queue)
        self.assertEqual(worker.consume_task(queue.pop())["status"], "COMPLETED")
        with self.assertRaises(ValueError):
            api.create_task("unknown", 3, queue)


if __name__ == "__main__":
    unittest.main()
