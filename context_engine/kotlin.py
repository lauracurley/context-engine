"""Kotlin syntax evidence; no compiler binding or runtime execution."""

import importlib.metadata
import json


def identity():
    versions = []
    for name in ("tree-sitter", "tree-sitter-kotlin"):
        try:
            versions.append(importlib.metadata.version(name))
        except importlib.metadata.PackageNotFoundError:
            versions.append("missing")
    return "kotlin-v1:" + ":".join(versions)


def extract(text):
    try:
        import tree_sitter_kotlin
        from tree_sitter import Language, Parser

        raw = text.encode("utf-8")
        tree = Parser(Language(tree_sitter_kotlin.language())).parse(raw)
    except (ImportError, AttributeError, TypeError, ValueError):
        return {
            "facts": [],
            "gaps": [
                "Kotlin parser unavailable or incompatible; install requirements-navigation.txt "
                "in the engine Python environment and reindex; text fallback remains available"
            ],
            "omitted": 0,
        }
    if tree.root_node.has_error:
        return {
            "facts": [],
            "gaps": ["Kotlin parse failed or syntax is unsupported by the grammar; text fallback"],
            "omitted": 0,
        }

    facts = []

    def value(node):
        return raw[node.start_byte : node.end_byte].decode("utf-8") if node else ""

    def add(kind, name, node, owner=None, **extra):
        facts.append(
            dict(
                kind=kind,
                name=name[:300],
                lines=[node.start_point.row + 1, node.end_point.row + 1],
                owner=owner,
                classification="extracted",
                **extra,
            )
        )

    declarations = {
        "class_declaration",
        "object_declaration",
        "function_declaration",
        "companion_object",
        "type_alias",
        "property_declaration",
        "class_parameter",
    }
    stack = [(tree.root_node, None)]
    while stack:
        node, owner = stack.pop()
        # Literal contents and comments must never manufacture calls or references.
        # String interpolation is deliberately omitted rather than partially resolved.
        if node.type in {
            "line_comment",
            "multiline_comment",
            "string_literal",
            "character_literal",
        }:
            continue
        next_owner = owner
        name_node = node.child_by_field_name("name")
        if node.type == "type_alias":
            name_node = node.child_by_field_name("type")
        if node.type == "property_declaration":
            variable = next(
                (c for c in node.named_children if c.type == "variable_declaration"), None
            )
            name_node = (
                next((c for c in variable.named_children if c.type == "identifier"), None)
                if variable
                else None
            )
        if node.type == "class_parameter" and any(c.type in ("val", "var") for c in node.children):
            name_node = next((c for c in node.named_children if c.type == "identifier"), None)
        if node.type in declarations and name_node:
            name = value(name_node).strip("`")
            qualified = ".".join(filter(None, [owner, name]))
            add(
                "definition",
                name,
                node,
                owner,
                qualified_name=qualified,
                declaration_kind=node.type,
                method="kotlin-tree-sitter",
            )
            next_owner = qualified
        if node.type in ("package_header", "import"):
            qualified = next(
                (c for c in node.named_children if c.type == "qualified_identifier"), None
            )
            if qualified:
                name = value(qualified)
                if node.type == "import" and any(c.type == "*" for c in node.children):
                    name += ".*"
                alias = next(
                    (value(c) for c in node.named_children if c.type == "identifier"), None
                )
                add(
                    "package" if node.type == "package_header" else "import",
                    name,
                    node,
                    owner,
                    alias=alias,
                )
            continue
        if node.type == "call_expression" and node.named_children:
            callee = node.named_children[0]
            target = callee
            if callee.type == "navigation_expression":
                target = callee.named_children[-1] if callee.named_children else None
            if target and target.type == "identifier":
                add("call", value(target).strip("`"), node, owner, expression=value(callee)[:300])
        if node.type == "identifier":
            parent = node.parent
            is_name = parent and (
                parent.child_by_field_name("name") == node
                or parent.type
                in ("variable_declaration", "parameter", "class_parameter", "type_alias")
            )
            if not is_name:
                add("reference", value(node).strip("`"), node, owner)
        stack.extend((child, next_owner) for child in reversed(node.named_children))
    unique = {json.dumps(f, sort_keys=True): f for f in facts}
    ordered = sorted(unique.values(), key=lambda f: (f["lines"][0], f["kind"], f["name"]))
    return {"facts": ordered[:4000], "gaps": [], "omitted": max(0, len(ordered) - 4000)}
