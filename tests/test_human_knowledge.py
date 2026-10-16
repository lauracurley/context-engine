import shutil
import tempfile
import unittest
from pathlib import Path

from context_engine.core import Engine
from context_engine.human_knowledge import detail

ROOT = Path(__file__).resolve().parents[1]


class HumanKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "examples", self.root / "examples")
        self.engine = Engine(self.root / "examples/acme.json", self.root / "state")
        self.docs = self.root / "examples/acme/api/docs"
        self.docs.mkdir(exist_ok=True)

    def tearDown(self):
        self.engine.close()
        self.temp.cleanup()

    def test_every_section_reads_documentation_without_approving_it(self):
        for kind, filename in (
            ("practice", "DEVELOPMENT.md"),
            ("convention", "TEAM-CONVENTIONS.md"),
            ("decision", "DECISIONS.md"),
            ("procedure", "OPERATIONS.md"),
        ):
            (self.docs / filename).write_text(
                f"# Guide for {kind}\n\nUseful {kind} explanation.\n\n```sh\n# comment stays a comment\n```\n"
            )
        self.engine.index()
        for kind in ("practice", "convention", "decision", "procedure"):
            result = self.engine.knowledge.wiki(kind, "api")
            self.assertIn(f"Useful {kind} explanation.", result["markdown"])
            self.assertIn("No guidance has been approved", result["markdown"])
            self.assertIn("\n# comment stays a comment\n", result["markdown"])
            self.assertFalse(self.engine.knowledge.lookup(kind, "api")["items"])
        (self.docs / "OPERATIONS.md").write_text("Changed operations")
        result = self.engine.knowledge.wiki("procedure", "api")
        self.assertNotIn("Useful procedure explanation", result["markdown"])
        self.assertNotEqual(result["state"], "ready")

    def test_empty_unknown_scope_and_bounded_guides(self):
        self.engine.index()
        self.assertIn(
            "No repository guide", self.engine.knowledge.wiki("decision", "api")["markdown"]
        )
        with self.assertRaises(ValueError):
            self.engine.knowledge.wiki("practice", "unknown")
        (self.docs / "OPERATIONS.md").write_text("# Run\n" + "A long guide line.\n" * 2000)
        self.engine.index()
        result = self.engine.knowledge.wiki("procedure", "api")
        self.assertLess(len(result["markdown"]), 25500)
        self.assertIn("shortened", result["gaps"][0])

    def test_details_are_prose_and_ordered_steps(self):
        text = "\n".join(
            detail(
                {
                    "steps": ["Start", "Verify"],
                    "diagnostics": [{"if": "stale", "then": "refresh"}],
                    "references": [{"id": "rule", "revision": 2}],
                }
            )
        )
        self.assertIn("1. Start\n2. Verify", text)
        self.assertIn("If stale → refresh", text)
        self.assertIn("rule (revision 2)", text)
        self.assertNotIn("{'", text)
