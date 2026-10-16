"""Incremental, cited structural facts. No source execution or model calls."""

import ast
import json
import re
from collections import Counter, defaultdict
from pathlib import PurePosixPath

from .budget import pack
from .core import digest, terms

EXTRACTOR_VERSION = "1"
LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".go": "go",
    ".rs": "rust",
    ".cs": "csharp",
    ".rb": "ruby",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".md": "markdown",
}


def language(path):
    return LANGUAGES.get(
        PurePosixPath(path).suffix, PurePosixPath(path).suffix.lstrip(".") or "text"
    )


def extract(path, text):
    facts, errors = [], []
    lines = text.splitlines()

    def add(kind, name, line, end=None, classification="extracted", **detail):
        if name:
            facts.append(
                {
                    "kind": kind,
                    "name": str(name)[:300],
                    "line": line,
                    "end": end or line,
                    "classification": classification,
                    **detail,
                }
            )

    if path.endswith(".py"):
        try:
            tree = ast.parse(text)
            if ast.get_docstring(tree):
                add("description", ast.get_docstring(tree).splitlines()[0], tree.body[0].lineno)

            def symbols(nodes, scope=""):
                for node in nodes:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        name = scope + node.name
                        if isinstance(node, ast.ClassDef):
                            signature = (
                                "class "
                                + node.name
                                + "("
                                + ", ".join(ast.unparse(x) for x in node.bases)
                                + ")"
                            )
                        else:
                            signature = (
                                ("async " if isinstance(node, ast.AsyncFunctionDef) else "")
                                + "def "
                                + node.name
                                + "("
                                + ast.unparse(node.args)
                                + ")"
                            )
                            if node.returns:
                                signature += " -> " + ast.unparse(node.returns)
                        add(
                            "symbol",
                            name,
                            node.lineno,
                            node.end_lineno,
                            signature=signature[:400],
                            symbol_kind="class" if isinstance(node, ast.ClassDef) else "function",
                        )
                        if node.name in ("main", "run", "serve", "handler"):
                            add(
                                "entrypoint",
                                name,
                                node.lineno,
                                classification="inferred",
                                reason="conventional function name",
                            )
                        symbols(node.body, name + ".")

            symbols(tree.body)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        add("import", alias.name, node.lineno)
                elif isinstance(node, ast.ImportFrom):
                    add(
                        "import",
                        "." * node.level + (node.module or ""),
                        node.lineno,
                        names=[a.name for a in node.names][:30],
                    )
                elif isinstance(node, ast.Call):
                    function = (
                        node.func.attr
                        if isinstance(node.func, ast.Attribute)
                        else getattr(node.func, "id", "")
                    )
                    value = (
                        node.args[0].value
                        if node.args and isinstance(node.args[0], ast.Constant)
                        else None
                    )
                    if (
                        isinstance(value, str)
                        and function
                        in ("route", "get", "post", "put", "patch", "delete", "websocket")
                        and value.startswith("/")
                    ):
                        add(
                            "route",
                            function.upper() + " " + value,
                            node.lineno,
                            classification="inferred",
                            reason="route-shaped call; framework not resolved",
                        )
                    if isinstance(value, str) and function in (
                        "publish",
                        "subscribe",
                        "emit",
                        "send_event",
                        "consume",
                    ):
                        add("event", value, node.lineno, usage=function)
                elif isinstance(node, ast.Dict):
                    for key, value in zip(node.keys, node.values):
                        if (
                            isinstance(key, ast.Constant)
                            and key.value in ("event", "topic", "queue")
                            and isinstance(value, ast.Constant)
                            and isinstance(value.value, str)
                        ):
                            add("event", value.value, value.lineno, usage="declared")
                elif isinstance(node, ast.Compare) and isinstance(node.left, ast.Subscript):
                    sub = node.left.slice
                    if isinstance(sub, ast.Constant) and sub.value in ("event", "topic", "queue"):
                        for value in node.comparators:
                            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                                add("event", value.value, value.lineno, usage="checked")
                elif isinstance(node, ast.If) and ast.unparse(node.test) in (
                    "__name__ == '__main__'",
                    "'__main__' == __name__",
                ):
                    add("entrypoint", "__main__", node.lineno)
        except (SyntaxError, RecursionError, ValueError):
            errors.append("Python parsing failed; structural facts unavailable")
    else:
        for number, line in enumerate(lines, 1):
            if path.endswith((".js", ".jsx", ".ts", ".tsx")):
                imp = re.search(r"\b(?:from\s+|require\s*\(\s*|import\s*)['\"]([^'\"]+)['\"]", line)
                if imp:
                    add("import", imp.group(1), number, classification="inferred")
                symbol = re.search(
                    r"^\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?(?:function|class|interface|type|enum)\s+(\w+)",
                    line,
                )
                if not symbol:
                    symbol = re.search(
                        r"^\s*(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>",
                        line,
                    )
                if symbol:
                    add(
                        "symbol",
                        symbol.group(1),
                        number,
                        classification="inferred",
                        signature=line.strip()[:400],
                        symbol_kind="declaration",
                    )
                route = re.search(
                    r"\.(get|post|put|patch|delete|route)\s*\(\s*['\"](/[^'\"]*)", line
                )
                if route:
                    add(
                        "route",
                        route.group(1).upper() + " " + route.group(2),
                        number,
                        classification="inferred",
                    )
                event = re.search(r"\b(?:event|topic)\s*:\s*['\"]([^'\"]+)", line)
                if event:
                    add("event", event.group(1), number, classification="inferred", usage="literal")
            elif path.endswith((".java", ".kt", ".go", ".rs", ".cs", ".rb")):
                imp = re.search(r"^\s*(?:import|use|using)\s+([^;]+)", line)
                if imp:
                    add("import", imp.group(1).strip(), number, classification="inferred")
                symbol = re.search(
                    r"^\s*(?:(?:public|private|protected|static|open|data|pub|async|export)\s+)*(?:class|interface|struct|enum|fun|func|fn|def)\s+(\w+)",
                    line,
                )
                if symbol:
                    add(
                        "symbol",
                        symbol.group(1),
                        number,
                        classification="inferred",
                        signature=line.strip()[:400],
                        symbol_kind="declaration",
                    )
            if path.endswith(".md") and line.startswith("# "):
                add("description", line[2:].strip(), number)
                break
        if PurePosixPath(path).name == "package.json":
            try:
                package = json.loads(text)
                if not isinstance(package, dict):
                    raise ValueError("Expected an object")
                for field in ("name", "description"):
                    if isinstance(package.get(field), str):
                        line = next(
                            (n for n, s in enumerate(lines, 1) if '"' + field + '"' in s), 1
                        )
                        add("description", package[field], line)
                for field in ("dependencies", "devDependencies", "peerDependencies"):
                    if isinstance(package.get(field), dict):
                        for dep in package[field]:
                            line = next(
                                (n for n, s in enumerate(lines, 1) if '"' + dep + '"' in s), 1
                            )
                            add("dependency", dep, line, dependency_kind=field)
                for field in ("main", "module"):
                    if isinstance(package.get(field), str):
                        line = next(
                            (n for n, s in enumerate(lines, 1) if '"' + field + '"' in s), 1
                        )
                        add("entrypoint", package[field], line)
            except (ValueError, TypeError):
                errors.append("Package manifest parsing failed")
    if PurePosixPath(path).name in (
        "__main__.py",
        "main.py",
        "main.go",
        "main.rs",
        "server.ts",
        "app.py",
    ):
        add("entrypoint", path, 1, classification="inferred", reason="conventional filename")
    unique = {json.dumps(f, sort_keys=True): f for f in facts}
    facts = sorted(unique.values(), key=lambda f: (f["line"], f["kind"], f["name"]))
    return {
        "language": language(path),
        "facts": facts[:2000],
        "omitted_facts": max(0, len(facts) - 2000),
        "errors": errors,
    }


class Architecture:
    def __init__(self, engine):
        self.engine, self.db = engine, engine.db
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS architecture_files(source TEXT,path TEXT,hash TEXT,revision TEXT,facts TEXT,
                PRIMARY KEY(source,path));
            CREATE TABLE IF NOT EXISTS architecture_edges(id TEXT PRIMARY KEY,document TEXT);
            CREATE INDEX IF NOT EXISTS architecture_from ON architecture_edges(json_extract(document,'$.from'));
            CREATE INDEX IF NOT EXISTS architecture_to ON architecture_edges(json_extract(document,'$.to'));
        """)

    def metadata(self):
        row = self.db.execute("SELECT value FROM meta WHERE key='architecture'").fetchone()
        return json.loads(row[0]) if row else {}

    def refresh(self, files, index):
        """Called in the code-index transaction: one generation for all facts."""
        prior = self.metadata()
        if (
            prior.get("generation") == index["generation"]
            and prior.get("extractor") == EXTRACTOR_VERSION
        ):
            return dict(prior, changed=0, reused=len(files))
        old = {
            (r["source"], r["path"]): dict(r)
            for r in self.db.execute("SELECT * FROM architecture_files")
        }
        changed = 0
        for key in old.keys() - files.keys():
            self.db.execute("DELETE FROM architecture_files WHERE source=? AND path=?", key)
        for key, file in sorted(files.items()):
            if (
                key in old
                and old[key]["hash"] == file["hash"]
                and prior.get("extractor") == EXTRACTOR_VERSION
            ):
                self.db.execute(
                    "UPDATE architecture_files SET revision=? WHERE source=? AND path=?",
                    (file["revision"], *key),
                )
                continue
            facts = extract(key[1], file["text"])
            self.db.execute(
                "INSERT OR REPLACE INTO architecture_files VALUES(?,?,?,?,?)",
                (*key, file["hash"], file["revision"], json.dumps(facts)),
            )
            changed += 1
        self.rebuild_edges()
        meta = {
            "generation": index["generation"],
            "extractor": EXTRACTOR_VERSION,
            "indexed_at": index["indexed_at"],
            "files": len(files),
            "changed": changed,
            "reused": len(files) - changed,
            "deleted": len(old.keys() - files.keys()),
            "edges": self.db.execute("SELECT count(*) FROM architecture_edges").fetchone()[0],
        }
        self.db.execute("INSERT OR REPLACE INTO meta VALUES('architecture',?)", (json.dumps(meta),))
        return meta

    def rows(self):
        return [
            dict(r, facts=json.loads(r["facts"]))
            for r in self.db.execute("SELECT * FROM architecture_files ORDER BY source,path")
        ]

    @staticmethod
    def node_id(row):
        return row["source"] + ":" + row["path"]

    @staticmethod
    def citation(row, fact=None):
        fact = fact or {"line": 1, "end": 1}
        return {
            "source": row["source"],
            "path": row["path"],
            "lines": [fact["line"], fact["end"]],
            "hash": row["hash"],
            "revision": row["revision"],
        }

    def rebuild_edges(self):
        rows = self.rows()
        paths = {(r["source"], r["path"]): r for r in rows}
        events = defaultdict(list)
        edges = []
        for row in rows:
            for fact in row["facts"]["facts"]:
                if fact["kind"] == "event":
                    events[fact["name"]].append((row, fact))
                if fact["kind"] != "import":
                    continue
                name = fact["name"]
                candidates = []
                if row["path"].endswith(".py"):
                    level = len(name) - len(name.lstrip("."))
                    base = PurePosixPath(row["path"]).parent
                    for _ in range(max(0, level - 1)):
                        base = base.parent
                    module = (
                        str(base / name[level:].replace(".", "/"))
                        if level
                        else name.replace(".", "/")
                    )
                    modules = [module]
                    modules.extend(
                        str(PurePosixPath(module) / child) for child in fact.get("names", [])
                    )
                    candidates = [
                        p
                        for m in modules
                        for p in (m + ".py", str(PurePosixPath(m) / "__init__.py"))
                    ]
                elif row["path"].endswith((".js", ".jsx", ".ts", ".tsx")) and name.startswith("."):
                    import posixpath

                    base = posixpath.normpath(str(PurePosixPath(row["path"]).parent / name))
                    candidates = (
                        [base]
                        + [base + suffix for suffix in (".ts", ".tsx", ".js", ".jsx")]
                        + [base + "/index" + suffix for suffix in (".ts", ".tsx", ".js", ".jsx")]
                    )
                targets = [
                    paths[(row["source"], path)]
                    for path in candidates
                    if (row["source"], path) in paths and path != row["path"]
                ]
                for target in targets:
                    edges.append(
                        {
                            "kind": "edge",
                            "relation": "imports",
                            "from": self.node_id(row),
                            "to": self.node_id(target),
                            "classification": "inferred",
                            "reason": "static module-path candidate; runtime resolution not established",
                            "citations": [self.citation(row, fact)],
                        }
                    )
        # Shared literals suggest a contract; do not manufacture a producer/consumer direction.
        for event, occurrences in sorted(events.items()):
            by_source = {}
            for row, fact in occurrences:
                by_source.setdefault(row["source"], (row, fact))
            selected = sorted(by_source.values(), key=lambda pair: self.node_id(pair[0]))
            for other in selected[1:]:
                first = selected[0]
                edges.append(
                    {
                        "kind": "edge",
                        "relation": "shared_event_literal",
                        "name": event,
                        "from": self.node_id(first[0]),
                        "to": self.node_id(other[0]),
                        "classification": "inferred",
                        "citations": [self.citation(*first), self.citation(*other)],
                    }
                )
        self.db.execute("DELETE FROM architecture_edges")
        for edge in edges:
            identity = digest(json.dumps(edge, sort_keys=True).encode())
            self.db.execute(
                "INSERT OR IGNORE INTO architecture_edges VALUES(?,?)",
                (identity, json.dumps(dict(edge, id=identity[:20]))),
            )

    def neighbors(
        self, source, path, query="", direction="both", relation=None, limit=5, token_budget=2000
    ):
        status = self.engine.status()
        result = self._neighbors(
            source, path, query, direction, relation, limit, token_budget, status=status
        )
        if result["state"] != "ready":
            return result
        latest = self.engine.status()
        if latest["state"] != "ready" or latest["index"].get("generation") != status["index"].get(
            "generation"
        ):
            return pack(
                self.engine,
                [],
                token_budget,
                state="stale",
                gaps=["Sources changed during graph expansion"],
            )
        return result

    def _neighbors(
        self,
        source,
        path,
        query="",
        direction="both",
        relation=None,
        limit=5,
        token_budget=2000,
        *,
        status,
    ):
        """Explicit one-hop expansion; never added to ordinary search automatically."""
        self.engine.navigation.scope(source, None, "all")
        if direction not in ("both", "outgoing", "incoming"):
            raise ValueError("direction must be both, outgoing or incoming")
        if relation not in (None, "imports", "shared_event_literal"):
            raise ValueError("Unknown graph relation")
        if not isinstance(query, str) or len(query) > 4000:
            raise ValueError("query must be a string of at most 4000 characters")
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("limit must be 1..50")
        generation = status["index"].get("generation")
        meta = self.metadata()
        if (
            status["state"] != "ready"
            or meta.get("generation") != generation
            or meta.get("extractor") != EXTRACTOR_VERSION
        ):
            return pack(
                self.engine,
                [],
                token_budget,
                state=status["state"] if status["state"] != "ready" else "stale",
                gaps=["Refresh code and architecture before graph expansion"],
            )
        if not self.db.execute(
            "SELECT 1 FROM architecture_files WHERE source=? AND path=?", (source, path)
        ).fetchone():
            raise ValueError("File is not in this indexed scope")
        anchor = source + ":" + path
        edges = [
            json.loads(r[0])
            for r in self.db.execute(
                "SELECT document FROM architecture_edges WHERE json_extract(document,'$.from')=? "
                "OR json_extract(document,'$.to')=? ORDER BY id",
                (anchor, anchor),
            )
        ]
        tokens = set(terms(query).split())
        items = []
        for edge in edges:
            if relation is not None and edge["relation"] != relation:
                continue
            # Shared literals are undirected: never invent a producer/consumer direction.
            if edge["relation"] == "imports" and (
                direction == "outgoing"
                and edge["from"] != anchor
                or direction == "incoming"
                and edge["to"] != anchor
            ):
                continue
            target = edge["to"] if edge["from"] == anchor else edge["from"]
            sid, target_path = target.split(":", 1)
            row = self.db.execute(
                "SELECT * FROM architecture_files WHERE source=? AND path=?", (sid, target_path)
            ).fetchone()
            if row is None:
                continue
            items.append(
                dict(
                    edge,
                    source=sid,
                    path=target_path,
                    hash=row["hash"],
                    revision=row["revision"],
                    lines=[1, 1],
                    direction="undirected"
                    if edge["relation"] == "shared_event_literal"
                    else "outgoing"
                    if edge["from"] == anchor
                    else "incoming",
                )
            )
        items.sort(
            key=lambda e: (
                -len(
                    tokens
                    & set(terms(e["path"] + " " + e.get("name", "") + " " + e["relation"]).split())
                ),
                e["id"],
            )
        )
        return pack(
            self.engine,
            items[:limit],
            token_budget,
            generation=generation,
            retrieval="graph",
            hops=1,
            matched_candidates=len(items),
            limit_omitted=max(0, len(items) - limit),
            gaps=[
                "Static graph candidates are inferred, not resolved runtime relationships; no link does not prove absence"
            ],
        )

    def overview(self, query="", source=None, node=None, token_budget=2000, if_none_match=None):
        if not isinstance(query, str) or len(query) > 4000:
            raise ValueError("query must be a string of at most 4000 characters")
        if source is not None and source not in self.engine.sources:
            raise ValueError("Unknown source")
        if node is not None and (not isinstance(node, str) or len(node) > 4500):
            raise ValueError("Invalid architecture node")
        status = self.engine.status()
        meta = self.metadata()
        generation = meta.get("generation")
        if (
            status["state"] != "ready"
            or generation != status["index"].get("generation")
            or meta.get("extractor") != EXTRACTOR_VERSION
        ):
            return pack(
                self.engine,
                [],
                token_budget,
                state="stale" if meta else "unindexed",
                generation=generation,
                gaps=["Run index or crawl before using the architecture overview"],
            )
        etag = digest(
            json.dumps(
                [
                    str(self.engine.store),
                    generation,
                    EXTRACTOR_VERSION,
                    query,
                    source,
                    node,
                    token_budget,
                ]
            ).encode()
        )
        if if_none_match == etag:
            return pack(
                self.engine, [], token_budget, state="unchanged", generation=generation, etag=etag
            )
        rows = [r for r in self.rows() if source is None or r["source"] == source]
        all_edges = [
            json.loads(r[0])
            for r in self.db.execute("SELECT document FROM architecture_edges ORDER BY id")
        ]
        edges = [
            e
            for e in all_edges
            if source is None or any(c["source"] == source for c in e["citations"])
        ]
        directory_nodes = set()
        for row in rows:
            for parent in PurePosixPath(row["path"]).parents:
                if str(parent) != ".":
                    directory_nodes.add("directory:" + row["source"] + ":" + str(parent) + "/")
        directory_cards = []
        if node and node not in directory_nodes | {self.node_id(r) for r in rows} | {
            "source:" + r["source"] for r in rows
        }:
            raise ValueError("Unknown architecture node in selected scope")
        if node and not node.startswith("directory:"):
            neighbors = {node}
            for edge in edges:
                if node in (edge["from"], edge["to"]):
                    neighbors.update((edge["from"], edge["to"]))
            rows = [
                r for r in rows if self.node_id(r) in neighbors or node == "source:" + r["source"]
            ]
            edges = [
                e
                for e in edges
                if node in (e["from"], e["to"])
                or node.startswith("source:")
                and any(c["source"] == node[7:] for c in e["citations"])
            ]
        if node and node.startswith(("source:", "directory:")):
            if node.startswith("source:"):
                sid, prefix = node[7:], ""
            else:
                sid, prefix = node[len("directory:") :].split(":", 1)
            selected = [r for r in rows if r["source"] == sid and r["path"].startswith(prefix)]
            children = {}
            leaves = []
            for row in selected:
                relative = row["path"][len(prefix) :]
                if "/" in relative:
                    folder = prefix + relative.split("/", 1)[0] + "/"
                    children.setdefault(folder, []).append(row)
                else:
                    leaves.append(row)
            for folder, members in sorted(children.items()):
                key = "directory:" + sid + ":" + folder
                directory_cards.append(
                    {
                        "kind": "directory",
                        "id": key,
                        "expand": key,
                        "source": sid,
                        "path": folder,
                        "files": len(members),
                        "classification": "path_group",
                        "languages": dict(Counter(r["facts"]["language"] for r in members)),
                    }
                )
            rows = leaves
            visible = {self.node_id(r) for r in rows}
            edges = [e for e in edges if e["from"] in visible and e["to"] in visible]
        degree = Counter(x for e in all_edges for x in (e["from"], e["to"]))
        tokens = set(terms(query).split())

        def rank(row):
            facts = row["facts"]["facts"]
            words = set(terms(row["path"] + " " + " ".join(f["name"] for f in facts)).split())
            return (
                -(
                    10 * len(tokens & words)
                    + min(10, degree[self.node_id(row)])
                    + 3 * any(f["kind"] in ("entrypoint", "route", "event") for f in facts)
                    + 2 * any(f["kind"] == "description" for f in facts)
                ),
                row["source"],
                row["path"],
            )

        items = sorted(
            directory_cards, key=lambda c: (-len(tokens & set(terms(c["path"]).split())), c["id"])
        )
        if not node or node.startswith("source:"):
            for sid in sorted({r["source"] for r in rows}):
                selected = [r for r in rows if r["source"] == sid]
                items.append(
                    {
                        "kind": "repository",
                        "id": "source:" + sid,
                        "source": sid,
                        "files": len(selected),
                        "languages": dict(Counter(r["facts"]["language"] for r in selected)),
                        "expand": "source:" + sid,
                    }
                )
        ranked = sorted(rows, key=rank)
        modules = []
        for row in ranked:
            facts = row["facts"]["facts"]
            descriptions = [f for f in facts if f["kind"] == "description"]
            symbols = [f for f in facts if f["kind"] == "symbol"]
            signals = [
                f for f in facts if f["kind"] in ("entrypoint", "event", "route", "dependency")
            ]
            citation_fact = (
                descriptions[0]
                if descriptions
                else signals[0]
                if signals
                else symbols[0]
                if symbols
                else None
            )
            modules.append(
                {
                    "kind": "module",
                    "id": self.node_id(row),
                    "language": row["facts"]["language"],
                    "description": descriptions[0]["name"] if descriptions else "",
                    "symbols": [
                        {"name": f["name"], "line": f["line"]}
                        for f in symbols[: (20 if node else 3)]
                    ],
                    "signals": [
                        {k: f[k] for k in ("kind", "name", "line", "classification")}
                        for f in signals[: (10 if node else 2)]
                    ],
                    "omitted_facts": max(0, len(symbols) - (20 if node else 3))
                    + max(0, len(signals) - (10 if node else 2))
                    + row["facts"]["omitted_facts"],
                    "citation": self.citation(row, citation_fact),
                }
            )
        # Cross-repository contracts receive a slot before lower-ranked module detail.
        items.extend(modules[:1])
        items.extend(
            sorted(edges, key=lambda e: (e["relation"] != "shared_event_literal", e["id"]))[:50]
        )
        items.extend(modules[1:])
        gaps = [
            "Static evidence only: inferred relationships require verification; no resolved call graph"
        ]
        if any(r["facts"]["errors"] or r["facts"]["omitted_facts"] for r in rows):
            gaps.append(
                "Some files have parsing gaps or truncated facts; use code retrieval for details"
            )
        # Recheck after assembly to avoid serving a generation replaced during the query.
        latest = self.engine.status()
        if latest["state"] != "ready" or latest["index"].get("generation") != generation:
            return pack(
                self.engine,
                [],
                token_budget,
                state="stale",
                gaps=["Sources changed during overview retrieval; retry after indexing"],
            )
        return pack(
            self.engine,
            items[:300],
            token_budget,
            generation=generation,
            etag=etag,
            gaps=gaps,
            indexed_at=status["index"]["indexed_at"],
            candidate_limit_reached=len(items) > 300,
        )
