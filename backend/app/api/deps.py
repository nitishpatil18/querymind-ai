"""Dependency container: builds the object graph once and exposes it to routes."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request
from langchain_core.runnables import Runnable
from sqlalchemy.engine import Engine

from app.config import Settings, get_settings
from app.database.connection import get_engine
from app.llm.sql_generator import SQLGenerator
from app.rag.embeddings import Embedder
from app.rag.indexing import SchemaIndexer
from app.rag.retriever import SchemaRetriever
from app.rag.vector_store import SchemaVectorStore
from app.services.conversation_service import ConversationService
from app.services.evaluation_service import EvaluationService
from app.services.execution_service import ExecutionService
from app.services.history_service import HistoryService
from app.services.query_service import QueryService
from app.services.schema_service import SchemaService
from app.services.validation_service import ValidationService


@dataclass
class Container:
    settings: Settings
    engine: Engine
    validator: ValidationService
    store: SchemaVectorStore
    indexer: SchemaIndexer
    schema_service: SchemaService
    retriever: SchemaRetriever
    generator: SQLGenerator
    executor: ExecutionService
    history: HistoryService
    conversations: ConversationService
    query_service: QueryService
    evaluation_service: EvaluationService


def build_container(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
    embedder: Embedder | None = None,
    llm: Runnable | None = None,
    history_url: str | None = None,
) -> Container:
    s = settings or get_settings()
    engine = engine or get_engine()
    validator = ValidationService(s)
    store = SchemaVectorStore(s.chroma_dir, s.chroma_collection)
    indexer = SchemaIndexer(store, s, embedder)
    schema_service = SchemaService(indexer, engine, s)
    retriever = SchemaRetriever(store, schema_service.get_schema, s, embedder)
    generator = SQLGenerator(s, validator, llm)
    executor = ExecutionService(engine, validator, schema_service.get_schema, s)
    history = HistoryService(s, history_url)
    conversations = ConversationService(history, s)
    query_service = QueryService(schema_service, retriever, generator, validator, executor, history, conversations, s)
    evaluation = EvaluationService(query_service, schema_service, executor, validator, s)
    return Container(
        s, engine, validator, store, indexer, schema_service, retriever, generator, executor, history,
        conversations, query_service, evaluation,
    )


def get_container(request: Request) -> Container:
    return request.app.state.container
