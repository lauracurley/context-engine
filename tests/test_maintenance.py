import copy
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_p1 as fixtures

from context_engine.maintenance import Maintenance


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.P1Tests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.engine = self.fixture.engine
        self.maintenance = Maintenance(self.engine)
        self.record = self.fixture.record()
        self.engine.knowledge.propose(self.record)
        self.engine.knowledge.decide("rule", 1, "approve")

    def test_feedback_scope_and_revision_are_local_and_do_not_change_authority(self):
        for outcome in ("useful", "wrong_scope", "stale", "redundant"):
            self.maintenance.feedback("rule", 1, outcome)
        self.maintenance.feedback("rule", 1, "useful")
        item = self.maintenance.queue("api")["items"][0]
        self.assertEqual(item["feedback"]["useful"], 2)
        self.assertEqual(item["status"], "approved")
        self.assertFalse(self.maintenance.queue("worker")["items"])
        with self.assertRaises(ValueError):
            self.maintenance.feedback("rule", 1, "company free text")
        with self.assertRaises(ValueError):
            self.maintenance.feedback("rule", 2, "stale")
        self.assertNotIn("rule", json.dumps(self.engine.usage.report()))
        with patch("context_engine.governance.authorize", side_effect=ValueError("Denied")):
            with self.assertRaises(ValueError):
                self.maintenance.feedback("rule", 1, "useful")
        self.assertEqual(self.maintenance.queue("api")["items"][0]["feedback"]["useful"], 2)

    def test_exact_candidates_preserve_scope_and_exceptions(self):
        duplicate = copy.deepcopy(self.record)
        duplicate["id"] = "duplicate"
        self.engine.knowledge.propose(duplicate)
        different = copy.deepcopy(self.record)
        different.update(id="different", exceptions=["Different exception"])
        self.engine.knowledge.propose(different)
        row = next(r for r in self.maintenance.queue("api")["items"] if r["id"] == "rule")
        self.assertEqual([r["id"] for r in row["exact_guidance_candidates"]], ["duplicate"])
        self.assertEqual(len(self.engine.knowledge.lookup("practice", "api")["items"]), 1)

    def test_stale_draft_preserves_content_requires_review_and_detects_conflict(self):
        old = self.record["citations"][0]["hash"]
        self.fixture.code.write_text("def enqueue(): return 7\n")
        self.assertTrue(self.maintenance.queue("api")["items"][0]["stale_evidence"])
        with self.assertRaises(ValueError):
            self.maintenance.refresh_draft("rule", 1)
        self.engine.index()
        draft = self.maintenance.refresh_draft("rule", 1)["draft"]
        self.assertNotEqual(draft["citations"][0]["hash"], old)
        self.assertEqual(draft["exceptions"], self.record["exceptions"])
        self.assertEqual(draft["rationale"], self.record["rationale"])
        self.assertTrue(draft["statement"].startswith("DRAFT:"))
        self.assertEqual(len(self.engine.knowledge.rows()), 1)
        self.engine.knowledge.propose(draft, 1)
        with self.assertRaises(ValueError):
            self.engine.knowledge.decide("rule", 2, "approve")
        with self.assertRaises(ValueError):
            self.maintenance.refresh_draft("rule", 1)
        self.fixture.code.unlink()
        self.engine.index()
        with self.assertRaises(ValueError):
            self.maintenance.refresh_draft("rule", 2)

    def test_template_is_empty_and_does_not_require_company_sources(self):
        result = subprocess.run(
            [sys.executable, "-m", "context_engine", "reasoning-template"],
            capture_output=True,
            text=True,
            check=True,
        )
        text = json.loads(result.stdout)["markdown"]
        self.assertIn("Alternatives and hypotheses", text)
        self.assertNotIn(str(self.fixture.root), text)
        self.assertNotIn("enqueue", text)

    def test_rejected_replacement_can_refresh_active_content_with_latest_revision(self):
        rejected = dict(self.record, statement="Rejected replacement text")
        self.engine.knowledge.propose(rejected, 1)
        self.engine.knowledge.decide("rule", 2, "reject")
        self.fixture.code.write_text("def enqueue(): return 9\n")
        self.engine.index()
        item = self.maintenance.queue("api")["items"][0]
        self.assertEqual((item["revision"], item["status"]), (1, "approved"))
        self.assertTrue(item["stale_evidence"])
        result = self.maintenance.refresh_draft("rule", 1)
        self.assertEqual(result["expected_revision"], 2)
        self.assertEqual(result["draft"]["statement"], "DRAFT: " + self.record["statement"])
        self.assertNotEqual(result["draft"]["citations"], self.record["citations"])
        with self.assertRaises(ValueError):
            self.maintenance.refresh_draft("rule", 2)
        self.engine.knowledge.propose(result["draft"], result["expected_revision"])
        with self.assertRaises(ValueError):
            self.engine.knowledge.decide("rule", 3, "approve")
        with self.assertRaises(ValueError):
            self.maintenance.refresh_draft("rule", 1)
        with self.assertRaises(ValueError):
            self.engine.knowledge.propose(result["draft"], result["expected_revision"])
        revised = self.maintenance.refresh_draft("rule", 3)
        revised["draft"]["statement"] = self.record["statement"]
        self.engine.knowledge.propose(revised["draft"], revised["expected_revision"])
        self.engine.knowledge.decide("rule", 4, "approve")
        self.assertEqual(self.engine.knowledge.lookup("practice", "api")["items"][0]["revision"], 4)
        self.engine.knowledge.decide("rule", 4, "retire")
        with self.assertRaises(ValueError):
            self.maintenance.refresh_draft("rule", 4)
