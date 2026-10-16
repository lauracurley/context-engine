"""Incremental vector cache and exact similarity baseline within one engine store."""

import fnmatch
import hashlib
import json

from .embeddings import EmbeddingError, normalize

INPUT_VERSION = "path-symbol-text-v1"


def key(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def chunk(row):
    text = row["path"] + "\n" + (row["symbol"] or "") + "\n" + row["text"]
    return key([INPUT_VERSION, row["source"], row["path"], row["method"], text]), text


def tie_key(row):
    return (
        row["source"],
        row["path"],
        row["line_start"],
        row["line_end"],
        row["method"],
        row["symbol"] or "",
    )


class SemanticIndex:
    def __init__(self, engine, provider):
        self.engine, self.provider = engine, provider
        self.db = engine.db
        self.fingerprint = key([provider.identity.to_dict(), INPUT_VERSION]) if provider else None
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS vectors(provider TEXT, chunk_key TEXT, vector TEXT, PRIMARY KEY(provider,chunk_key))"
        )
        self.db.commit()

    def rows(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM evidence ORDER BY id")]

    def status(self):
        if not self.provider:
            return {"state": "disabled", "configured": False}
        expected = {chunk(r)[0] for r in self.rows()}
        present = {
            r[0]
            for r in self.db.execute(
                "SELECT chunk_key FROM vectors WHERE provider=?", (self.fingerprint,)
            )
        }
        row = self.db.execute("SELECT value FROM meta WHERE key='semantic'").fetchone()
        meta = json.loads(row[0]) if row else {}
        ready = (
            meta.get("provider") == self.fingerprint
            and meta.get("generation") == self.engine.metadata().get("generation")
            and meta.get("state") == "ready"
            and expected <= present
        )
        return {
            "state": "ready"
            if ready
            else "error"
            if meta.get("provider") == self.fingerprint and meta.get("state") == "error"
            else "pending",
            "configured": True,
            "identity": self.provider.identity.to_dict(),
            "chunks": len(expected),
            "embedded_chunks": len(expected & present),
            "last_index": meta,
        }

    def index(self):
        if not self.provider:
            return self.status()
        generation = self.engine.metadata().get("generation")
        chunks = dict(chunk(r) for r in self.rows())
        # Remove deleted source content, even if the provider subsequently fails.
        with self.db:
            for fingerprint, ck in self.db.execute(
                "SELECT provider,chunk_key FROM vectors"
            ).fetchall():
                if ck not in chunks:
                    self.db.execute(
                        "DELETE FROM vectors WHERE provider=? AND chunk_key=?", (fingerprint, ck)
                    )
        cached = set()
        with self.db:
            for ck, encoded in self.db.execute(
                "SELECT chunk_key,vector FROM vectors WHERE provider=?", (self.fingerprint,)
            ).fetchall():
                try:
                    normalize(json.loads(encoded), self.provider.identity.dimensions)
                    cached.add(ck)
                except (EmbeddingError, ValueError, TypeError):
                    self.db.execute(
                        "DELETE FROM vectors WHERE provider=? AND chunk_key=?",
                        (self.fingerprint, ck),
                    )
        missing = sorted(chunks.keys() - cached)
        added = []
        report = {
            "provider": self.fingerprint,
            "generation": generation,
            "state": "ready",
            "embedded": 0,
            "reused": len(chunks.keys() & cached),
        }
        try:
            for start in range(0, len(missing), 32):
                batch = missing[start : start + 32]
                vectors = self.provider.embed_documents([chunks[k] for k in batch])
                if len(vectors) != len(batch):
                    raise EmbeddingError("Provider returned wrong batch size")
                added.extend(
                    (
                        self.fingerprint,
                        k,
                        json.dumps(normalize(v, self.provider.identity.dimensions)),
                    )
                    for k, v in zip(batch, vectors)
                )
            # Do not publish vectors for a snapshot changed during a slow provider call.
            with self.db:
                self.db.execute("BEGIN IMMEDIATE")
                if (
                    self.engine.metadata().get("generation") != generation
                    or self.engine.status()["state"] != "ready"
                ):
                    raise EmbeddingError(
                        "Source snapshot changed during embedding; run index again"
                    )
                self.db.executemany("INSERT OR REPLACE INTO vectors VALUES(?,?,?)", added)
                self.db.execute("DELETE FROM vectors WHERE provider != ?", (self.fingerprint,))
                report["embedded"] = len(added)
                self.db.execute(
                    "INSERT OR REPLACE INTO meta VALUES('semantic',?)", (json.dumps(report),)
                )
        except Exception as exc:
            report["state"] = "error"
            report["error"] = (
                str(exc) if isinstance(exc, EmbeddingError) else "Embedding provider failed"
            )
            with self.db:
                self.db.execute(
                    "INSERT OR REPLACE INTO meta VALUES('semantic',?)", (json.dumps(report),)
                )
        return report

    def candidates(self, query, source=None, path_glob=None, content="all"):
        if self.status()["state"] != "ready":
            raise EmbeddingError(
                "Semantic index is not ready; run index with the configured provider"
            )
        try:
            q = normalize(self.provider.embed_query(query), self.provider.identity.dimensions)
        except EmbeddingError:
            raise
        except Exception:
            raise EmbeddingError("Embedding query provider failed") from None
        ranked = []
        try:
            cache = {
                r[0]: json.loads(r[1])
                for r in self.db.execute(
                    "SELECT chunk_key,vector FROM vectors WHERE provider=?", (self.fingerprint,)
                )
            }
            for row in self.rows():
                from .core import content_kind

                if (
                    (source is not None and row["source"] != source)
                    or (path_glob is not None and not fnmatch.fnmatchcase(row["path"], path_glob))
                    or (content != "all" and content_kind(row["path"]) != content)
                ):
                    continue
                v = normalize(cache[chunk(row)[0]], self.provider.identity.dimensions)
                score = sum(a * b for a, b in zip(q, v))
                ranked.append(dict(row, rank=-score))
        except (ValueError, KeyError, TypeError):
            raise EmbeddingError("Invalid semantic cache; rebuild the index") from None
        return sorted(ranked, key=lambda r: (r["rank"], tie_key(r)))[:250]


def fuse(lexical, semantic):
    rows, scores, signals = {}, {}, {}
    for method, candidates in [("lexical", lexical), ("semantic", semantic)]:
        for rank, row in enumerate(candidates, 1):
            item = dict(row)
            ident = item["id"]
            rows[ident] = item
            scores[ident] = scores.get(ident, 0) + 1 / (60 + rank)
            signals.setdefault(ident, []).append(method)
    return [
        dict(rows[i], rank=-scores[i], retrieval_methods=signals[i])
        for i in sorted(rows, key=lambda i: (-scores[i], tie_key(rows[i])))
    ]
