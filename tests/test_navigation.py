import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from context_engine.budget import encode
from context_engine.core import Engine

ROOT = Path(__file__).resolve().parents[1]


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for folder in ("api", "worker"):
            (self.root / folder).mkdir()
        (self.root / "api/main.py").write_text(
            '"""API handles HTTP tasks."""\n\ndef schedule_task(name):\n    return {"event": "task.requested", "name": name}\n'
        )
        (self.root / "worker/run.py").write_text(
            'def consume_task(message):\n    return message["event"] == "task.requested"\n'
        )
        (self.root / "api/README.md").write_text("# Task documentation\nHTTP deployment guide.\n")
        (self.root / "api/settings.json").write_text('{"task_timeout": 10}')
        self.manifest = self.root / "team.json"
        self.manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "environment": "team",
                    "workspace": "nav",
                    "sources": [{"id": "api", "path": "api"}, {"id": "worker", "path": "worker"}],
                }
            )
        )
        self.engine = Engine(self.manifest, self.root / "state")
        self.engine.index()

    def tearDown(self):
        self.engine.close()
        self.tmp.cleanup()

    def bounded(self, result, budget):
        self.assertEqual(result["budget"]["used_bytes"], len(encode(result).encode("utf-8")))
        self.assertLessEqual(result["budget"]["used_bytes"], budget)

    def test_discover_scope_content_symbols_and_literal_regex(self):
        for mode in ("lexical", "literal", "regex", "symbols"):
            result = self.engine.navigation.search(
                "schedule_task", mode=mode, source="api", path_glob="*.py"
            )
            self.assertTrue(result["items"], result)
            self.assertTrue(
                all(i["source"] == "api" and i["path"] == "main.py" for i in result["items"])
            )
            self.bounded(result, 2000)
        doc = self.engine.navigation.search("HTTP", content="docs")
        self.assertEqual([r["path"] for r in doc["items"]], ["README.md"])
        config = self.engine.navigation.search("", mode="files", content="config")
        self.assertEqual([r["path"] for r in config["items"]], ["settings.json"])
        self.assertFalse(
            self.engine.navigation.search("http", mode="literal", case_sensitive=True)["items"]
        )
        self.assertTrue(self.engine.navigation.search(r"task\.requested", mode="regex")["items"])
        with self.assertRaises(ValueError):
            self.engine.navigation.search("[invalid", mode="regex")
        with self.assertRaises(ValueError):
            self.engine.navigation.search("secret", source="personal")

    def test_outline_is_smaller_and_expansion_validates_hash(self):
        outline = self.engine.navigation.search("schedule_task", max_snippet_lines=0)
        preview = self.engine.navigation.search("schedule_task", max_snippet_lines=5)
        self.assertLess(len(encode(outline)), len(encode(preview)))
        item = outline["items"][0]
        expanded = self.engine.navigation.read(
            item["source"], item["path"], item["lines"][0], expected_hash=item["hash"]
        )
        self.assertIn("schedule_task", expanded["items"][0]["text"])
        self.bounded(expanded, 4000)
        (self.root / "api/main.py").write_text("def changed():\n    pass\n")
        self.assertEqual(self.engine.navigation.read("api", "main.py")["state"], "stale")
        self.engine.index()
        self.assertEqual(
            self.engine.navigation.read("api", "main.py", expected_hash=item["hash"])["state"],
            "stale",
        )
        with self.assertRaises(ValueError):
            self.engine.navigation.read("api", "../team.json")

    def test_large_excerpts_do_not_prevent_location_discovery(self):
        (self.root / "api/large.py").write_text('HUGE_SYMBOL = "' + "x" * 40000 + '"\n')
        self.engine.index()
        result = self.engine.navigation.search("HUGE_SYMBOL", max_snippet_lines=0)
        self.assertTrue(result["items"])
        expanded = self.engine.navigation.read("api", "large.py", token_budget=1024)
        self.assertEqual(expanded["items"], [])
        self.assertEqual(expanded["next_line"], 1)

    def test_compact_candidates_are_not_cut_off_by_legacy_payload_cost(self):
        for n in range(50):
            (self.root / "api" / (str(n).zfill(2) + "x" * 150 + ".py")).write_text(
                "def budget_probe():\n    pass\n"
            )
        self.engine.index()
        with patch.object(self.engine, "scan", wraps=self.engine.scan) as scan:
            result = self.engine.navigation.search(
                "budget_probe", mode="lexical", limit=50, token_budget=32000, max_snippet_lines=0
            )
        self.assertEqual(len(result["items"]), 50)
        self.assertEqual(scan.call_count, 2)
        self.bounded(result, 32000)

    def test_compact_search_rejects_changes_during_retrieval(self):
        candidates = self.engine._search_candidates

        def changed(*args, **kwargs):
            result = candidates(*args, **kwargs)
            (self.root / "api/main.py").write_text("def changed():\n    pass\n")
            return result

        with patch.object(self.engine, "_search_candidates", side_effect=changed):
            result = self.engine.navigation.search("schedule_task", mode="lexical")
        self.assertEqual(result["state"], "stale")
        self.assertEqual(result["items"], [])

    def test_source_filter_is_applied_before_lexical_candidate_limit(self):
        (self.root / "api/noise.py").write_text(
            "\n".join("def noise_%s():\n    return 'task requested'" % i for i in range(300))
        )
        self.engine.index()
        result = self.engine.navigation.search("task", source="worker")
        self.assertTrue(result["items"])
        self.assertEqual({r["source"] for r in result["items"]}, {"worker"})

    def test_regex_timeout_is_reported_and_related_is_cited(self):
        with patch(
            "context_engine.navigation.subprocess.run",
            side_effect=subprocess.TimeoutExpired("regex", 2),
        ):
            # Patch only the regex worker: status invokes Git through subprocess.run too.
            with (
                patch.object(
                    self.engine,
                    "status",
                    return_value={"state": "ready", "index": self.engine.metadata()},
                ),
                patch.object(self.engine, "scan", return_value=({}, {})),
            ):
                result = self.engine.navigation.search("(a+)+$", mode="regex")
        self.assertFalse(result["items"])
        self.assertTrue(any("execution limit" in g for g in result["gaps"]))
        related = self.engine.navigation.related("api", "main.py", line=3, token_budget=8000)
        self.assertTrue(any(x["source"] == "worker" for x in related["items"]), related)
        self.assertTrue(all(x["hash"] for x in related["items"]))

    def test_mcp_wire_payload_budget_and_refresh_tools(self):
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "get_system_overview", "arguments": {"token_budget": 2000}},
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "search_code",
                    "arguments": {"query": "task", "byte_budget": 1024, "max_snippet_lines": 0},
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "refresh_context",
                    "arguments": {"history": False, "force": True},
                },
            },
        ]
        requests.append(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "search_code",
                    "arguments": {"query": "task", "byte_budget": 1024, "token_budget": 2000},
                },
            }
        )
        requests.extend(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {
                        "name": "search_code",
                        "arguments": {
                            "query": "schedule_task",
                            "task_id": "wire",
                            "task_byte_budget": 8000,
                            "byte_budget": 2000,
                        },
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "tools/call",
                    "params": {
                        "name": "search_code",
                        "arguments": {
                            "query": "schedule_task",
                            "task_id": "wire",
                            "task_end": True,
                        },
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 8,
                    "method": "tools/call",
                    "params": {
                        "name": "find_related",
                        "arguments": {
                            "source": "api",
                            "path": "main.py",
                            "mode": "graph",
                            "byte_budget": 4000,
                        },
                    },
                },
            ]
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "context_engine",
                "--manifest",
                str(self.manifest),
                "--state",
                str(self.root / "state"),
                "serve",
            ],
            input="\n".join(map(json.dumps, requests)) + "\n",
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        responses = [json.loads(line)["result"] for line in result.stdout.splitlines()]
        for response, ceiling in zip(responses[1:3], (2000, 1024)):
            payload = response["content"][0]["text"]
            self.assertFalse(response["isError"], payload)
            self.assertLessEqual(len(payload.encode()), ceiling)
            self.assertEqual(len(payload.encode()), json.loads(payload)["budget"]["used_bytes"])
        self.assertTrue(responses[4]["isError"])
        self.assertIn("not both", responses[4]["content"][0]["text"])
        first = json.loads(responses[5]["content"][0]["text"])
        second = json.loads(responses[6]["content"][0]["text"])
        self.assertTrue(first["items"])
        self.assertFalse(second["items"])
        self.assertGreater(second["already_seen"], 0)
        self.assertEqual(
            second["task_budget"]["remaining_bytes"],
            8000 - len(encode(first).encode()) - len(encode(second).encode()),
        )
        self.assertFalse(responses[7]["isError"])
        graph = json.loads(responses[7]["content"][0]["text"])
        self.assertEqual(graph["retrieval"], "graph")
        refresh = json.loads(responses[3]["content"][0]["text"])
        self.assertEqual(refresh["jobs"]["history"]["state"], "disabled")


if __name__ == "__main__":
    unittest.main()
