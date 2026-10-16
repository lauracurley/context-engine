"""Small discovery responses, explicit expansion, and bounded pattern search."""

import fnmatch
import json
import subprocess
import sys

from .architecture import language
from .budget import encode, pack
from .core import content_kind, digest, terms

# Run Python's potentially backtracking regex engine in a killable child process.
REGEX_WORKER = """
import json,re,sys
data=json.load(sys.stdin)
try:
    regex=re.compile(data['query'], 0 if data['case_sensitive'] else re.IGNORECASE)
    hits=[]
    for i,text in enumerate(data['texts']):
        match=regex.search(text)
        if match:
            hits.append([i, text.count('\\n',0,match.start())+1])
        if len(hits)>=250: break
    print(json.dumps({'hits':hits}))
except (re.error,OverflowError,RecursionError):
    print(json.dumps({'error':'Invalid regular expression'}))
"""


class Navigation:
    def __init__(self, engine):
        self.engine = engine

    def scope(self, source, path_glob, content):
        if source is not None and source not in self.engine.sources:
            raise ValueError("Unknown source")
        if path_glob is not None and (not isinstance(path_glob, str) or len(path_glob) > 4000):
            raise ValueError("Invalid path_glob")
        if content not in ("all", "code", "docs", "config"):
            raise ValueError("content must be all, code, docs or config")

    @staticmethod
    def allowed(source, path, wanted_source, path_glob, content):
        return (
            (wanted_source is None or source == wanted_source)
            and (path_glob is None or fnmatch.fnmatchcase(path, path_glob))
            and (content == "all" or content_kind(path) == content)
        )

    def search(
        self,
        query,
        mode="auto",
        source=None,
        path_glob=None,
        content="all",
        limit=10,
        token_budget=2000,
        max_snippet_lines=5,
        case_sensitive=False,
        exclude_evidence_ids=None,
    ):
        if exclude_evidence_ids is None:
            exclude_evidence_ids = []
        if (
            not isinstance(exclude_evidence_ids, list)
            or len(exclude_evidence_ids) > 5000
            or any(not isinstance(i, str) or len(i) > 128 for i in exclude_evidence_ids)
        ):
            raise ValueError("exclude_evidence_ids must contain at most 5000 evidence IDs")
        excluded = set(exclude_evidence_ids)
        if not isinstance(query, str) or len(query) > 4000:
            raise ValueError("query must be a string of at most 4000 characters")
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("limit must be 1..50")
        if type(max_snippet_lines) is not int or not 0 <= max_snippet_lines <= 80:
            raise ValueError("max_snippet_lines must be 0..80")
        if type(case_sensitive) is not bool:
            raise ValueError("case_sensitive must be a boolean")
        if mode not in (
            "auto",
            "lexical",
            "semantic",
            "hybrid",
            "literal",
            "regex",
            "symbols",
            "files",
        ):
            raise ValueError("Unknown search mode")
        self.scope(source, path_glob, content)
        status = self.engine.status()
        generation = status["index"].get("generation")
        if status["state"] != "ready":
            return pack(
                self.engine,
                [],
                token_budget,
                state=status["state"],
                generation=generation,
                gaps=["Run index or crawl before retrieval"],
            )
        items, gaps = [], []
        used_mode = mode
        if mode in ("auto", "lexical", "semantic", "hybrid"):
            found = self.engine._search_candidates(query, mode, status, source, path_glob, content)
            used_mode = found["retrieval"]["used"]
            gaps.extend(found["gaps"])
            gaps.append(
                "Retrieved candidates do not establish relationships or exhaustive coverage"
            )
            spans = []
            for row in found["rows"]:
                if any(
                    s == row["source"]
                    and p == row["path"]
                    and a <= row["line_end"]
                    and b >= row["line_start"]
                    for s, p, a, b in spans
                ):
                    continue
                spans.append((row["source"], row["path"], row["line_start"], row["line_end"]))
                item = self.compact(row)
                if max_snippet_lines:
                    lines = row["text"].splitlines()
                    tokens = set(terms(query).split())
                    best = (
                        max(
                            range(len(lines)),
                            key=lambda n: len(tokens & set(terms(lines[n]).split())),
                        )
                        if lines
                        else 0
                    )
                    start = max(0, best - (1 if max_snippet_lines > 1 else 0))
                    snippet = lines[start : start + max_snippet_lines]
                    item.update(snippet="\n".join(snippet), snippet_line=row["line_start"] + start)
                items.append(item)
        elif mode == "symbols":
            from .structure import identity

            if status["index"].get("structure", {}).get("extractor") != identity():
                return pack(
                    self.engine,
                    [],
                    token_budget,
                    state="stale",
                    gaps=["Index with the current parsers before symbol discovery"],
                )
            rows = self.engine.db.execute(
                "SELECT * FROM structure_files WHERE (? IS NULL OR source=?) ORDER BY source,path",
                (source, source),
            )
            for row in rows:
                if not self.allowed(row["source"], row["path"], source, path_glob, content):
                    continue
                data = json.loads(row["data"])
                if data["gaps"] or data["omitted"]:
                    gaps.append(
                        "Some scoped files have parser gaps or omitted facts; use literal search when needed"
                    )
                for fact in data["facts"]:
                    name = fact.get("qualified_name", fact["name"])
                    if fact["kind"] != "definition" or (
                        (query if case_sensitive else query.lower())
                        not in (name if case_sensitive else name.lower())
                    ):
                        continue
                    items.append(
                        {
                            "source": row["source"],
                            "path": row["path"],
                            "lines": fact["lines"],
                            "hash": row["hash"],
                            "revision": row["revision"],
                            "symbol": name,
                            "classification": fact["classification"],
                        }
                    )
                    if len(items) == 250:
                        break
                if len(items) == 250:
                    break
            gaps = list(dict.fromkeys(gaps))
        elif mode == "files":
            for row in self.engine.db.execute("SELECT * FROM files ORDER BY source,path"):
                name = row["path"] if case_sensitive else row["path"].lower()
                if (
                    self.allowed(row["source"], row["path"], source, path_glob, content)
                    and (query if case_sensitive else query.lower()) in name
                ):
                    items.append(dict(row, language=language(row["path"])))
        else:
            current, _ = self.engine.scan()
            documents, total_bytes = [], 0
            for (sid, path), file in sorted(current.items()):
                if not self.allowed(sid, path, source, path_glob, content):
                    continue
                total_bytes += len(file["text"].encode("utf-8"))
                if total_bytes > 16_000_000 or len(documents) >= 10000:
                    gaps.append(
                        "Pattern scan capped at 16 MB/10000 files; narrow source or path_glob"
                    )
                    break
                documents.append(dict(file, source=sid, path=path))
            if mode == "regex":
                try:
                    completed = subprocess.run(
                        [sys.executable, "-c", REGEX_WORKER],
                        input=encode(
                            {
                                "query": query,
                                "case_sensitive": case_sensitive,
                                "texts": [d["text"] for d in documents],
                            }
                        ),
                        text=True,
                        capture_output=True,
                        timeout=2,
                    )
                    if completed.returncode:
                        raise ValueError("Regex worker failed")
                    output = json.loads(completed.stdout)
                    if output.get("error"):
                        raise ValueError(output["error"])
                    hits = output["hits"]
                except subprocess.TimeoutExpired:
                    hits = []
                    gaps.append(
                        "Regex exceeded its 2-second execution limit; simplify the pattern or narrow the scope"
                    )
                except OSError:
                    hits = []
                    gaps.append("Regex worker unavailable")
            else:
                hits = []
                for number, doc in enumerate(documents):
                    haystack, needle = (
                        (doc["text"], query)
                        if case_sensitive
                        else (doc["text"].lower(), query.lower())
                    )
                    position = haystack.find(needle)
                    if position >= 0:
                        hits.append((number, doc["text"].count("\n", 0, position) + 1))
                    if len(hits) >= 250:
                        break
            for number, line in hits:
                doc = documents[number]
                item = {k: doc[k] for k in ("source", "path", "hash", "revision")}
                item["lines"] = [line, line]
                if max_snippet_lines:
                    start = max(0, line - 2)
                    item.update(
                        snippet="\n".join(
                            doc["text"].splitlines()[start : start + max_snippet_lines]
                        ),
                        snippet_line=start + 1,
                    )
                items.append(item)
            gaps.append(
                "Pattern search returns the first matching location per file; it is not an exhaustive occurrence list"
            )
        for item in items:
            item.setdefault(
                "evidence_id",
                digest(
                    encode(
                        [
                            item["source"],
                            item["path"],
                            item["hash"],
                            item.get("lines"),
                            item.get("symbol"),
                        ]
                    ).encode()
                ),
            )
        seen_count = sum(item["evidence_id"] in excluded for item in items)
        items = [item for item in items if item["evidence_id"] not in excluded]
        latest = self.engine.status()
        if latest["state"] != "ready" or latest["index"].get("generation") != generation:
            return pack(
                self.engine,
                [],
                token_budget,
                state="stale",
                gaps=["Sources changed during retrieval; retry after indexing"],
            )
        if len(items) >= 250:
            gaps.append("Candidate limit reached; narrow the search")
        if not items:
            gaps.append(
                "All matching candidates were already seen; narrow or change the query for more"
                if seen_count
                else "No matching evidence; this does not prove absence of behavior"
            )
        return pack(
            self.engine,
            items[:limit],
            token_budget,
            generation=generation,
            gaps=gaps,
            retrieval=used_mode,
            matched_candidates=len(items),
            already_seen=seen_count,
            limit_omitted=max(0, len(items) - limit),
        )

    @staticmethod
    def compact(row):
        return {
            "source": row["source"],
            "path": row["path"],
            "lines": [row["line_start"], row["line_end"]],
            "hash": row["hash"],
            "revision": row["revision"],
            "symbol": row.get("symbol"),
            "evidence_id": row.get("evidence_id")
            or digest(
                (
                    row["source"]
                    + row["path"]
                    + row["hash"]
                    + str(row["line_start"])
                    + row["method"]
                ).encode()
            ),
        }

    def read(
        self, source, path, line_start=1, line_end=None, expected_hash=None, token_budget=4000
    ):
        snapshot = self.engine.scan()
        status = self.engine._status(snapshot)
        response = self._read(
            source,
            path,
            line_start,
            line_end,
            expected_hash,
            token_budget,
            snapshot=(status, snapshot[0]),
        )
        if response["state"] == "ready":
            latest = self.engine.status()
            if latest["state"] != "ready" or latest["index"].get("generation") != status[
                "index"
            ].get("generation"):
                return pack(
                    self.engine,
                    [],
                    token_budget,
                    state="stale",
                    gaps=["Sources changed during file expansion"],
                )
        return response

    def _read(
        self,
        source,
        path,
        line_start=1,
        line_end=None,
        expected_hash=None,
        token_budget=4000,
        *,
        snapshot,
    ):
        """Internal expansion; the enclosing public request must recheck freshness."""
        self.scope(source, None, "all")
        if source is None:
            raise ValueError("source is required")
        if not isinstance(path, str) or len(path) > 4000:
            raise ValueError("Invalid path")
        if (
            type(line_start) is not int
            or line_start < 1
            or (line_end is not None and (type(line_end) is not int or line_end < line_start))
        ):
            raise ValueError("Invalid line range")
        status, current = snapshot
        generation = status["index"].get("generation")
        if status["state"] != "ready":
            return pack(
                self.engine,
                [],
                token_budget,
                state=status["state"],
                generation=generation,
                gaps=["Run index or crawl before reading evidence"],
            )
        # Only indexed paths can be expanded; no arbitrary filesystem reads.
        indexed = self.engine.db.execute(
            "SELECT * FROM files WHERE source=? AND path=?", (source, path)
        ).fetchone()
        if indexed is None:
            raise ValueError("File is not in this indexed scope")
        if expected_hash is not None and expected_hash != indexed["hash"]:
            return pack(
                self.engine,
                [],
                token_budget,
                state="stale",
                generation=generation,
                gaps=["Expected content hash changed; repeat discovery"],
            )
        file = current.get((source, path))
        if not file or file["hash"] != indexed["hash"] or file["revision"] != indexed["revision"]:
            return pack(
                self.engine,
                [],
                token_budget,
                state="stale",
                gaps=["File changed while expanding evidence"],
            )
        lines = file["text"].splitlines()
        stop = min(
            line_end if line_end is not None else line_start + 79, len(lines), line_start + 199
        )
        if line_start > len(lines):
            return pack(
                self.engine,
                [],
                token_budget,
                generation=generation,
                gaps=["Requested line is beyond the file"],
            )
        item = {
            "source": source,
            "path": path,
            "lines": [line_start, stop],
            "hash": indexed["hash"],
            "revision": indexed["revision"],
            "text": "\n".join(lines[line_start - 1 : stop]),
        }
        # Shrink by whole lines; never invent line ranges or silently truncate code.
        while True:
            response = pack(
                self.engine,
                [item],
                token_budget,
                generation=generation,
                next_line=stop + 1 if stop < len(lines) else None,
            )
            if response["items"] or stop <= line_start:
                if not response["items"]:
                    return pack(
                        self.engine,
                        [],
                        token_budget,
                        generation=generation,
                        next_line=line_start,
                        gaps=[
                            "A single source line exceeds this budget; increase the budget or inspect the file locally"
                        ],
                    )
                return response
            stop -= 1
            item.update(lines=[line_start, stop], text="\n".join(lines[line_start - 1 : stop]))

    def related(
        self,
        source,
        path,
        line=1,
        token_budget=2000,
        limit=5,
        mode="similarity",
        query="",
        direction="both",
        relation=None,
    ):
        if mode == "graph":
            return self.engine.architecture.neighbors(
                source, path, query, direction, relation, limit, token_budget
            )
        if mode != "similarity":
            raise ValueError("mode must be similarity or graph")
        if query or direction != "both" or relation is not None:
            raise ValueError("query, direction and relation require graph mode")
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("limit must be 1..50")
        if type(line) is not int or line < 1:
            raise ValueError("line must be a positive integer")
        seed = self.read(source, path, line, line + 10, token_budget=8000)
        if not seed["items"]:
            return pack(self.engine, [], token_budget, state=seed["state"], gaps=seed["gaps"])
        query = seed["items"][0]["text"][:2000]
        found = self.search(query, limit=50, token_budget=32000, max_snippet_lines=3)
        items = [
            dict(item, relation="content_similarity")
            for item in found["items"]
            if (item["source"], item["path"]) != (source, path)
        ]
        return pack(
            self.engine,
            items[:limit],
            token_budget,
            state=found["state"],
            generation=found.get("generation"),
            gaps=[
                "Similarity suggests related code; use the architecture overview for cited structural connections",
                *found["gaps"],
            ],
        )
