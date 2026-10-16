"""Reproducible payload-size and architecture smoke evaluation; not model tokens."""

import argparse
import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from context_engine.budget import encode
from context_engine.core import Engine

ROOT = Path(__file__).resolve().parent


def evaluate():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        shutil.copytree(ROOT / "examples", root / "examples")
        engine = Engine(root / "examples/acme.json", root / "state")
        try:
            engine.index()
            cases = []
            for query in ("task.requested priority", "UNKNOWN_TEMPLATE", "COMPLETED"):
                full = engine.search(query, token_budget=32000, mode="lexical")
                compact = engine.navigation.search(
                    query, token_budget=8000, mode="lexical", max_snippet_lines=5
                )
                outline = engine.navigation.search(
                    query, token_budget=8000, mode="lexical", max_snippet_lines=0
                )

                def paths(result):
                    return sorted({i["source"] + "/" + i["path"] for i in result["items"]})

                baseline_bytes = len(encode(full).encode())
                compact_bytes = len(encode(compact).encode())
                cases.append(
                    {
                        "query": query,
                        "same_files": paths(full) == paths(compact) == paths(outline),
                        "files": paths(compact),
                        "full_payload_bytes": baseline_bytes,
                        "compact_payload_bytes": compact_bytes,
                        "outline_payload_bytes": len(encode(outline).encode()),
                        "compact_reduction_percent": round(
                            100 * (1 - compact_bytes / baseline_bytes), 1
                        ),
                    }
                )
            overview = engine.architecture.overview()
            unchanged = engine.architecture.overview(if_none_match=overview["etag"])

            # Measure a complete discovery/read sequence, including redundant setup calls.
            def trajectory(include_setup):
                responses = []
                with patch.object(engine, "scan", wraps=engine.scan) as scans:
                    if include_setup:
                        responses.extend([engine.status(), engine.architecture.overview()])
                    found = engine.navigation.search(
                        "UNKNOWN_TEMPLATE", mode="lexical", max_snippet_lines=0
                    )
                    responses.append(found)
                    for item in found["items"]:
                        responses.append(
                            engine.navigation.read(
                                item["source"],
                                item["path"],
                                item["lines"][0],
                                item["lines"][1],
                                expected_hash=item["hash"],
                            )
                        )
                    scan_count = scans.call_count
                return {
                    "payload_bytes": sum(len(encode(r).encode()) for r in responses),
                    "tool_calls": len(responses),
                    "source_scans": scan_count,
                    "evidence": [
                        i for r in responses[1 if not include_setup else 3 :] for i in r["items"]
                    ],
                }

            routed, prefixed = trajectory(False), trajectory(True)
            routed_evidence, prefixed_evidence = routed.pop("evidence"), prefixed.pop("evidence")
            same_read_evidence = bool(routed_evidence) and routed_evidence == prefixed_evidence
            report = {
                "measurement": "UTF-8 bytes of complete compact JSON payload; not actual model tokens",
                "fixture": "examples/acme.json (two tiny Python modules)",
                "cases": cases,
                "identifier_trajectory": {
                    "routed": routed,
                    "status_overview_prefix": prefixed,
                    "same_read_evidence": same_read_evidence,
                },
                "overview": {
                    "bytes": len(encode(overview).encode()),
                    "budget": 2000,
                    "shared_contract_cited": any(
                        i.get("relation") == "shared_event_literal" for i in overview["items"]
                    ),
                    "unchanged_bytes": len(encode(unchanged).encode()),
                    "unchanged_state": unchanged["state"],
                },
                "limitations": [
                    "Synthetic smoke fixture; no production quality or scale claim",
                    "Fewer bytes does not establish equivalent task success",
                    "Semantic quality remains a separate evaluation",
                ],
            }
            report["passed"] = (
                all(
                    c["same_files"] and c["compact_payload_bytes"] < c["full_payload_bytes"]
                    for c in cases
                )
                and same_read_evidence
                and routed["payload_bytes"] < prefixed["payload_bytes"]
                and report["overview"]["shared_contract_cited"]
                and report["overview"]["bytes"] <= 2000
                and report["overview"]["unchanged_state"] == "unchanged"
            )
            return report
        finally:
            engine.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args()
    report = evaluate()
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text)
    print(text, end="")
    raise SystemExit(0 if report["passed"] else 1)
