"""Frozen question comparison against deterministic literal full-file search."""
import argparse
import json
from pathlib import Path
import re
import tempfile
from context_engine.core import Engine, digest

ROOT = Path(__file__).resolve().parent


def literal_search(files, sources, query, token_budget):
    """Case-insensitive OR of literal query words; source/path order, no index/ranker."""
    words = set(re.findall(r"\w+", query.lower()))
    items, used = [], 0
    for (source, path), file in sorted(files.items()):
        text = file["text"]
        if not any(word in (path + " " + text).lower() for word in words):
            continue
        item = {"source": source, "path": path, "hash": file["hash"], "revision": file["revision"],
                "line_start": 1, "line_end": len(text.splitlines()), "symbol": None,
                "method": "literal-full-file", "text": text,
                "absolute_path": str(Path(sources[source]["root"]) / path),
                "source_type": sources[source].get("type", "files"), "rank": 0,
                "reason": "Literal query-word match; source/path order, no relevance ranking",
                "evidence_id": digest((source + path + file["hash"]).encode())}
        cost = len(json.dumps(item, ensure_ascii=False).encode("utf-8"))
        if used + cost > token_budget:
            continue
        items.append(item)
        used += cost
        if len(items) == 10:
            break
    return {"items": items, "budget": {"used_estimated_tokens": used}}


def score(expected, retrieved):
    expected = set(expected)
    retrieved = list(dict.fromkeys(retrieved))
    hits = expected & set(retrieved)
    return {"precision": len(hits) / len(retrieved) if retrieved else 0.0,
            "recall": len(hits) / len(expected) if expected else None,
            "reciprocal_rank": next((1 / (n + 1) for n, path in enumerate(retrieved) if path in expected), 0.0),
            "exact_files": set(retrieved) == expected}


def evaluate(questions, token_budget=8000):
    results = []
    with tempfile.TemporaryDirectory() as state:
        for case in questions["cases"]:
            engine = Engine(ROOT / "examples" / (case["environment"] + ".json"), state)
            try:
                engine.index()
                files, _ = engine.scan()
                outputs = {"context_engine": engine.search(case["query"], token_budget=token_budget),
                           "literal_file_search": literal_search(files, engine.sources, case["query"], token_budget)}
                row = dict(case, methods={})
                for method, bundle in outputs.items():
                    paths = list(dict.fromkeys(i["source"] + "/" + i["path"] for i in bundle["items"]))
                    row["methods"][method] = dict(score(case["expected"], paths), retrieved=paths,
                        used_estimated_tokens=bundle["budget"]["used_estimated_tokens"])
                results.append(row)
            finally:
                engine.close()
    summary = {}
    for method in ("context_engine", "literal_file_search"):
        positive = [r["methods"][method] for r in results if r["expected"]]
        negative = [r["methods"][method] for r in results if not r["expected"]]
        summary[method] = {"positive_cases": len(positive), "negative_cases": len(negative),
            "macro_precision_positive": sum(r["precision"] for r in positive) / len(positive) if positive else None,
            "macro_recall_positive": sum(r["recall"] for r in positive) / len(positive) if positive else None,
            "mrr_positive": sum(r["reciprocal_rank"] for r in positive) / len(positive) if positive else None,
            "negative_accuracy": sum(r["exact_files"] for r in negative) / len(negative) if negative else None,
            "exact_file_sets": sum(r["methods"][method]["exact_files"] for r in results), "total": len(results)}
    return {"question_version": questions["version"], "token_budget": token_budget,
            "methodology": "Same eligible files, 10-item cap, and serialized evidence UTF-8 byte budget. Engine uses BM25/excerpts; baseline uses literal query-word OR matching and whole files in source/path order. Different excerpts and metadata may have different costs. No semantic or task-completion score. New questions were frozen before first run; author saw fixtures; no tuning on this set.",
            "summary": summary, "cases": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=ROOT / "evaluation/questions.json")
    parser.add_argument("--token-budget", type=int, default=8000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.token_budget <= 32000:
        parser.error("token budget must be 1..32000")
    report = evaluate(json.loads(args.questions.read_text()), args.token_budget)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
