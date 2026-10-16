"""Scoped evidence store; embedding providers are supplied through an adapter."""

import ast
import fnmatch
import hashlib
import json
import os
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import runtime_identity
from .embeddings import EmbeddingError, configured_provider
from .locking import exclusive
from .semantic import SemanticIndex, fuse

VERSION = "1"
SUFFIXES = {
    ".py",
    ".kt",
    ".kts",
    ".java",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".html",
    ".css",
    ".yaml",
    ".yml",
    ".json",
    ".md",
    ".toml",
    ".sql",
    ".graphql",
    ".go",
    ".rs",
    ".c",
    ".h",
    ".cpp",
    ".cs",
    ".rb",
    ".sh",
}
BUILD_NAMES = {
    "Dockerfile",
    "Containerfile",
    "Makefile",
    "GNUmakefile",
    "CMakeLists.txt",
    "Justfile",
    "justfile",
}


def build_file(path):
    name = Path(path).name
    return name in BUILD_NAMES or bool(
        re.fullmatch(r"requirements(?:[-.][A-Za-z0-9_-]+)?\.txt", name)
    )


SKIP = {
    ".context-wiki",
    ".git",
    ".context-engine",
    "node_modules",
    "build",
    "dist",
    ".gradle",
    ".venv",
    "venv",
    "__pycache__",
    "vendor",
}


def digest(value):
    return hashlib.sha256(value).hexdigest()


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=15)
    return result.stdout if result.returncode == 0 else None


def terms(text):
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    return " ".join(re.findall(r"\w+", text + " " + expanded.replace("_", " "))).lower()


def content_kind(path):
    suffix = Path(path).suffix.lower()
    return (
        "docs"
        if suffix == ".md"
        else "config"
        if suffix in (".json", ".yaml", ".yml", ".toml") or build_file(path)
        else "code"
    )


def units(path, content):
    lines = content.splitlines()
    symbols = []
    error = None
    if path.endswith((".kt", ".kts")):
        from .kotlin import extract

        data = extract(content)
        error = "; ".join(data["gaps"]) or None
        if data["omitted"]:
            error = "Kotlin structural fact limit reached; text windows preserve file coverage"
        symbols.extend(
            (*fact["lines"], fact["name"], "kotlin-tree-sitter")
            for fact in data["facts"]
            if fact["kind"] == "definition"
        )
    if path.endswith(".py"):
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    start = min([node.lineno] + [d.lineno for d in node.decorator_list])
                    symbols.append((start, node.end_lineno, node.name, "python-ast"))
        except SyntaxError as exc:
            error = "Python syntax error at line %s; text fallback" % exc.lineno
    # Text coverage includes imports, module constants, and unsupported languages.
    symbols += [
        (i + 1, min(i + 40, len(lines)), None, "text-window") for i in range(0, len(lines), 40)
    ]
    for start, end, name, method in symbols:
        # Bound large symbols while keeping real source line ranges.
        for offset in range(start, end + 1, 80):
            stop = min(offset + 79, end)
            yield {
                "line_start": offset,
                "line_end": stop,
                "symbol": name,
                "method": method,
                "text": "\n".join(lines[offset - 1 : stop]),
                "parser_error": error,
            }


class Engine:
    def __init__(self, manifest, state, embedding_provider=None):
        self.manifest = Path(manifest).resolve()
        self.config = json.loads(self.manifest.read_text())
        c = self.config
        if not isinstance(c, dict):
            raise ValueError("Manifest must be a JSON object")
        if type(c.get("schema_version")) is not int or c["schema_version"] != 1:
            raise ValueError("Expected schema_version 1")
        for key in ("environment", "workspace"):
            if not isinstance(c.get(key), str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", c[key]):
                raise ValueError("Invalid " + key)
        sources = c.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError("At least one source is required")
        from .policy import enforce, within

        self.policy = enforce(c, state, embedding_provider)
        self.sources = {}
        self.state = Path(state).resolve()
        managed_scope = c["workspace"] + "-" + digest(json.dumps(c, sort_keys=True).encode())[:16]
        for source in sources:
            if not isinstance(source, dict):
                raise ValueError("Each source must be an object")
            sid = source.get("id")
            if (
                not isinstance(sid, str)
                or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", sid)
                or sid in self.sources
            ):
                raise ValueError("Source IDs must be unique simple names")
            if source.get("type", "files") not in ("files", "git", "markdown", "remote-git"):
                raise ValueError("Unsupported source type")
            if source.get("type") == "remote-git":
                from .managed import validate

                validate(source)
                root = self.state / c["environment"] / "repositories" / managed_scope / sid
            else:
                if not isinstance(source.get("path"), str) or not source["path"].strip():
                    raise ValueError("Local sources require a nonempty path string")
                root = (self.manifest.parent / source["path"]).resolve()
            if (
                self.policy
                and source.get("type") != "remote-git"
                and not within(root, self.policy["source_roots"])
            ):
                raise ValueError("Source is outside approved source roots")
            self.sources[sid] = dict(source, root=str(root))
        embedding_config = c.get("embeddings")
        if isinstance(embedding_config, dict) and embedding_config.get("cache_folder"):
            embedding_config = dict(
                embedding_config,
                cache_folder=str(
                    (self.manifest.parent / embedding_config["cache_folder"]).resolve()
                ),
            )
        if (
            self.policy
            and isinstance(embedding_config, dict)
            and embedding_config.get("cache_folder")
            and not within(embedding_config["cache_folder"], self.policy["storage_roots"])
        ):
            raise ValueError("Model cache is outside approved storage roots")
        self.embedding_provider = embedding_provider or configured_provider(embedding_config)
        from .chunking import Chunker

        self.chunker = Chunker(c.get("chunking"))
        self.excludes = c.get("exclude", [])
        if not isinstance(self.excludes, list) or not all(
            isinstance(p, str) for p in self.excludes
        ):
            raise ValueError("exclude must be a list of glob patterns")
        self.state = Path(state).resolve()
        signature = digest(
            json.dumps({"config": c, "sources": self.sources}, sort_keys=True).encode()
        )
        self.store = (
            self.state / c["environment"] / (c["workspace"] + "-" + signature[:16] + ".sqlite3")
        )
        # This directory contains company source excerpts and derived evidence.
        # Restrict existing stores too; never chmod through a symlink.
        directory = self.store.parent
        if directory.is_symlink():
            raise ValueError("Refusing symlink state directory")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if directory.stat().st_uid != os.getuid():
            raise ValueError("State directory must be owned by the current user")
        directory.chmod(0o700)
        for private in (self.store, Path(str(self.store) + "-wal"), Path(str(self.store) + "-shm")):
            if private.is_symlink() or (private.exists() and not private.is_file()):
                raise ValueError("Refusing non-regular index file")
            if private.exists():
                if private.stat().st_uid != os.getuid():
                    raise ValueError("Index files must be owned by the current user")
                private.chmod(0o600)
        descriptor = os.open(self.store, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.close(descriptor)
        self.db = sqlite3.connect(str(self.store), timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.create_function("path_matches", 2, fnmatch.fnmatchcase)
        self.db.create_function("content_kind", 1, content_kind)
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS files(source TEXT,path TEXT,hash TEXT,revision TEXT,
                PRIMARY KEY(source,path));
            CREATE TABLE IF NOT EXISTS evidence(id INTEGER PRIMARY KEY,source TEXT,path TEXT,
                hash TEXT,revision TEXT,line_start INTEGER,line_end INTEGER,symbol TEXT,method TEXT,text TEXT);
            CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(tokens);
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
        """)
        from .usage import RELEASE, Usage

        self.usage = Usage(self.store.parent / (self.store.stem + "-usage-" + RELEASE))
        self.semantic = SemanticIndex(self, self.embedding_provider)
        from .history import History

        self.history = History(self)
        from .architecture import Architecture
        from .crawler import Crawler

        self.architecture = Architecture(self)
        self.crawler = Crawler(self)
        from .navigation import Navigation

        self.navigation = Navigation(self)
        from .instructions import Instructions

        self.instructions = Instructions(self)
        from .structure import Structure

        self.structure = Structure(self)
        from .knowledge import Knowledge

        self.knowledge = Knowledge(self)
        from .review_context import ReviewContext

        self.review_context = ReviewContext(self)

    def close(self):
        self.db.close()

    def scan(self):
        files, coverage = {}, {}
        from .managed import status as remote_status

        remotes = remote_status(self)
        for sid, source in self.sources.items():
            root = Path(source["root"])
            report = {"root": str(root), "files": 0, "excluded": 0, "errors": [], "revision": None}
            coverage[sid] = report
            managed = source.get("type") == "remote-git"
            if managed and remotes.get(sid, {}).get("state") != "ready":
                report["errors"].append(
                    "Managed remote snapshot is not current; run crawl and inspect remote_sources status"
                )
            if not root.is_dir():
                report["errors"].append("Source directory unavailable")
                continue
            revision = git(root, "rev-parse", "HEAD")
            report["revision"] = revision.decode().strip() if revision else None
            if managed:
                dirty = git(root, "status", "--porcelain", "--untracked-files=all")
                if (
                    dirty is None
                    or dirty.strip()
                    or report["revision"] != remotes.get(sid, {}).get("revision")
                ):
                    report["errors"].append(
                        "Managed checkout differs from its synchronized snapshot; run crawl"
                    )
            names = git(
                root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "."
            )
            if names is not None:
                paths = sorted(set(os.fsdecode(p) for p in names.split(b"\0") if p))
            else:
                paths = []
                for directory, dirs, names_in_dir in os.walk(root, followlinks=False):
                    dirs[:] = [
                        d for d in dirs if d not in SKIP and not Path(directory, d).is_symlink()
                    ]
                    paths.extend(str((Path(directory) / n).relative_to(root)) for n in names_in_dir)
                paths.sort()
            for rel in paths:
                p = root / rel
                resolved = p.resolve()
                excluded = (
                    any(part in SKIP or part.startswith(".env") for part in Path(rel).parts)
                    or (p.suffix.lower() not in SUFFIXES and not build_file(p))
                    or (source.get("type") == "markdown" and p.suffix.lower() != ".md")
                    or any(fnmatch.fnmatch(rel, pattern) for pattern in self.excludes)
                    or resolved != p.absolute()
                    or root not in resolved.parents
                    or (not managed and (self.state == resolved or self.state in resolved.parents))
                )
                if excluded:
                    report["excluded"] += 1
                    continue
                try:
                    if p.stat().st_size > 512_000:
                        report["excluded"] += 1
                        continue
                    raw = p.read_bytes()
                    content = raw.decode("utf-8")
                    if "\0" in content:
                        report["excluded"] += 1
                        continue
                    files[(sid, rel)] = {
                        "hash": digest(raw),
                        "revision": report["revision"],
                        "text": content,
                    }
                    report["files"] += 1
                except FileNotFoundError:
                    # Git still lists unstaged deletions; a local file can also
                    # disappear after discovery. Keep unavailable roots and
                    # damaged managed snapshots visible as coverage errors.
                    if managed or not root.is_dir():
                        report["errors"].append(rel + ": FileNotFoundError")
                except (OSError, UnicodeError) as exc:
                    report["errors"].append(rel + ": " + type(exc).__name__)
        return files, coverage

    @exclusive
    def index(self):
        from .artifacts import Artifacts

        artifacts = Artifacts(self)
        current, coverage = self.scan()
        changed = deleted = unchanged = 0
        parser_errors = []
        same_chunker = self.metadata().get("chunker") == self.chunker.identity
        with self.db:
            old = {
                (r["source"], r["path"]): dict(r) for r in self.db.execute("SELECT * FROM files")
            }
            for key in sorted(old.keys() | current.keys()):
                sid, path = key
                previous, item = old.get(key), current.get(key)
                if previous and item and previous["hash"] == item["hash"] and same_chunker:
                    unchanged += 1
                    self.db.execute(
                        "UPDATE files SET revision=? WHERE source=? AND path=?",
                        (item["revision"], sid, path),
                    )
                    self.db.execute(
                        "UPDATE evidence SET revision=? WHERE source=? AND path=?",
                        (item["revision"], sid, path),
                    )
                    continue
                self.db.execute(
                    "DELETE FROM search WHERE rowid IN (SELECT id FROM evidence WHERE source=? AND path=?)",
                    key,
                )
                self.db.execute("DELETE FROM evidence WHERE source=? AND path=?", key)
                self.db.execute("DELETE FROM files WHERE source=? AND path=?", key)
                if item is None:
                    deleted += 1
                    continue
                changed += 1
                self.db.execute(
                    "INSERT INTO files VALUES(?,?,?,?)", (sid, path, item["hash"], item["revision"])
                )
                for unit in artifacts.units(sid, path, item):
                    if unit["parser_error"]:
                        parser_errors.append(
                            {"source": sid, "path": path, "error": unit["parser_error"]}
                        )
                    cur = self.db.execute(
                        "INSERT INTO evidence(source,path,hash,revision,line_start,line_end,symbol,method,text) VALUES(?,?,?,?,?,?,?,?,?)",
                        (
                            sid,
                            path,
                            item["hash"],
                            item["revision"],
                            unit["line_start"],
                            unit["line_end"],
                            unit["symbol"],
                            unit["method"],
                            unit["text"],
                        ),
                    )
                    self.db.execute(
                        "INSERT INTO search(rowid,tokens) VALUES(?,?)",
                        (
                            cur.lastrowid,
                            terms(path + " " + (unit["symbol"] or "") + " " + unit["text"]),
                        ),
                    )
            prior = self.metadata().get("parser_errors", []) if same_chunker else []
            parser_errors += [
                e
                for e in prior
                if (e["source"], e["path"]) in current
                and (e["source"], e["path"]) in old
                and current[(e["source"], e["path"])]["hash"]
                == old[(e["source"], e["path"])]["hash"]
            ]
            parser_errors = list({json.dumps(e, sort_keys=True): e for e in parser_errors}.values())
            generation = digest(
                json.dumps(
                    [(k, v["hash"], v["revision"]) for k, v in sorted(current.items())]
                ).encode()
            )
            meta = {
                "generation": generation,
                "indexed_at": datetime.now(timezone.utc).isoformat(),
                "index_version": VERSION,
                "backend": runtime_identity.identity(),
                "coverage": coverage,
                "parser_errors": parser_errors,
                "chunker": self.chunker.identity,
                "changed": changed,
                "deleted": deleted,
                "unchanged": unchanged,
            }
            meta["chunk_artifacts"] = artifacts.prune()
            meta["architecture"] = self.architecture.refresh(current, meta)
            meta["structure"] = self.structure.refresh(current, meta)
            self.db.execute("INSERT OR REPLACE INTO meta VALUES('index',?)", (json.dumps(meta),))
        if self.embedding_provider:
            meta["semantic"] = self.semantic.index()
        return meta

    def metadata(self):
        row = self.db.execute("SELECT value FROM meta WHERE key='index'").fetchone()
        return json.loads(row[0]) if row else {}

    def status(self):
        return self._status(self.scan())

    def _status(self, snapshot):
        """Internal request snapshot; public callers always perform a fresh scan."""
        current, coverage = snapshot
        indexed = {
            (r["source"], r["path"]): (r["hash"], r["revision"])
            for r in self.db.execute("SELECT * FROM files")
        }
        live = {k: (v["hash"], v["revision"]) for k, v in current.items()}
        drift = sum(indexed.get(k) != live.get(k) for k in indexed.keys() | live.keys())
        meta = self.metadata()
        runtime = runtime_identity.health(meta)
        state = "unindexed" if not meta else "stale" if drift else "ready"
        if runtime["state"] not in ("current", "unindexed"):
            state = "stale"
        if any(r["errors"] for r in coverage.values()):
            state = "degraded"
        semantic = self.semantic.status()
        from .managed import status as remote_status

        return {
            "environment": self.config["environment"],
            "workspace": self.config["workspace"],
            "state": state,
            "runtime": runtime,
            "semantic": semantic,
            "chunking": self.chunker.identity,
            "history": self.history.status(),
            "architecture": self.architecture.metadata(),
            "crawler": self.crawler.status(),
            "remote_sources": remote_status(self),
            "drift_files": drift,
            "coverage": coverage,
            "index": meta,
            "capabilities": {
                "retrieval": "hybrid-rrf"
                if state == "ready" and semantic["state"] == "ready"
                else "lexical-fts5",
                "python": "ast-symbols",
                "kotlin": "optional-tree-sitter-syntax-with-text-fallback",
                "other_languages": "text-windows",
                "semantic_search": state == "ready" and semantic["state"] == "ready",
                "history_retrieval": not self.policy or self.policy["allow_history"],
                "resolved_relationships": False,
            },
        }

    def _search_candidates(self, query, mode, status, source=None, path_glob=None, content="all"):
        """Internal ranked candidates: no response packing, snippet clipping or byte cutoff.

        Callers validate inputs and provide the request's initial freshness snapshot.
        """
        requested_mode = mode
        mode = ("hybrid" if self.embedding_provider else "lexical") if mode == "auto" else mode
        result = {
            "status": status,
            "retrieval": {"requested": requested_mode, "used": mode},
            "rows": [],
            "gaps": [],
        }
        # A single snake-case identifier/error is a phrase, not a bag of words.
        tokens = (
            [query.lower()]
            if re.fullmatch(r"\w+_\w+", query)
            else list(dict.fromkeys(terms(query).split()))[:64]
        )
        if not tokens:
            result["gaps"].append("No searchable terms")
            return result
        match = " OR ".join('"' + t.replace('"', '""') + '"' for t in tokens)
        where, parameters = ["search MATCH ?"], [match]
        for condition, value in (
            ("e.source=?", source),
            ("path_matches(e.path,?)", path_glob),
            ("content_kind(e.path)=?", content if content != "all" else None),
        ):
            if value is not None:
                where.append(condition)
                parameters.append(value)
        rows = self.db.execute(
            "SELECT e.*,bm25(search) AS rank FROM search JOIN evidence e ON e.id=search.rowid WHERE "
            + " AND ".join(where)
            + " ORDER BY rank,e.source,e.path,e.line_start,e.line_end,e.method,e.id LIMIT 250",
            parameters,
        ).fetchall()
        if mode in ("semantic", "hybrid"):
            try:
                semantic_rows = self.semantic.candidates(
                    query, source=source, path_glob=path_glob, content=content
                )
                rows = (
                    fuse(rows, semantic_rows)
                    if mode == "hybrid"
                    else [dict(r, retrieval_methods=["semantic"]) for r in semantic_rows]
                )
            except EmbeddingError as exc:
                result["gaps"].append(str(exc))
                if mode == "semantic":
                    result["retrieval"]["used"] = "none"
                    return result
                mode = "lexical"
                result["retrieval"]["used"] = "lexical"
                result["gaps"].append("Using lexical fallback; semantic retrieval was unavailable")
        if requested_mode != "lexical" and self.embedding_provider:
            latest = self.status()
            if latest["state"] != "ready" or latest["index"].get("generation") != status[
                "index"
            ].get("generation"):
                result["status"] = latest
                result["gaps"].append(
                    "Source snapshot changed during retrieval; retry after indexing"
                )
                return result
        if mode == "hybrid" and re.fullmatch(r"\w+", query):
            # Preserve exact identifiers ahead of merely similar semantic candidates.
            exact = re.compile(r"(?<!\w)" + re.escape(query) + r"(?!\w)", re.IGNORECASE)
            rows = sorted(rows, key=lambda r: not bool(exact.search(r["path"] + " " + r["text"])))
        result["rows"] = [dict(row) for row in rows]
        return result

    def search(
        self,
        query,
        limit=10,
        token_budget=2000,
        mode="auto",
        source=None,
        path_glob=None,
        content="all",
        snippet_lines=None,
    ):
        if mode not in ("auto", "lexical", "semantic", "hybrid"):
            raise ValueError("mode must be auto, lexical, semantic or hybrid")
        requested_mode = mode
        mode = ("hybrid" if self.embedding_provider else "lexical") if mode == "auto" else mode
        if not isinstance(query, str) or len(query) > 4000:
            raise ValueError("query must be a string of at most 4000 characters")
        if (
            type(limit) is not int
            or not 1 <= limit <= 50
            or type(token_budget) is not int
            or not 1 <= token_budget <= 32000
        ):
            raise ValueError("limit must be 1..50 and token_budget 1..32000")
        if source is not None and source not in self.sources:
            raise ValueError("Unknown source")
        if path_glob is not None and (not isinstance(path_glob, str) or len(path_glob) > 4000):
            raise ValueError("Invalid path_glob")
        if content not in ("all", "code", "docs", "config"):
            raise ValueError("content must be all, code, docs or config")
        if snippet_lines is not None and (
            type(snippet_lines) is not int or not 0 <= snippet_lines <= 80
        ):
            raise ValueError("snippet_lines must be 0..80")
        status = self.status()
        # Fail closed on drift: never serve stale or unavailable source evidence.
        bundle = {
            "environment": self.config["environment"],
            "workspace": self.config["workspace"],
            "query": query,
            "status": status,
            "retrieval": {"requested": requested_mode, "used": mode},
            "items": [],
            "budget": {
                "max_estimated_tokens": token_budget,
                "used_estimated_tokens": 0,
                "omitted_files": [],
                "method": "UTF-8 bytes (conservative proxy; evidence items only)",
            },
            "gaps": [],
            "content_is_untrusted": True,
        }
        if status["state"] != "ready":
            bundle["gaps"].append(
                "Index is " + status["state"] + "; run index or watch before retrieval"
            )
            return bundle
        found = self._search_candidates(query, requested_mode, status, source, path_glob, content)
        bundle["status"] = found["status"]
        bundle["retrieval"] = found["retrieval"]
        bundle["gaps"].extend(found["gaps"])
        mode = found["retrieval"]["used"]
        rows = found["rows"]
        if found["status"]["state"] != "ready":
            return bundle
        spans = []
        over_budget = []
        for row in rows:
            item = dict(row)
            if any(
                s == item["source"]
                and p == item["path"]
                and a <= item["line_end"]
                and b >= item["line_start"]
                for s, p, a, b in spans
            ):
                continue
            if snippet_lines is not None:
                original_lines = item["text"].splitlines()
                if snippet_lines and original_lines:
                    query_terms = set(terms(query).split())
                    best = max(
                        range(len(original_lines)),
                        key=lambda n: len(query_terms & set(terms(original_lines[n]).split())),
                    )
                    first = max(0, best - 1)
                    selected = original_lines[first : first + snippet_lines]
                    item["line_start"] += first
                    item["line_end"] = item["line_start"] + len(selected) - 1
                    item["text"] = "\n".join(selected)
                else:
                    item["text"] = ""
            item["absolute_path"] = str(Path(self.sources[item["source"]]["root"]) / item["path"])
            item["source_type"] = self.sources[item["source"]].get("type", "files")
            item["reason"] = (
                "Lexical BM25 match; lower rank is better, not a confidence probability"
                if mode == "lexical"
                else "Rank-fused lexical/semantic evidence; rank is negative RRF, not confidence"
                if mode == "hybrid"
                else "Embedding similarity; rank is negative cosine similarity, not confidence"
            )
            item["evidence_id"] = digest(
                (
                    item["source"]
                    + item["path"]
                    + item["hash"]
                    + str(item["line_start"])
                    + item["method"]
                ).encode()
            )
            del item["id"]
            cost = len(json.dumps(item, ensure_ascii=False).encode("utf-8"))
            if bundle["budget"]["used_estimated_tokens"] + cost > token_budget:
                over_budget.append(
                    (item["source"], item["path"], item["line_start"], item["line_end"])
                )
                continue
            bundle["items"].append(item)
            bundle["budget"]["used_estimated_tokens"] += cost
            spans.append((item["source"], item["path"], item["line_start"], item["line_end"]))
            if len(bundle["items"]) == limit:
                break
        # A smaller overlapping excerpt may have fit after a larger one did not.
        # Match the retrieval overlap policy so that it is not reported as omitted.
        omitted = sorted(
            {
                (s, p)
                for s, p, a, b in over_budget
                if not any(s == ss and p == pp and aa <= b and bb >= a for ss, pp, aa, bb in spans)
            }
        )
        bundle["budget"]["omitted_files"] = [{"source": s, "path": p} for s, p in omitted]
        if omitted:
            bundle["gaps"].append(
                "Evidence budget omitted matching excerpts from: "
                + ", ".join(s + "/" + p for s, p in omitted)
                + ". Only examined candidates are reported; increase token_budget for more evidence."
            )
        if not bundle["items"]:
            bundle["gaps"].append(
                "No matching evidence fits the budget" if rows else "No matching evidence"
            )
        bundle["gaps"].append(
            "Lexical retrieval only; relationships and exhaustive coverage are not established"
            if mode == "lexical"
            else "Similarity is not proof of relevance; relationships and exhaustive coverage are not established"
        )
        return bundle
