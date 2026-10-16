import json
import multiprocessing
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from context_engine.core import Engine
from context_engine.readiness import purge
from context_engine.usage import Usage, decode, validate


def accumulate(root):
    for _ in range(15):
        Usage(root).record("search_code", "success", 50, 100)


class ClientReadinessTests(unittest.TestCase):
    def test_numeric_only_retention_concurrency_and_import(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "usage"
            usage = Usage(root)
            usage.record("search_code", "success", 50, 100)
            self.assertFalse(root.exists())
            usage.configure(True)
            processes = [multiprocessing.Process(target=accumulate, args=(root,)) for _ in range(3)]
            for process in processes:
                process.start()
            for process in processes:
                process.join(10)
                self.assertEqual(process.exitcode, 0)
            report = usage.report()
            self.assertEqual(report["operations"]["search_code"]["calls"], 45)
            for bad in ("PRIVATE_QUERY", {"prompt": "secret"}):
                with self.assertRaises((ValueError, TypeError)):
                    usage.record(bad, "success", 50, 100)
                with self.assertRaises((ValueError, TypeError)):
                    usage.record("search_code", "success", bad, 100)
            with self.assertRaises(ValueError):
                validate(dict(report, company="SECRET"))
            with self.assertRaises(ValueError):
                decode('{"x":1,"x":2}')
            state = json.loads((root / "aggregates.json").read_text())
            state["days"]["2000-01-01"] = state["days"][next(iter(state["days"]))]
            (root / "aggregates.json").write_text(json.dumps(state))
            self.assertEqual(usage.report()["operations"]["search_code"]["calls"], 45)
            self.assertNotIn("2000-01-01", (root / "aggregates.json").read_text())
            usage.configure(False)
            usage.record("search_code", "success", 50, 100)
            self.assertEqual(usage.report()["operations"]["search_code"]["calls"], 45)
            usage.clear()
            self.assertEqual(usage.report()["operations"], {})
            (root / "aggregates.json").write_text("42")
            with self.assertRaises(ValueError):
                usage.report()
            usage.clear()

    def test_policy_usage_wire_and_purge_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "src").mkdir()
            (root / "src/code.py").write_text('PRIVATE_COMPANY_MARKER = "hidden"\n')
            manifest = root / "manifest.json"
            config = {
                "schema_version": 1,
                "environment": "test",
                "workspace": "readiness",
                "sources": [{"id": "source", "path": "src"}],
            }
            manifest.write_text(json.dumps(config))
            policy = root / "policy.json"
            policy.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "storage_roots": [str(root / "state")],
                        "source_roots": [str(root / "src")],
                        "allow_history": False,
                        "allow_remote_git": False,
                        "allow_embeddings": False,
                    }
                )
            )
            policy.chmod(0o600)
            with patch.dict(os.environ, {"CONTEXT_ENGINE_POLICY": str(policy)}):
                with self.assertRaisesRegex(ValueError, "storage"):
                    Engine(manifest, root / "outside")
                engine = Engine(manifest, root / "state")
                try:
                    engine.index()
                    engine.usage.configure(True)
                    self.assertFalse(engine.crawler.config()["history"])
                    with self.assertRaisesRegex(ValueError, "disabled"):
                        engine.history.ingest()
                finally:
                    engine.close()
                base = [
                    sys.executable,
                    "-m",
                    "context_engine",
                    "--manifest",
                    str(manifest),
                    "--state",
                    str(root / "state"),
                ]
                subprocess.run(
                    base + ["discover", "PRIVATE_COMPANY_MARKER"], capture_output=True, check=True
                )
                report = subprocess.run(
                    base + ["usage", "report"], capture_output=True, text=True, check=True
                ).stdout
                self.assertNotIn("PRIVATE_COMPANY_MARKER", report)
                self.assertNotIn(str(root), report)
                self.assertEqual(validate(decode(report))["operations"]["search_code"]["calls"], 1)
                engine = Engine(manifest, root / "state")
                try:
                    purge(engine)
                    self.assertFalse(engine.db.execute("SELECT * FROM evidence").fetchall())
                    self.assertEqual(engine.status()["state"], "unindexed")
                    engine.index()
                    self.assertTrue(engine.navigation.search("PRIVATE_COMPANY_MARKER")["items"])
                finally:
                    engine.close()
            self.assertTrue((root / "src/code.py").exists())

    def test_synthetic_benchmark_requires_kotlin_and_recovers_stale_index(self):
        from context_engine.benchmark import run
        from context_engine.navigation import Navigation

        original = Navigation.search

        def without_kotlin(instance, query, **kwargs):
            result = original(instance, query, **kwargs)
            if query == "Demo.process":
                result["items"] = []
            return result

        with patch.object(Navigation, "search", without_kotlin):
            report = run()
        self.assertFalse(report["passed"])
        self.assertFalse(report["kotlin_parser_ready"])
        self.assertTrue(all(case["passed"] for case in report["cases"]))
        self.assertNotIn("/", json.dumps(report))

    def test_improvement_intake_rejects_content_and_preserves_uncertainty(self):
        from context_engine.usage import blank
        from scripts.improvement_cycle import analyze

        report = Usage._report({}, "0")
        self.assertEqual(analyze(report)["decision"], "insufficient_signal")
        with self.assertRaises(ValueError):
            analyze(dict(report, prompt="PRIVATE_COMPANY_MARKER"))
        row = blank()
        row["calls"] = 100
        row["outcomes"]["stale"] = 40
        row["outcomes"]["success"] = 60
        row["duration_ms_bins"]["le_100"] = 100
        packet = analyze(Usage._report({"search_code": row}, "1-7"))
        self.assertEqual(packet["decision"], "investigate")
        self.assertEqual(packet["candidates"][0]["calls"], 100)
        self.assertEqual(packet["candidates"][0]["count"], 40)
        self.assertEqual(packet["mode"], "read_only")
