import pytest

from app.config import Settings
from app.rag.embeddings import HashingEmbedder
from app.rag.indexing import SchemaIndexer
from app.rag.retriever import SchemaRetriever
from app.rag.vector_store import SchemaVectorStore


@pytest.fixture()
def stack(tmp_path, mini_schema):
    s = Settings(_env_file=None, data_dir=tmp_path, chroma_path=tmp_path / "chroma", embedding_provider="hashing",
                 retrieval_top_k=8, retrieval_max_tables=2, retrieval_expand_max=2)
    emb = HashingEmbedder()
    store = SchemaVectorStore(s.chroma_dir, "schema_t")
    indexer = SchemaIndexer(store, s, emb)
    indexer.build(mini_schema)
    return s, store, indexer, SchemaRetriever(store, lambda: mini_schema, s, emb)


def test_index_state_and_persistence(stack, mini_schema, tmp_path):
    s, store, indexer, _ = stack
    assert indexer.state.status == "ready" and indexer.state.tables_indexed == 5
    assert indexer.state.documents_indexed == store.count() == 5 + 4
    assert indexer.is_current(mini_schema)
    # a new indexer object sees the persisted state, and the persisted collection
    again = SchemaIndexer(SchemaVectorStore(s.chroma_dir, "schema_t"), s, HashingEmbedder())
    assert again.state.status == "ready" and again.is_current(mini_schema)


def test_stale_index_is_detected_and_rebuilt(stack, mini_schema):
    _, _, indexer, _ = stack
    changed = mini_schema.model_copy(update={"fingerprint": "other"})
    assert not indexer.is_current(changed)
    assert indexer.ensure(changed).schema_fingerprint == "other"


def test_semantic_retrieval_ranks_relevant_tables_first(stack):
    _, _, _, r = stack
    res = r.retrieve("which customers registered in each city", expand=False)
    assert res.semantic_tables[0].name == "customers"
    assert len(res.semantic_tables) <= 2
    assert all(0 <= h.score <= 1.0001 for h in res.hits)


def test_fk_expansion_adds_bridge_and_verified_joins(stack):
    _, _, _, r = stack
    res = r.retrieve("total spending of each customer from order items")
    names = res.table_names
    assert "customers" in names or "orders" in names
    expanded = [t for t in res.tables if t.source == "expanded"]
    assert len(expanded) <= 2 and all("foreign-key expansion" in t.reason for t in expanded)
    # every relationship in context connects two tables that are in context
    for rel in res.relationships:
        assert rel.child_table in names and rel.parent_table in names
    assert "Verified foreign-key relationships" in res.context
    assert "orders.customer_id = customers.customer_id" in res.context or "customers" not in names or "orders" not in names


def test_expansion_can_be_disabled_and_top_k_is_respected(stack):
    _, _, _, r = stack
    res = r.retrieve("products and categories", top_k=3, expand=False)
    assert len(res.hits) == 3 and res.tables == res.semantic_tables


def test_metadata_filter_by_doc_type(stack):
    _, _, _, r = stack
    res = r.retrieve("customer orders relationship", doc_types=["relationship"], expand=False)
    assert res.hits and all(h.doc_type == "relationship" for h in res.hits)


def test_empty_index_returns_empty_result(tmp_path, mini_schema):
    s = Settings(_env_file=None, data_dir=tmp_path, chroma_path=tmp_path / "c2", embedding_provider="hashing")
    store = SchemaVectorStore(s.chroma_dir, "schema_empty")
    res = SchemaRetriever(store, lambda: mini_schema, s, HashingEmbedder()).retrieve("anything")
    assert res.empty and res.tables == []
