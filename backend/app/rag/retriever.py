"""Schema-aware retrieval: semantic search over schema documents + foreign-key expansion."""
from __future__ import annotations

import logging
import time
from typing import Callable

from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.database.inspector import RelationshipInfo, SchemaInfo
from app.rag.document_generator import render_table_document
from app.rag.embeddings import Embedder, get_embedder
from app.rag.vector_store import SchemaVectorStore

logger = logging.getLogger(__name__)


class RetrievalHit(BaseModel):
    doc_id: str
    doc_type: str
    tables: list[str]
    score: float
    preview: str


class RetrievedTable(BaseModel):
    name: str
    score: float | None = None
    source: str  # "semantic" | "expanded"
    reason: str = ""


class RetrievalResult(BaseModel):
    query: str
    top_k: int
    max_tables: int
    hits: list[RetrievalHit] = Field(default_factory=list)
    semantic_tables: list[RetrievedTable] = Field(default_factory=list)  # before FK expansion
    tables: list[RetrievedTable] = Field(default_factory=list)  # final context (semantic + expanded)
    relationships: list[RelationshipInfo] = Field(default_factory=list)
    context: str = ""
    embedding_model: str | None = None
    latency_ms: float = 0.0
    empty: bool = False

    @property
    def table_names(self) -> list[str]:
        return [t.name for t in self.tables]

    def debug_dict(self) -> dict:
        return self.model_dump(exclude={"context"})


class SchemaRetriever:
    def __init__(
        self,
        store: SchemaVectorStore,
        schema_provider: Callable[[], SchemaInfo],
        settings: Settings | None = None,
        embedder: Embedder | None = None,
    ):
        self.store = store
        self.schema_provider = schema_provider
        self.settings = settings or get_settings()
        self._embedder = embedder

    @property
    def embedder(self) -> Embedder:
        return self._embedder or get_embedder(self.settings)

    # ------------------------------------------------------------------
    def retrieve(
        self,
        question: str,
        *,
        top_k: int | None = None,
        max_tables: int | None = None,
        expand: bool = True,
        doc_types: list[str] | None = None,
    ) -> RetrievalResult:
        started = time.perf_counter()
        schema = self.schema_provider()
        top_k = top_k or self.settings.retrieval_top_k
        max_tables = max_tables or self.settings.retrieval_max_tables
        result = RetrievalResult(query=question, top_k=top_k, max_tables=max_tables, embedding_model=self.embedder.model_name)

        # metadata filtering: only authorised schemas (and optionally selected document types)
        clauses: list[dict] = [{"schema": {"$in": schema.schemas}}] if schema.schemas else []
        if doc_types:
            clauses.append({"doc_type": {"$in": doc_types}})
        where = clauses[0] if len(clauses) == 1 else ({"$and": clauses} if clauses else None)

        vector = self.embedder.embed_query(question)
        raw_hits = self.store.query(vector, top_k, where)
        known = {t.name for t in schema.tables}

        table_scores: dict[str, float] = {}
        for h in raw_hits:
            tables = [t for t in str(h.metadata.get("tables", "")).split(",") if t in known]
            result.hits.append(
                RetrievalHit(
                    doc_id=h.doc_id,
                    doc_type=str(h.metadata.get("doc_type", "")),
                    tables=tables,
                    score=h.score,
                    preview=h.text[:160].replace("\n", " "),
                )
            )
            for t in tables:
                table_scores[t] = max(table_scores.get(t, -1.0), h.score)

        ranked = sorted(table_scores.items(), key=lambda kv: (-kv[1], kv[0]))[:max_tables]
        result.semantic_tables = [
            RetrievedTable(name=n, score=round(s, 4), source="semantic", reason="matched by semantic similarity") for n, s in ranked
        ]
        if not result.semantic_tables:
            result.empty = True
            result.latency_ms = round((time.perf_counter() - started) * 1000, 2)
            return result

        selected = [t.name for t in result.semantic_tables]
        final = list(result.semantic_tables)
        if expand and self.settings.retrieval_expand_max > 0:
            final.extend(self._expand(schema, selected, table_scores))
        result.tables = final

        names = {t.name for t in final}
        result.relationships = [r for r in schema.relationships if r.child_table in names and r.parent_table in names]
        result.context = self.build_context(schema, [t.name for t in final], result.relationships)
        result.latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return result

    # ------------------------------------------------------------------
    def _expand(self, schema: SchemaInfo, selected: list[str], scores: dict[str, float]) -> list[RetrievedTable]:
        """Add FK neighbours. Bridge tables (connecting two selected tables) come first, then parents, then children."""
        chosen = set(selected)
        neighbours: dict[str, dict] = {}
        for rel in schema.relationships:
            for here, there, role in ((rel.child_table, rel.parent_table, "parent"), (rel.parent_table, rel.child_table, "child")):
                if here in chosen and there not in chosen:
                    n = neighbours.setdefault(there, {"links": set(), "role": role, "via": []})
                    n["links"].add(here)
                    n["via"].append(f"{rel.child_table}.{','.join(rel.child_columns)} -> {rel.parent_table}")
                    if role == "parent":
                        n["role"] = "parent"

        def sort_key(item):
            name, info = item
            bridge = 0 if len(info["links"]) >= 2 else 1
            role = 0 if info["role"] == "parent" else 1
            return (bridge, role, -scores.get(name, 0.0), name)

        out: list[RetrievedTable] = []
        for name, info in sorted(neighbours.items(), key=sort_key)[: self.settings.retrieval_expand_max]:
            kind = "bridges " + " and ".join(sorted(info["links"])) if len(info["links"]) >= 2 else f"related to {sorted(info['links'])[0]}"
            out.append(
                RetrievedTable(
                    name=name,
                    score=round(scores[name], 4) if name in scores else None,
                    source="expanded",
                    reason=f"foreign-key expansion ({kind}; {info['via'][0]})",
                )
            )
        return out

    @staticmethod
    def build_context(schema: SchemaInfo, table_names: list[str], relationships: list[RelationshipInfo]) -> str:
        parts = []
        for name in table_names:
            t = schema.table(name)
            if t:
                parts.append(render_table_document(t, schema, include_relationships=False))
        if relationships:
            parts.append(
                "Verified foreign-key relationships (use exactly these JOIN conditions):\n"
                + "\n".join(f"- {r.child_table} -> {r.parent_table}: {r.fk_sql()} ({r.cardinality})" for r in relationships)
            )
        return "\n\n".join(parts)
