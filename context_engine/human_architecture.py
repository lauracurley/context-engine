"""A repository reading guide for people, separate from agent graph retrieval."""

import posixpath
import re
from collections import defaultdict
from pathlib import PurePosixPath

GUIDES = (
    "docs/architecture-overview.md",
    "architecture-overview.md",
    "docs/architecture.md",
    "architecture.md",
    "readme.md",
)


def overview(engine, source):
    if source not in engine.sources:
        raise ValueError("Select a known repository")
    status = engine.status()
    result = {
        "source": source,
        "state": status["state"],
        "generation": status["index"].get("generation"),
        "markdown": "",
        "items": [],
        "links": {},
        "diagram": [],
        "gaps": [],
        "reader": True,
    }
    if status["state"] != "ready":
        result["gaps"] = ["Refresh code to read an overview of the current repository."]
        return result
    current, _ = engine.scan()
    files = {path: row for (sid, path), row in current.items() if sid == source}
    indexed = {r["path"]: r for r in engine.architecture.rows() if r["source"] == source}
    files = {p: r for p, r in files.items() if p in indexed and r["hash"] == indexed[p]["hash"]}

    def link(path, label=None):
        if path not in files:
            return label or path
        key = "source-" + str(len(result["items"]))
        result["links"][key] = len(result["items"])
        result["items"].append(
            dict(engine.architecture.citation(indexed[path]), title=label or path)
        )
        return f"[{label or path}]({key})"

    by_name = {p.lower(): p for p in files}
    guide = next((by_name[p] for p in GUIDES if p in by_name), None)
    lines = []
    if guide:
        result["basis"] = "Repository documentation"
        result["document"] = guide
        text = files[guide]["text"]
        if len(text) > 24000:
            text = text[:24000].rsplit("\n", 1)[0]
            result["gaps"].append("The guide is shortened here; open the source to read the rest.")

        def local_link(match):
            label, target = match.groups()
            target = target.split("#", 1)[0]
            if not target or re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target):
                return label
            path = posixpath.normpath(posixpath.join(posixpath.dirname(guide), target))
            return link(path, label)

        text = re.sub(r"!?\[([^\]\n]+)\]\(([^)\s]+)\)", local_link, text)
        lines = [text, "", "## About this overview", "", "From " + link(guide) + "."]
    else:
        result["basis"] = "Source reading guide"
        lines = [
            "# " + source + " architecture",
            "",
            "This repository has no indexed architecture guide or root README. "
            "The reading path below uses source descriptions and file organization. "
            "It cannot explain undocumented design decisions.",
            "",
            "## Main parts of the repository",
            "",
        ]
        groups = defaultdict(list)
        for path, row in indexed.items():
            if path not in files:
                continue
            parts = PurePosixPath(path).parts
            if any(p.lower() in {"tests", "test", "fixtures", "examples", "docs"} for p in parts):
                continue
            facts = row["facts"]["facts"]
            description = next((f["name"] for f in facts if f["kind"] == "description"), "")
            if description:
                groups[parts[0] if len(parts) > 1 else "Repository root"].append(
                    (path, description)
                )
        for group, members in sorted(groups.items())[:12]:
            lines.extend(["### " + group, ""])
            for path, description in members[:6]:
                lines.append("- " + link(path) + " — " + description)
            if len(members) > 6:
                lines.append(f"{len(members) - 6} additional described files in this component.")
            lines.append("")
        if not groups:
            lines.append(
                "Source files do not contain module descriptions to explain their responsibilities."
            )
        lines.extend(["", "## Where to start reading", ""])
        entries = [
            p
            for p, r in indexed.items()
            if p in files
            and not any(x in {"tests", "test", "fixtures"} for x in PurePosixPath(p).parts)
            and any(f["kind"] == "entrypoint" for f in r["facts"]["facts"])
        ]
        if entries:
            lines.append(
                "These files contain entry-point signals. Start here to trace how work enters the code; naming alone does not establish runtime order."
            )
            lines.extend("- " + link(p) for p in entries[:8])
        else:
            lines.append(
                "No entry point was identified. Start with the package configuration and its launch commands."
            )
        lines.extend(
            [
                "",
                "## What still needs explaining",
                "",
                "Repository purpose, an end-to-end example, and the reasons behind component boundaries "
                "need an authored explanation. A docs/ARCHITECTURE-OVERVIEW.md guide will appear here automatically.",
            ]
        )
    approved = [
        row
        for row in engine.knowledge.rows()
        if row["source"] == source
        and row["kind"] == "architecture"
        and row["status"] == "approved"
        and engine.knowledge.fresh(row, current)
    ]
    if approved:
        lines.extend(["", "## Reviewed design guidance", ""])
        for row in approved:
            lines.extend(["### " + row["title"], "", row["statement"], "", row["rationale"], ""])
            lines.extend("- " + link(c["path"]) for c in row["citations"] if c["source"] == source)
    latest = engine.status()
    if latest["state"] != "ready" or latest["index"].get("generation") != result["generation"]:
        result.update(
            state="stale",
            items=[],
            links={},
            gaps=["Code changed while loading. Refresh and reopen Architecture."],
        )
        return result
    result["markdown"] = "\n".join(lines)
    return result
