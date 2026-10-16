import json
import tempfile
import unittest
from pathlib import Path

from context_engine.core import Engine, content_kind


class BuildCoverageTests(unittest.TestCase):
    def test_explicit_build_files_keep_scanner_boundaries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "src"
            source.mkdir()
            supported = [
                "requirements.txt",
                "requirements-structure.txt",
                "requirements.dev.txt",
                "Dockerfile",
                "Containerfile",
                "Makefile",
                "CMakeLists.txt",
                "justfile",
            ]
            for name in supported:
                (source / name).write_text("BUILD_CANARY = dependency\n")
                self.assertEqual(content_kind(name), "config")
            for name in ["private.txt", "requirements-secret.txt", ".env.txt"]:
                (source / name).write_text("PRIVATE_CANARY")
            (source / "requirements-binary.txt").write_bytes(b"PRIVATE\x00CANARY")
            (source / "requirements-large.txt").write_text("x" * 512001)
            (root / "outside").write_text("PRIVATE_CANARY")
            (source / "requirements-link.txt").symlink_to(root / "outside")
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "environment": "test",
                        "workspace": "build",
                        "sources": [{"id": "code", "path": str(source)}],
                        "exclude": ["requirements-secret.txt"],
                    }
                )
            )
            engine = Engine(manifest, root / "state")
            try:
                engine.index()
                paths = {row[0] for row in engine.db.execute("SELECT path FROM evidence")}
                self.assertEqual(paths, set(supported))
                self.assertTrue(engine.navigation.search("BUILD_CANARY")["items"])
                self.assertFalse(engine.navigation.search("PRIVATE_CANARY")["items"])
                (source / "requirements-structure.txt").unlink()
                engine.index()
                self.assertFalse(
                    engine.db.execute(
                        "SELECT 1 FROM evidence WHERE path = ?", ("requirements-structure.txt",)
                    ).fetchone()
                )
            finally:
                engine.close()
