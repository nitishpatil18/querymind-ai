"""ChromaDB persistence for schema documents (cosine similarity)."""
from __future__ import annotations

import logging
import threading
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings
from pydantic import BaseModel

from app.core.errors import VectorStoreError
from app.rag.document_generator import SchemaDocument
from app.rag.embeddings import Embedder

logger = logging.getLogger(__name__)


class VectorHit(BaseModel):
    doc_id: str
    text: str
    metadata: dict
    score: float  # cosine similarity (1 = identical)


class SchemaVectorStore:
    def __init__(self, path: Path, collection: str = "schema_docs"):
        self.path = Path(path)
        self.collection_name = collection
        self._lock = threading.RLock()
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                self.path.mkdir(parents=True, exist_ok=True)
                self._client = chromadb.PersistentClient(
                    path=str(self.path), settings=ChromaSettings(anonymized_telemetry=False)
                )
            except Exception as exc:
                raise VectorStoreError("Could not open the vector store (ChromaDB).") from exc
        return self._client

    def _collection(self):
        return self.client.get_collection(self.collection_name)

    # ------------------------------------------------------------------
    def rebuild(self, documents: list[SchemaDocument], embedder: Embedder, batch_size: int = 64) -> int:
        """Replace the collection with the given documents. Returns the number of documents stored."""
        with self._lock:
            try:
                vectors = embedder.embed_documents([d.text for d in documents])
                try:
                    self.client.delete_collection(self.collection_name)
                except Exception:
                    pass  # did not exist yet
                col = self.client.create_collection(
                    self.collection_name,
                    metadata={"hnsw:space": "cosine", "embedding_provider": embedder.provider, "embedding_model": embedder.model_name},
                )
                for i in range(0, len(documents), batch_size):
                    chunk = documents[i : i + batch_size]
                    col.add(
                        ids=[d.doc_id for d in chunk],
                        documents=[d.text for d in chunk],
                        metadatas=[d.metadata for d in chunk],
                        embeddings=vectors[i : i + batch_size],
                    )
                return col.count()
            except VectorStoreError:
                raise
            except Exception as exc:
                if exc.__class__.__name__ == "EmbeddingError":
                    raise
                logger.exception("vector store rebuild failed")
                raise VectorStoreError("Writing to the vector store failed.") from exc

    def count(self) -> int:
        with self._lock:
            try:
                return self._collection().count()
            except Exception:
                return 0

    def collection_metadata(self) -> dict:
        with self._lock:
            try:
                return dict(self._collection().metadata or {})
            except Exception:
                return {}

    def query(self, query_vector: list[float], k: int, where: dict | None = None) -> list[VectorHit]:
        with self._lock:
            try:
                col = self._collection()
            except Exception:
                return []  # collection not created yet: nothing indexed
            try:
                n = col.count()
                if n == 0:
                    return []
                res = col.query(
                    query_embeddings=[query_vector],
                    n_results=min(k, n),
                    where=where or None,
                    include=["documents", "metadatas", "distances"],
                )
            except Exception as exc:
                raise VectorStoreError("Searching the vector store failed. Try re-indexing the schema.") from exc
        hits = []
        for doc_id, doc, meta, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]):
            hits.append(VectorHit(doc_id=doc_id, text=doc, metadata=meta or {}, score=round(1.0 - float(dist), 4)))
        return hits
