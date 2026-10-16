"""Opt-in real model + MCP smoke; regular tests remain dependency-free."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from context_engine.core import Engine

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(
    os.environ.get("CONTEXT_ENGINE_MODEL_CACHE"),
    "Set CONTEXT_ENGINE_MODEL_CACHE to a prefetched pinned model cache",
)
class LocalModelTests(unittest.TestCase):
    def test_actual_embeddings_through_mcp(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "auth").mkdir()
            (root / "shipping").mkdir()
            (root / "auth/session.py").write_text(
                'def revoke_session(token, sessions):\n    """Invalidate the authentication session."""\n    sessions.pop(token, None)\n'
            )
            (root / "shipping/send.py").write_text(
                'def dispatch_parcel(parcel, truck):\n    """Transport goods to their destination."""\n    truck.append(parcel)\n'
            )
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "environment": "real-model-test",
                        "workspace": "mcp",
                        "sources": [
                            {"id": "auth", "path": "auth"},
                            {"id": "shipping", "path": "shipping"},
                        ],
                        "embeddings": {
                            "provider": "sentence-transformers",
                            "model": "sentence-transformers/all-MiniLM-L6-v2",
                            "revision": "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
                            "dimensions": 384,
                            "cache_folder": os.environ["CONTEXT_ENGINE_MODEL_CACHE"],
                        },
                    }
                )
            )
            engine = Engine(manifest, root / "state")
            try:
                self.assertEqual(engine.index()["semantic"]["state"], "ready")
                self.assertEqual(engine.index()["semantic"]["embedded"], 0)
                self.assertEqual(engine.search("sign someone out", mode="lexical")["items"], [])
            finally:
                engine.close()
            requests = [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-11-25"},
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "index_status", "arguments": {}},
                },
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "get_context_bundle",
                        "arguments": {
                            "task": "sign someone out",
                            "mode": "semantic",
                            "token_budget": 8000,
                        },
                    },
                },
            ]
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "context_engine",
                    "--manifest",
                    str(manifest),
                    "--state",
                    str(root / "state"),
                    "serve",
                ],
                cwd=ROOT,
                input="\n".join(map(json.dumps, requests)) + "\n",
                text=True,
                capture_output=True,
                check=True,
                timeout=120,
            )
            responses = [json.loads(line) for line in result.stdout.splitlines()]
            status = json.loads(responses[1]["result"]["content"][0]["text"])
            bundle = json.loads(responses[2]["result"]["content"][0]["text"])
            self.assertTrue(status["capabilities"]["semantic_search"])
            self.assertEqual(bundle["retrieval"]["used"], "semantic")
            self.assertEqual(bundle["items"][0]["source"], "auth")
            self.assertTrue(bundle["items"][0]["hash"])
