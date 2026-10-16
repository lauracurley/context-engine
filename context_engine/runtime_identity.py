"""Client-local backend identity; never included in vendor usage reports."""

import hashlib
import os
from pathlib import Path

from . import __version__

ROOT = Path(__file__).resolve().parent


def source_build(root=ROOT):
    """Path-independent identity of engine Python sources, excluding bytecode."""
    digest = hashlib.sha256()
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for name in dirs + sorted(names):
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError("Backend sources must not contain symlinks")
            if not path.is_file() or path.suffix != ".py":
                continue
            relative = path.relative_to(root).as_posix().encode()
            content = path.read_bytes()
            digest.update(len(relative).to_bytes(8, "big") + relative)
            digest.update(len(content).to_bytes(8, "big") + content)
    return digest.hexdigest()


# Capture once, before the engine serves requests. Do not relabel a running process
# with a hash of replacement files that it has not loaded.
BUILD = source_build()


def identity():
    return {"release": __version__, "build_id": BUILD}


def sources_current():
    try:
        return source_build() == BUILD
    except (OSError, ValueError):
        return False


def require_current():
    if not sources_current():
        raise ValueError(
            "Backend files changed while this process was running. Stop this writer, "
            "restart it with the intended backend, then refresh code."
        )


def health(index):
    loaded = identity()
    writer = index.get("backend")
    current = sources_current()
    state = (
        "restart_required"
        if not current
        else "unindexed"
        if not index
        else "legacy_index"
        if writer is None
        else "different_writer"
        if writer != loaded
        else "current"
    )
    recovery = {
        "restart_required": "Stop this writer and restart with the intended backend; then refresh code.",
        "legacy_index": "Stop older writers in all windows and terminals, then refresh with this backend.",
        "different_writer": "Align all writers to the intended backend, then refresh code. Do not alternate old and new writers.",
        "unindexed": "Refresh code with the intended backend.",
        "current": "No backend mismatch observed. This does not verify another process or an MCP connection.",
    }
    return {"loaded": loaded, "index_writer": writer, "state": state, "recovery": recovery[state]}
