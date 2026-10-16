import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.ralph_checkpoint import fingerprint, verify


class RalphCheckpointTests(unittest.TestCase):
    def test_untracked_source_change_cannot_receive_a_green_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "untracked.py"
            source.write_text("before")
            before = fingerprint(root)

            def changed(*args, **kwargs):
                source.write_text("after")
                from subprocess import CompletedProcess

                return CompletedProcess(args, 0)

            with patch("scripts.ralph_checkpoint.run_checks", side_effect=changed):
                result = verify(root)
            self.assertEqual(result["status"], "source_changed")
            self.assertNotEqual(before, fingerprint(root))
            record = next(root.glob(".context-engine/ralph/*/checkpoint.json"))
            self.assertEqual(record.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(record.read_text())["status"], "source_changed")

    def test_failed_and_unavailable_checks_stay_failed(self):
        from subprocess import CompletedProcess, TimeoutExpired

        for outcome, expected in [
            (CompletedProcess([], 1), "failed"),
            (OSError(), "unavailable"),
            (TimeoutExpired([], 1), "timeout"),
            (CompletedProcess([], 0), "passed"),
        ]:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp:
                options = (
                    {"side_effect": outcome}
                    if isinstance(outcome, Exception)
                    else {"return_value": outcome}
                )
                with patch("scripts.ralph_checkpoint.run_checks", **options):
                    self.assertEqual(verify(Path(temp))["status"], expected)

    def test_symlink_source_and_output_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            outside = Path(temp) / "outside"
            outside.mkdir()
            (root / "escape.py").symlink_to(outside)
            with self.assertRaises(ValueError):
                fingerprint(root)
            (root / "escape.py").unlink()
            (root / ".context-engine").symlink_to(outside)
            with self.assertRaises(ValueError):
                verify(root)
            self.assertEqual(list(outside.iterdir()), [])
