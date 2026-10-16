import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from context_engine import governance
from context_engine.budget import size
from context_engine.core import Engine
from context_engine.review_ingest import NoRedirect, get_page


class LaunchKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / "src").mkdir()
        (root / "src/main.kt").write_text("fun run() = 1\n")
        manifest = root / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "environment": "synthetic",
                    "workspace": "launch",
                    "sources": [{"id": "api", "path": "src", "github": "fixture/project"}],
                }
            )
        )
        self.engine = Engine(manifest, root / "state")
        self.engine.index()

    def tearDown(self):
        self.engine.close()
        self.temp.cleanup()

    def record(self, kind, identity):
        record = self.engine.knowledge.template(kind, "api", "main.kt")
        record.update(id=identity, title=identity, statement="Approved bounded guidance")
        return record

    def rules(self):
        uid = os.getuid()
        return {
            "schema_version": 1,
            "authors": [uid],
            "reviewers": [uid],
            "sources": ["api"],
            "separation_of_duties": False,
            "allow_github": True,
            "github_repositories": {"api": "fixture/project"},
        }

    def test_all_slices_preserve_conditions_procedures_and_history(self):
        knowledge = self.engine.knowledge
        convention = self.record("convention", "kotlin-review")
        convention.update(
            languages=["kotlin"], tasks=["review"], exceptions=["Generated files are exempt"]
        )
        knowledge.propose(convention)
        knowledge.decide(convention["id"], 1, "approve")
        self.assertFalse(knowledge.lookup("convention", "api", "main.kt")["items"])
        found = knowledge.lookup("convention", "api", "main.kt", task="review")
        self.assertEqual(found["items"][0]["exceptions"], convention["exceptions"])
        self.assertFalse(knowledge.lookup("convention", "api", "main.py", task="review")["items"])
        procedure = self.record("procedure", "recover")
        knowledge.propose(procedure)
        knowledge.decide("recover", 1, "approve")
        result = knowledge.lookup("procedure", "api", token_budget=4000)
        self.assertEqual(result["items"][0]["details"], procedure["details"])
        self.assertLessEqual(size(result), 4000)
        bad = dict(procedure, details={"steps": ["unsafe incomplete procedure"]})
        with self.assertRaises(ValueError):
            knowledge.propose(bad, 1)
        decision = self.record("decision", "old")
        knowledge.propose(decision)
        knowledge.decide("old", 1, "approve")
        replacement = self.record("decision", "new")
        replacement["conflicts"] = [{"id": "old", "revision": 1}]
        knowledge.propose(replacement)
        with self.assertRaisesRegex(ValueError, "conflict"):
            knowledge.decide("new", 1, "approve")
        replacement["supersedes"] = [{"id": "old", "revision": 1}]
        knowledge.propose(replacement, 1)
        knowledge.decide("new", 2, "approve")
        self.assertEqual(
            knowledge.lookup("decision", "api", record_id="old")["items"][0]["id"], "new"
        )
        self.assertEqual(knowledge.history("old")["records"][0]["status"], "superseded")
        self.assertEqual(knowledge.history("old")["replaced_by"][-1]["id"], "new")
        decision["supersedes"] = [{"id": "new", "revision": 2}]
        knowledge.propose(decision, 1)
        with self.assertRaisesRegex(ValueError, "cycle"):
            knowledge.decide("old", 2, "approve")
        wiki = knowledge.wiki("all", "api")
        for title in ("Team conventions", "Decisions", "Operations and troubleshooting"):
            self.assertIn(title, wiki["markdown"])
        self.assertIn("Generated files are exempt", wiki["markdown"])
        self.assertNotIn("Generated files", json.dumps(self.engine.usage.report()))

    def test_governance_identity_separation_audit_and_policy_file(self):
        knowledge = self.engine.knowledge
        rules = self.rules()
        with patch.object(governance, "policy", return_value=rules):
            knowledge.propose(self.record("practice", "rule"))
            rules["reviewers"] = [os.getuid() + 1]
            with self.assertRaisesRegex(ValueError, "not authorized"):
                knowledge.decide("rule", 1, "approve")
            rules["reviewers"] = [os.getuid()]
            rules["separation_of_duties"] = True
            with self.assertRaisesRegex(ValueError, "independent"):
                knowledge.decide("rule", 1, "approve")
            rules["separation_of_duties"] = False
            knowledge.decide("rule", 1, "approve")
        audit = governance.audit(self.engine)
        self.assertEqual([r["action"] for r in audit["events"]], ["propose", "approve"])
        self.assertEqual(audit["events"][1]["actor_uid"], os.getuid())
        self.engine.db.execute("UPDATE knowledge_audit SET body='{}' WHERE seq=1")
        self.engine.db.commit()
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            governance.audit(self.engine)
        policy = Path(self.temp.name) / "review-policy.json"
        policy.write_text(json.dumps(rules))
        with patch.dict(os.environ, {"CONTEXT_ENGINE_REVIEW_POLICY": str(policy)}):
            if os.getuid() != 0:
                with self.assertRaisesRegex(ValueError, "administrator-owned"):
                    governance.policy()

    def test_github_import_dedup_update_invalidation_and_no_automatic_rules(self):
        reviews = self.engine.knowledge.reviews
        event = {
            "event_id": "comments-1",
            "pull": 1,
            "body": "COMPANY_REVIEW_BODY",
            "path": "main.kt",
            "author": "reviewer",
            "commit": "abc",
            "updated": "2026-09-10",
        }
        with self.assertRaisesRegex(ValueError, "administrator"):
            reviews.ingest("api", [event])
        with patch.object(governance, "policy", return_value=self.rules()):
            self.assertEqual(reviews.ingest("api", [event])["changed"], 1)
            self.assertEqual(reviews.ingest("api", [event])["changed"], 0)
            self.assertFalse(self.engine.knowledge.rows())
            item = reviews.events("api")["events"][0]
            draft = reviews.candidate(item["id"], "main.kt")
            self.engine.knowledge.propose(draft)
            with self.assertRaisesRegex(ValueError, "draft"):
                self.engine.knowledge.decide(draft["id"], 1, "approve")
            draft["statement"] = "Use a general testable convention"
            self.engine.knowledge.propose(draft, 1)
            self.engine.knowledge.decide(draft["id"], 2, "approve")
            self.assertTrue(self.engine.knowledge.lookup("practice", "api", task="review")["items"])
            changed = dict(event, body="UPDATED_COMPANY_COMMENT")
            reviews.ingest("api", [changed])
            self.assertFalse(
                self.engine.knowledge.lookup("practice", "api", task="review")["items"]
            )
            self.assertNotIn("COMPANY", json.dumps(self.engine.usage.report()))
            with self.assertRaises(ValueError):
                reviews.ingest("api", [dict(event, path="../outside")])
            reviews.ingest("api", [], reconcile_pull=1)
            self.assertFalse(reviews.events("api")["events"])

    def test_fetch_bounded_atomic_and_transport_refuses_redirects(self):
        value = {"id": 1, "body": "review", "path": "main.kt", "user": {"login": "reviewer"}}
        with (
            patch.object(governance, "policy", return_value=self.rules()),
            patch(
                "context_engine.review_ingest.get_page",
                side_effect=[json.dumps([dict(value, state="APPROVED")]), json.dumps([value])],
            ) as fetch,
        ):
            self.assertEqual(self.engine.knowledge.reviews.fetch("api", 12)["received"], 2)
            self.assertTrue(
                all(
                    call.args[0].startswith("repos/fixture/project/pulls/12/")
                    for call in fetch.call_args_list
                )
            )
        with (
            patch.object(governance, "policy", return_value=self.rules()),
            patch(
                "context_engine.review_ingest.get_page",
                side_effect=[json.dumps([value]), ValueError("rate limited")],
            ),
        ):
            with self.assertRaises(ValueError):
                self.engine.knowledge.reviews.fetch("api", 13)
        self.assertTrue(
            all(e["pull"] == 12 for e in self.engine.knowledge.reviews.events("api")["events"])
        )
        with self.assertRaisesRegex(ValueError, "redirects"):
            NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.test")
        with patch.dict(os.environ, {"CONTEXT_ENGINE_GITHUB_TOKEN": ""}):
            with self.assertRaises(ValueError):
                get_page("repos/fixture/project/pulls/1/reviews")
