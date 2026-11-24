"""Embedding providers behind one small interface.

Production default: Hugging Face Sentence Transformers (all-MiniLM-L6-v2), run locally.
The hashing embedder is a dependency-free, deterministic fallback meant for offline CI and unit tests only;
retrieval quality measured with it must never be reported as MiniLM quality.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
import threading
from functools import lru_cache
from typing import Protocol

from app.config import Settings, get_settings
from app.core.errors import EmbeddingError

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    provider: str
    model_name: str
    dimension: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class SentenceTransformerEmbedder:
    provider = "sentence-transformers"

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()
        self.dimension = 0

    def _load(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    try:
                        from sentence_transformers import SentenceTransformer

                        logger.info("loading embedding model", extra={"model": self.model_name})
                        self._model = SentenceTransformer(self.model_name)
                        self.dimension = int(self._model.get_sentence_embedding_dimension())
                    except Exception as exc:
                        raise EmbeddingError(
                            f"Could not load the embedding model '{self.model_name}'. Check the model name, "
                            "internet access for the first download, or set EMBEDDING_MODEL to a local path."
                        ) from exc
        return self._model

    def _encode(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        try:
            vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False, batch_size=32)
        except Exception as exc:
            raise EmbeddingError("The embedding model failed while encoding text.") from exc
        return [v.tolist() for v in vectors]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts) if texts else []

    def embed_query(self, text: str) -> list[float]:
        return self._encode([text])[0]


_TOKEN = re.compile(r"[a-z0-9]+")


def _stem(tok: str) -> str:
    if tok.endswith("ies") and len(tok) > 4:
        return tok[:-3] + "y"
    if tok.endswith("ses") or tok.endswith("xes"):
        return tok[:-2]
    if tok.endswith("s") and not tok.endswith("ss") and len(tok) > 3:
        return tok[:-1]
    return tok


class HashingEmbedder:
    """Signed feature hashing over word stems, bigrams and character trigrams (384-d, L2-normalised)."""

    provider = "hashing"

    def __init__(self, dimension: int = 384):
        self.model_name = f"hashing-{dimension}"
        self.dimension = dimension

    def _features(self, text: str):
        stems = [_stem(t) for t in _TOKEN.findall(text.lower())]
        for s in stems:
            yield s, 1.0
            padded = f"#{s}#"
            for i in range(len(padded) - 2):
                yield "c:" + padded[i : i + 3], 0.25
        for a, b in zip(stems, stems[1:]):
            yield f"{a}_{b}", 0.5

    def _vec(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        for feat, weight in self._features(text):
            h = int.from_bytes(hashlib.blake2b(feat.encode(), digest_size=8).digest(), "big")
            vec[h % self.dimension] += weight if (h >> 40) & 1 else -weight
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


@lru_cache(maxsize=4)
def _build(provider: str, model: str) -> Embedder:
    if provider in ("sentence-transformers", "sentence_transformers", "huggingface"):
        return SentenceTransformerEmbedder(model)
    if provider == "hashing":
        return HashingEmbedder()
    raise EmbeddingError(f"Unknown EMBEDDING_PROVIDER '{provider}'. Use 'sentence-transformers' or 'hashing'.")


def get_embedder(settings: Settings | None = None) -> Embedder:
    s = settings or get_settings()
    return _build(s.embedding_provider.lower(), s.embedding_model)
