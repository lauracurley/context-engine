"""One read-only improvement cycle from a vetted report; no uploads or automatic changes."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from context_engine.usage import decode, validate


def analyze(report):
    report = validate(report)
    candidates = []
    for operation, row in report["operations"].items():
        if row["calls"] < 20:
            continue
        for outcome, hypothesis, check in [
            (
                "stale",
                "Freshness recovery may interrupt retrieval",
                "Reproduce saved-file drift and compare refresh/retry calls on synthetic fixtures",
            ),
            (
                "internal_error",
                "An operation needs reliability investigation",
                "Reproduce controlled failures without importing diagnostic text",
            ),
            (
                "empty",
                "Discovery outcomes need further classification",
                "Compare absent identifiers and expected matches in a frozen synthetic suite",
            ),
        ]:
            count = row["outcomes"][outcome]
            if count / row["calls"] >= 0.1:
                candidates.append(
                    {
                        "operation": operation,
                        "signal": outcome,
                        "count": count,
                        "calls": row["calls"],
                        "hypothesis": hypothesis,
                        "next_check": check,
                    }
                )
    candidates.sort(key=lambda c: (-c["count"] / c["calls"], c["operation"], c["signal"]))
    return {
        "schema_version": 1,
        "mode": "read_only",
        "decision": "investigate" if candidates else "insufficient_signal",
        "candidates": candidates[:3],
        "limits": [
            "Voluntary reports are not a randomized experiment",
            "Counts do not establish answer quality or root cause",
            "No client content or report attachment is copied into this packet",
        ],
        "next": "Choose one hypothesis, freeze baseline and guardrails, reproduce synthetically, then review a bounded patch",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    packet = analyze(decode(Path(args.report).read_text()))
    with Path(args.output).open("x") as handle:
        json.dump(packet, handle, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
