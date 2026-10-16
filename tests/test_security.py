import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from context_engine.core import Engine


class StorageSecurityTests(unittest.TestCase):
    def test_private_database_and_existing_wal_permissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "src").mkdir()
            (root / "src/code.py").write_text('SYNTHETIC = "private"\n')
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "environment": "test",
                        "workspace": "security",
                        "sources": [{"id": "src", "path": "src"}],
                    }
                )
            )
            old = os.umask(0o022)
            try:
                engine = Engine(manifest, root / "state")
                try:
                    engine.index()
                    store = engine.store
                    self.assertEqual(stat.S_IMODE(store.parent.stat().st_mode), 0o700)
                    for path in (store, Path(str(store) + "-wal"), Path(str(store) + "-shm")):
                        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                finally:
                    engine.close()
                store.chmod(0o644)
                engine = Engine(manifest, root / "state")
                engine.close()
                self.assertEqual(stat.S_IMODE(store.stat().st_mode), 0o600)
                store.unlink()
                target = root / "outside"
                target.write_text("do not modify")
                store.symlink_to(target)
                with self.assertRaisesRegex(ValueError, "non-regular"):
                    Engine(manifest, root / "state")
                self.assertEqual(target.read_text(), "do not modify")
            finally:
                os.umask(old)
