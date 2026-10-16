import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from context_engine import runtime_identity
from context_engine.core import Engine


class RuntimeIdentityTests(unittest.TestCase):
    def test_foreign_or_legacy_writer_is_stale_even_without_file_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "src"
            source.mkdir()
            (source / "code.py").write_text("SAFE_CANARY = 1\n")
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "environment": "test",
                        "workspace": "runtime",
                        "sources": [{"id": "code", "path": str(source)}],
                    }
                )
            )
            engine = Engine(manifest, root / "state")
            try:
                engine.index()
                self.assertEqual(engine.status()["runtime"]["state"], "current")
                for backend, expected in [
                    (None, "legacy_index"),
                    ({"release": "old", "build_id": "0" * 64}, "different_writer"),
                ]:
                    metadata = engine.metadata()
                    if backend is None:
                        metadata.pop("backend")
                    else:
                        metadata["backend"] = backend
                    with engine.db:
                        engine.db.execute(
                            "UPDATE meta SET value=? WHERE key='index'", (json.dumps(metadata),)
                        )
                    status = engine.status()
                    self.assertEqual(status["drift_files"], 0)
                    self.assertEqual(status["state"], "stale")
                    self.assertEqual(status["runtime"]["state"], expected)
                    self.assertFalse(engine.navigation.search("SAFE_CANARY")["items"])
                    engine.index()
                    self.assertEqual(engine.status()["state"], "ready")
                    self.assertTrue(engine.navigation.search("SAFE_CANARY")["items"])
            finally:
                engine.close()

    def test_replacing_backend_files_fences_an_already_loaded_process(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree(
                runtime_identity.ROOT,
                root / "context_engine",
                ignore=shutil.ignore_patterns("__pycache__"),
            )
            code = r"""
import json
from pathlib import Path
from context_engine.core import Engine
from context_engine import runtime_identity
Path('src').mkdir()
Path('src/code.py').write_text('SOURCE_CANARY = 1\n')
Path('manifest.json').write_text(json.dumps({'schema_version':1, 'environment':'test', 'workspace':'runtime', 'sources':[{'id':'code','path':'src'}]}))
e = Engine('manifest.json', 'state')
e.index()
before = e.metadata()
identity = runtime_identity.identity()
p = Path('context_engine/core.py')
p.write_text(p.read_text() + '\n# replacement installed while running\n')
assert runtime_identity.identity() == identity
assert e.status()['runtime']['state'] == 'restart_required'
assert e.status()['state'] == 'stale'
assert not e.navigation.search('SOURCE_CANARY')['items']
try:
    e.index()
except ValueError as error:
    assert 'restart' in str(error)
else:
    raise AssertionError('old loaded writer was allowed')
assert e.metadata() == before
e.close()
print('fenced')
"""
            result = subprocess.run(
                [sys.executable, "-c", code],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
                env={**os.environ, "PYTHONPATH": str(root)},
            )
            self.assertEqual(result.stdout.strip(), "fenced")
            # A fresh process can deliberately refresh with the replacement backend.
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "context_engine",
                    "--manifest",
                    str(root / "manifest.json"),
                    "--state",
                    str(root / "state"),
                    "index",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
                env={**os.environ, "PYTHONPATH": str(root)},
            )
            self.assertIn("backend", json.loads(result.stdout))

    def test_build_identity_is_location_independent_and_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("a", "b"):
                (root / name).mkdir()
                (root / name / "engine.py").write_text("x = 1\n")
            self.assertEqual(
                runtime_identity.source_build(root / "a"), runtime_identity.source_build(root / "b")
            )
            (root / "b/engine.py").write_text("x = 2\n")
            self.assertNotEqual(
                runtime_identity.source_build(root / "a"), runtime_identity.source_build(root / "b")
            )
            (root / "a/escape.py").symlink_to(root / "b/engine.py")
            with self.assertRaises(ValueError):
                runtime_identity.source_build(root / "a")
