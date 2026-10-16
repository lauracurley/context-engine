import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from context_engine.core import Engine


class ManagedSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.upstream = self.root / "upstream"
        self.upstream.mkdir()
        self.git("init", "--quiet")
        self.git("checkout", "-b", "main")
        (self.upstream / "main.py").write_text(
            'def first_version():\n    return "CANONICAL_SENTINEL"\n'
        )
        self.commit()
        self.manifest = self.root / "canonical.json"
        self.config = {
            "schema_version": 1,
            "environment": "team",
            "workspace": "canonical",
            "sources": [
                {
                    "id": "api",
                    "type": "remote-git",
                    "url": str(self.upstream),
                    "ref": "refs/heads/main",
                }
            ],
        }
        self.manifest.write_text(json.dumps(self.config))
        self.engine = Engine(self.manifest, self.root / "state")

    def tearDown(self):
        self.engine.close()
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-C", str(self.upstream), *args], text=True, stderr=subprocess.DEVNULL
        ).strip()

    def commit(self):
        self.git("add", ".")
        self.git(
            "-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-m", "snapshot"
        )

    def test_remote_snapshots_update_without_touching_developer_checkout(self):
        self.assertEqual(self.engine.status()["state"], "degraded")
        report = self.engine.crawler.cycle(history=False, force=True)
        self.assertEqual(report["jobs"]["code"]["state"], "ready", report)
        managed = Path(self.engine.sources["api"]["root"])
        self.assertNotEqual(managed, self.upstream)
        self.assertTrue(self.engine.navigation.search("CANONICAL_SENTINEL")["items"])
        first = self.engine.metadata()["generation"]
        (self.upstream / "main.py").write_text(
            'def second_version():\n    return "NEW_CANONICAL"\n'
        )
        self.commit()
        (self.upstream / "scratch.py").write_text("UNCOMMITTED_DEVELOPER_SENTINEL")
        self.engine.crawler.cycle(history=False, force=True)
        self.assertNotEqual(self.engine.metadata()["generation"], first)
        self.assertTrue(self.engine.navigation.search("NEW_CANONICAL")["items"])
        self.assertFalse(self.engine.navigation.search("UNCOMMITTED_DEVELOPER_SENTINEL")["items"])
        self.assertTrue((self.upstream / "scratch.py").exists())
        self.assertEqual(self.git("branch", "--show-current"), "main")

    def test_remote_error_withholds_old_snapshot_and_edits_are_preserved(self):
        self.engine.crawler.cycle(history=False, force=True)
        managed = Path(self.engine.sources["api"]["root"])
        (managed / "local_note.md").write_text("Do not delete this")
        self.assertEqual(self.engine.navigation.search("CANONICAL_SENTINEL")["items"], [])
        report = self.engine.crawler.cycle(history=False, force=True)
        self.assertEqual(report["jobs"]["code"]["state"], "partial")
        self.assertTrue((managed / "local_note.md").exists())
        self.assertEqual(self.engine.architecture.overview()["items"], [])
        self.assertIn("local edits", self.engine.status()["remote_sources"]["api"]["error"])

    def test_resume_owned_checkout_without_origin(self):
        self.engine.crawler.cycle(history=False, force=True)
        managed = Path(self.engine.sources["api"]["root"])
        subprocess.check_call(["git", "-C", str(managed), "remote", "remove", "origin"])
        report = self.engine.crawler.cycle(history=False, force=True)
        self.assertEqual(report["jobs"]["code"]["state"], "ready", report)
        self.assertTrue(self.engine.navigation.search("CANONICAL_SENTINEL")["items"])

    def test_reject_unsafe_remote_and_scope_changes_get_separate_checkouts(self):
        for change in (
            {"url": "ext::sh -c danger"},
            {"url": "https://token@example.test/repo"},
            {"ref": "main"},
            {"path": "/tmp/owned"},
        ):
            config = dict(self.config, sources=[dict(self.config["sources"][0], **change)])
            self.manifest.write_text(json.dumps(config))
            with self.assertRaises(ValueError):
                Engine(self.manifest, self.root / "state")
        config = dict(self.config, workspace="other")
        self.manifest.write_text(json.dumps(config))
        other = Engine(self.manifest, self.root / "state")
        try:
            self.assertNotEqual(other.sources["api"]["root"], self.engine.sources["api"]["root"])
        finally:
            other.close()


if __name__ == "__main__":
    unittest.main()
