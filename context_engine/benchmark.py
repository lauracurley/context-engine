"""Offline synthetic benchmark; never opens the selected workspace or exports paths."""

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from .budget import size


def run():
    from . import __version__
    from .core import Engine
    from .policy import load

    policy = load()
    parent = policy["storage_roots"][0] if policy else None
    with tempfile.TemporaryDirectory(prefix="context-synthetic-", dir=parent) as directory:
        root = Path(directory)
        for folder in ("api", "worker"):
            (root / folder).mkdir()
        (root / "api/main.py").write_text(
            "def enqueue():\n    return {'event': 'demo.requested'}\n"
        )
        (root / "worker/run.py").write_text(
            "def consume(message):\n    return message['event'] == 'demo.requested'\n"
        )
        (root / "api/Main.kt").write_text("class Demo {\n    fun process() = 1\n}\n")
        manifest = root / "fixture.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "environment": "synthetic",
                    "workspace": "benchmark",
                    "sources": [{"id": s, "path": s} for s in ("api", "worker")],
                }
            )
        )
        # A closed synthetic scope: ambient company source roots are never read.
        local_policy = root / "policy.json"
        local_policy.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "storage_roots": [str(root)],
                    "source_roots": [str(root)],
                    "allow_history": False,
                    "allow_remote_git": False,
                    "allow_embeddings": False,
                }
            )
        )
        local_policy.chmod(0o600)
        with patch.dict(
            os.environ,
            {"CONTEXT_ENGINE_POLICY": str(local_policy), "CONTEXT_ENGINE_REVIEW_POLICY": ""},
        ):
            engine = Engine(manifest, root / "state")
            try:
                start = time.monotonic()
                engine.index()
                index_ms = round((time.monotonic() - start) * 1000)
                rows = []
                recovery_count = 0

                def recovery():
                    nonlocal recovery_count
                    recovery_count += 1
                    (root / "api/main.py").write_text(
                        f"def enqueue():\n    return {recovery_count}\n"
                    )
                    before = engine.navigation.search("enqueue", mode="lexical")
                    engine.index()
                    after = engine.navigation.search("enqueue", mode="lexical")
                    return dict(after, before_state=before["state"])

                cases = [
                    (
                        "identifier",
                        lambda: engine.navigation.search("enqueue", source="api", mode="lexical"),
                        lambda r: len(r["items"]) == 1 and r["items"][0]["path"] == "main.py",
                    ),
                    (
                        "contract",
                        lambda: engine.navigation.related(
                            "api", "main.py", mode="graph", token_budget=4000
                        ),
                        lambda r: any(i["source"] == "worker" for i in r["items"]),
                    ),
                    (
                        "missing",
                        lambda: engine.navigation.search("NO_SUCH_IDENTIFIER_782"),
                        lambda r: not r["items"],
                    ),
                ]
                cases.append(
                    (
                        "stale_recovery",
                        recovery,
                        lambda r: (
                            r["before_state"] == "stale"
                            and r["state"] == "ready"
                            and bool(r["items"])
                        ),
                    )
                )
                for name, call, check in cases:
                    durations = []
                    results = []
                    for _ in range(3):
                        start = time.monotonic()
                        result = call()
                        durations.append(round((time.monotonic() - start) * 1000))
                        results.append(result)
                    rows.append(
                        {
                            "case": name,
                            "passed": all(check(r) for r in results),
                            "iterations": 3,
                            "response_bytes": size(results[-1]),
                            "median_ms": sorted(durations)[1],
                        }
                    )
                knowledge_checks = {}
                for kind in ("practice", "architecture", "convention", "decision", "procedure"):
                    record = engine.knowledge.template(kind, "api", "Main.kt")
                    record.update(
                        id="synthetic-" + kind,
                        title="Synthetic " + kind,
                        statement="Verify the synthetic fixture before changing it.",
                    )
                    engine.knowledge.propose(record)
                    hidden = not engine.knowledge.lookup(kind, "api", token_budget=8000)["items"]
                    engine.knowledge.decide(record["id"], 1, "approve")
                    agent = engine.knowledge.lookup(kind, "api", token_budget=8000)
                    wiki = engine.knowledge.wiki(kind, "api")
                    knowledge_checks[kind] = (
                        hidden
                        and bool(agent["items"])
                        and record["statement"] in wiki["markdown"]
                        and "rationale" not in agent["items"][0]
                    )
                kotlin = engine.navigation.search("Demo.process", mode="symbols")
                # Parser coverage is reported separately; absent optional parser is not silently a pass.
                from .evaluation_p1 import run as run_p1

                p1 = run_p1()
                return {
                    "p1_evidence": p1,
                    "schema_version": 1,
                    "report_kind": "synthetic_benchmark",
                    "suite": "client-readiness-3",
                    "engine_release": __version__,
                    "index_ms": index_ms,
                    "cases": rows,
                    "kotlin_parser_ready": bool(kotlin["items"]),
                    "knowledge_layers": knowledge_checks,
                    "passed": all(r["passed"] for r in rows)
                    and bool(kotlin["items"])
                    and all(knowledge_checks.values())
                    and p1["passed"],
                    "token_measurement": "unavailable",
                }
            finally:
                engine.close()
