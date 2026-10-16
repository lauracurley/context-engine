"""Optional AST/token chunking compatible with the referenced code-search demo."""

import importlib.metadata
from pathlib import PurePosixPath

LANGUAGES = {".py": "Python", ".rs": "Rust", ".go": "Golang", ".md": "Markdown"}


class Chunker:
    def __init__(self, config=None):
        config = {} if config is None else config
        if not isinstance(config, dict) or set(config) - {"provider", "max_tokens"}:
            raise ValueError("chunking requires provider and optional max_tokens")
        self.provider = config.get("provider", "builtin")
        self.max_tokens = config.get("max_tokens", 256)
        if self.provider not in ("builtin", "code-splitter"):
            raise ValueError("chunking.provider must be builtin or code-splitter")
        if type(self.max_tokens) is not int or not 32 <= self.max_tokens <= 4096:
            raise ValueError("chunking.max_tokens must be 32..4096")
        self.module = None
        version = "builtin-v1"
        if self.provider == "code-splitter":
            try:
                import code_splitter

                self.module = code_splitter
                version = importlib.metadata.version("code-splitter")
            except (ImportError, importlib.metadata.PackageNotFoundError):
                version = "unavailable"
        self.identity = {
            "provider": self.provider,
            "version": version,
            "max_tokens": self.max_tokens,
            "state": "fallback" if version == "unavailable" else "ready",
        }
        from .kotlin import identity as kotlin_identity

        self.identity["kotlin"] = kotlin_identity()

    def units(self, path, text):
        from .core import units

        lang = LANGUAGES.get(PurePosixPath(path).suffix)
        error = None
        if self.provider == "code-splitter" and lang:
            if self.module is None:
                error = "Optional code-splitter unavailable; using builtin chunks"
            else:
                try:
                    splitter = self.module.TiktokenSplitter(
                        getattr(self.module.Language, lang), max_size=self.max_tokens
                    )
                    chunks = splitter.split(text.encode("utf-8"))
                    lines = text.splitlines()
                    result = []
                    for chunk in chunks:
                        # Bindings use zero-based start/end rows (end can be the trailing empty row).
                        start, end = chunk.start + 1, min(chunk.end + 1, len(lines))
                        if not 1 <= start <= end:
                            continue
                        result.append(
                            {
                                "line_start": start,
                                "line_end": end,
                                "symbol": None,
                                "method": "code-splitter-ast",
                                "text": "\n".join(lines[start - 1 : end]),
                                "parser_error": None,
                            }
                        )
                    if result or not text.strip():
                        yield from result
                        return
                    error = "AST splitter returned no chunks; using builtin chunks"
                except Exception:
                    error = "AST splitter failed; using builtin chunks"
        for unit in units(path, text):
            if error:
                unit["parser_error"] = error
            yield unit
