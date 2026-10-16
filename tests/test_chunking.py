import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from context_engine.chunking import Chunker
from context_engine.core import Engine


class ChunkingTests(unittest.TestCase):
    def test_missing_optional_provider_falls_back_with_gap(self):
        chunker = Chunker({"provider": "code-splitter"})
        chunker.module = None
        chunks = list(chunker.units("src/main.rs", 'fn main() { println!("hello"); }'))
        self.assertTrue(chunks)
        self.assertTrue(all("unavailable" in c["parser_error"] for c in chunks))

    @unittest.skipUnless(
        importlib.util.find_spec("code_splitter"), "Optional code-splitter is not installed"
    )
    def test_real_rust_ast_boundaries_citations_and_incremental_index(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "code").mkdir()
            text = "// intro\n\n" + "\n".join(
                "pub fn function_%s() -> i32 {\n    %s\n}\n" % (i, i) for i in range(20)
            )
            (root / "code/lib.rs").write_text(text)
            manifest = root / "team.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "environment": "rust",
                        "workspace": "test",
                        "sources": [{"id": "rust", "path": "code"}],
                        "chunking": {"provider": "code-splitter", "max_tokens": 32},
                    }
                )
            )
            engine = Engine(manifest, root / "state")
            try:
                engine.index()
                rows = list(engine.db.execute("SELECT * FROM evidence"))
                self.assertGreater(len(rows), 1)
                self.assertTrue(all(r["method"] == "code-splitter-ast" for r in rows))
                for row in rows:
                    self.assertEqual(
                        row["text"],
                        "\n".join(text.splitlines()[row["line_start"] - 1 : row["line_end"]]),
                    )
                    self.assertEqual(row["text"].count("{"), row["text"].count("}"))
                self.assertTrue(
                    engine.navigation.search("function_13", mode="lexical", token_budget=8000)[
                        "items"
                    ]
                )
                self.assertEqual(engine.index()["changed"], 0)
            finally:
                engine.close()


if __name__ == "__main__":
    unittest.main()
