#!/usr/bin/env python3
"""Bind an offline quality run to a source snapshot; retain private local evidence."""

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SKIP = {
    ".git",
    ".context-engine",
    ".venv",
    "venv",
    "__pycache__",
    ".ruff_cache",
    "node_modules",
    "dist",
    "backend",
    "coverage",
    "htmlcov",
}


def fingerprint(root):
    """Include untracked inputs; refuse symlinks rather than follow outside the checkout."""
    result = hashlib.sha256()
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP)
        for name in sorted(dirs + names):
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError("Source snapshot contains a symlink")
        for name in sorted(names):
            path = Path(directory) / name
            if path.suffix == ".pyc":
                continue
            relative = path.relative_to(root).as_posix().encode()
            content = path.read_bytes()
            result.update(len(relative).to_bytes(8, "big") + relative)
            result.update(len(content).to_bytes(8, "big") + content)
    return result.hexdigest()


def run_checks(command, root, log, timeout):
    # A timed-out gate must not leave npm/Python children modifying the checkout.
    if os.name != "posix":
        raise OSError("Checkpoint process-tree containment currently requires POSIX")
    with subprocess.Popen(
        command, cwd=root, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
    ) as process:
        try:
            return subprocess.CompletedProcess(command, process.wait(timeout=timeout))
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            raise


def verify(root, timeout=1800):
    root = Path(root).resolve()
    before = fingerprint(root)
    # Detailed output, filenames and hashes are client-local diagnostics, NEVER a usage export.
    base = root / ".context-engine" / "ralph"
    if (root / ".context-engine").is_symlink() or base.is_symlink():
        raise ValueError("Checkpoint directory must not be a symlink")
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    base.chmod(0o700)
    folder = base / uuid4().hex
    folder.mkdir(mode=0o700)
    command = [sys.executable, str(root / "scripts/check.py")]
    result = {
        "schema_version": 1,
        "status": "running",
        "source_before": before,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "gate": "scripts/check.py",
    }
    with (folder / "checks.log").open("x") as log:
        os.chmod(log.name, 0o600)
        try:
            process = run_checks(command, root, log, timeout)
            result["exit_code"] = process.returncode
            result["status"] = "passed" if process.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            result["status"] = "timeout"
        except OSError:
            result["status"] = "unavailable"
    try:
        result["source_after"] = fingerprint(root)
        if result["source_after"] != before:
            result["status"] = "source_changed"
    except (ValueError, OSError):
        result["status"] = "source_changed"
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    with (folder / "checkpoint.json").open("x") as output:
        os.chmod(output.name, 0o600)
        json.dump(result, output, indent=2)
        output.write("\n")
    print(f"Checkpoint {result['status']}: {folder}", flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout", type=int, default=1800, help="Quality process timeout in seconds"
    )
    args = parser.parse_args()
    if not 1 <= args.timeout <= 7200:
        parser.error("timeout must be 1..7200 seconds")
    return 0 if verify(ROOT, args.timeout)["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
