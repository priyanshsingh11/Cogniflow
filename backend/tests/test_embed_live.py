"""Opt-in live check of the real embedding model.

Run with: RUN_LIVE_EMBED=1 uv run pytest tests/test_embed_live.py -s
Downloads ~100 MB (sentence-transformers/all-MiniLM-L6-v2, ONNX) on first run.
All other tests use FakeEmbedder, so CI never downloads it.
"""

import math
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_LIVE_EMBED"), reason="set RUN_LIVE_EMBED=1"
)


def test_fastembed_real_model_roundtrip():
    from app.rag.embeddings import EMBEDDING_DIM, FastEmbedder

    embedder = FastEmbedder()
    vec = embedder.embed_query("the capital of France")
    assert len(vec) == EMBEDDING_DIM
    assert abs(math.sqrt(sum(v * v for v in vec)) - 1.0) < 0.01  # normalized

    a, b, c = embedder.embed(
        ["the capital of France", "the capital of France", "zzz unrelated qqq"]
    )
    assert a == pytest.approx(b)  # deterministic for identical input
    assert not c == pytest.approx(a)
    cosine = sum(x * y for x, y in zip(vec, a, strict=True))
    assert cosine > 0.99  # query path agrees with the embed path
