import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from context_engine.core import Engine
from context_engine.history import window
from context_engine.history_providers import CollectionError, GitHub, local_git, repository

ROOT = Path(__file__).resolve().parents[1]
START, END = "2026-03-09T00:00:00Z", "2026-09-09T23:59:59Z"


def record(**kwargs):
    return dict(
        {
            "source": "api",
            "kind": "pr",
            "id": "12",
            "occurred_at": "2026-06-01T12:00:00Z",
            "title": "Retry task delivery",
            "body": "Deduplicate delivery before retrying a task.",
            "author": "github:alice",
            "files": ["src/tasks.py", "src/queue.py"],
            "reviewers": ["github:bob", "github:bob"],
            "url": "https://github.com/company/api/pull/12",
        },
        **kwargs,
    )


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / "api"
        self.repo.mkdir()
        self.manifest = self.root / "team.json"
        self.manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "environment": "test",
                    "workspace": "team",
                    "sources": [{"id": "api", "path": "api"}],
                    "exclude": ["private/*"],
                }
            )
        )
        self.engine = Engine(self.manifest, self.root / "state")

    def tearDown(self):
        self.engine.close()
        self.tmp.cleanup()

    def ingest(self, rows, **kwargs):
        return self.engine.history.ingest(
            provider="import",
            since=START,
            until=END,
            data={"schema_version": 1, "records": rows, "gaps": []},
            **kwargs,
        )

    def git(self, *args, **kwargs):
        return subprocess.check_output(
            ["git", "-C", str(self.repo), *args], text=True, **kwargs
        ).strip()

    def commit(self, path, date="2026-06-01T12:00:00+00:00"):
        file = self.repo / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("hello\n")
        self.git("add", ".")
        self.git(
            "-c",
            "user.name=Alice",
            "-c",
            "user.email=alice@example.test",
            "commit",
            "-m",
            "Retry delivery",
            env=dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date),
        )
        return self.git("rev-parse", "HEAD")

    def test_calendar_window_timezone_and_validation(self):
        self.assertEqual(
            window(until="2024-08-31"), ("2024-02-29T00:00:00Z", "2024-08-31T00:00:00Z")
        )
        self.assertEqual(window(since="2026-03-09T04:00:00+04:00", until=END)[0], START)
        for kwargs in (
            {"months": 0},
            {"months": True},
            {"since": "tomorrow"},
            {"since": END, "until": START},
        ):
            with self.assertRaises(ValueError):
                window(**kwargs)

    def test_import_idempotency_fts_holders_and_budget(self):
        rows = [
            record(),
            record(kind="commit", id="a" * 40, author="git:Alice <a@example.test>", reviewers=[]),
        ]
        first = self.ingest(rows)
        self.assertEqual(first["inserted"], 2)
        self.assertEqual(self.ingest(rows)["unchanged"], 2)
        result = self.engine.history.search("deduplicate", token_budget=8000)
        self.assertEqual(len(result["items"]), 2)
        self.assertTrue(all(i["citation"]["hash"] for i in result["items"]))
        holders = self.engine.history.search("delivery", kind="holder", token_budget=8000)["items"]
        bob = next(i for i in holders if i["actor"] == "github:bob")
        self.assertEqual(
            bob["reviewed_prs"], 1
        )  # Two files in one area and duplicate reviewer: one event.
        self.assertEqual(bob["authored_prs"], 0)
        self.assertEqual(bob["area"], "src")
        tiny = self.engine.history.search("delivery", token_budget=1)
        self.assertEqual(tiny["items"], [])
        self.assertGreater(tiny["budget"]["omitted_items"], 0)
        self.assertEqual(
            self.engine.search("delivery")["items"], []
        )  # Separate from code freshness/index.
        self.engine.index()
        self.assertEqual(self.engine.history.status()["records"], 2)

    def test_scope_filter_invalid_rows_and_window(self):
        result = self.ingest(
            [
                record(),
                record(source="personal"),
                record(id="13", files=["../secret"]),
                record(id="14", files=["private/secret"]),
                record(id="15", occurred_at="2025-01-01"),
                record(id="16", body=42),
            ]
        )
        self.assertEqual((result["accepted"], result["rejected"], result["skipped"]), (1, 3, 2))
        with self.assertRaises(ValueError):
            self.engine.history.search("", source="personal")
        self.assertEqual(self.engine.history.search("", since="2026-07-01", until=END)["items"], [])
        config = json.loads(self.manifest.read_text())
        config["environment"] = "personal"
        self.manifest.write_text(json.dumps(config))
        other = Engine(self.manifest, self.root / "state")
        try:
            self.assertEqual(other.history.status()["records"], 0)
        finally:
            other.close()

    def test_local_git_real_subdirectory_scope_and_gateway_denial(self):
        self.git("init", "-q")
        self.commit("old.py", "2025-01-01T12:00:00+00:00")
        inside = self.commit("src/task.py")
        self.commit("private/secret.py")
        rows, gaps = local_git({"root": str(self.repo / "src")}, START, END)
        self.assertEqual([r["id"] for r in rows], [inside])
        self.assertEqual(rows[0]["files"], ["task.py"])
        self.assertIsNone(repository({"root": str(self.repo / "src")}))
        result = self.engine.history.ingest(provider="gateway", since=START, until=END)
        self.assertEqual(result["inserted"], 1)
        self.assertTrue(any("No gateway adapter" in g for g in result["gaps"]))
        self.assertEqual(self.engine.history.search("delivery")["items"][0]["id"], inside)

    def test_gateway_command_and_fallback_preserve_remote_snapshot(self):
        script = self.root / "gateway.py"
        script.write_text(
            "import json,sys\nr=json.load(sys.stdin)\nassert r['since']=='" + START + "'\n"
            "print("
            + repr(
                json.dumps(
                    {"schema_version": 1, "records": [record()], "gaps": ["reviews limited"]}
                )
            )
            + ")\n"
        )
        self.engine.config["history"] = {"gateway_command": [sys.executable, str(script)]}
        result = self.engine.history.ingest(since=START, until=END)
        self.assertEqual(result["inserted"], 1)
        self.assertIn("reviews limited", result["gaps"])
        self.ingest([record(files=[], reviewers=[], body="")])
        item = self.engine.history.search("deduplicate")["items"][0]
        self.assertEqual(item["files"], ["src/queue.py", "src/tasks.py"])
        self.assertEqual(item["reviewers"], ["github:bob"])
        self.ingest([record(occurred_at="2026-04-01", title="older")])
        self.assertEqual(
            self.engine.history.search("delivery")["items"][0]["title"], "Retry task delivery"
        )

    def test_cli_and_mcp_share_ingestion_and_readonly_annotations(self):
        data = self.root / "history.json"
        data.write_text(json.dumps({"schema_version": 1, "records": [record()], "gaps": []}))
        cli = [
            sys.executable,
            "-m",
            "context_engine",
            "--manifest",
            str(self.manifest),
            "--state",
            str(self.root / "state"),
        ]
        completed = subprocess.run(
            cli
            + [
                "ingest-history",
                "--provider",
                "import",
                "--input",
                str(data),
                "--since",
                START,
                "--until",
                END,
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(json.loads(completed.stdout)["inserted"], 1)
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "search_history", "arguments": {"query": "delivery"}},
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "ingest_history",
                    "arguments": {
                        "provider": "import",
                        "since": START,
                        "until": END,
                        "data": {"schema_version": 1, "records": [record(id="13")], "gaps": []},
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "history_request", "arguments": {"until": END}},
            },
        ]
        completed = subprocess.run(
            cli + ["serve"],
            input="\n".join(map(json.dumps, requests)) + "\n",
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        results = [json.loads(line)["result"] for line in completed.stdout.splitlines()]
        annotations = {t["name"]: t["annotations"] for t in results[1]["tools"]}
        self.assertFalse(annotations["ingest_history"]["readOnlyHint"])
        self.assertTrue(annotations["search_history"]["readOnlyHint"])
        self.assertEqual(json.loads(results[2]["content"][0]["text"])["items"][0]["id"], "12")
        self.assertEqual(json.loads(results[3]["content"][0]["text"])["inserted"], 1)
        self.assertEqual(
            json.loads(results[4]["content"][0]["text"])["since"], "2026-03-09T23:59:59Z"
        )

    def test_gateway_outage_keeps_remote_citations_and_does_not_bypass_gateway(self):
        remote = record(kind="commit", id="a" * 40, reviewers=[])
        self.ingest([remote])
        before = self.engine.history.search("delivery")["items"][0]["citation"]
        self.engine.config["history"] = {"gateway_command": ["/does/not/exist"]}
        fallback = dict(remote, author="git:Alice <a@example.test>", url="", files=[])
        with (
            patch("context_engine.history.local_git", return_value=([fallback], [])),
            patch("context_engine.history.GitHub") as github,
        ):
            report = self.engine.history.ingest(since=START, until=END)
        github.assert_not_called()
        self.assertEqual(report["unchanged"], 1)
        after = self.engine.history.search("delivery")["items"][0]
        self.assertEqual(after["citation"], before)
        self.assertEqual(after["author"], "github:alice")
        self.assertTrue(report["gaps"])

    def test_excerpt_keeps_late_query_match_and_reports_actual_omissions(self):
        body = "Background " * 500 + "idempotency"
        self.ingest([record(body=body)])
        item = self.engine.history.search("idempotency")["items"][0]
        self.assertIn("idempotency", item["summary"])
        self.assertGreater(item["summary_character_start"], 1200)
        self.assertEqual(len(item["summary"]) + item["omitted"]["body_characters"], len(body))


class GitHubTests(unittest.TestCase):
    def pr(self, number=1, updated="2026-06-01T00:00:00Z"):
        return {
            "number": number,
            "updated_at": updated,
            "title": "Task retries",
            "body": "Retry",
            "user": {"login": "alice"},
            "html_url": "https://github.com/company/api/pull/" + str(number),
        }

    def test_pr_pagination_window_and_partial_detail(self):
        client = GitHub("company/api")
        calls = []

        def api(endpoint, params=None):
            calls.append((endpoint, params))
            if endpoint == "commits":
                raise CollectionError("denied")
            if endpoint == "pulls":
                return (
                    [self.pr(i) for i in range(1, 101)]
                    if params["page"] == 1
                    else [self.pr(101), self.pr(102, "2025-01-01T00:00:00Z")]
                )
            if endpoint.endswith("/files"):
                return [{"filename": "src/task.py"}]
            raise CollectionError("reviews denied")

        with patch.object(client, "api", side_effect=api):
            rows, gaps = client.collect(START, END)
        self.assertEqual(len(rows), 101)
        self.assertTrue(all(r["files"] == ["src/task.py"] and not r["reviewers"] for r in rows))
        self.assertTrue(any("commits incomplete" in g for g in gaps))
        self.assertTrue(any("reviews denied" in g for g in gaps))
        self.assertEqual(len([x for x in calls if x[0] == "pulls"]), 2)

    def test_pagination_cap_preserves_collected_records(self):
        client = GitHub("company/api", max_pages=1)

        def api(endpoint, params=None):
            if endpoint == "commits":
                return []
            if endpoint == "pulls":
                return [self.pr(i) for i in range(1, 101)]
            return []

        with patch.object(client, "api", side_effect=api):
            rows, gaps = client.collect(START, END)
        self.assertEqual(len(rows), 100)
        self.assertTrue(any("Pagination limit" in g for g in gaps))

    def test_remote_commit_uses_local_files_and_actual_reviewers(self):
        client = GitHub("company/api")

        def api(endpoint, params=None):
            if endpoint == "commits":
                return [
                    {
                        "sha": "a" * 40,
                        "commit": {
                            "author": {"name": "Alice", "email": "a@example.test"},
                            "committer": {"date": "2026-06-01T00:00:00Z"},
                            "message": "Retry tasks",
                        },
                        "author": {"login": "alice"},
                    }
                ]
            if endpoint == "pulls":
                return [self.pr()]
            if endpoint.endswith("/files"):
                return [{"filename": "src/task.py"}]
            if endpoint.endswith("/reviews"):
                return [
                    {"user": {"login": "bob"}, "submitted_at": "2026-06-01T00:00:00Z"},
                    {"user": {"login": "carol"}, "submitted_at": None},
                ]
            raise AssertionError("Unexpected commit detail fetch")

        with patch.object(client, "api", side_effect=api):
            rows, gaps = client.collect(START, END, [{"id": "a" * 40, "files": ["src/task.py"]}])
        self.assertEqual(rows[0]["author"], "github:alice")
        self.assertEqual(rows[0]["files"], ["src/task.py"])
        self.assertEqual(rows[1]["reviewers"], ["github:bob"])


if __name__ == "__main__":
    unittest.main()
