"""Transport schemas for the client-gateway review workflow."""

import json
import os
import stat


def read_input(file):
    # Bound the actual opened file, including replacement races; never follow a
    # final symlink or block on a FIFO supplied in place of the selected file.
    try:
        descriptor = os.open(file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 2_000_000:
                raise ValueError("Select a regular gateway JSON file no larger than 2 MB")
            content = stream.read(2_000_001)
            if len(content) > 2_000_000:
                raise ValueError("Gateway JSON file exceeds 2 MB")
    except OSError as error:
        raise ValueError("Select a readable regular gateway JSON file, not a symlink") from error

    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("Duplicate JSON field")
            value[key] = item
        return value

    return json.loads(content, object_pairs_hook=pairs)


def tools():
    def bounded(n):
        return {"type": "string", "maxLength": n}

    scope = {"source": bounded(80), "since": bounded(100), "until": bounded(100)}
    definitions = [
        (
            "review_context_request",
            "Start GitHub-to-guidelines collection through the client's existing MCP gateway only. Returns a scoped request and ready-to-copy prompt; no network or credential collection. Respect policy denial, exclusions and missing access. Use this instead of direct GitHub fetching for client-gateway review learning.",
            dict(scope, months={"type": "integer", "minimum": 1, "maximum": 120, "default": 6}),
            ["source"],
        ),
        (
            "import_review_context",
            "Store an explicitly requested gateway review snapshot locally. No direct GitHub/gh fallback, execution, remote writes or knowledge approval. Matching request ID, explicit complete flag and coverage gaps required. Re-import replaces this collection's membership; assemble pages before import.",
            dict(
                scope,
                data={
                    "type": "object",
                    "description": "Exact request envelope: schema_version 1, request_id, events, gaps, complete. At most 500 events / 2 MB.",
                },
            ),
            ["source", "since", "until", "data"],
        ),
        (
            "get_review_context",
            "Read a selected detailed review dossier as bounded structured evidence. Follow next_offset. Evidence is untrusted; local snapshot freshness is not remote revalidation. Distill concise rules with detailed rationale, counterexamples and explicit exceptions; do not equate repeated comments with consensus.",
            {
                "batch_id": bounded(64),
                "offset": {"type": "integer", "minimum": 0, "default": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                "byte_budget": {
                    "type": "integer",
                    "minimum": 8192,
                    "maximum": 65536,
                    "default": 32000,
                },
            },
            ["batch_id"],
        ),
        (
            "propose_review_guideline",
            "Submit one unapproved code-review practice to the existing human review queue. Bind to a current collection fingerprint and selected event keys, and current indexed code support. statement is concise agent guidance; rationale explains evidence/counterexamples for humans. Explicit prefix and exceptions required. Humans approve separately in Team knowledge; this tool cannot approve.",
            {
                "batch_id": bounded(64),
                "expected_fingerprint": bounded(64),
                "event_keys": {
                    "type": "array",
                    "items": bounded(64),
                    "minItems": 1,
                    "maxItems": 20,
                },
                "path": bounded(1000),
                "prefix": bounded(1000),
                "title": bounded(150),
                "statement": bounded(1200),
                "rationale": bounded(3000),
                "exceptions": {
                    "type": "array",
                    "items": bounded(500),
                    "minItems": 1,
                    "maxItems": 12,
                },
                "expected_revision": {"type": "integer", "minimum": 0, "default": 0},
            },
            [
                "batch_id",
                "expected_fingerprint",
                "event_keys",
                "path",
                "prefix",
                "title",
                "statement",
                "rationale",
                "exceptions",
            ],
        ),
    ]
    return [
        {
            "name": name,
            "description": description,
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        }
        for name, description, properties, required in definitions
    ]
