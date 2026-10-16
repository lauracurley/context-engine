"""Read-only history collectors. Gateway adapters exchange normalized JSON."""

import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlencode


class CollectionError(ValueError):
    pass


def whole_checkout(source):
    try:
        top = command(["git", "rev-parse", "--show-toplevel"], cwd=source["root"]).strip()
        return Path(top).resolve() == Path(source["root"]).resolve()
    except CollectionError:
        return False


def command(argv, cwd=None, payload=None):
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            input=payload,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CollectionError(type(exc).__name__) from exc
    if result.returncode:
        # stderr can contain credentials or private gateway diagnostics.
        raise CollectionError("command failed (exit %s); check access locally" % result.returncode)
    return result.stdout


def repository(source):
    explicit = source.get("github")
    if explicit is not None:
        if (
            not isinstance(explicit, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+", explicit)
            or explicit.split("/")[-1] in (".", "..")
        ):
            raise ValueError("sources[].github must be owner/repository")
        return explicit
    try:
        root = Path(source["root"])
        top = command(["git", "rev-parse", "--show-toplevel"], cwd=root).strip()
        # Never expand a selected subdirectory into a whole remote repository.
        if Path(top).resolve() != root:
            return None
        remote = command(["git", "remote", "get-url", "origin"], cwd=root).strip()
        match = re.fullmatch(
            r"(?:https://github\.com/|git@github\.com:)([\w.-]+/[\w.-]+?)(?:\.git)?/?", remote
        )
        return match.group(1) if match else None
    except CollectionError:
        return None


def local_git(source, since, until, cap=10000):
    records, gaps = [], []
    root = source["root"]
    try:
        shallow = command(["git", "rev-parse", "--is-shallow-repository"], cwd=root).strip()
        if shallow == "true":
            gaps.append("Shallow checkout: older commits may be unavailable")
        raw = command(
            [
                "git",
                "log",
                "--all",
                "--since=" + since,
                "--until=" + until,
                "--max-count=" + str(cap + 1),
                "-z",
                "--format=%H%x00%cI%x00%an%x00%ae%x00%B",
                "--",
                ".",
            ],
            cwd=root,
        )
        fields = raw.split("\0")
        for i in range(0, len(fields) - 4, 5):
            sha, timestamp, author, email, body = fields[i : i + 5]
            if len(records) >= cap:
                gaps.append("Local commit limit reached")
                break
            files = []
            try:
                paths = command(
                    [
                        "git",
                        "diff-tree",
                        "--root",
                        "--no-commit-id",
                        "--name-only",
                        "--relative",
                        "-r",
                        "-z",
                        sha,
                        "--",
                        ".",
                    ],
                    cwd=root,
                )
                files = [p for p in paths.split("\0") if p]
            except CollectionError as exc:
                gaps.append("Commit file list unavailable: " + str(exc))
            records.append(
                {
                    "kind": "commit",
                    "id": sha,
                    "occurred_at": timestamp,
                    "title": body.splitlines()[0] if body.splitlines() else sha,
                    "body": body,
                    "author": "git:" + author + " <" + email + ">",
                    "files": files,
                    "reviewers": [],
                    "url": "",
                }
            )
        gaps.append(
            "Local Git covers locally reachable refs only; no fetch was performed. Merge file lists may be empty"
        )
    except CollectionError as exc:
        gaps.append("Local Git unavailable: " + str(exc))
    return records, gaps


class GitHub:
    """Use the user's gh authentication; never store tokens or raw API responses."""

    def __init__(self, repo, max_pages=100):
        self.repo, self.max_pages = repo, max_pages

    def api(self, endpoint, params=None):
        path = "repos/" + self.repo + "/" + endpoint
        if params:
            path += "?" + urlencode(params)
        try:
            return json.loads(
                command(["gh", "api", "--method", "GET", "--hostname", "github.com", path])
            )
        except json.JSONDecodeError as exc:
            raise CollectionError("GitHub returned invalid JSON") from exc

    def pages(self, endpoint, params=None):
        for page in range(1, self.max_pages + 1):
            rows = self.api(endpoint, dict(params or {}, page=page, per_page=100))
            if not isinstance(rows, list):
                raise CollectionError("GitHub returned an unexpected response")
            yield rows
            if len(rows) < 100:
                return
        raise CollectionError("Pagination limit reached for " + endpoint)

    def collect(self, since, until, local_records=()):
        records, gaps = [], []
        local_files = {r["id"]: r["files"] for r in local_records}
        # Endpoint failures are independent: PR denial does not discard commits.
        try:
            for page in self.pages("commits", {"since": since, "until": until}):
                for row in page:
                    sha, commit = row["sha"], row["commit"]
                    files = local_files.get(sha)
                    if files is None:
                        files = []
                        try:
                            # GitHub caps commit files at 3000, even with pagination.
                            for number in range(1, self.max_pages + 1):
                                detail = self.api(
                                    "commits/" + sha, {"per_page": 100, "page": number}
                                )
                                batch = detail.get("files", [])
                                files.extend(f["filename"] for f in batch)
                                if len(batch) < 100:
                                    break
                                if len(files) >= 3000 or number == self.max_pages:
                                    gaps.append("Commit file list may be truncated: " + sha)
                                    break
                        except CollectionError as exc:
                            gaps.append("Commit files unavailable for " + sha + ": " + str(exc))
                    author = row.get("author") or {}
                    identity = (
                        "github:" + author["login"]
                        if author.get("login")
                        else "git:"
                        + commit["author"]["name"]
                        + " <"
                        + commit["author"]["email"]
                        + ">"
                    )
                    body = commit.get("message", "")
                    records.append(
                        {
                            "kind": "commit",
                            "id": sha,
                            "occurred_at": commit["committer"]["date"],
                            "title": body.splitlines()[0] if body else sha,
                            "body": body,
                            "author": identity,
                            "files": files,
                            "reviewers": [],
                            "url": row.get("html_url", ""),
                        }
                    )
        except (CollectionError, KeyError, TypeError) as exc:
            gaps.append(
                "GitHub commits incomplete: "
                + (str(exc) if isinstance(exc, CollectionError) else "invalid response")
            )
        try:
            done = False
            for page in self.pages(
                "pulls", {"state": "all", "sort": "updated", "direction": "desc"}
            ):
                for row in page:
                    if row["updated_at"] < since:
                        done = True
                        break
                    if row["updated_at"] > until:
                        continue
                    number = str(row["number"])
                    files, reviewers = [], []
                    for endpoint, target, key in (
                        ("files", files, "filename"),
                        ("reviews", reviewers, "user"),
                    ):
                        try:
                            for batch in self.pages("pulls/" + number + "/" + endpoint):
                                for item in batch:
                                    if key == "filename":
                                        target.append(item[key])
                                    elif item.get("submitted_at") and item.get("user"):
                                        target.append("github:" + item["user"]["login"])
                            if endpoint == "files" and len(files) >= 3000:
                                gaps.append("PR file list may be truncated: " + number)
                        except (CollectionError, KeyError, TypeError) as exc:
                            gaps.append(
                                "PR "
                                + number
                                + " "
                                + endpoint
                                + " incomplete: "
                                + (
                                    str(exc)
                                    if isinstance(exc, CollectionError)
                                    else "invalid response"
                                )
                            )
                    records.append(
                        {
                            "kind": "pr",
                            "id": number,
                            "occurred_at": row["updated_at"],
                            "title": row["title"],
                            "body": row.get("body") or "",
                            "author": "github:" + row["user"]["login"] if row.get("user") else "",
                            "files": files,
                            "reviewers": sorted(set(reviewers)),
                            "url": row.get("html_url", ""),
                        }
                    )
                if done:
                    break
        except (CollectionError, KeyError, TypeError) as exc:
            gaps.append(
                "GitHub PRs incomplete: "
                + (str(exc) if isinstance(exc, CollectionError) else "invalid response")
            )
        gaps.append(
            "GitHub commits cover the default branch; PRs use current updated_at, not an as-of snapshot. Review text and discussion comments are not collected"
        )
        return records, gaps


def gateway(argv, request):
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
        raise ValueError("history.gateway_command must be a nonempty argv list")
    try:
        return json.loads(command(argv, payload=json.dumps(request)))
    except json.JSONDecodeError as exc:
        raise CollectionError("Gateway returned invalid JSON") from exc
