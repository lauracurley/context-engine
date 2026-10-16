import json
import tempfile
import unittest
from pathlib import Path

from context_engine.budget import size
from context_engine.core import Engine
from context_engine.retrieval_task import RetrievalTasks


class RetrievalEfficiencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        for source in ("api", "worker", "noise"):
            (root / source / "pkg").mkdir(parents=True)
        (root / "api/pkg/main.py").write_text(
            "from . import helper\ndef send():\n    return {'event': 'task.requested'}\n"
        )
        (root / "api/pkg/helper.py").write_text("def assist():\n    pass\n")
        (root / "worker/pkg/main.py").write_text(
            "def consume(message):\n    return message['event'] == 'task.requested'\n"
        )
        for n in range(80):
            (root / "noise/pkg" / f"file{n}.py").write_text(
                f"def send_{n}():\n    return 'task priority requested'\n"
            )
        manifest = root / "team.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "environment": "test",
                    "workspace": "efficiency",
                    "sources": [{"id": s, "path": s} for s in ("api", "worker", "noise")],
                }
            )
        )
        self.engine = Engine(manifest, root / "state")
        self.engine.index()

    def tearDown(self):
        self.engine.close()
        self.temp.cleanup()

    def test_graph_one_hop_direction_contract_and_scope(self):
        nav = self.engine.navigation
        imports = nav.related(
            "api",
            "pkg/main.py",
            mode="graph",
            relation="imports",
            direction="outgoing",
            token_budget=8000,
        )
        self.assertEqual([i["path"] for i in imports["items"]], ["pkg/helper.py"])
        self.assertEqual(imports["hops"], 1)
        self.assertFalse(
            nav.related(
                "api", "pkg/main.py", mode="graph", relation="imports", direction="incoming"
            )["items"]
        )
        incoming = nav.related(
            "api",
            "pkg/helper.py",
            mode="graph",
            relation="imports",
            direction="incoming",
            token_budget=8000,
        )
        self.assertEqual(incoming["items"][0]["path"], "pkg/main.py")
        contract = nav.related(
            "api",
            "pkg/main.py",
            mode="graph",
            relation="shared_event_literal",
            direction="incoming",
            token_budget=8000,
        )
        self.assertEqual([i["source"] for i in contract["items"]], ["worker"])
        self.assertEqual(contract["items"][0]["direction"], "undirected")
        self.assertEqual(
            {c["source"] for c in contract["items"][0]["citations"]}, {"api", "worker"}
        )
        self.assertEqual(contract["budget"]["used_bytes"], size(contract))
        with self.assertRaises(ValueError):
            nav.related("outside", "pkg/main.py", mode="graph")
        (Path(self.temp.name) / "worker/pkg/main.py").write_text("# changed\n")
        self.assertEqual(nav.related("api", "pkg/main.py", mode="graph")["state"], "stale")

    def test_hierarchy_and_seen_ids_preserve_expansion(self):
        overview = self.engine.architecture.overview(node="source:noise", token_budget=2000)
        directory = next(i for i in overview["items"] if i["kind"] == "directory")
        self.assertEqual(directory["files"], 80)
        expanded = self.engine.architecture.overview(
            node=directory["expand"], query="file1", token_budget=8000
        )
        self.assertTrue(any(i["kind"] == "module" for i in expanded["items"]))
        nav = self.engine.navigation
        first = nav.search("send", mode="lexical", source="noise", limit=2)
        second = nav.search(
            "send",
            mode="lexical",
            source="noise",
            limit=2,
            exclude_evidence_ids=[i["evidence_id"] for i in first["items"]],
        )
        self.assertTrue(second["items"])
        self.assertFalse({i["path"] for i in first["items"]} & {i["path"] for i in second["items"]})
        self.assertEqual(second["already_seen"], len(first["items"]))

    def test_task_accounting_reuse_read_and_exhaustion(self):
        ledger = RetrievalTasks()
        total = 0
        for n in range(2):
            args, ticket = ledger.prepare(
                "search_code",
                {
                    "query": "send",
                    "source": "noise",
                    "mode": "lexical",
                    "task_id": "task",
                    "task_byte_budget": 8000,
                },
            )
            result = ledger.finish(ticket, self.engine.navigation.search(**args))
            total += size(result)
            self.assertEqual(result["budget"]["used_bytes"], size(result))
            self.assertEqual(result["task_budget"]["remaining_bytes"], 8000 - total)
            if n:
                self.assertGreater(result["already_seen"], 0)
        item = result["items"][0]
        args, ticket = ledger.prepare(
            "read_code",
            {
                "source": item["source"],
                "path": item["path"],
                "expected_hash": item["hash"],
                "task_id": "task",
                "task_end": True,
            },
        )
        result = ledger.finish(ticket, self.engine.navigation.read(**args))
        self.assertTrue(result["items"])
        self.assertNotIn("task", ledger.tasks)
        with self.assertRaises(ValueError):
            ledger.prepare("search_code", {"task_id": "task"})
        args, ticket = ledger.prepare(
            "search_code",
            {"task_id": "tiny", "task_byte_budget": 1280, "query": "send", "max_snippet_lines": 0},
        )
        result = ledger.finish(ticket, self.engine.navigation.search(**args))
        self.assertLessEqual(size(result), 1280)
        with self.assertRaisesRegex(ValueError, "exhausted"):
            ledger.prepare("search_code", {"task_id": "tiny"})
