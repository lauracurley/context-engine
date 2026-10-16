"""Small public-safe lexical baseline; not the full product benchmark."""

import json
import tempfile
from pathlib import Path

from context_engine.core import Engine

ROOT = Path(__file__).resolve().parent
CASES = [
    ("acme", "task.requested priority", {"api", "worker"}),
    ("acme", "UNKNOWN_TEMPLATE", {"api"}),
    ("acme", "COMPLETED", {"worker"}),
    ("harbor", "parcelCode", {"dispatch", "handbook"}),
    ("harbor", "delivery receipt", {"handbook"}),
]


def main():
    results = []
    with tempfile.TemporaryDirectory() as state:
        for name, query, expected in CASES:
            engine = Engine(ROOT / "examples" / (name + ".json"), state)
            try:
                engine.index()
                bundle = engine.search(query, token_budget=8000)
                actual = {item["source"] for item in bundle["items"]}
                results.append(
                    {
                        "environment": name,
                        "query": query,
                        "expected_sources": sorted(expected),
                        "retrieved_sources": sorted(actual),
                        "passed": expected <= actual,
                    }
                )
            finally:
                engine.close()
    print(
        json.dumps(
            {"cases": results, "passed": sum(r["passed"] for r in results), "total": len(results)},
            indent=2,
        )
    )
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
