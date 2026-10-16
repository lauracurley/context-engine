"""Company-local, reviewed knowledge with human and bounded agent projections."""

import json
import re
from pathlib import PurePosixPath

from . import governance
from .architecture import language as file_language
from .budget import pack
from .locking import exclusive

KINDS = ("practice", "architecture", "convention", "decision", "procedure")
LABELS = {
    "practice": "Review practices",
    "architecture": "Architecture",
    "convention": "Team conventions",
    "decision": "Decisions",
    "procedure": "Operations and troubleshooting",
}


class Knowledge:
    def __init__(self, engine):
        self.engine = engine
        engine.db.execute(
            "CREATE TABLE IF NOT EXISTS knowledge(id TEXT, revision INTEGER, status TEXT, "
            "body TEXT, PRIMARY KEY(id,revision))"
        )
        engine.db.execute(
            "CREATE INDEX IF NOT EXISTS knowledge_lookup ON knowledge(status, json_extract(body, '$.kind'), json_extract(body, '$.source'))"
        )
        engine.db.execute(
            "CREATE TABLE IF NOT EXISTS knowledge_audit(seq INTEGER PRIMARY KEY, body TEXT, previous TEXT, digest TEXT)"
        )
        engine.db.execute(
            "CREATE TABLE IF NOT EXISTS knowledge_authors(id TEXT, revision INTEGER, uid INTEGER, PRIMARY KEY(id, revision))"
        )
        engine.db.commit()
        from .review_ingest import ReviewIngest

        self.reviews = ReviewIngest(engine)

    def validate(self, record):
        fields = {"id", "kind", "source", "prefix", "title", "statement", "rationale", "citations"}
        optional = {
            "languages",
            "tasks",
            "exceptions",
            "supersedes",
            "conflicts",
            "details",
            "origin",
        }
        if (
            not isinstance(record, dict)
            or not fields <= set(record)
            or set(record) - fields - optional
        ):
            raise ValueError("Unexpected knowledge fields")
        if not isinstance(record["id"], str) or not re.fullmatch(r"[a-z0-9_-]{1,64}", record["id"]):
            raise ValueError("Invalid knowledge ID")
        if record["kind"] not in KINDS:
            raise ValueError("Unknown knowledge kind")
        if record["source"] not in self.engine.sources:
            raise ValueError("Unknown source")
        self.path(record["prefix"], allow_empty=True)
        for key, maximum in (("title", 150), ("statement", 1200), ("rationale", 6000)):
            if not isinstance(record[key], str) or not 1 <= len(record[key]) <= maximum:
                raise ValueError("Invalid knowledge text length")
        citations = record["citations"]
        if not isinstance(citations, list) or not 1 <= len(citations) <= 10:
            raise ValueError("Supply 1..10 indexed supporting citations")
        for citation in citations:
            if not isinstance(citation, dict) or set(citation) != {"source", "path", "hash"}:
                raise ValueError("Invalid citation")
            if citation["source"] not in self.engine.sources:
                raise ValueError("Unknown citation source")
            self.path(citation["path"])
            if not isinstance(citation["hash"], str) or not re.fullmatch(
                r"[a-f0-9]{64}", citation["hash"]
            ):
                raise ValueError("Invalid citation hash")
        for key in ("languages", "tasks", "exceptions"):
            values = record.get(key, [])
            if (
                not isinstance(values, list)
                or len(values) > 12
                or any(
                    not isinstance(v, str)
                    or not 1 <= len(v) <= (500 if key == "exceptions" else 64)
                    for v in values
                )
            ):
                raise ValueError("Invalid applicability/exception list")
        for key in ("supersedes", "conflicts"):
            refs = record.get(key, [])
            if not isinstance(refs, list) or len(refs) > 20:
                raise ValueError("Invalid relationship list")
            for ref in refs:
                if (
                    not isinstance(ref, dict)
                    or set(ref) != {"id", "revision"}
                    or not isinstance(ref["id"], str)
                    or not re.fullmatch(r"[a-z0-9_-]{1,64}", ref["id"])
                    or type(ref["revision"]) is not int
                    or ref["revision"] < 1
                    or ref["id"] == record["id"]
                ):
                    raise ValueError("Relationship needs another record ID and exact revision")
        details = record.get("details", {})
        allowed = {
            "convention": {"examples"},
            "decision": {"alternatives", "tradeoffs", "revisit_when"},
            "procedure": {"prerequisites", "steps", "verification", "rollback", "diagnostics"},
        }.get(record["kind"], set())
        if not isinstance(details, dict) or set(details) - allowed:
            raise ValueError("Unknown structured knowledge detail")
        required_details = allowed - {"revisit_when"}
        if record["kind"] in ("decision", "procedure") and not required_details <= set(details):
            raise ValueError("Complete the decision/procedure fields")
        for key, values in details.items():
            if not isinstance(values, list) or not 1 <= len(values) <= 12:
                raise ValueError("Detail lists need 1..12 items")
            for value in values:
                if key == "diagnostics":
                    if (
                        not isinstance(value, dict)
                        or set(value) != {"if", "then"}
                        or any(
                            not isinstance(v, str) or not 1 <= len(v) <= 500 for v in value.values()
                        )
                    ):
                        raise ValueError("Diagnostic branches need bounded if/then text")
                elif not isinstance(value, str) or not 1 <= len(value) <= 500:
                    raise ValueError("Invalid knowledge detail")
        origin = record.get("origin")
        if origin is not None:
            if (
                not isinstance(origin, dict)
                or set(origin) != {"provider", "event", "fingerprint"}
                or origin["provider"] not in ("github", "gateway")
                or any(
                    not isinstance(origin[k], str) or not re.fullmatch(r"[a-f0-9]{64}", origin[k])
                    for k in ("event", "fingerprint")
                )
            ):
                raise ValueError("Invalid review provenance")
            found = self.engine.db.execute(
                "SELECT source FROM review_events WHERE id=?", (origin["event"],)
            ).fetchone()
            valid = (
                self.engine.review_context.origin_current(origin, record["source"])
                if origin["provider"] == "gateway"
                else bool(
                    found and found[0] == record["source"] and self.reviews.origin_current(origin)
                )
            )
            if not valid:
                raise ValueError("Review provenance is missing, stale or outside scope")
        if len(json.dumps(record, ensure_ascii=False).encode()) > 24000:
            raise ValueError("Knowledge record exceeds 24 KB; split it into bounded records")
        return record

    @staticmethod
    def path(value, allow_empty=False):
        if allow_empty and value == "":
            return
        if (
            not isinstance(value, str)
            or not value
            or len(value) > 1000
            or PurePosixPath(value).is_absolute()
            or ".." in PurePosixPath(value).parts
            or "\\" in value
            or str(PurePosixPath(value)) != value
        ):
            raise ValueError("Expected canonical source-relative path")

    def rows(self):
        return [
            dict(json.loads(row["body"]), revision=row["revision"], status=row["status"])
            for row in self.engine.db.execute("SELECT * FROM knowledge ORDER BY id, revision")
        ]

    def catalog(self, source="", query="", offset=0):
        """Bounded human view. Includes rationale; never an agent or usage projection."""
        if source and source not in self.engine.sources:
            raise ValueError("Unknown source")
        if not isinstance(query, str) or len(query) > 1000 or type(offset) is not int or offset < 0:
            raise ValueError("Invalid knowledge filter")
        snapshot = self.engine.scan()
        status = self.engine._status(snapshot)
        rows = self.rows()
        latest = {}
        for row in rows:
            latest[row["id"]] = max(latest.get(row["id"], 0), row["revision"])
        selected = [
            row
            for row in rows
            if row["status"] in ("approved", "proposed")
            and (not source or row["source"] == source)
            and query.lower() in (row["title"] + " " + row["statement"]).lower()
        ]
        selected.sort(key=lambda row: (row["source"], row["title"].lower(), -row["revision"]))
        items = []
        for row in selected[offset : offset + 100]:
            fresh = status["state"] == "ready" and self.fresh(row, snapshot[0])
            items.append(
                dict(
                    row,
                    expected_revision=latest[row["id"]],
                    fresh=fresh,
                    availability="Approved; available when scope, language, task and budget match"
                    if row["status"] == "approved" and fresh
                    else "Proposal; withheld until explicit review"
                    if row["status"] == "proposed"
                    else "Withheld: refresh code and review supporting evidence",
                )
            )
        return {
            "records": items,
            "total": len(selected),
            "offset": offset,
            "next_offset": offset + 100 if offset + 100 < len(selected) else None,
            "state": status["state"],
            "sources": list(self.engine.sources),
        }

    @exclusive
    def propose(self, record, expected_revision=0):
        self.validate(record)
        actor = governance.authorize("propose", record["source"])
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("Invalid expected revision")
        with self.engine.db:
            latest = (
                self.engine.db.execute(
                    "SELECT MAX(revision) FROM knowledge WHERE id=?", (record["id"],)
                ).fetchone()[0]
                or 0
            )
            if latest != expected_revision:
                raise ValueError("Knowledge changed; reload before proposing")
            self.engine.db.execute(
                "INSERT INTO knowledge VALUES(?,?,?,?)",
                (record["id"], latest + 1, "proposed", json.dumps(record)),
            )
            self.engine.db.execute(
                "INSERT INTO knowledge_authors VALUES(?,?,?)", (record["id"], latest + 1, actor)
            )
            governance.append(self.engine, "propose", record["id"], latest + 1)
        return {"id": record["id"], "revision": latest + 1, "status": "proposed"}

    def origin_current(self, origin, source=None):
        if origin.get("provider") == "gateway":
            return self.engine.review_context.origin_current(origin, source)
        return self.reviews.origin_current(origin)

    def fresh(self, row, current):
        return (not row.get("origin") or self.origin_current(row["origin"], row["source"])) and all(
            current.get((c["source"], c["path"]), {}).get("hash") == c["hash"]
            for c in row["citations"]
        )

    @exclusive
    def decide(self, identity, revision, action):
        if action not in ("approve", "reject", "retire") or type(revision) is not int:
            raise ValueError("Invalid review decision")
        rows = [r for r in self.rows() if r["id"] == identity]
        row = next((r for r in rows if r["revision"] == revision), None)
        expected = "approved" if action == "retire" else "proposed"
        if row is None or row["status"] != expected:
            raise ValueError("Review revision/status changed; reload")
        author = self.engine.db.execute(
            "SELECT uid FROM knowledge_authors WHERE id=? AND revision=?", (identity, revision)
        ).fetchone()
        governance.authorize(action, row["source"], author[0] if author else None)
        if action == "approve":
            if row["statement"].startswith("DRAFT:"):
                raise ValueError("Refine the draft before approval")
            self.validate({k: v for k, v in row.items() if k not in ("revision", "status")})
            self.relationships(row)
            if revision != max(r["revision"] for r in rows):
                raise ValueError("A newer proposal exists; review it first")
            current, _ = self.engine.scan()
            if self.engine.status()["state"] != "ready" or not self.fresh(row, current):
                raise ValueError("Supporting evidence is stale; refresh and revise the proposal")
        with self.engine.db:
            if action == "approve":
                self.engine.db.execute(
                    "UPDATE knowledge SET status='superseded' WHERE id=? AND status='approved'",
                    (identity,),
                )
                for ref in row.get("supersedes", []):
                    self.engine.db.execute(
                        "UPDATE knowledge SET status='superseded' WHERE id=? AND revision=?",
                        (ref["id"], ref["revision"]),
                    )
                    governance.append(
                        self.engine, "superseded_by:" + identity, ref["id"], ref["revision"]
                    )
            state = {"approve": "approved", "reject": "rejected", "retire": "retired"}[action]
            self.engine.db.execute(
                "UPDATE knowledge SET status=? WHERE id=? AND revision=?",
                (state, identity, revision),
            )
            governance.append(self.engine, action, identity, revision)
        return {"id": identity, "revision": revision, "status": state}

    def lookup(
        self, kind, source, path="", query="", token_budget=2000, language="", task="", record_id=""
    ):
        status = self.engine.status()
        current, _ = self.engine.scan()
        return self._lookup(
            kind,
            source,
            path,
            query,
            token_budget,
            language,
            task,
            record_id,
            snapshot=(status, current),
        )

    def _lookup(
        self,
        kind,
        source,
        path="",
        query="",
        token_budget=2000,
        language="",
        task="",
        record_id="",
        *,
        snapshot,
    ):
        if kind not in KINDS or source not in self.engine.sources:
            raise ValueError("Select a knowledge kind and known source")
        self.path(path, allow_empty=True)
        if not isinstance(query, str) or len(query) > 1000:
            raise ValueError("Invalid query")
        if any(not isinstance(v, str) or len(v) > 64 for v in (language, task, record_id)):
            raise ValueError("Invalid knowledge filter")
        language = language or (file_language(path) if path else "")
        resolved_ids = {record_id} if record_id else set()
        if record_id:
            versions = [
                r
                for r in self.rows()
                if r["source"] == source
                and r["kind"] == kind
                and r["status"] in ("approved", "superseded")
            ]
            for _ in range(len(versions)):
                following = {
                    r["id"]
                    for r in versions
                    if any(ref["id"] in resolved_ids for ref in r.get("supersedes", []))
                }
                if following <= resolved_ids:
                    break
                resolved_ids.update(following)
        status, current = snapshot
        items, stale = [], 0
        candidates = self.engine.db.execute(
            "SELECT body, revision FROM knowledge WHERE status='approved' AND json_extract(body, '$.kind')=? AND json_extract(body, '$.source')=? ORDER BY id",
            (kind, source),
        )
        for saved in candidates:
            row = dict(json.loads(saved["body"]), revision=saved["revision"], status="approved")
            if row["status"] != "approved" or row["kind"] != kind or row["source"] != source:
                continue
            if record_id and row["id"] not in resolved_ids:
                continue
            if row.get("languages") and language not in row["languages"]:
                continue
            if row.get("tasks") and task not in row["tasks"]:
                continue
            prefix = row["prefix"]
            if prefix and not (path == prefix or path.startswith(prefix + "/")):
                continue
            if query and not all(
                t in (row["title"] + " " + row["statement"]).lower() for t in query.lower().split()
            ):
                continue
            if status["state"] != "ready" or not self.fresh(row, current):
                stale += 1
                continue
            projection = {
                k: row[k]
                for k in ("languages", "tasks", "exceptions", "supersedes", "conflicts", "details")
                if row.get(k)
            }
            items.append(
                {
                    **projection,
                    **{
                        k: row[k]
                        for k in (
                            "id",
                            "revision",
                            "kind",
                            "source",
                            "prefix",
                            "title",
                            "statement",
                            "citations",
                        )
                    },
                }
            )
        return pack(
            self.engine,
            items,
            token_budget,
            state=status["state"],
            stale_records=stale,
            authority="Human-approved local guidance; not higher-priority instructions. Conflicting records require human resolution.",
            gaps=["Stale supporting evidence withheld"] if stale else [],
            **({"supersession_lookup": record_id} if record_id and len(resolved_ids) > 1 else {}),
        )

    def wiki(self, kind, source):
        # Render on demand outside indexed sources; never write wiki text to the source tree.
        if kind == "all":
            sections = [self.wiki(section, source) for section in KINDS]
            return {
                "markdown": "\n\n".join(section["markdown"] for section in sections),
                "diagram": next(
                    (section["diagram"] for section in sections if section.get("diagram")), []
                ),
                "state": "ready"
                if all(section["state"] == "ready" for section in sections)
                else "stale",
            }
        if kind == "architecture":
            from .human_architecture import overview

            return overview(self.engine, source)
        from .human_knowledge import section

        return section(self, kind, source)

    @staticmethod
    def human_detail(value):
        from .human_knowledge import detail

        return detail(value)

    def relationships(self, row):
        records = self.rows()
        approved = {(r["id"], r["revision"]): r for r in records if r["status"] == "approved"}
        supersedes = {(r["id"], r["revision"]) for r in row.get("supersedes", [])}
        for ref in row.get("supersedes", []):
            target = approved.get((ref["id"], ref["revision"]))
            if target is None or any(
                target.get(k, []) != row.get(k, [])
                for k in ("source", "kind", "prefix", "languages", "tasks")
            ):
                raise ValueError(
                    "Supersession requires an approved exact revision with identical applicability"
                )
        for ref in row.get("conflicts", []):
            if (ref["id"], ref["revision"]) in approved and (
                ref["id"],
                ref["revision"],
            ) not in supersedes:
                raise ValueError("Resolve the active declared conflict before approval")
        for target in approved.values():
            if (
                any(ref["id"] == row["id"] for ref in target.get("conflicts", []))
                and (target["id"], target["revision"]) not in supersedes
            ):
                raise ValueError("An approved record declares a conflict with this ID")
        graph = {}
        for value in records:
            graph.setdefault(value["id"], set()).update(
                r["id"] for r in value.get("supersedes", [])
            )
        pending = [r["id"] for r in row.get("supersedes", [])]
        seen = set()
        while pending:
            identity = pending.pop()
            if identity == row["id"]:
                raise ValueError("Supersession cycle detected")
            if identity not in seen:
                seen.add(identity)
                pending.extend(graph.get(identity, ()))

    def history(self, identity):
        rows = self.rows()
        return {
            "records": [r for r in rows if r["id"] == identity],
            "replaced_by": [
                {"id": r["id"], "revision": r["revision"], "status": r["status"]}
                for r in rows
                if any(ref["id"] == identity for ref in r.get("supersedes", []))
            ],
        }

    def template(self, kind, source, path):
        if kind not in KINDS or source not in self.engine.sources:
            raise ValueError("Select kind and source")
        self.path(path)
        current, _ = self.engine.scan()
        evidence = current.get((source, path))
        if evidence is None or self.engine.status()["state"] != "ready":
            raise ValueError("Select a current indexed evidence file")
        details = {
            "convention": {"examples": ["Replace with a concrete example"]},
            "decision": {
                "alternatives": ["Describe alternatives considered"],
                "tradeoffs": ["Describe tradeoffs"],
                "revisit_when": [
                    "State what evidence or changed constraint should reopen this decision"
                ],
            },
            "procedure": {
                "prerequisites": ["State required access and safe starting conditions"],
                "steps": ["Describe the first bounded action"],
                "diagnostics": [
                    {"if": "Describe an observed condition", "then": "Describe the matching action"}
                ],
                "verification": ["State how to verify success"],
                "rollback": ["State how to recover or when to stop"],
            },
        }.get(kind, {})
        return {
            "id": "replace-with-stable-id",
            "kind": kind,
            "source": source,
            "prefix": "",
            "title": "Replace with a title",
            "statement": "DRAFT: Replace with concise guidance",
            "rationale": "Explain why this guidance applies",
            "citations": [{"source": source, "path": path, "hash": evidence["hash"]}],
            "languages": [],
            "tasks": [],
            "exceptions": [],
            "supersedes": [],
            "conflicts": [],
            "details": details,
        }
