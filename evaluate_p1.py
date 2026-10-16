"""Run offline P1 evidence evaluation; optionally save the synthetic result."""

import argparse
import json
from pathlib import Path

from context_engine.evaluation_p1 import run

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = run()
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text)
    print(text)
    raise SystemExit(0 if result["passed"] else 1)
