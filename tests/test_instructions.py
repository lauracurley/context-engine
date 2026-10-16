import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from context_engine.budget import encode
from context_engine.core import Engine


class InstructionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        repo = self.root / "repo"
        for path, text in {
            "AGENTS.md": "Use English.\n",
            "src/AGENTS.md": "Run relevant tests.\n",
            "other/AGENTS.md": "UNRELATED_SENTINEL",
            "skills/review/SKILL.md": "Review evidence.\n",
            "src/main.py": "pass\n",
        }.items():
            file = repo / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(text)
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "environment": "team",
                    "workspace": "instructions",
                    "sources": [{"id": "repo", "path": str(repo)}],
                }
            )
        )
        self.engine = Engine(self.manifest, self.root / "state")
        self.engine.index()

    def tearDown(self):
        self.engine.close()
        self.tmp.cleanup()

    def test_order_applicability_and_explicit_skills(self):
        result = self.engine.instructions.resolve(
            "repo", ["src/new.py", "main.py"], ["skills/review/SKILL.md"]
        )
        self.assertEqual(
            [item["path"] for item in result["items"]],
            ["AGENTS.md", "src/AGENTS.md", "skills/review/SKILL.md"],
        )
        self.assertEqual(result["items"][1]["applies_to"], ["src/new.py"])
        self.assertNotIn("UNRELATED_SENTINEL", encode(result))
        for item in result["items"]:
            read = self.engine.navigation.read(
                item["source"], item["path"], expected_hash=item["hash"]
            )
            self.assertTrue(read["items"])
        self.assertTrue(result["content_is_untrusted"])

    def test_scope_and_invalid_paths(self):
        for path in [
            "../secret.py",
            "/tmp/secret.py",
            "./main.py",
            "a//b.py",
            ".git/config",
            "src",
        ]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.engine.instructions.resolve("repo", [path])
        with self.assertRaises(ValueError):
            self.engine.instructions.resolve("other", ["main.py"])
        (self.root / "repo/link").symlink_to(self.root)
        with self.assertRaises(ValueError):
            self.engine.instructions.resolve("repo", ["link/secret.py"])

    def test_stale_missing_and_budget(self):
        result = self.engine.instructions.resolve(
            "repo", ["src/new.py"], ["skills/missing/SKILL.md"]
        )
        self.assertEqual(result["state"], "partial")
        self.assertEqual(result["unavailable_candidates"], 1)
        result = self.engine.instructions.resolve("repo", ["src/new.py"], token_budget=1024)
        self.assertLessEqual(len(encode(result).encode()), 1024)
        self.assertEqual(result["budget"]["used_bytes"], len(encode(result).encode()))
        self.assertGreater(result["budget"]["omitted_items"], 0)
        (self.root / "repo/src/AGENTS.md").write_text("Changed instructions")
        result = self.engine.instructions.resolve("repo", ["src/new.py"])
        self.assertNotEqual(result["state"], "ready")
        self.assertFalse(result["items"])

    def test_excluded_and_symlink_instructions_are_reported_without_content(self):
        self.engine.excludes.append("src/AGENTS.md")
        self.engine.index()
        result = self.engine.instructions.resolve("repo", ["src/new.py"])
        self.assertEqual(result["state"], "partial")
        self.assertEqual([item["path"] for item in result["items"]], ["AGENTS.md"])
        (self.root / "private.md").write_text("PRIVATE_SENTINEL")
        (self.root / "repo/AGENTS.md").unlink()
        (self.root / "repo/AGENTS.md").symlink_to(self.root / "private.md")
        self.engine.index()
        result = self.engine.instructions.resolve("repo", ["main.py"])
        self.assertEqual(result["state"], "partial")
        self.assertFalse(result["items"])
        self.assertNotIn("PRIVATE_SENTINEL", encode(result))

    def test_cli_and_mcp(self):
        command = [
            sys.executable,
            "-m",
            "context_engine",
            "--manifest",
            str(self.manifest),
            "--state",
            str(self.root / "state"),
        ]
        cli = subprocess.run(
            [*command, "instructions", "--source=repo", "--path=src/new.py"],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(len(json.loads(cli.stdout)["items"]), 2)
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "resolve_instructions",
                "arguments": {"source": "repo", "paths": ["src/new.py"]},
            },
        }
        mcp = subprocess.run(
            [*command, "serve"],
            input=json.dumps({"jsonrpc": "2.0", "id": 0, "method": "initialize"})
            + "\n"
            + json.dumps(request)
            + "\n",
            text=True,
            capture_output=True,
            check=True,
        )
        result = json.loads(mcp.stdout.splitlines()[-1])["result"]
        self.assertFalse(result["isError"])
        self.assertEqual(len(json.loads(result["content"][0]["text"])["items"]), 2)
