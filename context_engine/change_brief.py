"""Read-only local diff context, grounded in the current scoped index."""

import re
import subprocess
import tempfile
from pathlib import Path

from .budget import pack
from .knowledge import KINDS


def git_output(root, arguments, ceiling=2 * 1024 * 1024):
    # Avoid unbounded subprocess capture for large patches. Git never executes external diffs.
    with tempfile.TemporaryFile() as output:
        try:
            result = subprocess.run(
                ["git", "--literal-pathspecs", "-C", str(root), *arguments],
                stdout=output,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise ValueError("Local diff timed out; narrow the selected source") from None
        if result.returncode:
            raise ValueError("Local Git comparison failed; select a checkout and valid commit")
        if output.tell() > ceiling:
            raise ValueError("Local diff exceeds the preview limit; narrow the change")
        output.seek(0)
        return output.read()


def brief(engine, source, base="HEAD", token_budget=6000):
    if source not in engine.sources:
        raise ValueError("Unknown source")
    if (
        not isinstance(base, str)
        or not re.fullmatch(r"[A-Za-z0-9_./~^+-]{1,120}", base)
        or base.startswith("-")
    ):
        raise ValueError("Select a commit or branch ref")
    if type(token_budget) is not int or not 1024 <= token_budget <= 32000:
        raise ValueError("Byte budget must be 1024..32000")
    scan = engine.scan()
    status = engine._status(scan)
    current = scan[0]
    if status["state"] != "ready":
        return pack(
            engine,
            [],
            token_budget,
            state=status["state"],
            gaps=["Refresh the index before preparing a change brief"],
        )
    root = Path(engine.sources[source]["root"])
    revision = git_output(root, ["rev-parse", "--verify", base + "^{commit}"]).decode().strip()
    flags = ["diff", "--no-ext-diff", "--no-textconv", "--relative", "--no-renames"]
    paths = (
        git_output(root, [*flags, "--name-only", "-z", revision, "--", "."]).decode().split("\0")
    )
    paths = [p for p in paths if p]
    items, gaps, seen = [], [], set()
    selected = [p for p in paths if (source, p) in current][:12]
    missing = len(paths) - len(selected)
    upstream_omitted = 0

    def add(category, item, reason):
        nonlocal upstream_omitted
        key = (category, repr(item))
        if key not in seen:
            seen.add(key)
            items.append({"category": category, "reason": reason, **item})

    for path in selected:
        changed_symbols = set()
        patch = git_output(root, [*flags, "--unified=0", revision, "--", path]).decode(
            "utf-8", errors="replace"
        )
        hunks = re.findall(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", patch, re.M)
        upstream_omitted += max(0, len(hunks) - 3)
        for start, _count in hunks[:3] or [("1", "1")]:
            line = max(1, int(start))
            result = engine.navigation._read(
                source,
                path,
                max(1, line - 2),
                line + 5,
                expected_hash=current[(source, path)]["hash"],
                token_budget=8000,
                snapshot=(status, current),
            )
            upstream_omitted += result["budget"]["omitted_items"]
            gaps.extend(result["gaps"])
            for item in result["items"]:
                symbols = [
                    row[0]
                    for row in engine.db.execute(
                        "SELECT DISTINCT symbol FROM evidence WHERE source=? AND path=? AND hash=? "
                        "AND symbol IS NOT NULL AND line_start<=? AND line_end>=? ORDER BY symbol LIMIT 8",
                        (
                            source,
                            path,
                            current[(source, path)]["hash"],
                            line + max(1, int(_count or 1)) - 1,
                            line,
                        ),
                    )
                ]
                item["enclosing_symbols"] = symbols
                changed_symbols.update(symbols)
                add(
                    "changed_code",
                    item,
                    "Current source near a changed hunk; inspect full diff separately",
                )
        for symbol in sorted(changed_symbols)[:8]:
            name = symbol.rsplit(".", 1)[-1]
            tests = engine.db.execute(
                "SELECT source,path,hash,revision,line_start,text FROM evidence "
                "WHERE source=? AND lower(path) LIKE '%test%' AND instr(text,?)>0 "
                "ORDER BY path,line_start LIMIT 3",
                (source, name),
            ).fetchall()
            upstream_omitted += max(0, len(tests) - 2)
            for row in tests[:2]:
                lines = row["text"].splitlines()
                match = next((n for n, text in enumerate(lines) if name in text), 0)
                start = max(0, match - 2)
                snippet = lines[start : start + 8]
                add(
                    "test_candidate",
                    {
                        "source": row["source"],
                        "path": row["path"],
                        "hash": row["hash"],
                        "revision": row["revision"],
                        "lines": [
                            row["line_start"] + start,
                            row["line_start"] + start + len(snippet) - 1,
                        ],
                        "text": "\n".join(snippet),
                        "classification": "inferred",
                    },
                    "Test-path snippet mentions an enclosing changed symbol; coverage is not verified",
                )
        for kind in KINDS:
            result = engine.knowledge._lookup(
                kind,
                source,
                path=path,
                task="review",
                token_budget=8000,
                snapshot=(status, current),
            )
            upstream_omitted += result["budget"]["omitted_items"]
            gaps.extend(result["gaps"])
            for item in result["items"]:
                add(
                    "guidance",
                    item,
                    "Approved guidance applicable to a changed path and review task",
                )
        result = engine.architecture._neighbors(
            source, path, limit=3, token_budget=6000, status=status
        )
        upstream_omitted += result["budget"]["omitted_items"] + result.get("limit_omitted", 0)
        gaps.extend(result["gaps"])
        for item in result["items"]:
            add(
                "related_evidence",
                item,
                "One-hop indexed relationship; classification is preserved",
            )
    final_status = engine.status()
    if final_status["state"] != "ready" or final_status["index"].get("generation") != status[
        "index"
    ].get("generation"):
        return pack(
            engine,
            [],
            token_budget,
            state="stale",
            gaps=["Source changed while assembling the brief; retry after refresh"],
        )
    return pack(
        engine,
        items,
        token_budget,
        generation=status["index"].get("generation"),
        gaps=list(dict.fromkeys(gaps)),
        base_revision=revision,
        omitted_changed_paths=missing,
        upstream_omissions=upstream_omitted,
        coverage="Tracked working-tree changes against base; untracked files excluded. At most 12 indexed paths, 3 hunks/path, up to 8 enclosing chunk symbols/hunk, 2 test snippets/symbol and 3 graph neighbors/path. Deleted/excluded paths have no current evidence. This is context, not a review verdict.",
    )
