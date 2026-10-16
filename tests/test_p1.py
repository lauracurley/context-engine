import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from context_engine.budget import size
from context_engine.change_brief import brief
from context_engine.commonplace import Commonplace
from context_engine.core import Engine


class P1Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.src = self.root / "api"
        self.src.mkdir()
        self.code = self.src / "main.py"
        self.code.write_text("def enqueue():\n    return {'event': 'demo.requested'}\n")
        (self.root / "worker").mkdir()
        (self.root / "worker/run.py").write_text(
            "def consume():\n    return {'event': 'demo.requested'}\n"
        )
        self.git("init", "-q")
        self.git("add", ".")
        self.git(
            "-c",
            "user.name=Synthetic",
            "-c",
            "user.email=synthetic@example.invalid",
            "commit",
            "-qm",
            "fixture",
        )
        manifest = self.root / "fixture.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "environment": "test",
                    "workspace": "p1",
                    "sources": [
                        {"id": "api", "path": "api", "github": "synthetic/api"},
                        {"id": "worker", "path": "worker"},
                    ],
                }
            )
        )
        self.engine = Engine(manifest, self.root / "state")
        self.addCleanup(self.engine.close)
        self.engine.index()

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.src), *args], check=True, capture_output=True
        ).stdout

    def record(self, identity="rule"):
        record = self.engine.knowledge.template("practice", "api", "main.py")
        record.update(
            id=identity,
            statement="Preserve idempotency for retries.",
            exceptions=["Explicit manual recovery is exempt."],
        )
        return record

    def test_unstaged_git_deletion_and_rename_keep_other_evidence_available(self):
        keep = self.src / "keep.py"
        keep.write_text("def retained_behavior(): return 1\n")
        self.git("add", ".")
        self.git(
            "-c",
            "user.name=Synthetic",
            "-c",
            "user.email=synthetic@example.invalid",
            "commit",
            "-qm",
            "keep fixture",
        )
        self.engine.index()
        self.code.unlink()
        self.assertEqual(self.engine.status()["state"], "stale")
        self.assertEqual(self.engine.index()["deleted"], 1)
        self.assertEqual(self.engine.status()["state"], "ready")
        self.assertTrue(self.engine.navigation.search("retained_behavior")["items"])
        self.assertFalse(self.engine.navigation.search("enqueue")["items"])
        renamed = self.src / "renamed.py"
        keep.rename(renamed)
        self.assertEqual(self.engine.index()["deleted"], 1)
        found = self.engine.navigation.search("retained_behavior")
        self.assertEqual(found["state"], "ready")
        self.assertEqual([r["path"] for r in found["items"]], ["renamed.py"])
        self.assertIn(b" D main.py", self.git("status", "--porcelain"))

        original_read = Path.read_bytes

        def denied(path):
            if path == renamed:
                raise PermissionError("Fixture read denied")
            return original_read(path)

        with patch.object(Path, "read_bytes", denied):
            status = self.engine.status()
            self.assertEqual(status["state"], "degraded")
            self.assertIn("renamed.py: PermissionError", status["coverage"]["api"]["errors"])
        self.src.rename(self.root / "unavailable")
        self.assertEqual(self.engine.status()["state"], "degraded")

    def test_language_guidance_covers_tsx_jsx_and_kotlin_scripts_in_change_briefs(self):
        fixtures = {
            "widget.ts": "export function widget() { return 1; }\n",
            "widget.tsx": "export function Widget() { return <div>hello</div>; }\n",
            "widget.js": "export function widget() { return 1; }\n",
            "widget.jsx": "export function Widget() { return <div>hello</div>; }\n",
            "build.kts": "fun build() = 1\n",
        }
        for path, text in fixtures.items():
            (self.src / path).write_text(text)
        self.git("add", ".")
        self.git(
            "-c",
            "user.name=Synthetic",
            "-c",
            "user.email=synthetic@example.invalid",
            "commit",
            "-qm",
            "language fixtures",
        )
        self.engine.index()
        for language in ("typescript", "javascript", "kotlin"):
            record = dict(self.record(language), prefix="", languages=[language])
            self.engine.knowledge.propose(record)
            self.engine.knowledge.decide(language, 1, "approve")
        for path, language in (
            ("widget.ts", "typescript"),
            ("widget.tsx", "typescript"),
            ("widget.js", "javascript"),
            ("widget.jsx", "javascript"),
            ("build.kts", "kotlin"),
        ):
            with self.subTest(path=path):
                found = self.engine.knowledge.lookup(
                    "practice", "api", path=path, token_budget=8000
                )
                self.assertEqual([r["id"] for r in found["items"]], [language])
        self.assertFalse(self.engine.knowledge.lookup("practice", "api", path="main.py")["items"])
        override = self.engine.knowledge.lookup(
            "practice", "api", path="widget.tsx", language="javascript", token_budget=8000
        )
        self.assertEqual([r["id"] for r in override["items"]], ["javascript"])
        for path in ("widget.tsx", "widget.jsx", "build.kts"):
            (self.src / path).write_text(fixtures[path] + "// changed\n")
        self.engine.index()
        result = brief(self.engine, "api", token_budget=32000)
        self.assertEqual(
            {r["id"] for r in result["items"] if r["category"] == "guidance"},
            {"typescript", "javascript", "kotlin"},
        )

    def test_commonplace_atomic_conflict_and_no_approval_import(self):
        record = self.record()
        self.engine.knowledge.propose(record)
        self.engine.knowledge.decide("rule", 1, "approve")
        common = Commonplace(self.engine)
        file = Path(common.materialize()["snapshot"]) / "edit.json"
        value = json.loads(file.read_text())
        value["changes"][0]["record"]["statement"] = "Use stable retry keys."
        file.write_text(json.dumps(value))
        preview = common.preview(file)
        self.assertEqual(len(preview["changes"]), 1)
        common.import_edits(file, preview["preview_token"])
        self.assertEqual(self.engine.knowledge.rows()[-1]["status"], "proposed")
        self.assertEqual(
            self.engine.knowledge.lookup("practice", "api")["items"][0]["statement"],
            record["statement"],
        )
        with self.assertRaises(ValueError):
            common.import_edits(file, preview["preview_token"])
        self.assertEqual(common.preview(file)["conflicts"], ["rule"])
        value["changes"][0]["record"]["status"] = "approved"
        file.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            common.preview(file)

    def test_preview_tamper_and_batch_validation(self):
        common = Commonplace(self.engine)
        file = self.root / "edit.json"
        value = {"schema_version": 1, "changes": [{"base": None, "record": self.record()}]}
        file.write_text(json.dumps(value))
        preview = common.preview(file)
        value["changes"][0]["record"]["statement"] = "Changed after preview"
        file.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            common.import_edits(file, preview["preview_token"])
        self.assertEqual(self.engine.knowledge.rows(), [])
        value["changes"].append({"base": None, "record": {"id": "invalid"}})
        file.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            common.preview(file)
        self.assertEqual(self.engine.knowledge.rows(), [])

    def test_branch_reuse_scope_and_chunker_invalidation(self):
        original = self.code.read_text()
        self.code.write_text("def other_branch(): return 2\n")
        self.engine.index()
        self.assertFalse(self.engine.navigation.search("enqueue", source="api")["items"])
        self.code.write_text(original)
        with patch.object(self.engine.chunker, "units", wraps=self.engine.chunker.units) as units:
            self.engine.index()
            self.assertEqual(units.call_count, 0)
        self.assertTrue(self.engine.navigation.search("enqueue", source="api")["items"])
        self.assertFalse(self.engine.navigation.search("other_branch", source="api")["items"])
        self.engine.chunker.identity["test_version"] = 2
        with patch.object(self.engine.chunker, "units", wraps=self.engine.chunker.units) as units:
            self.engine.index()
            self.assertGreater(units.call_count, 0)

    def test_brief_exceptions_graph_budget_and_staleness(self):
        self.code.write_text(self.code.read_text() + "\n# enforce retry keys\n")
        self.engine.index()
        self.engine.knowledge.propose(self.record())
        self.engine.knowledge.decide("rule", 1, "approve")
        result = brief(self.engine, "api", token_budget=8000)
        self.assertLessEqual(size(result), 8000)
        self.assertEqual(size(result), result["budget"]["used_bytes"])
        self.assertTrue(any(i["category"] == "changed_code" for i in result["items"]))
        guidance = next(i for i in result["items"] if i["category"] == "guidance")
        self.assertIn("exempt", guidance["exceptions"][0])
        self.assertNotIn("rationale", guidance)
        self.assertTrue(any(i["category"] == "related_evidence" for i in result["items"]))
        self.assertLessEqual(size(brief(self.engine, "api", token_budget=1024)), 1024)
        self.code.write_text("def changed(): return 1\n")
        self.assertEqual(brief(self.engine, "api")["state"], "stale")
        self.assertFalse(brief(self.engine, "api")["items"])

    def test_brief_scans_twice_for_twelve_changed_files_and_withholds_mid_request_drift(self):
        for n in range(12):
            (self.src / f"part_{n}.py").write_text(f"def part_{n}(): return 1\n")
        self.git("add", ".")
        self.git(
            "-c",
            "user.name=Synthetic",
            "-c",
            "user.email=synthetic@example.invalid",
            "commit",
            "-qm",
            "baseline",
        )
        for n in range(12):
            (self.src / f"part_{n}.py").write_text(f"def part_{n}(): return 2\n")
        self.engine.index()
        with patch.object(self.engine, "scan", wraps=self.engine.scan) as scan:
            result = brief(self.engine, "api", token_budget=32000)
        self.assertEqual(result["state"], "ready")
        self.assertEqual(scan.call_count, 2)
        read = self.engine.navigation._read

        def mutate(*args, **kwargs):
            value = read(*args, **kwargs)
            self.code.write_text("def changed_during_request(): return 3\n")
            return value

        with patch.object(self.engine.navigation, "_read", side_effect=mutate):
            result = brief(self.engine, "api", token_budget=32000)
        self.assertEqual(result["state"], "stale")
        self.assertFalse(result["items"])

    def test_human_catalog_distinguishes_proposals_stale_evidence_and_revision_conflicts(self):
        self.engine.knowledge.propose(self.record())
        catalog = self.engine.knowledge.catalog("api", "Replace")
        self.assertEqual(catalog["records"][0]["status"], "proposed")
        self.assertEqual(catalog["records"][0]["expected_revision"], 1)
        self.assertIn("rationale", catalog["records"][0])
        self.engine.knowledge.decide("rule", 1, "approve")
        self.engine.knowledge.propose(
            dict(self.record(), statement="Replacement proposal"), expected_revision=1
        )
        catalog = self.engine.knowledge.catalog()
        self.assertEqual({r["status"] for r in catalog["records"]}, {"approved", "proposed"})
        self.assertTrue(all(r["expected_revision"] == 2 for r in catalog["records"]))
        self.code.write_text("def changed(): return 3\n")
        self.assertFalse(any(r["fresh"] for r in self.engine.knowledge.catalog()["records"]))
        self.assertFalse(self.engine.knowledge.catalog("worker")["records"])
        with self.assertRaises(ValueError):
            self.engine.knowledge.catalog("outside")

    def test_review_inbox_counts_and_draft_only(self):
        reviews = self.engine.knowledge.reviews
        # Same schema returned by the read-only adapter, with no remote calls.
        events = [
            {"id": str(i), "body": "Please preserve retry keys.", "path": "main.py", "pull": pull}
            for i, pull in enumerate([1, 1, 2])
        ]
        with patch.object(reviews, "events", return_value={"events": events}):
            inbox = reviews.inbox("api")
        self.assertEqual(len(inbox["groups"]), 1)
        self.assertEqual(inbox["groups"][0]["distinct_pulls"], 2)
        self.assertEqual(inbox["groups"][0]["event_count"], 3)

    def test_mcp_brief_task_budget_and_unknown_scope(self):
        import sys

        self.code.write_text(self.code.read_text() + "\n# changed\n")
        self.engine.index()
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "get_change_brief",
                    "arguments": {
                        "source": "api",
                        "byte_budget": 4000,
                        "task_id": "synthetic",
                        "task_byte_budget": 6000,
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "get_change_brief", "arguments": {"source": "outside"}},
            },
        ]
        requests.insert(0, {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}})
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "context_engine",
                "--manifest",
                str(self.root / "fixture.json"),
                "--state",
                str(self.root / "state"),
                "serve",
            ],
            input="".join(json.dumps(r) + "\n" for r in requests),
            capture_output=True,
            text=True,
            check=True,
        )
        replies = [json.loads(line)["result"] for line in result.stdout.splitlines()[1:]]
        self.assertFalse(replies[0]["isError"])
        value = json.loads(replies[0]["content"][0]["text"])
        self.assertLessEqual(size(value), 4000)
        self.assertEqual(value["task_budget"]["remaining_bytes"], 6000 - size(value))
        self.assertTrue(replies[1]["isError"])

    def test_artifact_retention_and_source_deletion_do_not_expose_old_evidence(self):
        from context_engine.artifacts import Artifacts

        self.engine.db.execute("UPDATE chunk_artifacts SET touched=0")
        with self.engine.db:
            Artifacts(self.engine).prune()
        self.assertEqual(
            self.engine.db.execute("SELECT count(*) FROM chunk_artifacts").fetchone()[0], 0
        )
        self.code.unlink()
        self.engine.index()
        self.assertFalse(self.engine.navigation.search("enqueue")["items"])

    def test_decision_revisit_and_legacy_records(self):
        record = self.engine.knowledge.template("decision", "api", "main.py")
        self.assertIn("revisit_when", record["details"])
        self.engine.knowledge.validate(record)
        del record["details"]["revisit_when"]
        self.engine.knowledge.validate(record)

    def test_large_edit_batch_duplicate_fields_and_transaction_rollback(self):
        from context_engine import governance

        common = Commonplace(self.engine)
        file = self.root / "edit.json"
        entries = []
        for n in range(15):
            record = self.record("rule-" + str(n))
            record["rationale"] = "x" * 5000
            entries.append({"base": None, "record": record})
        file.write_text(json.dumps({"schema_version": 1, "changes": entries}))
        self.assertGreater(file.stat().st_size, 65536)
        preview = common.preview(file)
        original = governance.append
        calls = 0

        def fail_second(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError("Synthetic audit failure")
            return original(*args)

        with patch.object(governance, "append", side_effect=fail_second):
            with self.assertRaises(ValueError):
                common.import_edits(file, preview["preview_token"])
        self.assertEqual(self.engine.knowledge.rows(), [])
        self.assertEqual(common.import_edits(file, preview["preview_token"])["imported"], 15)
        file.write_text('{"schema_version":1,"schema_version":1,"changes":[]}')
        with self.assertRaises(ValueError):
            common.preview(file)

    def test_change_brief_names_enclosing_symbols_and_qualifies_test_candidates(self):
        self.code.write_text(
            self.code.read_text().replace("    return", "    retry_key = 1\n    return")
        )
        (self.src / "test_retry.py").write_text(
            "from main import enqueue\n\ndef test_retry():\n    assert enqueue()\n"
        )
        self.engine.index()
        result = brief(self.engine, "api", token_budget=8000)
        code = next(i for i in result["items"] if i["category"] == "changed_code")
        self.assertIn("enqueue", code["enclosing_symbols"])
        test = next(i for i in result["items"] if i["category"] == "test_candidate")
        self.assertEqual(test["path"], "test_retry.py")
        self.assertEqual(test["classification"], "inferred")
        self.assertLessEqual(size(result), 8000)
