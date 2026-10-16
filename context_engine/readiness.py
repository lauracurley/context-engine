"""Local deployment checks and selected-index cleanup; never export this as telemetry."""

import importlib.metadata
import os
import platform
import sys

from .locking import writer_lock


def inspect(engine):
    from .kotlin import extract

    parser = not extract("fun readinessProbe() = 1\n")["gaps"]
    checks = {
        "managed_policy": engine.policy is not None,
        "reviewed_platform": platform.system() == "Darwin" and platform.machine() == "arm64",
        "approved_release_python": sys.version_info[:3] == (3, 13, 15),
        "kotlin_parser": parser,
        "private_store": engine.store.stat().st_mode & 0o077 == 0,
        "local_only_features": not engine.embedding_provider
        and not any(s.get("type") == "remote-git" for s in engine.sources.values())
        and not engine.config.get("history"),
    }
    from .governance import policy as review_policy

    review = review_policy()
    checks["review_governance"] = not review or (
        not review["separation_of_duties"]
        and os.getuid() in review["authors"]
        and os.getuid() in review["reviewers"]
        and set(engine.sources) <= set(review["sources"])
    )
    tools = {}
    for name in (
        "pip",
        "setuptools",
        "tree-sitter",
        "tree-sitter-kotlin",
        "tree-sitter-javascript",
        "tree-sitter-typescript",
    ):
        try:
            tools[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            tools[name] = "not installed"
    expected = {
        "tree-sitter": "0.23.2",
        "tree-sitter-kotlin": "1.1.0",
        "tree-sitter-javascript": "0.23.1",
        "tree-sitter-typescript": "0.23.2",
    }
    checks["reviewed_parser_versions"] = all(
        tools[name] == version for name, version in expected.items()
    )
    checks["restricted_policy"] = bool(engine.policy) and not any(
        engine.policy[name] for name in ("allow_history", "allow_remote_git", "allow_embeddings")
    )
    return {
        "state": "checks_passed" if all(checks.values()) else "action_required",
        "checks": checks,
        "platform": platform.system(),
        "packages": tools,
        "client_approval": "External sign-off required; checks are not approval",
        "inventory": inventory(engine),
    }


def inventory(engine):
    paths = []
    for path in sorted(engine.state.rglob("*")):
        if path.is_file() and not path.is_symlink():
            paths.append({"path": str(path), "bytes": path.stat().st_size})
        if len(paths) >= 1000:
            break
    return {
        "selected_store": str(engine.store),
        "state_root": str(engine.state),
        "artifacts": paths,
        "possibly_truncated": len(paths) >= 1000,
        "note": "Local-only inventory includes identifying paths; never attach to usage reports",
    }


def purge(engine):
    # Transactional logical deletion preserves other connections' ability to detect an
    # unindexed generation. No source files or managed checkouts are deleted.
    names = {r[0] for r in engine.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    tables = (
        "search",
        "evidence",
        "files",
        "vectors",
        "architecture_edges",
        "architecture_files",
        "structure_files",
        "history_search",
        "history_activity",
        "history_records",
        "history_runs",
        "meta",
    )
    with writer_lock(engine), engine.db:
        for table in tables:
            if table in names:
                engine.db.execute('DELETE FROM "' + table + '"')
    engine.usage.clear()
    return {
        "state": "unindexed",
        "cleared_store": str(engine.store),
        "note": "Logical index and usage reset only. Stop agents/crawlers first. Old store generations, source checkouts, backups and external client history are not erased.",
    }
