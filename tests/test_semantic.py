import json
import tempfile
import unittest
from pathlib import Path

from context_engine.core import Engine
from context_engine.embeddings import EmbeddingError, EmbeddingIdentity, normalize


class Provider:
    """Deterministic contract double, not evidence of semantic model quality."""

    def __init__(self, revision="one"):
        self.identity = EmbeddingIdentity("test", "concepts", revision, 2)
        self.calls = []
        self.fail = False
        self.on_query = None
        self.on_documents = None

    def embed_documents(self, texts):
        self.calls.extend(texts)
        if self.on_documents:
            self.on_documents()
        if self.fail:
            raise RuntimeError("secret: provider response must not leak")
        return [[1.0, 0.0] if "invoice" in t else [0.0, 1.0] for t in texts]

    def embed_query(self, text):
        if self.on_query:
            self.on_query()
        if self.fail:
            raise RuntimeError("secret")
        return [1.0, 0.0] if text == "billing" else [0.0, 1.0]


class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "src").mkdir()
        (self.root / "src/pay.py").write_text('def invoice():\n    return "charged"\n')
        (self.root / "src/ship.py").write_text('def parcel():\n    return "sent"\n')
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "environment": "test",
                    "workspace": "demo",
                    "sources": [{"id": "code", "path": "src"}],
                }
            )
        )
        self.provider = Provider()
        self.engine = Engine(self.manifest, self.root / "state", self.provider)

    def tearDown(self):
        self.engine.close()
        self.tmp.cleanup()

    def test_real_boundary_semantic_hybrid_and_lexical(self):
        self.assertFalse(self.engine.status()["capabilities"]["semantic_search"])
        self.engine.index()
        self.assertTrue(self.engine.status()["capabilities"]["semantic_search"])
        self.assertEqual(self.engine.search("billing", mode="lexical")["items"], [])
        sem = self.engine.search("billing", mode="semantic", token_budget=8000)
        self.assertEqual(sem["items"][0]["path"], "pay.py")
        self.assertEqual(sem["retrieval"]["used"], "semantic")
        # Query vector points at shipping, but literal identifier still wins.
        hybrid = self.engine.search("invoice", mode="hybrid", token_budget=8000)
        self.assertEqual(hybrid["items"][0]["path"], "pay.py")
        self.assertLessEqual(hybrid["budget"]["used_estimated_tokens"], 8000)
        self.assertTrue(
            self.engine.search("billing", mode="semantic", token_budget=1)["budget"][
                "omitted_files"
            ]
        )

    def test_incremental_cache_revision_and_deletion(self):
        first = self.engine.index()["semantic"]
        self.assertGreater(first["embedded"], 0)
        self.provider.calls.clear()
        self.assertEqual(self.engine.index()["semantic"]["embedded"], 0)
        self.assertEqual(self.provider.calls, [])
        (self.root / "src/pay.py").write_text('def invoice():\n    return "refunded"\n')
        self.assertEqual(self.engine.search("billing", mode="semantic")["items"], [])
        update = self.engine.index()["semantic"]
        self.assertGreater(update["embedded"], 0)
        self.assertTrue(all("refunded" in t for t in self.provider.calls))
        (self.root / "src/pay.py").unlink()
        self.engine.index()
        self.assertTrue(
            all(
                i["path"] == "ship.py"
                for i in self.engine.search("billing", mode="semantic")["items"]
            )
        )
        self.assertEqual(
            self.engine.semantic.status()["chunks"],
            self.engine.db.execute("SELECT count(*) FROM vectors").fetchone()[0],
        )

    def test_model_identity_change_rebuilds_without_mixing(self):
        self.engine.index()
        self.engine.close()
        changed = Provider("two")
        self.engine = Engine(self.manifest, self.root / "state", changed)
        self.assertEqual(self.engine.status()["semantic"]["state"], "pending")
        self.assertEqual(self.engine.search("billing", mode="semantic")["items"], [])
        self.engine.index()
        self.assertGreater(len(changed.calls), 0)
        self.assertEqual(
            self.engine.db.execute("SELECT count(distinct provider) FROM vectors").fetchone()[0], 1
        )

    def test_provider_outage_fallback_and_recovery(self):
        self.provider.fail = True
        result = self.engine.index()
        self.assertEqual(result["semantic"]["state"], "error")
        self.assertNotIn("secret", json.dumps(result))
        fallback = self.engine.search("invoice", mode="hybrid")
        self.assertEqual(fallback["retrieval"]["used"], "lexical")
        self.assertTrue(fallback["items"])
        self.assertEqual(self.engine.search("invoice", mode="semantic")["items"], [])
        self.provider.fail = False
        self.engine.index()
        self.provider.fail = True
        self.assertEqual(
            self.engine.search("invoice", mode="hybrid")["retrieval"]["used"], "lexical"
        )
        self.assertEqual(
            self.engine.search("invoice", mode="semantic")["retrieval"]["used"], "none"
        )

    def test_source_change_during_query_is_withheld_even_on_failure(self):
        self.engine.index()
        self.provider.on_query = lambda: (self.root / "src/pay.py").write_text("NEW = 1\n")
        self.provider.fail = True
        self.assertEqual(self.engine.search("invoice", mode="hybrid")["items"], [])

    def test_source_change_during_embedding_is_not_published(self):
        self.provider.on_documents = lambda: (self.root / "src/pay.py").write_text("NEW = 1\n")
        result = self.engine.index()
        self.assertEqual(result["semantic"]["state"], "error")
        self.assertEqual(self.engine.db.execute("SELECT count(*) FROM vectors").fetchone()[0], 0)

    def test_invalid_vectors_fail_atomically(self):
        for vector in ([0, 0], [float("nan"), 1], [float("inf"), 1], [1], ["1", 1], [True, 1]):
            with self.assertRaises(EmbeddingError):
                normalize(vector, 2)
        self.provider.embed_documents = lambda texts: [[1.0] for t in texts]
        self.assertEqual(self.engine.index()["semantic"]["state"], "error")
        self.assertEqual(self.engine.db.execute("SELECT count(*) FROM vectors").fetchone()[0], 0)
        self.provider.embed_documents = lambda texts: []
        self.assertEqual(self.engine.index()["semantic"]["state"], "error")

    def test_personal_source_never_crosses_store(self):
        self.engine.index()
        personal = self.root / "personal"
        personal.mkdir()
        (personal / "secret.md").write_text("personal sentinel invoice")
        manifest = self.root / "personal.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "environment": "personal",
                    "workspace": "mine",
                    "sources": [{"id": "notes", "path": "personal"}],
                }
            )
        )
        other = Engine(manifest, self.root / "state", Provider())
        try:
            other.index()
            self.assertNotEqual(other.store, self.engine.store)
            self.assertTrue(
                all(
                    i["source"] == "code"
                    for i in self.engine.search("sentinel", mode="semantic")["items"]
                )
            )
        finally:
            other.close()

    def test_corrupt_vector_falls_back_and_reindex_repairs(self):
        self.engine.index()
        with self.engine.db:
            self.engine.db.execute("UPDATE vectors SET vector='[0,0]'")
        fallback = self.engine.search("invoice", mode="hybrid")
        self.assertEqual(fallback["retrieval"]["used"], "lexical")
        self.assertGreater(self.engine.index()["semantic"]["embedded"], 0)
        self.assertEqual(
            self.engine.search("billing", mode="semantic")["retrieval"]["used"], "semantic"
        )

    def test_equal_scores_are_stable_after_row_ids_change(self):
        self.provider.embed_documents = lambda texts: [[1.0, 0.0] for t in texts]
        self.provider.embed_query = lambda text: [1.0, 0.0]
        self.engine.index()
        before = self.engine.search("unmatched", mode="hybrid", token_budget=8000)["items"][0][
            "path"
        ]
        path = self.root / "src/pay.py"
        original = path.read_text()
        path.write_text(original + "# temporary edit\n")
        self.engine.index()
        path.write_text(original)
        self.engine.index()
        after = self.engine.search("unmatched", mode="hybrid", token_budget=8000)["items"][0][
            "path"
        ]
        self.assertEqual(before, after)
