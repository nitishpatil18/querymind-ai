"""Schema indexing: documents -> embeddings -> ChromaDB, with persisted index state."""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from app.config import Settings, get_settings
from app.core.errors import AppError
from app.database.inspector import SchemaInfo
from app.rag.document_generator import generate_documents
from app.rag.embeddings import Embedder, get_embedder
from app.rag.vector_store import SchemaVectorStore

logger = logging.getLogger(__name__)


class IndexState(BaseModel):
    status: str = "not_indexed"  # not_indexed | indexing | ready | failed
    last_indexed_at: datetime | None = None
    tables_indexed: int = 0
    documents_indexed: int = 0
    schema_fingerprint: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    duration_ms: float | None = None
    error: str | None = None


class SchemaIndexer:
    def __init__(self, store: SchemaVectorStore, settings: Settings | None = None, embedder: Embedder | None = None):
        self.settings = settings or get_settings()
        self.store = store
        self._embedder = embedder
        self._state_file: Path = self.settings.chroma_dir / "index_state.json"
        self._lock = threading.Lock()
        self._state = self._load_state()

    @property
    def embedder(self) -> Embedder:
        return self._embedder or get_embedder(self.settings)

    # -- state ------------------------------------------------------------------
    def _load_state(self) -> IndexState:
        try:
            return IndexState.model_validate_json(self._state_file.read_text())
        except Exception:
            return IndexState()

    def _save_state(self) -> None:
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(self._state.model_dump_json(indent=2))
        except OSError:
            logger.warning("could not persist index state")

    @property
    def state(self) -> IndexState:
        return self._state

    def is_current(self, schema: SchemaInfo) -> bool:
        s = self._state
        emb = self.embedder
        return (
            s.status == "ready"
            and s.schema_fingerprint == schema.fingerprint
            and s.embedding_model == emb.model_name
            and s.embedding_provider == emb.provider
            and self.store.count() >= s.documents_indexed > 0
        )

    # -- operations -------------------------------------------------------------
    def build(self, schema: SchemaInfo) -> IndexState:
        with self._lock:
            started = time.perf_counter()
            self._state = self._state.model_copy(update={"status": "indexing", "error": None})
            self._save_state()
            try:
                docs = generate_documents(schema, self.settings.column_chunk_size)
                emb = self.embedder
                stored = self.store.rebuild(docs, emb)
                self._state = IndexState(
                    status="ready",
                    last_indexed_at=datetime.now(timezone.utc),
                    tables_indexed=len(schema.tables),
                    documents_indexed=stored,
                    schema_fingerprint=schema.fingerprint,
                    embedding_provider=emb.provider,
                    embedding_model=emb.model_name,
                    duration_ms=round((time.perf_counter() - started) * 1000, 1),
                )
                logger.info("schema indexed", extra={"documents": stored, "tables": len(schema.tables)})
            except AppError as exc:
                self._state = self._state.model_copy(update={"status": "failed", "error": exc.message})
                self._save_state()
                raise
            except Exception as exc:
                self._state = self._state.model_copy(update={"status": "failed", "error": "Indexing failed unexpectedly."})
                self._save_state()
                logger.exception("indexing failed")
                raise AppError("Indexing failed unexpectedly.") from exc
            self._save_state()
            return self._state

    def ensure(self, schema: SchemaInfo) -> IndexState:
        """Index only when missing or stale (schema changed / embedding model changed)."""
        if self.is_current(schema):
            return self._state
        return self.build(schema)
