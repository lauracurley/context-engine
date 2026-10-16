"""Repeatable offline task-evidence comparison using only generated fixtures."""

import json
import math
import os
import subprocess
import tempfile
import time
import tracemalloc
from pathlib import Path
from unittest.mock import patch

from .budget import size


def run():
    from .change_brief import brief
    from .core import Engine
    from .policy import load

    policy = load()
    parent = policy["storage_roots"][0] if policy else None
    with tempfile.TemporaryDirectory(prefix="context-p1-synthetic-", dir=parent) as directory:
        root = Path(directory).resolve()
        for name in ("api", "worker", "private"):
            (root / name).mkdir()
        original = "def enqueue():\n    return {'event': 'demo.requested'}\n"
        target = root / "api/main.py"
        target.write_text(original)
        (root / "worker/run.py").write_text(
            "def consume():\n    return {'event': 'demo.requested'}\n"
        )
        (root / "api/Main.kt").write_text("class Demo {\n    fun process() = 1\n}\n")
        (root / "api/Other.kt").write_text("class Other {\n    fun process() = 2\n}\n")
        (root / "private/secret.py").write_text("def private_marker(): return 1\n")
        for n in range(120):
            (root / "api" / f"distractor{n}.py").write_text(f"def unrelated_{n}(): return {n}\n")

        def git(*args):
            return subprocess.run(
                ["git", "-C", str(root / "api"), *args], check=True, capture_output=True
            ).stdout

        git("init", "-q")
        git("add", ".")
        git(
            "-c",
            "user.name=Synthetic",
            "-c",
            "user.email=synthetic@example.invalid",
            "commit",
            "-qm",
            "fixture A",
        )
        manifest = root / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "environment": "synthetic",
                    "workspace": "p1-evaluation",
                    "sources": [{"id": n, "path": n} for n in ("api", "worker")],
                }
            )
        )
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
            tracing = tracemalloc.is_tracing()
            if not tracing:
                tracemalloc.start()
            try:
                index_times = {}
                for phase in ("cold", "warm", "branch_b", "return_a"):
                    if phase == "branch_b":
                        git("checkout", "-qb", "fixture-b")
                        target.write_text("def alternate(): return 2\n")
                        git("add", ".")
                        git(
                            "-c",
                            "user.name=Synthetic",
                            "-c",
                            "user.email=synthetic@example.invalid",
                            "commit",
                            "-qm",
                            "fixture B",
                        )
                    if phase == "return_a":
                        git("checkout", "-q", "-")
                    start = time.perf_counter()
                    engine.index()
                    index_times[phase] = {
                        "ms": round((time.perf_counter() - start) * 1000, 3),
                        **engine.metadata()["chunk_artifacts"],
                    }
                cache_ok = (
                    index_times["return_a"]["hits"] == 1 and index_times["warm"]["computed"] == 0
                )
                no_branch_leak = not engine.navigation.search("alternate", source="api")["items"]
                target.write_text(original + "\n# preserve idempotency\n")
                engine.index()
                record = engine.knowledge.template("practice", "api", "main.py")
                record.update(
                    id="retry-rule",
                    title="Retry rule",
                    statement="Use idempotency keys.",
                    tasks=["review"],
                    exceptions=["Manual recovery is exempt."],
                )
                engine.knowledge.propose(record)
                engine.knowledge.decide("retry-rule", 1, "approve")

                def search(query, mode="lexical", source=None, budget=3000):
                    return engine.navigation.search(
                        query, mode=mode, source=source, token_budget=budget
                    )

                def file_hit(results, source, path):
                    return any(
                        i.get("source") == source and i.get("path") == path
                        for r in results
                        for i in r["items"]
                    )

                def manual_change():
                    return [
                        engine.navigation.read("api", "main.py", token_budget=2000),
                        engine.knowledge.lookup(
                            "practice", "api", "main.py", task="review", token_budget=2000
                        ),
                        engine.navigation.related(
                            "api", "main.py", mode="graph", token_budget=2000
                        ),
                    ]

                def change_correct(results):
                    return (
                        file_hit(results, "api", "main.py")
                        and file_hit(results, "worker", "run.py")
                        and any(
                            i.get("id") == "retry-rule"
                            and i.get("exceptions") == record["exceptions"]
                            for r in results
                            for i in r["items"]
                        )
                    )

                # Labels are fixed before running; held-out composition differs from development cases.
                cases = [
                    (
                        "identifier",
                        "development",
                        lambda: [search("enqueue", "literal")],
                        lambda: [search("enqueue")],
                        lambda r: file_hit(r, "api", "main.py"),
                        3000,
                    ),
                    (
                        "cross_repo_contract",
                        "development",
                        lambda: [search("demo.requested", "literal")],
                        lambda: [search("demo.requested")],
                        lambda r: file_hit(r, "api", "main.py") and file_hit(r, "worker", "run.py"),
                        3000,
                    ),
                    (
                        "missing_answer",
                        "held_out",
                        lambda: [search("missing_identifier_xyz", "literal")],
                        lambda: [search("missing_identifier_xyz")],
                        lambda r: not r[0]["items"],
                        3000,
                    ),
                    (
                        "outside_scope",
                        "held_out",
                        lambda: [search("private_marker", "literal")],
                        lambda: [search("private_marker")],
                        lambda r: not r[0]["items"],
                        3000,
                    ),
                    (
                        "kotlin_ambiguity",
                        "held_out",
                        lambda: [search("process", "literal")],
                        lambda: [search("process", "symbols")],
                        lambda r: file_hit(r, "api", "Main.kt") and file_hit(r, "api", "Other.kt"),
                        3000,
                    ),
                    (
                        "change_with_exception",
                        "held_out",
                        manual_change,
                        lambda: [brief(engine, "api", token_budget=6000)],
                        change_correct,
                        6000,
                    ),
                ]
                rows = []
                for name, split, baseline, candidate, check, budget in cases:
                    variants = {}
                    for variant, call in [("baseline", baseline), ("candidate", candidate)]:
                        durations, measurements, successes, citation_checks = [], [], [], []
                        for _ in range(3):
                            start = time.perf_counter()
                            results = call()
                            durations.append((time.perf_counter() - start) * 1000)
                            measurements.append(sum(size(r) for r in results))
                            successes.append(check(results) and measurements[-1] <= budget)
                            current, _ = engine.scan()
                            citations = [
                                i
                                for r in results
                                for i in r["items"]
                                if "path" in i and "hash" in i
                            ]
                            citation_checks.append(
                                all(
                                    current.get((i["source"], i["path"]), {}).get("hash")
                                    == i["hash"]
                                    for i in citations
                                )
                            )
                        variants[variant] = {
                            "passed": all(successes) and all(citation_checks),
                            "iterations": 3,
                            "calls": len(results),
                            "response_bytes": measurements[-1],
                            "citation_hashes_current": all(citation_checks),
                            "p50_ms": round(sorted(durations)[1], 3),
                            "p95_ms": round(
                                sorted(durations)[math.ceil(0.95 * len(durations)) - 1], 3
                            ),
                        }
                    rows.append(
                        {"case": name, "split": split, "sequence_byte_budget": budget, **variants}
                    )
                target.write_text("def replaced(): return 0\n")
                stale_code = not search("enqueue")["items"]
                stale_rule = not engine.knowledge.lookup(
                    "practice", "api", "main.py", task="review"
                )["items"]
                engine.index()
                recovered = bool(search("replaced")["items"])
                deleted = root / "worker/run.py"
                deleted.unlink()
                engine.index()
                deletion_ok = not search("demo.requested", source="worker")["items"]
                checks = {
                    "branch_reuse": cache_ok,
                    "branch_isolation": no_branch_leak,
                    "stale_code_withheld": stale_code,
                    "stale_rule_withheld": stale_rule,
                    "refresh_recovered": recovered,
                    "deleted_evidence_withheld": deletion_ok,
                }
                peak = tracemalloc.get_traced_memory()[1]
                return {
                    "schema_version": 1,
                    "suite": "p1-evidence-1",
                    "corpus": "generated-v1",
                    "report_kind": "synthetic_evidence_evaluation",
                    "cases": rows,
                    "checks": checks,
                    "indexing": index_times,
                    "python_traced_peak_bytes": peak,
                    "store_bytes": sum(
                        p.stat().st_size for p in engine.store.parent.iterdir() if p.is_file()
                    ),
                    "actual_model_tokens": None,
                    "model_task_completion": "not measured",
                    "passed": all(checks.values()) and all(r["candidate"]["passed"] for r in rows),
                    "limits": "Synthetic evidence tasks only; no model inference, billing or production scale claims. Three-run p95 is the maximum sample. Traced memory excludes native allocations.",
                }
            finally:
                engine.close()
                if not tracing:
                    tracemalloc.stop()
