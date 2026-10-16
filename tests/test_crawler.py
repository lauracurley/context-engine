import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from context_engine.core import Engine
from context_engine.locking import WriterBusy, writer_lock

ROOT = Path(__file__).resolve().parents[1]


class CrawlerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "code").mkdir()
        (self.root / "code/main.py").write_text('def main():\n    return "CRAWLER_SENTINEL"\n')
        self.manifest = self.root / "team.json"
        self.manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "environment": "team",
                    "workspace": "crawler",
                    "sources": [{"id": "api", "path": "code"}],
                    "crawler": {"history_provider": "git"},
                }
            )
        )
        self.engine = Engine(self.manifest, self.root / "state")

    def tearDown(self):
        self.engine.close()
        self.tmp.cleanup()

    def test_independent_cadences_restart_and_no_repeat_embedding_work(self):
        first = self.engine.crawler.cycle(clock=1000)
        self.assertEqual(first["jobs"]["code"]["state"], "ready")
        self.assertEqual(first["jobs"]["history"]["state"], "partial")
        self.assertTrue(self.engine.architecture.overview()["items"])
        self.engine.close()
        self.engine = Engine(self.manifest, self.root / "state")
        with (
            patch.object(self.engine, "index", side_effect=AssertionError("Code not due")),
            patch.object(
                self.engine.history, "ingest", side_effect=AssertionError("History not due")
            ),
        ):
            second = self.engine.crawler.cycle(clock=1001)
        self.assertEqual(second["jobs"]["code"]["finished_at"], 1000)
        with patch.object(
            self.engine.history, "ingest", side_effect=AssertionError("History not due")
        ):
            third = self.engine.crawler.cycle(clock=1300)
        self.assertEqual(third["jobs"]["code"]["result"]["architecture"]["changed"], 0)
        self.assertEqual(third["jobs"]["history"]["finished_at"], 1000)

    def test_errors_backoff_and_interrupted_job_resume(self):
        with patch.object(self.engine, "index", side_effect=OSError("sensitive details")):
            first = self.engine.crawler.cycle(clock=1000, history=False)
        self.assertEqual(first["jobs"]["code"]["next_due"], 1030)
        self.assertNotIn("sensitive details", json.dumps(first))
        second = self.engine.crawler.cycle(clock=1030, history=False)
        self.assertEqual(second["jobs"]["code"]["state"], "ready")
        second["jobs"]["code"]["state"] = "running"
        self.engine.crawler.save(second)
        resumed = self.engine.crawler.cycle(clock=1031, history=False)
        self.assertEqual(resumed["jobs"]["code"]["finished_at"], 1031)

    def test_writer_exclusion_across_process_and_lock_release(self):
        launch = [
            sys.executable,
            "-m",
            "context_engine",
            "--manifest",
            str(self.manifest),
            "--state",
            str(self.root / "state"),
        ]
        with writer_lock(self.engine):
            result = subprocess.run(
                launch + ["crawl", "--once", "--no-history"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertEqual(json.loads(result.stdout)["state"], "busy")
            other = Engine(self.manifest, self.root / "state")
            try:
                with self.assertRaises(WriterBusy):
                    other.index()
            finally:
                other.close()
        result = subprocess.run(
            launch + ["crawl", "--once", "--no-history"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(json.loads(result.stdout)["state"], "ready")

    def test_schedule_changes_preserve_index_knowledge_and_manifest(self):
        self.engine.index()
        record = self.engine.knowledge.template("practice", "api", "main.py")
        record.update(id="timing-rule", statement="Keep the queue behavior covered.")
        self.engine.knowledge.propose(record)
        self.engine.knowledge.decide(record["id"], 1, "approve")
        self.engine.crawler.cycle(clock=1000, history=False)
        before = self.manifest.read_bytes(), self.engine.store, self.engine.metadata()
        self.engine.crawler.configure({"interval": 60, "history_months": 3})
        self.engine.close()
        self.engine = Engine(self.manifest, self.root / "state")
        self.assertEqual(
            before, (self.manifest.read_bytes(), self.engine.store, self.engine.metadata())
        )
        self.assertEqual(self.engine.status()["state"], "ready")
        self.assertEqual(self.engine.knowledge.rows()[0]["status"], "approved")
        self.assertEqual(self.engine.crawler.config()["interval"], 60)
        self.assertEqual(self.engine.crawler.config()["history_months"], 3)
        next_cycle = self.engine.crawler.cycle(clock=1001, history=False)
        self.assertEqual(next_cycle["jobs"]["code"]["next_due"], 1061)
        for value in (
            {"interval": True},
            {"history_months": 121},
            {"history": True},
            {"interval": 0},
        ):
            with self.assertRaises(ValueError):
                self.engine.crawler.configure(value)
        self.assertEqual(self.engine.crawler.config()["interval"], 60)

    def test_invalid_configuration_and_force(self):
        for kwargs in ({"interval": 0}, {"history_interval": float("nan")}, {"history": "yes"}):
            with self.assertRaises(ValueError):
                self.engine.crawler.cycle(**kwargs)
        self.engine.crawler.cycle(clock=1000, history=False)
        forced = self.engine.crawler.cycle(clock=1001, history=False, force=True)
        self.assertEqual(forced["jobs"]["code"]["finished_at"], 1001)


if __name__ == "__main__":
    unittest.main()
