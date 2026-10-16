"""Cached syntax navigation. Binding candidates are hypotheses, never runtime call claims."""

import ast
import importlib.metadata
import json
import posixpath
from pathlib import PurePosixPath

from .budget import pack

SUPPORTED = {".py", ".js", ".jsx", ".ts", ".tsx", ".kt", ".kts"}
VERSION = "1"


def identity():
    versions = []
    for name in ("tree-sitter", "tree-sitter-javascript", "tree-sitter-typescript"):
        try:
            versions.append(importlib.metadata.version(name))
        except importlib.metadata.PackageNotFoundError:
            versions.append("missing")
    from .kotlin import identity as kotlin_identity

    return VERSION + ":" + ":".join(versions) + ":" + kotlin_identity()


def extract(path, text):
    if path.endswith((".kt", ".kts")):
        from .kotlin import extract as kotlin_extract

        return kotlin_extract(text)
    facts, gaps = [], []

    def add(kind, name, line, end=None, owner=None, **extra):
        facts.append(
            dict(
                kind=kind,
                name=name[:300],
                lines=[line, end or line],
                owner=owner,
                classification="extracted",
                **extra,
            )
        )

    if path.endswith(".py"):

        class Visitor(ast.NodeVisitor):
            owner = None

            def definition(self, node):
                parent = self.owner
                name = ".".join(filter(None, [parent, node.name]))
                add(
                    "definition",
                    node.name,
                    node.lineno,
                    node.end_lineno,
                    parent,
                    qualified_name=name,
                )
                self.owner = name
                self.generic_visit(node)
                self.owner = parent

            visit_FunctionDef = definition
            visit_AsyncFunctionDef = definition
            visit_ClassDef = definition

            def visit_Call(self, node):
                function = node.func
                if isinstance(function, (ast.Name, ast.Attribute)):
                    name = function.id if isinstance(function, ast.Name) else function.attr
                    add(
                        "call",
                        name,
                        node.lineno,
                        node.end_lineno,
                        self.owner,
                        expression=ast.unparse(function)[:300],
                    )
                self.generic_visit(node)

            def visit_Name(self, node):
                if isinstance(node.ctx, ast.Load):
                    add("reference", node.id, node.lineno, owner=self.owner)

            def visit_Attribute(self, node):
                if isinstance(node.ctx, ast.Load):
                    add("reference", node.attr, node.lineno, owner=self.owner)
                self.generic_visit(node)

            def visit_Import(self, node):
                for alias in node.names:
                    add("import", alias.name, node.lineno, owner=self.owner)

            def visit_ImportFrom(self, node):
                add(
                    "import",
                    "." * node.level + (node.module or ""),
                    node.lineno,
                    owner=self.owner,
                    imported=[dict(name=a.name, alias=a.asname or a.name) for a in node.names],
                )

        try:
            Visitor().visit(ast.parse(text))
        except (SyntaxError, RecursionError, ValueError):
            facts = []
            gaps.append("Python parse failed; use lexical search for this file")
    else:
        try:
            from tree_sitter import Language, Parser

            if path.endswith((".ts", ".tsx")):
                import tree_sitter_typescript as grammar

                language = (
                    grammar.language_tsx()
                    if path.endswith(".tsx")
                    else grammar.language_typescript()
                )
            else:
                import tree_sitter_javascript as grammar

                language = grammar.language()
            tree = Parser(Language(language)).parse(text.encode("utf-8"))
            if tree.root_node.has_error:
                return {
                    "facts": [],
                    "gaps": ["JS/TS parse failed; use lexical search for this file"],
                    "omitted": 0,
                }
            raw = text.encode("utf-8")

            def value(node):
                return raw[node.start_byte : node.end_byte].decode("utf-8") if node else ""

            declarations = {
                "function_declaration",
                "generator_function_declaration",
                "class_declaration",
                "interface_declaration",
                "type_alias_declaration",
                "enum_declaration",
                "method_definition",
                "variable_declarator",
            }
            stack = [(tree.root_node, None)]
            while stack:
                node, owner = stack.pop()
                name_node = node.child_by_field_name("name")
                name = value(name_node)
                next_owner = owner
                if (
                    node.type in declarations
                    and name_node
                    and name_node.type in ("identifier", "type_identifier", "property_identifier")
                ):
                    add(
                        "definition",
                        name,
                        node.start_point.row + 1,
                        node.end_point.row + 1,
                        owner,
                        qualified_name=".".join(filter(None, [owner, name])),
                    )
                    next_owner = ".".join(filter(None, [owner, name]))
                if node.type in ("call_expression", "new_expression"):
                    callee = node.child_by_field_name("function") or node.child_by_field_name(
                        "constructor"
                    )
                    target = (
                        callee.child_by_field_name("property")
                        if callee and callee.type == "member_expression"
                        else callee
                    )
                    if target and target.type in ("identifier", "property_identifier"):
                        add(
                            "call",
                            value(target),
                            node.start_point.row + 1,
                            node.end_point.row + 1,
                            owner,
                            expression=value(callee)[:300],
                        )
                    if value(callee) == "require":
                        args = node.child_by_field_name("arguments")
                        if args and args.named_children and args.named_children[0].type == "string":
                            add(
                                "import",
                                value(args.named_children[0])[1:-1],
                                node.start_point.row + 1,
                                owner=owner,
                            )
                if node.type in ("import_statement", "export_statement"):
                    source = node.child_by_field_name("source")
                    if source:
                        add("import", value(source)[1:-1], node.start_point.row + 1, owner=owner)
                if node.type in (
                    "identifier",
                    "property_identifier",
                    "type_identifier",
                    "shorthand_property_identifier",
                ):
                    parent = node.parent
                    declaration_name = (
                        parent
                        and parent.type in declarations
                        and parent.child_by_field_name("name") == node
                    )
                    if not declaration_name:
                        add("reference", value(node), node.start_point.row + 1, owner=owner)
                stack.extend((child, next_owner) for child in reversed(node.named_children))
        except (ImportError, AttributeError, TypeError, ValueError):
            return {
                "facts": [],
                "gaps": [
                    "JS/TS parser unavailable or incompatible; install requirements-navigation.txt in the engine Python environment and reindex"
                ],
                "omitted": 0,
            }
    unique = {json.dumps(fact, sort_keys=True): fact for fact in facts}
    ordered = sorted(unique.values(), key=lambda f: (f["lines"][0], f["kind"], f["name"]))
    return {"facts": ordered[:4000], "gaps": gaps, "omitted": max(0, len(ordered) - 4000)}


class Structure:
    def __init__(self, engine):
        self.engine = engine
        engine.db.execute(
            "CREATE TABLE IF NOT EXISTS structure_files(source TEXT,path TEXT,hash TEXT,revision TEXT,data TEXT, PRIMARY KEY(source,path))"
        )

    def refresh(self, files, index):
        db = self.engine.db
        files = {
            key: file for key, file in files.items() if PurePosixPath(key[1]).suffix in SUPPORTED
        }
        old = {
            (r["source"], r["path"]): r["hash"] for r in db.execute("SELECT * FROM structure_files")
        }
        same = self.engine.metadata().get("structure", {}).get("extractor") == identity()
        changed = 0
        for key in old.keys() - files.keys():
            db.execute("DELETE FROM structure_files WHERE source=? AND path=?", key)
        for key, file in sorted(files.items()):
            if same and old.get(key) == file["hash"]:
                db.execute(
                    "UPDATE structure_files SET revision=? WHERE source=? AND path=?",
                    (file["revision"], *key),
                )
                continue
            changed += 1
            db.execute(
                "INSERT OR REPLACE INTO structure_files VALUES(?,?,?,?,?)",
                (*key, file["hash"], file["revision"], json.dumps(extract(key[1], file["text"]))),
            )
        return dict(
            generation=index["generation"],
            extractor=identity(),
            changed=changed,
            reused=len(files) - changed,
            deleted=len(old.keys() - files.keys()),
        )

    @staticmethod
    def dependencies(row, fact, known):
        name = fact["name"]
        path = row["path"]
        if path.endswith(".py"):
            level = len(name) - len(name.lstrip("."))
            module = name[level:].replace(".", "/")
            if level:
                base = posixpath.dirname(path)
                for _ in range(level - 1):
                    base = posixpath.dirname(base)
                module = posixpath.join(base, module)
            choices = [module + ".py", posixpath.join(module, "__init__.py")]
            if not name.lstrip("."):
                choices += [
                    posixpath.join(module, item["name"]) + ".py"
                    for item in fact.get("imported", [])
                ]
        elif name.startswith("."):
            base = posixpath.normpath(posixpath.join(posixpath.dirname(path), name))
            choices = [base] + [base + suffix for suffix in (".ts", ".tsx", ".js", ".jsx")]
            choices += [base + "/index" + suffix for suffix in (".ts", ".tsx", ".js", ".jsx")]
        else:
            choices = []
        return sorted({choice for choice in choices if (row["source"], choice) in known})

    def query(
        self, mode="definitions", symbol="", source=None, path=None, limit=30, token_budget=4000
    ):
        if mode not in ("definitions", "references", "callers", "dependencies", "impact"):
            raise ValueError("Unknown structural navigation mode")
        if source is not None and (
            not isinstance(source, str) or source not in self.engine.sources
        ):
            raise ValueError("Unknown source")
        if not isinstance(symbol, str) or len(symbol) > 300:
            raise ValueError("symbol must be a string of at most 300 characters")
        if path is not None and (not isinstance(path, str) or not source):
            raise ValueError("path requires a source and must be a string")
        if mode in ("references", "callers") and not symbol:
            raise ValueError("symbol is required for references and callers")
        if mode in ("dependencies", "impact") and not path:
            raise ValueError("source and path are required for dependencies and impact")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be 1..100")
        status = self.engine.status()
        meta = self.engine.metadata()
        generation = meta.get("generation")
        if status["state"] != "ready" or meta.get("structure", {}).get("extractor") != identity():
            return pack(
                self.engine,
                [],
                token_budget,
                state="stale",
                gaps=["Index or crawl with the current parsers before structural navigation"],
            )
        rows = [
            dict(row)
            for row in self.engine.db.execute("SELECT * FROM structure_files ORDER BY source,path")
        ]
        if (
            path
            and not self.engine.db.execute(
                "SELECT 1 FROM files WHERE source=? AND path=?", (source, path)
            ).fetchone()
        ):
            raise ValueError("File is not in this indexed scope")
        known = {(r["source"], r["path"]) for r in rows}
        definitions, facts, errors, omitted = {}, [], 0, 0
        for row in rows:
            data = json.loads(row.pop("data"))
            if source is None or row["source"] == source:
                errors += bool(data["gaps"])
                omitted += data["omitted"]
            for fact in data["facts"]:
                item = dict(row, **fact)
                facts.append(item)
                if fact["kind"] == "definition":
                    definitions.setdefault(fact["name"], []).append(item)
        names = {
            f["name"]
            for f in facts
            if f["kind"] == "definition" and f["source"] == source and f["path"] == path
        }
        items = []
        for fact in facts:
            if source is not None and fact["source"] != source:
                continue
            is_import = fact["kind"] == "import"
            targets = self.dependencies(fact, fact, known) if is_import else []
            if mode == "impact":
                matches = fact["path"] != path and (
                    (is_import and path in targets)
                    or (fact["kind"] in ("call", "reference") and fact["name"] in names)
                )
            elif mode == "dependencies":
                matches = fact["path"] == path and is_import
            else:
                kind = {"definitions": "definition", "references": "reference", "callers": "call"}[
                    mode
                ]
                matches = (
                    fact["kind"] == kind
                    and (not symbol or symbol in (fact["name"], fact.get("qualified_name")))
                    and (path is None or fact["path"] == path)
                )
            if not matches:
                continue
            item = dict(fact)
            if is_import:
                item["target_paths"] = targets
                item["resolution"] = "inferred" if targets else "unresolved"
                item["reason"] = (
                    "Static in-source module path candidates; runtime/bundler resolution is not evaluated"
                )
            elif fact["kind"] != "definition":
                candidates = [
                    d for d in definitions.get(fact["name"], []) if d["source"] == fact["source"]
                ]
                item["target_candidates"] = [
                    {k: d[k] for k in ("source", "path", "lines", "hash")} for d in candidates[:5]
                ]
                item["omitted_targets"] = max(0, len(candidates) - 5)
                item["resolution"] = "inferred" if candidates else "unresolved"
                item["reason"] = (
                    "Identifier-name candidates; aliasing, shadowing and dynamic dispatch are not resolved"
                )
            else:
                item["resolution"] = "declaration"
            items.append(item)
        latest = self.engine.status()
        if latest["state"] != "ready" or latest["index"].get("generation") != generation:
            return pack(
                self.engine,
                [],
                token_budget,
                state="stale",
                gaps=["Sources changed during structural navigation"],
            )
        unsupported = self.engine.db.execute(
            "SELECT path FROM files" if source is None else "SELECT path FROM files WHERE source=?",
            () if source is None else (source,),
        ).fetchall()
        unsupported = sum(PurePosixPath(r["path"]).suffix not in SUPPORTED for r in unsupported)
        gaps = [
            "Syntax facts are extracted; bindings and impact are candidates, not a complete runtime call graph. Search aliases separately."
        ]
        if errors:
            gaps.append(
                "Some files could not be parsed. Install requirements-navigation.txt for JS/TS; use lexical search for parse failures."
            )
        if omitted or unsupported:
            gaps.append(
                "Coverage excludes unsupported files and capped facts; inspect coverage counts and use lexical search."
            )
        return pack(
            self.engine,
            items[:limit],
            token_budget,
            generation=generation,
            state="partial" if errors or omitted else "ready",
            gaps=gaps,
            mode=mode,
            matched_candidates=len(items),
            limit_omitted=max(0, len(items) - limit),
            coverage=dict(
                parse_gap_files=errors, unsupported_files=unsupported, omitted_facts=omitted
            ),
        )
