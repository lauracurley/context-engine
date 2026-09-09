"""Embedding boundary: the engine consumes vectors, not company API details."""
from dataclasses import dataclass, asdict
import importlib.metadata
import math
import re
from typing import List, Protocol, Sequence


class EmbeddingError(Exception):
    """Safe provider failure. Do not expose credentials, requests or source text."""


@dataclass(frozen=True)
class EmbeddingIdentity:
    provider: str
    model: str
    revision: str
    dimensions: int
    adapter_version: str = "1"

    def __post_init__(self):
        if type(self.dimensions) is not int or not 1 <= self.dimensions <= 65536:
            raise ValueError("Embedding dimensions must be 1..65536")
        if not all(isinstance(v, str) and v for v in (self.provider, self.model, self.revision, self.adapter_version)):
            raise ValueError("Embedding identity fields must be nonempty strings")

    def to_dict(self):
        return asdict(self)


class EmbeddingProvider(Protocol):
    identity: EmbeddingIdentity

    def embed_documents(self, texts: Sequence[str]) -> List[List[float]]: ...
    def embed_query(self, text: str) -> List[float]: ...


def normalize(vector, dimensions):
    try:
        values = list(vector)
        if len(values) != dimensions or any(isinstance(v, (bool, str, bytes)) for v in values):
            raise ValueError()
        values = [float(v) for v in values]
        norm = math.sqrt(sum(v * v for v in values))
        if not math.isfinite(norm) or norm <= 0:
            raise ValueError()
        return [v / norm for v in values]
    except (TypeError, ValueError, OverflowError):
        raise EmbeddingError("Invalid embedding vector") from None


class SentenceTransformerProvider:
    """Optional local reference adapter. Never downloads models implicitly."""
    def __init__(self, model, revision, dimensions, cache_folder=None):
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("Pin sentence-transformers revision to a 40-character commit SHA")
        try:
            version = importlib.metadata.version("sentence-transformers")
        except importlib.metadata.PackageNotFoundError:
            version = "not-installed"
        self.identity = EmbeddingIdentity("sentence-transformers", model, revision, dimensions, "1/st-" + version)
        self.cache_folder = cache_folder
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.identity.model, revision=self.identity.revision,
                    cache_folder=self.cache_folder, local_files_only=True, trust_remote_code=False, device="cpu")
                if self._model.get_sentence_embedding_dimension() != self.identity.dimensions:
                    self._model = None
                    raise ValueError()
            except Exception:
                raise EmbeddingError("Local embedding model unavailable or incompatible; install dependencies and prefetch the pinned model") from None
        return self._model

    def embed_documents(self, texts):
        try:
            return self._load().encode_document(list(texts), normalize_embeddings=True, show_progress_bar=False).tolist()
        except EmbeddingError:
            raise
        except Exception:
            raise EmbeddingError("Local document embedding failed") from None

    def embed_query(self, text):
        try:
            return self._load().encode_query(text, normalize_embeddings=True, show_progress_bar=False).tolist()
        except EmbeddingError:
            raise
        except Exception:
            raise EmbeddingError("Local query embedding failed") from None


def configured_provider(config):
    if config is None:
        return None
    allowed = {"provider", "model", "revision", "dimensions", "cache_folder"}
    if not isinstance(config, dict) or set(config) - allowed or config.get("provider") != "sentence-transformers":
        raise ValueError("Unsupported embedding configuration; company integrations can inject an EmbeddingProvider")
    try:
        return SentenceTransformerProvider(config["model"], config["revision"], config["dimensions"], config.get("cache_folder"))
    except KeyError:
        raise ValueError("Embedding configuration requires model, revision and dimensions") from None
