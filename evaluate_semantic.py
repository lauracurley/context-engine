"""Real local-model smoke comparison; not a production retrieval benchmark."""

import argparse
import json
import tempfile
import time
from pathlib import Path

from context_engine.core import Engine
from context_engine.embeddings import SentenceTransformerProvider

ROOT = Path(__file__).resolve().parent
MODEL = "sentence-transformers/all-MiniLM-L6-v2"
REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-folder", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads((ROOT / "evaluation/semantic-fixture.json").read_text())
    provider = SentenceTransformerProvider(MODEL, REVISION, 384, args.cache_folder)
    with tempfile.TemporaryDirectory(prefix="context-semantic-fixture-") as temp:
        root = Path(temp)
        for path, content in fixture["files"].items():
            p = root / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        sources = [
            {"id": s, "path": s} for s in sorted({p.split("/")[0] for p in fixture["files"]})
        ]
        manifest = root / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "environment": "semantic-smoke",
                    "workspace": "reference",
                    "sources": sources,
                }
            )
        )
        engine = Engine(manifest, root / "state", provider)
        try:
            start = time.monotonic()
            indexed = engine.index()
            index_seconds = time.monotonic() - start
            if engine.status()["semantic"]["state"] != "ready":
                raise RuntimeError(json.dumps(indexed["semantic"]))
            reused = engine.index()["semantic"]
            results = []
            for case in fixture["cases"]:
                row = dict(case, methods={})
                for mode in ["lexical", "semantic", "hybrid"]:
                    start = time.monotonic()
                    bundle = engine.search(case["query"], mode=mode, token_budget=8000)
                    paths = list(
                        dict.fromkeys(i["source"] + "/" + i["path"] for i in bundle["items"])
                    )
                    row["methods"][mode] = {
                        "retrieved": paths,
                        "top1_correct": bool(paths and paths[0] == case["expected"])
                        if case["expected"]
                        else not paths,
                        "used_mode": bundle["retrieval"]["used"],
                        "seconds": time.monotonic() - start,
                        "used_estimated_tokens": bundle["budget"]["used_estimated_tokens"],
                    }
                results.append(row)
            summary = {
                mode: {
                    "positive_top1": sum(
                        r["methods"][mode]["top1_correct"] for r in results if r["expected"]
                    ),
                    "positive_total": sum(bool(r["expected"]) for r in results),
                    "negative_empty": sum(
                        r["methods"][mode]["top1_correct"] for r in results if not r["expected"]
                    ),
                    "negative_total": sum(not r["expected"] for r in results),
                }
                for mode in ["lexical", "semantic", "hybrid"]
            }
            report = {
                "model": provider.identity.to_dict(),
                "fixture": fixture["description"],
                "index_seconds": index_seconds,
                "initial_index": indexed["semantic"],
                "repeat_index": reused,
                "summary": summary,
                "cases": results,
                "limits": "Synthetic top-one smoke only. Semantic nearest-neighbor retrieval has no calibrated relevance cutoff and returns candidates even for unsupported questions. No production quality claim.",
            }
            args.output.write_text(json.dumps(report, indent=2) + "\n")
            print(
                json.dumps(
                    {"summary": summary, "repeat_index": reused, "index_seconds": index_seconds},
                    indent=2,
                )
            )
        finally:
            engine.close()


if __name__ == "__main__":
    main()
