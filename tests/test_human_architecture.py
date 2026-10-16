import shutil
import tempfile
import unittest
from pathlib import Path

from context_engine.core import Engine

ROOT = Path(__file__).resolve().parents[1]


class HumanArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "examples", self.root / "examples")
        self.engine = Engine(self.root / "examples/acme.json", self.root / "state")
        self.source = self.root / "examples/acme/api"

    def tearDown(self):
        self.engine.close()
        self.temp.cleanup()

    def test_document_first_with_scoped_source_links_and_no_edge_dump(self):
        (self.source / "docs").mkdir(exist_ok=True)
        guide = self.source / "docs/ARCHITECTURE-OVERVIEW.md"
        guide.write_text(
            "# How the API works\n\nRequests become queued tasks.\n\n"
            "## Follow a request\n\nStart at [the API](../tasks.py).\n"
            "[outside](../../../secret.py) [remote](https://example.invalid)\n"
        )
        self.engine.index()
        result = self.engine.knowledge.wiki("architecture", "api")
        self.assertEqual(result["state"], "ready")
        self.assertIn("Requests become queued tasks.", result["markdown"])
        self.assertEqual(result["document"], "docs/ARCHITECTURE-OVERVIEW.md")
        self.assertEqual({c["source"] for c in result["items"]}, {"api"})
        self.assertEqual(
            {c["path"] for c in result["items"]}, {"tasks.py", "docs/ARCHITECTURE-OVERVIEW.md"}
        )
        self.assertNotIn("Relationship:", result["markdown"])
        self.assertNotIn("Classification:", result["markdown"])
        self.assertNotIn("https:", result["markdown"])
        self.assertEqual(result["diagram"], [])
        guide.write_text("# Changed guide")
        stale = self.engine.knowledge.wiki("architecture", "api")
        self.assertNotEqual(stale["state"], "ready")
        self.assertEqual(stale["markdown"], "")
        self.assertEqual(stale["items"], [])

    def test_undocumented_repository_is_honest_and_unknown_scope_rejected(self):
        self.engine.index()
        result = self.engine.knowledge.wiki("architecture", "api")
        self.assertIn("Where to start reading", result["markdown"])
        self.assertIn("undocumented design decisions", result["markdown"])
        self.assertNotIn("Relationship:", result["markdown"])
        with self.assertRaises(ValueError):
            self.engine.knowledge.wiki("architecture", "not-approved")

    def test_guide_precedence_and_bounded_document(self):
        (self.source / "docs").mkdir(exist_ok=True)
        (self.source / "README.md").write_text("# Setup only\n")
        (self.source / "docs/ARCHITECTURE-OVERVIEW.md").write_text(
            "# System walkthrough\n" + "A documented responsibility.\n" * 1100
        )
        self.engine.index()
        result = self.engine.knowledge.wiki("architecture", "api")
        self.assertTrue(result["markdown"].startswith("# System walkthrough"))
        self.assertLess(len(result["markdown"]), 25000)
        self.assertIn("shortened", result["gaps"][0])
