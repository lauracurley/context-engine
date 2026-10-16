"""Local OS identity, administrator-owned review policy, and company-local audit events."""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def policy():
    value = os.environ.get("CONTEXT_ENGINE_REVIEW_POLICY")
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("Review policy must be an absolute regular file")
    info = path.stat()
    if info.st_uid != 0 or info.st_mode & 0o022:
        raise ValueError("Review policy must be administrator-owned and not group/world writable")
    data = json.loads(path.read_text())
    if (
        not isinstance(data, dict)
        or set(data)
        != {
            "schema_version",
            "authors",
            "reviewers",
            "sources",
            "separation_of_duties",
            "allow_github",
            "github_repositories",
        }
        or type(data["schema_version"]) is not int
        or data["schema_version"] != 1
    ):
        raise ValueError("Invalid review policy schema")
    for key in ("authors", "reviewers"):
        if (
            not isinstance(data[key], list)
            or not data[key]
            or any(type(uid) is not int or uid < 0 for uid in data[key])
        ):
            raise ValueError("Policy identities must be OS user IDs")
    if (
        not isinstance(data["sources"], list)
        or not data["sources"]
        or any(not isinstance(s, str) or not s for s in data["sources"])
    ):
        raise ValueError("Review policy needs source IDs")
    if any(type(data[k]) is not bool for k in ("separation_of_duties", "allow_github")):
        raise ValueError("Invalid review policy permissions")
    repos = data["github_repositories"]
    if not isinstance(repos, dict) or any(
        source not in data["sources"] or not isinstance(repo, str) for source, repo in repos.items()
    ):
        raise ValueError("Invalid GitHub repository allowlist")
    return data


def authorize(action, source, author=None):
    rules = policy()
    actor = os.getuid()
    if rules:
        role = "reviewers" if action in ("approve", "reject", "retire") else "authors"
        if actor not in rules[role] or source not in rules["sources"]:
            raise ValueError("OS identity is not authorized for this source/action")
        if (
            action == "approve"
            and rules["separation_of_duties"]
            and (author is None or actor == author)
        ):
            raise ValueError("An independent reviewer must approve this proposal")
    if action == "github" and (not rules or not rules["allow_github"]):
        raise ValueError("GitHub review ingestion needs explicit administrator approval")
    return actor


def append(engine, action, identity, revision):
    previous = engine.db.execute(
        "SELECT digest FROM knowledge_audit ORDER BY seq DESC LIMIT 1"
    ).fetchone()
    body = json.dumps(
        {
            "action": action,
            "id": identity,
            "revision": revision,
            "actor_uid": os.getuid(),
            "at": datetime.now(timezone.utc).isoformat(),
        },
        sort_keys=True,
    )
    prior = previous[0] if previous else ""
    digest = hashlib.sha256((prior + body).encode()).hexdigest()
    engine.db.execute(
        "INSERT INTO knowledge_audit(body,previous,digest) VALUES(?,?,?)", (body, prior, digest)
    )


def audit(engine):
    rows, previous = [], ""
    for row in engine.db.execute("SELECT * FROM knowledge_audit ORDER BY seq"):
        if (
            row["previous"] != previous
            or hashlib.sha256((previous + row["body"]).encode()).hexdigest() != row["digest"]
        ):
            raise ValueError("Audit chain is inconsistent")
        previous = row["digest"]
        rows.append(dict(json.loads(row["body"]), sequence=row["seq"]))
    return {
        "events": rows,
        "integrity": "chain_consistent",
        "authority": "Local OS process identity. Not proof of a human click or tamper-proof against the store owner.",
    }
