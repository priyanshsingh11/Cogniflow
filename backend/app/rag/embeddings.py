"""Embedding backends.

Production uses fastembed (ONNX, local): ~100 MB model download once, then no
API keys, no rate limits, vectors in 384 dims -> pgvector ``vector(384)``.
Tests install a deterministic fake so CI never downloads the model; a single
opt-in test (`RUN_LIVE_EMBED=1`) exercises the real model.

The model is loaded lazily on first use and cached on the instance; embedding
is CPU-bound, so callers wrap calls in ``asyncio.to_thread``.
"""

from typing import Protocol

from app.config import settings

EMBEDDING_DIM = 384


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedder:
    """Local sentence-transformers/all-MiniLM-L6-v2 via fastembed (ONNX)."""

    dim = EMBEDDING_DIM

    def __init__(self, model_name: str | None = None, cache_dir: str | None = None) -> None:
        self.model_name = model_name or settings.embedding_model
        self.cache_dir = cache_dir or settings.embedding_cache_dir
        self._model = None

    def _load(self):
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self.model_name, cache_dir=self.cache_dir)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        # normalize=True matches cosine similarity used by pgvector's
        # vector_cosine_ops; fastembed returns generators of np arrays.
        vectors = model.embed(texts, normalize=True)
        return [[float(x) for x in vec] for vec in vectors]

    def embed_query(self, text: str) -> list[float]:
        model = self._load()
        vec = next(model.query_embed(text))
        return [float(x) for x in vec]


class FakeEmbedder:
    """Deterministic hash-based vectors for tests: same text -> same vector,
    related texts are NOT semantically close (tests assert structure, not
    similarity)."""

    dim = EMBEDDING_DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)

    @staticmethod
    def _vec(text: str) -> list[float]:
        import hashlib
        import math

        seed = hashlib.sha256(text.encode()).digest()
        values = [
            ((seed[i % len(seed)] * (i + 1)) % 251) / 251.0 - 0.5 for i in range(EMBEDDING_DIM)
        ]
        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values]


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = FastEmbedder()
    return _embedder


def set_embedder(embedder: Embedder | None) -> None:
    """Test hook: install a fake (pass None to reset to the real one)."""
    global _embedder
    _embedder = embedder
