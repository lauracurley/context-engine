#!/usr/bin/env python3
"""Run the same offline quality gates locally and in CI. Installs nothing."""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    print("Running: " + " ".join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix", action="store_true", help="Apply safe lint fixes and formatting first"
    )
    args = parser.parse_args()
    npm = shutil.which("npm")
    if not npm:
        parser.error("Install Node.js 24 LTS (or supported 22.13+) and npm first")
    if args.fix:
        # Format first to remove dense multi-statement lines before lint fixes.
        run(sys.executable, "-m", "ruff", "format", ".")
        run(sys.executable, "-m", "ruff", "check", ".", "--fix")
        run(npm, "run", "lint:fix", "--prefix", "vscode-extension")
        run(npm, "run", "format", "--prefix", "vscode-extension")
    run(sys.executable, "-m", "ruff", "check", ".")
    run(sys.executable, "-m", "ruff", "format", "--check", ".")
    run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q")
    run(sys.executable, "evaluate.py")
    run(sys.executable, "evaluate_efficiency.py")
    run(sys.executable, "evaluate_p1.py")
    with tempfile.TemporaryDirectory(prefix="context-quality-") as directory:
        run(sys.executable, "evaluate_context.py", "--output", Path(directory) / "context.json")
    # npm's pretest builds a fresh VSIX/backend before testing the extension.
    run(npm, "run", "verify", "--prefix", "vscode-extension")
    print("All quality gates passed.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
