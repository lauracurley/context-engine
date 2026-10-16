import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from context_engine.core import Engine, units
from context_engine.kotlin import extract

PARSERS = all(importlib.util.find_spec(n) for n in ("tree_sitter", "tree_sitter_kotlin"))
FIXTURE = """package demo.tasks
import demo.queue.publish as send

@Deprecated("old")
data class Task(val id: String, var priority: Int)
interface Queue {
    fun enqueue(task: Task)
}
object Worker {
    val label = "fakeCall()"
    // fakeCall()
    suspend fun consume(task: Task): String {
        send(task)
        return task.id
    }
}
fun String.valid(): Boolean = isNotEmpty()
typealias TaskId = String
"""


class KotlinTests(unittest.TestCase):
    def test_missing_parser_retains_text_and_reports_gap(self):
        with patch.dict("sys.modules", {"tree_sitter_kotlin": None}):
            data = extract(FIXTURE)
            self.assertFalse(data["facts"])
            self.assertIn("unavailable", data["gaps"][0])
            chunks = list(units("Worker.kt", FIXTURE))
            self.assertTrue(chunks)
            self.assertTrue(all(c["method"] == "text-window" and c["parser_error"] for c in chunks))

    @unittest.skipUnless(PARSERS, "Install requirements-navigation.txt for Kotlin parsing")
    def test_real_syntax_and_line_citations(self):
        data = extract(FIXTURE)
        self.assertFalse(data["gaps"], data)
        definitions = {f["name"]: f for f in data["facts"] if f["kind"] == "definition"}
        self.assertTrue(
            {
                "Task",
                "id",
                "priority",
                "Queue",
                "enqueue",
                "Worker",
                "label",
                "consume",
                "valid",
                "TaskId",
            }
            <= definitions.keys()
        )
        self.assertEqual(definitions["consume"]["qualified_name"], "Worker.consume")
        self.assertEqual(definitions["consume"]["lines"], [12, 15])
        calls = [f for f in data["facts"] if f["kind"] == "call"]
        self.assertEqual({f["name"] for f in calls}, {"send", "isNotEmpty"})
        self.assertEqual(next(f for f in data["facts"] if f["kind"] == "import")["alias"], "send")
        for c in units("Worker.kt", FIXTURE):
            self.assertEqual(
                c["text"], "\n".join(FIXTURE.splitlines()[c["line_start"] - 1 : c["line_end"]])
            )
        self.assertTrue(extract("fun broken( {")["gaps"])
        self.assertTrue(all(c["parser_error"] for c in units("Broken.kt", "fun broken( {")))
        # Script DSL calls and Unicode/backtick names retain real byte/line boundaries.
        data = extract('val café = "é"\nfun `valid name`() = café\nplugins {\n kotlin("jvm")\n}\n')
        self.assertFalse(data["gaps"], data)
        self.assertIn("valid name", {f["name"] for f in data["facts"] if f["kind"] == "definition"})

    @unittest.skipUnless(PARSERS, "Install requirements-navigation.txt for Kotlin parsing")
    def test_index_search_navigation_updates_and_deletion(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "src"
            source.mkdir()
            path = source / "Worker.kt"
            path.write_text(FIXTURE)
            (source / "build.gradle.kts").write_text('plugins {\n kotlin("jvm")\n}\n')
            manifest = root / "workspace.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "environment": "kotlin",
                        "workspace": "tasks",
                        "sources": [{"id": "api", "path": str(source)}],
                    }
                )
            )
            e = Engine(manifest, root / "state")
            try:
                e.index()
                self.assertTrue(e.structure.query(symbol="consume")["items"])
                symbols = e.navigation.search("Worker.consume", mode="symbols", source="api")
                self.assertEqual([i["symbol"] for i in symbols["items"]], ["Worker.consume"])
                self.assertEqual(symbols["items"][0]["lines"], [12, 15])
                calls = e.structure.query(mode="callers", symbol="send")["items"]
                self.assertEqual(calls[0]["owner"], "Worker.consume")
                self.assertTrue(e.search("consume", token_budget=8000)["items"])
                self.assertEqual(e.index()["changed"], 0)
                path.write_text(FIXTURE.replace("consume", "process"))
                self.assertEqual(e.status()["state"], "stale")
                self.assertEqual(e.index()["changed"], 1)
                self.assertFalse(e.structure.query(symbol="consume")["items"])
                self.assertTrue(e.structure.query(symbol="process")["items"])
                path.unlink()
                self.assertEqual(e.index()["deleted"], 1)
                self.assertFalse(e.structure.query(symbol="process")["items"])
            finally:
                e.close()
