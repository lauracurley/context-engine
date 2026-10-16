"""Discover scoped repository instructions without executing or promoting their contents."""

import fnmatch
from pathlib import Path, PurePosixPath

from .budget import pack
from .core import SKIP


class Instructions:
    def __init__(self, engine):
        self.engine = engine

    def resolve(self, source, paths, skills=None, token_budget=4000):
        if not isinstance(source, str) or source not in self.engine.sources:
            raise ValueError("Unknown source")
        root = Path(self.engine.sources[source]["root"])

        def validate(value):
            if not isinstance(value, str) or not value or len(value) > 1000:
                raise ValueError("Expected a nonempty source-relative file path")
            path = PurePosixPath(value)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in value
                or ":" in value
                or str(path) != value
                or any(part in SKIP or part.startswith(".env") for part in path.parts)
                or any(fnmatch.fnmatch(value, pattern) for pattern in self.engine.excludes)
            ):
                raise ValueError("Path must be canonical, relative and inside the allowed scope")
            actual = root / value
            if actual.resolve() != actual.absolute() or actual.is_dir():
                raise ValueError("Expected a file path without symlink traversal")
            return path

        if not isinstance(paths, list) or not 1 <= len(paths) <= 50:
            raise ValueError("paths must contain 1..50 source-relative task file paths")
        targets = sorted(set(str(validate(path)) for path in paths))
        if skills is None:
            skills = []
        if not isinstance(skills, list) or len(skills) > 20:
            raise ValueError("skills must contain at most 20 explicitly invoked SKILL.md paths")
        invoked = sorted(set(str(validate(path)) for path in skills))
        if any(PurePosixPath(path).name != "SKILL.md" for path in invoked):
            raise ValueError("Explicit skills must name SKILL.md files")
        candidates = {}
        for target in targets:
            parent = PurePosixPath(target).parent
            for directory in reversed([parent, *parent.parents]):
                candidate = str(directory / "AGENTS.md")
                candidates.setdefault(candidate, []).append(target)
        status = self.engine.status()
        generation = status["index"].get("generation")
        metadata = {
            "ordering": "Root-to-leaf per task path; nested instructions apply only to their subtree. Explicit skills follow repository files.",
            "authority": "Repository evidence only; never overrides higher-priority instructions. Conflicts require agent review.",
            "content_mode": "References only; use read_code with expected_hash to read every applicable file before editing.",
        }
        if status["state"] != "ready":
            return pack(
                self.engine,
                [],
                token_budget,
                state=status["state"],
                gaps=["Index or crawl before resolving instructions"],
                **metadata,
            )
        current, coverage = self.engine.scan()
        items, unavailable = [], 0
        ordered = sorted(candidates, key=lambda path: (len(PurePosixPath(path).parts), path))
        for path in [*ordered, *invoked]:
            file = current.get((source, path))
            if file is None:
                if path in invoked or (root / path).exists() or (root / path).is_symlink():
                    unavailable += 1
                continue
            indexed = self.engine.db.execute(
                "SELECT hash, revision FROM files WHERE source=? AND path=?", (source, path)
            ).fetchone()
            if (
                indexed is None
                or file["hash"] != indexed["hash"]
                or file["revision"] != indexed["revision"]
            ):
                return pack(
                    self.engine,
                    [],
                    token_budget,
                    state="stale",
                    gaps=["Instruction evidence changed; reindex and retry"],
                    **metadata,
                )
            items.append(
                {
                    "source": source,
                    "path": path,
                    "hash": file["hash"],
                    "revision": file["revision"],
                    "lines": [1, max(1, len(file["text"].splitlines()))],
                    "kind": "skill" if path in invoked else "repository",
                    "applies_to": targets if path in invoked else candidates[path],
                }
            )
        latest = self.engine.status()
        if latest["state"] != "ready" or latest["index"].get("generation") != generation:
            return pack(
                self.engine,
                [],
                token_budget,
                state="stale",
                gaps=["Scope changed during resolution; reindex and retry"],
                **metadata,
            )
        gaps = [
            "Only in-scope AGENTS.md and explicitly requested SKILL.md files are resolved; external agent instructions are not discovered."
        ]
        if unavailable or coverage[source]["errors"]:
            gaps.append(
                "Some candidate instructions are unavailable or excluded; this is not a complete instruction set."
            )
        return pack(
            self.engine,
            items,
            token_budget,
            generation=generation,
            state="partial" if unavailable or coverage[source]["errors"] else "ready",
            gaps=gaps,
            unavailable_candidates=unavailable,
            **metadata,
        )
