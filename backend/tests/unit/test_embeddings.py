import math

import pytest

from app.config import Settings
from app.core.errors import EmbeddingError
from app.rag.embeddings import HashingEmbedder, SentenceTransformerEmbedder, get_embedder


def cos(a, b):
    return sum(x * y for x, y in zip(a, b))


def test_hashing_embedder_is_deterministic_and_normalised():
    e = HashingEmbedder()
    v1, v2 = e.embed_query("top customers by spending"), e.embed_query("top customers by spending")
    assert v1 == v2 and len(v1) == e.dimension == 384
    assert math.isclose(sum(x * x for x in v1), 1.0, rel_tol=1e-9)


def test_hashing_embedder_ranks_related_text_higher():
    e = HashingEmbedder()
    q = e.embed_query("customers who placed orders")
    related = e.embed_documents(["Table: customers\nDescription: Registered customers"])[0]
    unrelated = e.embed_documents(["Table: warehouse_pallets\nDescription: forklift inventory"])[0]
    assert cos(q, related) > cos(q, unrelated)


def test_factory_selects_provider_and_rejects_unknown():
    assert isinstance(get_embedder(Settings(_env_file=None, embedding_provider="hashing")), HashingEmbedder)
    st = get_embedder(Settings(_env_file=None, embedding_provider="sentence-transformers"))
    assert isinstance(st, SentenceTransformerEmbedder) and st.model_name.endswith("all-MiniLM-L6-v2")
    with pytest.raises(EmbeddingError):
        get_embedder(Settings(_env_file=None, embedding_provider="nope"))


def test_sentence_transformer_load_failure_is_reported_cleanly():
    e = SentenceTransformerEmbedder("definitely/not-a-real-model-xyz")
    with pytest.raises(EmbeddingError) as err:
        e.embed_query("hello")
    assert "embedding model" in err.value.message


@pytest.mark.slow
def test_minilm_embeddings_when_model_available():
    """Runs only where the model can be loaded (needs sentence-transformers and a cached/downloadable model)."""
    st = SentenceTransformerEmbedder("sentence-transformers/all-MiniLM-L6-v2")
    try:
        v = st.embed_query("top customers by spending")
    except EmbeddingError:
        pytest.skip("all-MiniLM-L6-v2 is not available in this environment")
    assert len(v) == 384
    docs = st.embed_documents(["Table: customers", "Table: pallets"])
    assert cos(v, docs[0]) > cos(v, docs[1])
