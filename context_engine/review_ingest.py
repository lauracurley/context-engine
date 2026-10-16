"""Explicit bounded GitHub GETs; comments become local candidates, never approved rules."""

import hashlib
import json
import os
import re
import urllib.error
import urllib.request

from . import governance
from .locking import exclusive


class ReviewIngest:
    def __init__(self, engine):
        self.engine = engine
        engine.db.execute(
            "CREATE TABLE IF NOT EXISTS review_events(id TEXT PRIMARY KEY, source TEXT, fingerprint TEXT, body TEXT)"
        )
        engine.db.commit()

    def repo(self, source):
        item = self.engine.sources.get(source, {})
        repo = item.get("github")
        if not isinstance(repo, str) or not re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+", repo):
            raise ValueError("Set an explicit sources[].github owner/repository for this source")
        if repo.split("/")[1] in (".", ".."):
            raise ValueError("Invalid repository")
        rules = governance.policy()
        if rules and rules.get("github_repositories", {}).get(source) != repo:
            raise ValueError("Repository is not in the administrator review allowlist")
        return repo

    def fetch(self, source, pull):
        governance.authorize("github", source)
        repo = self.repo(source)
        if type(pull) is not int or not 1 <= pull <= 10**9:
            raise ValueError("Invalid pull request number")
        collected = []
        for endpoint in ("reviews", "comments"):
            for page in range(1, 11):
                raw = get_page(f"repos/{repo}/pulls/{pull}/{endpoint}?per_page=100&page={page}")
                values = json.loads(raw)
                if not isinstance(values, list):
                    raise ValueError("Unexpected GitHub response")
                for value in values:
                    if not isinstance(value, dict):
                        raise ValueError("Unexpected GitHub review item")
                    if not value.get("body") or value.get("state") in ("PENDING", "DISMISSED"):
                        continue
                    collected.append(
                        {
                            "event_id": f"{endpoint}-{value['id']}",
                            "pull": pull,
                            "body": value["body"],
                            "path": value.get("path", ""),
                            "author": value.get("user", {}).get("login", "unknown"),
                            "commit": value.get("commit_id", ""),
                            "updated": value.get("updated_at", value.get("submitted_at", "")),
                        }
                    )
                if len(values) < 100:
                    break
            else:
                raise ValueError("Review page limit reached; no partial import was stored")
        return self.ingest(source, collected, reconcile_pull=pull)

    @exclusive
    def ingest(self, source, events, reconcile_pull=None):
        governance.authorize("github", source)
        repo = self.repo(source)
        if not isinstance(events, list) or len(events) > 2000:
            raise ValueError("Invalid event batch")
        prepared = []
        seen = set()
        for event in events:
            if not isinstance(event, dict) or set(event) != {
                "event_id",
                "pull",
                "body",
                "path",
                "author",
                "commit",
                "updated",
            }:
                raise ValueError("Invalid review event fields")
            if not isinstance(event["event_id"], str) or not re.fullmatch(
                r"(reviews|comments)-[1-9][0-9]{0,19}", event["event_id"]
            ):
                raise ValueError("Invalid review event ID")
            if type(event["pull"]) is not int or not 1 <= event["pull"] <= 10**9:
                raise ValueError("Invalid pull request")
            for key, cap in (
                ("body", 12000),
                ("path", 1000),
                ("author", 100),
                ("commit", 100),
                ("updated", 100),
            ):
                if not isinstance(event[key], str) or len(event[key]) > cap:
                    raise ValueError("Review event exceeds field bounds")
            self.engine.knowledge.path(event["path"], allow_empty=True)
            value = dict(event, source=source, repository=repo)
            identity = hashlib.sha256(
                (source + ":" + repo + ":" + event["event_id"]).encode()
            ).hexdigest()
            if identity in seen:
                raise ValueError("Duplicate event in batch")
            seen.add(identity)
            body = json.dumps(value, sort_keys=True)
            prepared.append((identity, source, hashlib.sha256(body.encode()).hexdigest(), body))
        changed = 0
        with self.engine.db:
            if reconcile_pull is not None:
                for existing in self.engine.db.execute(
                    "SELECT id FROM review_events WHERE source=? AND json_extract(body, '$.pull')=?",
                    (source, reconcile_pull),
                ).fetchall():
                    if existing[0] not in seen:
                        self.engine.db.execute(
                            "DELETE FROM review_events WHERE id=?", (existing[0],)
                        )
                        governance.append(self.engine, "github_removed", existing[0], 0)
                        changed += 1
            for identity, sid, fingerprint, body in prepared:
                old = self.engine.db.execute(
                    "SELECT fingerprint FROM review_events WHERE id=?", (identity,)
                ).fetchone()
                if old and old[0] == fingerprint:
                    continue
                self.engine.db.execute(
                    "INSERT OR REPLACE INTO review_events VALUES(?,?,?,?)",
                    (identity, sid, fingerprint, body),
                )
                governance.append(self.engine, "github_import", identity, 0)
                changed += 1
        return {"changed": changed, "received": len(events), "status": "candidates_only"}

    def events(self, source):
        self.repo(source)
        return {
            "events": [
                dict(json.loads(r["body"]), id=r["id"], fingerprint=r["fingerprint"])
                for r in self.engine.db.execute(
                    "SELECT * FROM review_events WHERE source=? ORDER BY id", (source,)
                )
            ]
        }

    def inbox(self, source):
        """Group identical review text/path; counts describe independent PRs, not votes."""
        groups = {}
        for event in self.events(source)["events"]:
            key = (event["path"], " ".join(event["body"].split()))
            group = groups.setdefault(key, {"event": event, "pulls": set(), "events": 0})
            group["pulls"].add(event["pull"])
            group["events"] += 1
        return {
            "groups": [
                {"event": g["event"], "distinct_pulls": len(g["pulls"]), "event_count": g["events"]}
                for g in sorted(groups.values(), key=lambda g: (-len(g["pulls"]), g["event"]["id"]))
            ][:100],
            "omitted_groups": max(0, len(groups) - 100),
            "method": "Exact normalized text and path; repeated PR evidence is not consensus",
        }

    def origin_current(self, origin):
        row = self.engine.db.execute(
            "SELECT fingerprint FROM review_events WHERE id=?", (origin["event"],)
        ).fetchone()
        return bool(row and row[0] == origin["fingerprint"])

    def candidate(self, identity, path):
        row = self.engine.db.execute(
            "SELECT * FROM review_events WHERE id=?", (identity,)
        ).fetchone()
        if row is None:
            raise ValueError("Unknown review event")
        event = json.loads(row["body"])
        path = path or event["path"]
        value = self.engine.knowledge.template("practice", event["source"], path)
        sentences = re.split(r"(?<=[.!?])\s+|\n+", event["body"])
        suggestion = next(
            (
                s.strip()
                for s in sentences
                if re.search(r"\b(should|must|avoid|ensure|prefer|always|never|please)\b", s, re.I)
            ),
            "",
        )
        value.update(
            id="github-" + identity[:24],
            title="Review lesson to refine",
            statement="DRAFT: "
            + (
                suggestion[:1100]
                or "Replace with a general practice after checking the review context."
            ),
            rationale=event["body"][:6000],
            origin={"provider": "github", "event": identity, "fingerprint": row["fingerprint"]},
        )
        value["tasks"] = ["review"]
        # Candidate scope comes from an explicit indexed supporting path, never model inference.
        value["prefix"] = path.rsplit("/", 1)[0] if "/" in path else ""
        value["rationale"] = (
            "Review evidence (untrusted; verify before generalizing):\n" + event["body"]
        )[:6000]
        return value


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("GitHub redirects are refused; verify the configured repository")


def get_page(endpoint):
    token = os.environ.get("CONTEXT_ENGINE_GITHUB_TOKEN")
    if not token or not re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", token):
        raise ValueError("Supply an approved GitHub token for this request")
    request = urllib.request.Request(
        "https://api.github.com/" + endpoint,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "context-engine-review-import",
        },
        method="GET",
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
            payload = response.read(8 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as exc:
        raise ValueError(
            "GitHub request failed with HTTP "
            + str(exc.code)
            + "; check access/rate limits locally"
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ValueError(
            "GitHub network/TLS request failed; check approved local connectivity"
        ) from None
    if len(payload) > 8 * 1024 * 1024:
        raise ValueError("GitHub response exceeds import ceiling")
    return payload.decode("utf-8")
