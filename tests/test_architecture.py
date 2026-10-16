import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from context_engine.architecture import extract
from context_engine.budget import encode
from context_engine.core import Engine

ROOT = Path(__file__).resolve().parents[1]


class ArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / "examples", self.root / "examples")
        self.engine = Engine(self.root / "examples/acme.json", self.root / "state")

    def tearDown(self):
        self.engine.close()
        self.tmp.cleanup()

    def test_graph_preserves_unindexed_and_unavailable_source_states(self):
        self.assertEqual(self.engine.architecture.neighbors("api", "main.py")["state"], "unindexed")
        self.engine.index()
        source = Path(self.engine.sources["api"]["root"])
        source.rename(source.with_name("unavailable-api"))
        result = self.engine.architecture.neighbors("api", "main.py")
        self.assertEqual(result["state"], "degraded")
        self.assertEqual(result["items"], [])

    def test_cited_cross_repository_overview_and_conditional_budget(self):
        self.engine.index()
        result = self.engine.architecture.overview(token_budget=2000)
        self.assertEqual(len(encode(result).encode()), result["budget"]["used_bytes"])
        self.assertLessEqual(result["budget"]["used_bytes"], 2000)
        edge = next(x for x in result["items"] if x["kind"] == "edge")
        self.assertEqual(edge["name"], "task.requested")
        self.assertEqual(edge["classification"], "inferred")
        self.assertEqual({c["source"] for c in edge["citations"]}, {"api", "worker"})
        for cite in edge["citations"]:
            file = Path(self.engine.sources[cite["source"]]["root"]) / cite["path"]
            self.assertIn("task.requested", file.read_text().splitlines()[cite["lines"][0] - 1])
        reused = self.engine.architecture.overview(if_none_match=result["etag"])
        self.assertEqual(reused["state"], "unchanged")
        self.assertEqual(reused["items"], [])
        expanded = self.engine.architecture.overview(node="worker:consumer.py", token_budget=8000)
        self.assertTrue(any(x.get("id") == "worker:consumer.py" for x in expanded["items"]))
        self.assertNotEqual(
            self.engine.architecture.overview(query="worker", if_none_match=result["etag"])[
                "state"
            ],
            "unchanged",
        )

    def test_incremental_reuse_and_stale_withholding(self):
        self.engine.index()
        before = self.engine.architecture.overview()
        with patch(
            "context_engine.architecture.extract",
            side_effect=AssertionError("Must reuse extraction"),
        ):
            self.assertEqual(self.engine.index()["architecture"]["changed"], 0)
        path = self.root / "examples/acme/worker/consumer.py"
        path.write_text('"""New worker."""\n\ndef renamed():\n    return 1\n')
        stale = self.engine.architecture.overview(if_none_match=before["etag"])
        self.assertEqual(stale["state"], "stale")
        self.assertEqual(stale["items"], [])
        self.assertEqual(self.engine.index()["architecture"]["changed"], 1)
        self.assertFalse(
            any(
                x["kind"] == "edge"
                for x in self.engine.architecture.overview(token_budget=8000)["items"]
            )
        )
        path.unlink()
        self.engine.index()
        self.assertFalse(any(r["path"] == "consumer.py" for r in self.engine.architecture.rows()))

    def test_import_graph_symbols_manifests_and_no_source_execution(self):
        api = self.root / "examples/acme/api"
        (api / "main.py").write_text(
            'from .helpers import Utility\n\nclass API:\n    def serve(self, port: int = 80):\n        raise RuntimeError("never execute this")\n'
        )
        (api / "helpers.py").write_text("class Utility:\n    pass\n")
        (api / "package.json").write_text(
            '{"name":"api", "dependencies":{"express":"1"}, "main":"main.py"}'
        )
        self.engine.index()
        result = self.engine.architecture.overview(node="api:main.py", token_budget=8000)
        edges = [x for x in result["items"] if x["kind"] == "edge"]
        self.assertTrue(
            any(e["from"] == "api:main.py" and e["to"] == "api:helpers.py" for e in edges)
        )
        symbols = extract("main.py", (api / "main.py").read_text())["facts"]
        self.assertTrue(
            any(
                f["kind"] == "symbol" and f["name"] == "API.serve" and "port: int" in f["signature"]
                for f in symbols
            )
        )
        package = extract("package.json", (api / "package.json").read_text())
        self.assertTrue(
            any(f["kind"] == "dependency" and f["name"] == "express" for f in package["facts"])
        )
        self.assertTrue(extract("package.json", "[]")["errors"])

    def test_scope_isolation_bad_python_and_language_labels(self):
        api = self.root / "examples/acme/api"
        (api / "bad.py").write_text("def bad(:")
        (api / "app.ts").write_text('export function launch() {}\napp.get("/tasks", launch)\n')
        (api / "nested/private").mkdir(parents=True)
        (api / "nested/private/secret.py").write_text('"""PERSONAL_ARCHITECTURE_SENTINEL"""')
        self.engine.index()
        result = self.engine.architecture.overview(token_budget=8000)
        self.assertNotIn("PERSONAL_ARCHITECTURE_SENTINEL", encode(result))
        facts = extract("app.ts", (api / "app.ts").read_text())["facts"]
        self.assertTrue(all(f["classification"] == "inferred" for f in facts))
        self.assertTrue(any("parsing" in g for g in result["gaps"]))
        with self.assertRaises(ValueError):
            self.engine.architecture.overview(source="personal")
        with self.assertRaises(ValueError):
            self.engine.architecture.overview(node="personal:secret.py")


if __name__ == "__main__":
    unittest.main()
