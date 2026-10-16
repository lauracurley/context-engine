import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from context_engine.budget import size
from context_engine.core import Engine


class KnowledgeTests(unittest.TestCase):
    def test_review_projections_revision_scope_and_staleness(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "src").mkdir()
            code = root / "src/code.py"
            code.write_text("def review():\n    return 1\n")
            (root / "src/.context-wiki").mkdir()
            (root / "src/.context-wiki/wiki.md").write_text("WIKI_PRIVATE_DUPLICATE")
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "environment": "test",
                        "workspace": "knowledge",
                        "sources": [{"id": "api", "path": "src"}],
                    }
                )
            )
            engine = Engine(manifest, root / "state")
            try:
                engine.index()
                current, _ = engine.scan()
                self.assertNotIn(("api", ".context-wiki/wiki.md"), current)
                record = dict(
                    id="review-tests",
                    kind="practice",
                    source="api",
                    prefix="code.py",
                    title="Review tests",
                    statement="Require regression coverage for fixes.",
                    rationale="Human explanation with examples.",
                    citations=[
                        {
                            "source": "api",
                            "path": "code.py",
                            "hash": current[("api", "code.py")]["hash"],
                        }
                    ],
                )
                engine.knowledge.propose(record)
                self.assertFalse(engine.knowledge.lookup("practice", "api", "code.py")["items"])
                engine.knowledge.decide(record["id"], 1, "approve")
                agent = engine.knowledge.lookup("practice", "api", "code.py", token_budget=1024)
                self.assertLessEqual(size(agent), 1024)
                self.assertEqual(agent["items"][0]["statement"], record["statement"])
                self.assertNotIn("rationale", agent["items"][0])
                self.assertFalse(engine.knowledge.lookup("practice", "api", "other.py")["items"])
                wiki = engine.knowledge.wiki("practice", "api")["markdown"]
                self.assertIn(record["statement"], wiki)
                self.assertIn(record["rationale"], wiki)
                with self.assertRaises(ValueError):
                    engine.knowledge.propose(record)
                revised = dict(record, statement="Require a failing regression test before a fix.")
                engine.knowledge.propose(revised, 1)
                self.assertEqual(
                    engine.knowledge.lookup("practice", "api", "code.py")["items"][0]["revision"], 1
                )
                engine.knowledge.decide(record["id"], 2, "approve")
                self.assertEqual(engine.knowledge.rows()[0]["status"], "superseded")
                architecture = dict(
                    record,
                    id="review-boundary",
                    kind="architecture",
                    prefix="",
                    statement="The review module owns validation.",
                )
                engine.knowledge.propose(architecture)
                engine.knowledge.decide(architecture["id"], 1, "approve")
                self.assertIn(
                    architecture["statement"],
                    engine.knowledge.wiki("architecture", "api")["markdown"],
                )
                self.assertEqual(
                    engine.knowledge.lookup("architecture", "api")["items"][0]["id"],
                    architecture["id"],
                )
                requests = [
                    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {
                            "name": "lookup_knowledge",
                            "arguments": {
                                "kind": "architecture",
                                "source": "api",
                                "byte_budget": 1500,
                                "task_id": "review",
                                "task_byte_budget": 3000,
                            },
                        },
                    },
                ]
                wire = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "context_engine",
                        "--manifest",
                        str(manifest),
                        "--state",
                        str(root / "state"),
                        "serve",
                    ],
                    input="\n".join(json.dumps(r) for r in requests) + "\n",
                    capture_output=True,
                    text=True,
                    check=True,
                )
                response = json.loads(wire.stdout.splitlines()[1])["result"]
                self.assertFalse(response.get("isError", False), response)
                self.assertNotIn(record["rationale"], json.dumps(response))
                self.assertIn(architecture["statement"], json.dumps(response))
                code.write_text("def changed():\n    return 2\n")
                self.assertFalse(engine.knowledge.lookup("practice", "api", "code.py")["items"])
                self.assertIn("STALE", engine.knowledge.wiki("practice", "api")["markdown"])
                engine.index()
                self.assertEqual(
                    engine.knowledge.lookup("practice", "api", "code.py")["stale_records"], 1
                )
                engine.knowledge.propose(revised, 2)
                with self.assertRaises(ValueError):
                    engine.knowledge.decide(record["id"], 3, "approve")
                engine.knowledge.decide(record["id"], 3, "reject")
                engine.knowledge.decide(record["id"], 2, "retire")
                self.assertNotIn("review-tests", json.dumps(engine.usage.report()))
            finally:
                engine.close()
