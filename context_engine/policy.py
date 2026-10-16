"""Deployment allowlists supplied outside repository manifests by the administrator."""

import json
import os
from pathlib import Path


def load():
    value = os.environ.get("CONTEXT_ENGINE_POLICY")
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("Deployment policy must be an absolute regular file")
    if path.stat().st_mode & 0o022:
        raise ValueError("Deployment policy must not be group/world writable")
    data = json.loads(path.read_text())
    allowed = {
        "schema_version",
        "storage_roots",
        "source_roots",
        "allow_history",
        "allow_remote_git",
        "allow_embeddings",
    }
    if (
        not isinstance(data, dict)
        or set(data) != allowed
        or type(data["schema_version"]) is not int
        or data["schema_version"] != 1
    ):
        raise ValueError("Invalid deployment policy")
    for key in ("allow_history", "allow_remote_git", "allow_embeddings"):
        if type(data[key]) is not bool:
            raise ValueError("Policy permissions must be booleans")
    for key in ("storage_roots", "source_roots"):
        if (
            not isinstance(data[key], list)
            or not data[key]
            or any(not isinstance(p, str) or not Path(p).is_absolute() for p in data[key])
        ):
            raise ValueError("Policy roots must be absolute paths")
    return data


def within(path, roots):
    resolved = Path(path).resolve()
    return any(
        resolved == Path(root).resolve() or Path(root).resolve() in resolved.parents
        for root in roots
    )


def enforce(config, state, injected_provider=None):
    policy = load()
    if policy is None:
        return None
    if not within(state, policy["storage_roots"]):
        raise ValueError("State is outside approved storage roots")
    if (config.get("embeddings") or injected_provider) and not policy["allow_embeddings"]:
        raise ValueError("Embedding providers are disabled by deployment policy")
    if (
        any(s.get("type") == "remote-git" for s in config["sources"])
        and not policy["allow_remote_git"]
    ):
        raise ValueError("Managed remote repositories are disabled by deployment policy")
    if config.get("history") and not policy["allow_history"]:
        raise ValueError("History configuration is disabled by deployment policy")
    return policy
