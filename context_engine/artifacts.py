"""Bounded, client-store-local chunk reuse across content/branch changes."""

import json
import time

from .core import digest

# Bump when builtin chunk semantics change, independently of index schema.
ARTIFACT_VERSION = 1
MAX_BYTES = 16 * 1024 * 1024


class Artifacts:
    def __init__(self, engine):
        self.engine = engine
        self.hits = self.misses = 0
        engine.db.execute(
            "CREATE TABLE IF NOT EXISTS chunk_artifacts "
            "(key TEXT PRIMARY KEY, body TEXT, touched REAL)"
        )

    def units(self, source, path, item):
        identity = [ARTIFACT_VERSION, source, path, item["hash"], self.engine.chunker.identity]
        key = digest(json.dumps(identity, sort_keys=True).encode())
        row = self.engine.db.execute(
            "SELECT body FROM chunk_artifacts WHERE key=?", (key,)
        ).fetchone()
        if row:
            self.hits += 1
            self.engine.db.execute(
                "UPDATE chunk_artifacts SET touched=? WHERE key=?", (time.time(), key)
            )
            return json.loads(row[0])
        self.misses += 1
        value = list(self.engine.chunker.units(path, item["text"]))
        body = json.dumps(value)
        # Failed optional parsers must get another chance rather than cache a transient failure.
        if len(body.encode()) <= MAX_BYTES and not any(v["parser_error"] for v in value):
            self.engine.db.execute(
                "INSERT OR REPLACE INTO chunk_artifacts VALUES(?,?,?)", (key, body, time.time())
            )
        return value

    def prune(self):
        kept = 0
        for key, length, touched in self.engine.db.execute(
            "SELECT key,length(CAST(body AS BLOB)),touched FROM chunk_artifacts "
            "ORDER BY touched DESC,key"
        ).fetchall():
            kept += length
            if kept > MAX_BYTES or touched < time.time() - 30 * 86400:
                self.engine.db.execute("DELETE FROM chunk_artifacts WHERE key=?", (key,))
        return {"hits": self.hits, "computed": self.misses, "max_payload_bytes": MAX_BYTES}
