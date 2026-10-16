import json
import tempfile
import unittest
from pathlib import Path

from context_engine.commonplace import Commonplace
from context_engine.core import Engine
from context_engine.readiness import inspect


class CommonplaceTests(unittest.TestCase):
    def test_local_mapping_snapshots_and_source_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "src").mkdir()
            (root / "src/code.py").write_text("def example(): return 1\n")
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "environment": "test",
                        "workspace": "commonplace",
                        "sources": [{"id": "api", "path": "src"}],
                    }
                )
            )
            engine = Engine(manifest, root / "state")
            try:
                engine.index()
                common = Commonplace(engine)
                self.assertFalse(Path(common.status()["directory"]).exists())
                common.configure("team/commonplace", str(root / "team-placeholder"))
                self.assertEqual(Commonplace(engine).status()["repository"], "team/commonplace")
                record = engine.knowledge.template("practice", "api", "code.py")
                record.update(id="test-rule", statement="Keep tests current")
                engine.knowledge.propose(record)
                engine.knowledge.decide("test-rule", 1, "approve")
                first = Path(common.materialize()["snapshot"])
                second = Path(common.materialize()["snapshot"])
                self.assertNotEqual(first, second)
                self.assertIn("Keep tests current", (first / "wiki/api/practice.md").read_text())
                self.assertEqual(
                    json.loads((first / "records.json").read_text())["records"][0]["status"],
                    "approved",
                )
                self.assertEqual((first / "records.json").stat().st_mode & 0o077, 0)
                (first / "records.json").write_text("{}")
                self.assertEqual(
                    engine.knowledge.lookup("practice", "api")["items"][0]["statement"],
                    "Keep tests current",
                )
                with self.assertRaises(ValueError):
                    common.configure("team/commonplace", str(root / "src/wiki"))
                with self.assertRaises(ValueError):
                    common.configure("https://token@host/repo")
                self.assertTrue(inspect(engine)["checks"]["review_governance"])
                self.assertNotIn("team/commonplace", json.dumps(engine.usage.report()))
            finally:
                engine.close()
