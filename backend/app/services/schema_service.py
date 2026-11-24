"""Schema discovery + index lifecycle (refresh, re-index, status)."""
from __future__ import annotations

import logging
import threading

from pydantic import BaseModel

from app.config import Settings, get_settings
from app.core.errors import DatabaseUnavailableError, NotFoundError
from app.database.connection import get_engine
from app.database.inspector import SchemaInfo, SchemaInspector, TableInfo
from app.rag.indexing import IndexState, SchemaIndexer
from app.utils.validators import validate_identifier

logger = logging.getLogger(__name__)


class SchemaStatus(BaseModel):
    index: IndexState
    database: str | None = None
    tables_discovered: int = 0
    schema_fingerprint: str | None = None
    inspected_at: str | None = None
    index_is_current: bool = False
    vector_documents: int = 0


class SchemaService:
    def __init__(self, indexer: SchemaIndexer, engine=None, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.indexer = indexer
        self._engine = engine
        self._schema: SchemaInfo | None = None
        self._lock = threading.RLock()

    @property
    def engine(self):
        return self._engine or get_engine()

    def get_schema(self, force: bool = False) -> SchemaInfo:
        with self._lock:
            if self._schema is None or force:
                try:
                    self._schema = SchemaInspector(self.engine, self.settings.allowed_schemas).inspect()
                except Exception as exc:
                    if self._schema is not None:
                        logger.warning("schema re-inspection failed; serving cached schema")
                        return self._schema
                    raise DatabaseUnavailableError(
                        "Cannot read the database schema. Check that PostgreSQL is running and DATABASE_URL is correct."
                    ) from exc
            return self._schema

    def get_table(self, name: str) -> TableInfo:
        validate_identifier(name, "table name")
        table = self.get_schema().table(name)
        if table is None:
            raise NotFoundError(f"Table '{name}' was not found in the authorised schema.")
        return table

    def refresh(self, reindex: bool = True) -> SchemaStatus:
        """Re-discover the database structure and rebuild the vector index."""
        schema = self.get_schema(force=True)
        if reindex:
            self.indexer.build(schema)
        return self.status()

    def ensure_index(self) -> IndexState:
        return self.indexer.ensure(self.get_schema())

    def status(self) -> SchemaStatus:
        try:
            schema = self.get_schema()
            return SchemaStatus(
                index=self.indexer.state, database=schema.database, tables_discovered=len(schema.tables),
                schema_fingerprint=schema.fingerprint, inspected_at=schema.inspected_at.isoformat(),
                index_is_current=self.indexer.is_current(schema), vector_documents=self.indexer.store.count(),
            )
        except DatabaseUnavailableError:
            return SchemaStatus(index=self.indexer.state)
