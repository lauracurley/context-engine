"""Human-operated, company-local knowledge maintenance. No model or network calls."""

import copy
import json

from . import governance
from .locking import exclusive

OUTCOMES = ("useful", "wrong_scope", "stale", "redundant")


class Maintenance:
    def __init__(self, engine):
        self.engine = engine

    def record(self, identity, revision):
        if type(revision) is not int or revision < 1:
            raise ValueError("Choose an exact knowledge revision")
        row = next(
            (
                r
                for r in self.engine.knowledge.rows()
                if r["id"] == identity and r["revision"] == revision
            ),
            None,
        )
        if row is None:
            raise ValueError("Unknown knowledge revision")
        return row

    @exclusive
    def feedback(self, identity, revision, outcome):
        if outcome not in OUTCOMES:
            raise ValueError("Choose useful, wrong_scope, stale or redundant")
        row = self.record(identity, revision)
        governance.authorize("propose", row["source"])
        with self.engine.db:
            self.engine.db.execute(
                "CREATE TABLE IF NOT EXISTS knowledge_feedback "
                "(id TEXT, revision INTEGER, outcome TEXT, count INTEGER, PRIMARY KEY(id,revision,outcome))"
            )
            self.engine.db.execute(
                "INSERT INTO knowledge_feedback VALUES(?,?,?,1) "
                "ON CONFLICT(id,revision,outcome) DO UPDATE SET count=min(count+1,1000000)",
                (identity, revision, outcome),
            )
        return {
            "id": identity,
            "revision": revision,
            "outcome": outcome,
            "authority": "Local manual observation only; guidance has not changed",
        }

    def queue(self, source):
        if source not in self.engine.sources:
            raise ValueError("Choose a known source")
        current, _ = self.engine.scan()
        all_rows = [
            r
            for r in self.engine.knowledge.rows()
            if r["source"] == source and r["status"] in ("approved", "proposed")
        ]
        feedback = {}
        if self.engine.db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='knowledge_feedback'"
        ).fetchone():
            for identity, revision, outcome, count in self.engine.db.execute(
                "SELECT * FROM knowledge_feedback"
            ):
                feedback.setdefault((identity, revision), {})[outcome] = count
        groups, items = {}, []
        # Group exact guidance including applicability/exception fields, not prose similarity.
        for row in all_rows:
            key = json.dumps(
                {
                    k: row.get(k)
                    for k in (
                        "kind",
                        "source",
                        "prefix",
                        "statement",
                        "languages",
                        "tasks",
                        "exceptions",
                        "details",
                        "conflicts",
                        "supersedes",
                    )
                },
                sort_keys=True,
            )
            groups.setdefault(key, []).append({"id": row["id"], "revision": row["revision"]})
            items.append(
                {
                    "id": row["id"],
                    "revision": row["revision"],
                    "title": row["title"],
                    "status": row["status"],
                    "stale_evidence": not self.engine.knowledge.fresh(row, current),
                    "feedback": feedback.get((row["id"], row["revision"]), {}),
                    "_group": key,
                }
            )
        items.sort(
            key=lambda r: (
                not r["stale_evidence"],
                -sum(v for k, v in r["feedback"].items() if k != "useful"),
                r["id"],
                -r["revision"],
            )
        )
        for row in items[:100]:
            row["exact_guidance_candidates"] = [
                r for r in groups[row.pop("_group")] if r["id"] != row["id"]
            ][:10]
        return {
            "items": items[:100],
            "omitted_records": max(0, len(items) - 100),
            "index_state": self.engine.status()["state"],
            "limits": "Exact guidance matches are review candidates, not semantic equivalence. "
            "Counts are manual observations, not unique people or automatic usage. "
            "No guidance is merged, retired or approved automatically.",
        }

    def refresh_draft(self, identity, revision):
        row = self.record(identity, revision)
        versions = [r for r in self.engine.knowledge.rows() if r["id"] == identity]
        latest = max(r["revision"] for r in versions)
        active = max(
            (r["revision"] for r in versions if r["status"] in ("approved", "proposed")),
            default=0,
        )
        if revision != active or row["status"] not in ("approved", "proposed"):
            raise ValueError("Choose the latest approved or proposed revision")
        if self.engine.status()["state"] != "ready":
            raise ValueError("Refresh the code index first")
        if row.get("origin") and not self.engine.knowledge.origin_current(
            row["origin"], row["source"]
        ):
            raise ValueError(
                "Review origin changed; prepare a new candidate from current review evidence"
            )
        current, _ = self.engine.scan()
        draft = copy.deepcopy({k: v for k, v in row.items() if k not in ("status", "revision")})
        for citation in draft["citations"]:
            item = current.get((citation["source"], citation["path"]))
            if item is None:
                raise ValueError("Supporting file missing; select replacement evidence manually")
            citation["hash"] = item["hash"]
        if not draft["statement"].startswith("DRAFT:"):
            draft["statement"] = "DRAFT: " + draft["statement"]
        self.engine.knowledge.validate(draft)
        return {
            "draft": draft,
            # Rejected revisions remain in history and still count for the
            # optimistic proposal check, even when drafting from older content.
            "expected_revision": latest,
            "review_required": "Updated hashes do not validate the conclusion. Inspect changed evidence, "
            "rationale, applicability and exceptions; refine then save/import the draft only. Nothing was written.",
        }


REASONING_TEMPLATE = """# Working reasoning note

Exploration in company-controlled developer Scratch. Save deliberately; no automatic team promotion.

## Question and constraints

## Alternatives and hypotheses

## Experiments and observed evidence

Separate observations from hypotheses. Link only evidence permitted in this scope.

## Uncertainties and tentative conclusion

## What would change this conclusion?

## Potential reusable conclusion

Optional: prepare a separate knowledge proposal with concise guidance, scope, exceptions,
team-accessible evidence and rationale. Review before approval. Do not copy this whole note
into Commonplace. Do not capture hidden model reasoning or conversation transcripts automatically.
"""
