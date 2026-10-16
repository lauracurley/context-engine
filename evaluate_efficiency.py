"""Deterministic relational retrieval evaluation; no model calls or billing claims."""

import json
import shutil
import tempfile
from pathlib import Path

from context_engine.budget import size
from context_engine.core import Engine

ROOT = Path(__file__).resolve().parent


def evaluate():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        shutil.copytree(ROOT / "examples", root / "examples")
        manifest = root / "examples/acme.json"
        config = json.loads(manifest.read_text())
        noise = root / "noise"
        noise.mkdir()
        for n in range(100):
            (noise / f"noise{n}.py").write_text(
                f"def request_{n}():\n    return 'task requested priority'\n"
            )
        config["sources"].append({"id": "noise", "path": str(noise)})
        manifest.write_text(json.dumps(config))
        engine = Engine(manifest, root / "state")
        try:
            engine.index()
            nav = engine.navigation
            definitions = [
                (
                    "scoped_identifier",
                    lambda: nav.search("UNKNOWN_TEMPLATE", source="api", mode="lexical"),
                    {"api/tasks.py"},
                ),
                (
                    "cross_service_contract",
                    lambda: nav.related(
                        "api",
                        "tasks.py",
                        mode="graph",
                        relation="shared_event_literal",
                        token_budget=4000,
                    ),
                    {"worker/consumer.py"},
                ),
                (
                    "no_invented_dependency",
                    lambda: nav.related("api", "tasks.py", mode="graph", relation="imports"),
                    set(),
                ),
                (
                    "missing_identifier",
                    lambda: nav.search("NO_SUCH_IMPLEMENTATION_739", mode="lexical"),
                    set(),
                ),
            ]
            cases = []
            for name, operation, expected in definitions:
                result = operation()
                actual = {i["source"] + "/" + i["path"] for i in result["items"]}
                citations_valid = True
                for item in result["items"]:
                    for citation in item.get("citations", [item]):
                        file = Path(engine.sources[citation["source"]]["root"]) / citation["path"]
                        lines = file.read_text().splitlines()
                        citations_valid &= (
                            1 <= citation["lines"][0] <= citation["lines"][1] <= len(lines)
                        )
                cases.append(
                    {
                        "task": name,
                        "expected": sorted(expected),
                        "retrieved": sorted(actual),
                        "bytes": size(result),
                        "citations_valid": citations_valid,
                        "passed": expected == actual
                        and citations_valid
                        and size(result) <= result["budget"]["limit"],
                    }
                )
            return {
                "fixture": "acme plus 100 distractor files",
                "measurement": "JSON UTF-8 bytes; no model inference",
                "cases": cases,
                "passed": all(c["passed"] for c in cases),
            }
        finally:
            engine.close()


if __name__ == "__main__":
    result = evaluate()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
