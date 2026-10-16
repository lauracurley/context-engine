"""Readable knowledge sections built from scoped docs and reviewed records."""

import re
from pathlib import PurePosixPath

SECTIONS = {
    "practice": (
        "What to check before merging a change, and how to verify it.",
        ("review-practices.md", "contributing.md", "development.md"),
    ),
    "convention": (
        "Shared ways of working: naming, formatting, scope and repository habits.",
        ("team-conventions.md", "conventions.md", "style-guide.md"),
    ),
    "decision": (
        "Why choices were made, the alternatives considered, and when to revisit them.",
        ("decisions.md",),
    ),
    "procedure": (
        "How to run the project, diagnose problems and verify recovery.",
        ("operations.md", "runbook.md", "troubleshooting.md", "core-guide.md"),
    ),
}


def detail(value, level=3, ordered=False):
    """Keep structured procedures and relationships readable without repr dumps."""
    if isinstance(value, dict):
        if set(value) == {"provider", "event", "fingerprint"} and value["provider"] == "gateway":
            return [
                "Collected through the client MCP gateway. Open Review learning to inspect the local evidence dossier. Supporting observations are listed in the rationale; collection changes require re-review.",
                "",
            ]
        if set(value) == {"if", "then"}:
            return [f"- If {value['if']} → {value['then']}"]
        if set(value) == {"id", "revision"}:
            return [f"- {value['id']} (revision {value['revision']})"]
        lines = []
        for key, item in value.items():
            lines.extend(["#" * min(level, 6) + " " + key.replace("_", " ").title(), ""])
            lines.extend(detail(item, level + 1, key == "steps"))
            lines.append("")
        return lines
    if isinstance(value, list):
        lines = []
        for index, item in enumerate(value, 1):
            if isinstance(item, (dict, list)):
                lines.extend(detail(item, level))
            else:
                lines.append((f"{index}. " if ordered else "- ") + str(item))
        return lines
    return [str(value)]


def section(knowledge, kind, source):
    from .knowledge import LABELS

    engine = knowledge.engine
    if kind not in SECTIONS or source not in engine.sources:
        raise ValueError("Select a knowledge kind and known source")
    status = engine.status()
    current, _ = engine.scan()
    intro, names = SECTIONS[kind]
    lines = ["# " + LABELS[kind], "", intro, "", "Repository: " + source, ""]
    gaps = []
    if status["state"] != "ready":
        lines.extend(["Code has changed. Refresh the index to load current repository guides.", ""])
    else:
        indexed = {r["path"]: r for r in engine.architecture.rows() if r["source"] == source}
        docs = []
        for (sid, path), row in current.items():
            p = PurePosixPath(path.lower())
            if sid != source or path not in indexed or row["hash"] != indexed[path]["hash"]:
                continue
            if (p.name in names and p.parent.as_posix() in (".", "docs")) or (
                kind == "decision"
                and p.suffix == ".md"
                and p.parts[:2] in (("docs", "decisions"), ("docs", "adr"))
            ):
                docs.append((path, row))
        docs.sort(
            key=lambda pair: (
                names.index(PurePosixPath(pair[0].lower()).name)
                if PurePosixPath(pair[0].lower()).name in names
                else len(names),
                pair[0],
            )
        )
        # Prefer a dedicated section guide over a broad fallback manual.
        if kind != "decision":
            docs = docs[:1]
        if docs:
            lines.extend(
                [
                    "Repository documentation appears below. It has not been promoted to reviewed team guidance.",
                    "",
                ]
            )
        remaining = 24000
        for path, row in docs[:6]:
            if remaining <= 0:
                gaps.append("Additional guides are omitted from this view.")
                break
            text = row["text"]
            title_match = re.match(r"^#\s+([^\n]+)\n?", text)
            title = title_match[1] if title_match else path
            if title_match:
                text = text[title_match.end() :].lstrip("\n")
            if len(text) > remaining:
                text = text[:remaining].rsplit("\n", 1)[0]
                # Close an excerpt that ends inside a fenced code block.
                if len(re.findall(r"^\s*```", text, re.M)) % 2:
                    text += "\n```"
                gaps.append(f"{path} is shortened; open the repository file for the full guide.")
            remaining -= len(text)
            # Keep each document underneath its section in the table of contents.
            demoted = []
            fenced = False
            for line in text.splitlines():
                if re.match(r"^\s*```", line):
                    fenced = not fenced
                if not fenced:
                    line = re.sub(
                        r"^(#{1,6})\s+", lambda m: "#" * min(6, len(m[1]) + 1) + " ", line
                    )
                demoted.append(line)
            text = "\n".join(demoted)
            lines.extend(["## " + title, "", "From `" + path + "`.", "", text, ""])
        if len(docs) > 6:
            gaps.append(f"{len(docs) - 6} additional guides are omitted from this view.")
        if not docs:
            lines.extend(
                [
                    "No repository guide was found for this section. Add `docs/"
                    + names[0].upper().replace(".MD", ".md")
                    + "` to document it.",
                    "",
                ]
            )

    rows = sorted(
        (
            r
            for r in knowledge.rows()
            if r["status"] == "approved" and r["kind"] == kind and r["source"] == source
        ),
        key=lambda r: (r["title"].casefold(), r["id"], r["revision"]),
    )
    if not rows:
        lines.extend(
            [
                "## Reviewed guidance",
                "",
                "No guidance has been approved for this section yet. Use New knowledge draft to propose a lesson, then Review knowledge proposals to have it reviewed.",
                "",
            ]
        )
    for row in rows:
        fresh = status["state"] == "ready" and knowledge.fresh(row, current)
        lines.extend(
            [
                "## " + row["title"],
                "",
                "Reviewed guidance"
                if fresh
                else "STALE — evidence changed; withheld from agents until re-reviewed.",
                "",
                row["statement"],
                "",
                "### When this applies",
                "",
                "Scope: " + source + "/" + row["prefix"],
                "",
            ]
        )
        for key in ("languages", "tasks", "exceptions"):
            if row.get(key):
                lines.extend(detail({key: row[key]}))
        lines.extend(["### Why", "", row["rationale"], ""])
        if row.get("details"):
            lines.extend(detail(row["details"]))
        lines.extend(
            ["### Sources and review", "", f"Record: {row['id']} · Revision {row['revision']}", ""]
        )
        lines.extend(
            "- " + c["source"] + "/" + c["path"] + " · Evidence hash: `" + c["hash"] + "`"
            for c in row["citations"]
        )
        lines.append("")
        for key in ("supersedes", "conflicts", "origin"):
            if row.get(key):
                lines.extend(detail({key: row[key]}))
    latest = engine.status()
    if latest["state"] != status["state"] or latest["index"].get("generation") != status[
        "index"
    ].get("generation"):
        return {
            "markdown": "# "
            + LABELS[kind]
            + "\n\nCode changed while loading. Refresh and reopen the wiki.",
            "state": "stale",
            "diagram": [],
            "gaps": ["Code changed while loading."],
        }
    if gaps:
        lines.extend(["## Reading notes", "", *["- " + gap for gap in gaps]])
    return {"markdown": "\n".join(lines), "state": status["state"], "diagram": [], "gaps": gaps}
