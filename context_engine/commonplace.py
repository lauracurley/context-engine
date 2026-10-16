"""Local Commonplace snapshots and a future team-repository mapping. No Git/network calls."""

import json
import os
import re
import tempfile
from pathlib import Path

from .knowledge import KINDS
from .locking import exclusive
from .policy import within


class Commonplace:
    def __init__(self, engine):
        self.engine = engine
        self.settings = engine.store.with_suffix(".commonplace.json")

    def validate(self, config):
        if not isinstance(config, dict) or set(config) != {"repository", "directory"}:
            raise ValueError("Commonplace needs repository and directory fields")
        repo = config["repository"]
        if (
            not isinstance(repo, str)
            or (repo and not re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+", repo))
            or repo.split("/")[-1] in (".", "..")
        ):
            raise ValueError("Repository must be empty or owner/repository; no credentials or URLs")
        directory = config["directory"]
        if not isinstance(directory, str) or not Path(directory).is_absolute():
            raise ValueError("Commonplace directory must be absolute")
        root = Path(directory)
        if any(p.is_symlink() for p in (root, *root.parents)):
            # Resolve system aliases (e.g. /var) before configuring the directory.
            raise ValueError("Commonplace directory must use a canonical path without symlinks")
        for source in self.engine.sources.values():
            if within(root, [source["root"]]):
                relative = root.relative_to(Path(source["root"]).resolve())
                if not any(part in (".context-engine", ".context-wiki") for part in relative.parts):
                    raise ValueError(
                        "Commonplace must be outside indexed sources or in an excluded projection directory"
                    )
            if within(source["root"], [root]):
                raise ValueError("Commonplace cannot contain source checkouts")
        if self.engine.policy and not within(root, self.engine.policy["storage_roots"]):
            raise ValueError("Commonplace must be inside approved storage roots")
        return config

    def config(self):
        if self.settings.is_symlink():
            raise ValueError("Refusing symlink Commonplace settings")
        if self.settings.exists():
            value = json.loads(self.settings.read_text())
        else:
            value = self.engine.config.get(
                "commonplace",
                {
                    "repository": "",
                    "directory": str(
                        self.engine.store.parent / (self.engine.store.stem + "-commonplace")
                    ),
                },
            )
        return self.validate(value)

    @exclusive
    def configure(self, repository, directory=None):
        value = self.validate(
            {
                "repository": repository,
                "directory": str(Path(directory).resolve())
                if directory
                else self.config()["directory"],
            }
        )
        if self.settings.is_symlink():
            raise ValueError("Refusing symlink Commonplace settings")
        fd, temp = tempfile.mkstemp(dir=self.settings.parent, prefix="commonplace-config-")
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(value, stream, indent=2)
            os.replace(temp, self.settings)
        finally:
            Path(temp).unlink(missing_ok=True)
        return self.status()

    def status(self):
        return dict(
            self.config(),
            mode="local_reviewed_files",
            synchronization="not implemented",
            authority="Reviewed SQLite records remain authoritative; snapshots are not imported automatically",
        )

    @exclusive
    def materialize(self):
        config = self.config()
        root = Path(config["directory"])
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Never change permissions of an existing team repository or overwrite its files.
        snapshot = Path(tempfile.mkdtemp(prefix="commonplace-", dir=root))
        try:
            records = self.engine.knowledge.rows()
            self.write(
                snapshot / "records.json",
                json.dumps({"schema_version": 1, "records": records}, indent=2),
            )
            latest = {r["id"]: r for r in records}
            self.write(
                snapshot / "edit.json",
                json.dumps(
                    {
                        "schema_version": 1,
                        "changes": [
                            {
                                "base": row,
                                "record": {
                                    k: v for k, v in row.items() if k not in ("status", "revision")
                                },
                            }
                            for row in latest.values()
                        ],
                    },
                    indent=2,
                ),
            )
            wiki = snapshot / "wiki"
            wiki.mkdir(mode=0o700)
            for source in self.engine.sources:
                target = wiki / source
                target.mkdir(mode=0o700)
                for kind in KINDS:
                    self.write(
                        target / (kind + ".md"),
                        self.engine.knowledge.wiki(kind, source)["markdown"],
                    )
            self.write(
                snapshot / "README.md",
                "# Commonplace\n\nTeam knowledge, kept locally for this MVP.\n\nRepository mapping: "
                + (config["repository"] or "not configured")
                + "\n\n`records.json` is a snapshot of reviewed records and proposal history; `wiki/` is the human projection. SQLite remains authoritative. Use lookup_knowledge for agents. Edit `edit.json`, preview and explicitly import it as proposals, then review them. `records.json` and `wiki/` remain snapshots. Editing alone does not update approval or agent retrieval. No clone, commit, push, pull or automatic import occurs. This contains company knowledge: keep it in approved company storage, never in usage feedback.\n",
            )
        except BaseException:
            import shutil

            shutil.rmtree(snapshot)
            raise
        return dict(self.status(), snapshot=str(snapshot), records=len(records))

    @exclusive
    def preview(self, file):
        from .core import digest

        path = Path(file)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Choose a regular edit file up to 2 MiB")
        raw = path.read_bytes()
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("Edit file exceeds 2 MiB")

        def unique_fields(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate edit-file field")
                result[key] = value
            return result

        def invalid_constant(_):
            raise ValueError("Non-finite JSON number")

        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=unique_fields, parse_constant=invalid_constant
        )
        if (
            not isinstance(value, dict)
            or set(value) != {"schema_version", "changes"}
            or type(value["schema_version"]) is not int
            or value["schema_version"] != 1
            or not isinstance(value["changes"], list)
            or len(value["changes"]) > 100
        ):
            raise ValueError("Expected version 1 edit file with at most 100 changes")
        latest = {r["id"]: r for r in self.engine.knowledge.rows()}
        changes, conflicts, seen = [], [], set()
        for entry in value["changes"]:
            if not isinstance(entry, dict) or set(entry) != {"base", "record"}:
                raise ValueError("Each change needs base and record")
            record = entry["record"]
            if not isinstance(record, dict) or not isinstance(record.get("id"), str):
                raise ValueError("Record needs a string ID")
            if {"status", "revision"} & set(record):
                raise ValueError("Approval status and revision cannot be imported")
            identity = record["id"]
            if identity in seen:
                raise ValueError("Duplicate edited record ID")
            seen.add(identity)
            old = latest.get(identity)
            base = entry["base"]
            if base != old:
                conflicts.append(identity)
                continue
            body = {k: v for k, v in (old or {}).items() if k not in ("revision", "status")}
            if record != body:
                self.engine.knowledge.validate(record)
                changes.append(
                    {
                        "record": record,
                        "expected_revision": old["revision"] if old else 0,
                        "before": body or None,
                    }
                )
        token = digest(raw + json.dumps(latest, sort_keys=True).encode())
        return {
            "preview_token": token,
            "changes": changes,
            "conflicts": conflicts,
            "status": "conflict" if conflicts else "ready",
            "approval": "proposals only",
        }

    @exclusive
    def import_edits(self, file, preview_token):
        from . import governance

        preview = self.preview(file)
        if preview["conflicts"] or preview["preview_token"] != preview_token:
            raise ValueError("File or knowledge changed; preview and resolve conflicts again")
        prepared = []
        for change in preview["changes"]:
            record = change["record"]
            actor = governance.authorize("propose", record["source"])
            prepared.append((record, change["expected_revision"] + 1, actor))
        # All validation/authorization precedes one atomic transaction. Import never approves.
        with self.engine.db:
            for record, revision, actor in prepared:
                self.engine.db.execute(
                    "INSERT INTO knowledge VALUES(?,?,?,?)",
                    (record["id"], revision, "proposed", json.dumps(record)),
                )
                self.engine.db.execute(
                    "INSERT INTO knowledge_authors VALUES(?,?,?)", (record["id"], revision, actor)
                )
                governance.append(self.engine, "propose", record["id"], revision)
        return {
            "status": "proposed",
            "imported": len(prepared),
            "records": [{"id": r["id"], "revision": rev} for r, rev, _ in prepared],
        }

    @staticmethod
    def write(path, content):
        with path.open("x", encoding="utf-8") as stream:
            path.chmod(0o600)
            stream.write(content + "\n")
