"""Explicit remote Git sources, kept apart from developers' working trees."""

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


def validate(source):
    remote, ref = source.get("url"), source.get("ref")
    if not isinstance(remote, str) or not remote or any(c in remote for c in "\n\r\0"):
        raise ValueError("remote-git sources require a url")
    parsed = urlparse(remote)
    https = (
        parsed.scheme == "https"
        and parsed.hostname
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    )
    ssh = re.fullmatch(r"git@[A-Za-z0-9.-]+:[A-Za-z0-9_./-]+", remote)
    if not (https or ssh or Path(remote).is_absolute()):
        raise ValueError(
            "Remote URL must be credential-free HTTPS, git@host:path, or an absolute local Git path"
        )
    if not isinstance(ref, str) or not (
        re.fullmatch(r"refs/(?:heads|tags)/[A-Za-z0-9_./-]+", ref)
        or re.fullmatch(r"[a-fA-F0-9]{40,64}", ref)
    ):
        raise ValueError(
            "remote-git ref must be refs/heads/branch, refs/tags/tag, or a full commit SHA"
        )
    if ".." in ref or ref.endswith(("/", ".")):
        raise ValueError("Invalid remote Git ref")
    if "path" in source:
        raise ValueError("remote-git uses an engine-managed path; omit path")


def git(root, *args):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=" + os.devnull,
            "-c",
            "protocol.ext.allow=never",
            "-c",
            "submodule.recurse=false",
            "-C",
            str(root),
            *args,
        ],
        text=True,
        capture_output=True,
        timeout=120,
        env=env,
    )
    if result.returncode:
        raise ValueError("Git operation failed; check remote access/ref locally")
    return result.stdout.strip()


def status(engine):
    row = engine.db.execute("SELECT value FROM meta WHERE key='remote_sources'").fetchone()
    return json.loads(row[0]) if row else {}


def sync(engine):
    reports = status(engine)
    for sid, source in engine.sources.items():
        if source.get("type") != "remote-git":
            continue
        root = Path(source["root"])
        expected = {
            "source": sid,
            "url": source["url"],
            "ref": source["ref"],
            "store": str(engine.store),
        }
        marker = root.parent / (sid + ".managed.json")
        report = {"checked_at": datetime.now(timezone.utc).isoformat(), "ref": source["ref"]}
        try:
            if any(p.is_symlink() for p in (root, root / ".git", marker, *root.parents)):
                raise ValueError("Refusing symlink in managed checkout path")
            if root.exists():
                if not marker.is_file() or json.loads(marker.read_text()) != expected:
                    raise ValueError("Managed checkout ownership marker missing or mismatched")
            else:
                root.mkdir(parents=True, mode=0o700)
                marker.write_text(json.dumps(expected))
                marker.chmod(0o600)
            if not (root / ".git").is_dir():
                if any(root.iterdir()):
                    raise ValueError(
                        "Managed checkout contains unexpected files without Git metadata"
                    )
                git(root, "-c", "init.templateDir=", "init", "--quiet")
            # Resume if a process stopped between init and adding its origin.
            if "origin" not in git(root, "remote").splitlines():
                git(root, "remote", "add", "origin", source["url"])
            if git(root, "status", "--porcelain", "--untracked-files=all"):
                raise ValueError("Managed checkout has local edits; refusing to overwrite them")
            # A local configuration edit cannot silently redirect the crawler.
            if git(root, "remote", "get-url", "origin") != source["url"]:
                raise ValueError("Managed remote URL changed; refusing synchronization")
            git(root, "fetch", "--no-tags", "origin", source["ref"])
            git(root, "checkout", "--quiet", "--detach", "--no-overwrite-ignore", "FETCH_HEAD")
            report.update(state="ready", revision=git(root, "rev-parse", "HEAD"))
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            report.update(
                state="error", error=str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            )
        reports[sid] = report
        with engine.db:
            engine.db.execute(
                "INSERT OR REPLACE INTO meta VALUES('remote_sources',?)", (json.dumps(reports),)
            )
    return reports
