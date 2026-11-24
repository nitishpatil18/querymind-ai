from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.rag.retriever import RetrievalHit, RetrievedTable
from app.database.inspector import RelationshipInfo
from app.services.validation_service import ValidationResult


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody


class RetrievalDebug(BaseModel):
    query: str
    top_k: int
    embedding_model: str | None = None
    latency_ms: float = 0.0
    hits: list[RetrievalHit] = Field(default_factory=list)
    semantic_tables: list[RetrievedTable] = Field(default_factory=list)
    tables: list[RetrievedTable] = Field(default_factory=list)
    relationships: list[RelationshipInfo] = Field(default_factory=list)


class Latency(BaseModel):
    retrieval_ms: float = 0.0
    generation_ms: float = 0.0
    total_ms: float = 0.0


class GenerateResponse(BaseModel):
    history_id: int
    conversation_id: str
    question: str
    standalone_question: str
    status: str  # ok | clarification_needed | cannot_answer | invalid_sql
    sql: str | None = None
    explanation: str = ""
    tables_used: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    confidence: str | None = None
    clarification_question: str | None = None
    message: str | None = None
    validation: ValidationResult | None = None
    retrieval: RetrievalDebug | None = None
    attempts: int = 0
    attempt_errors: list[str] = Field(default_factory=list)
    latency: Latency = Field(default_factory=Latency)


class ExecuteResponse(BaseModel):
    status: str = "success"
    executed_sql: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    max_rows: int
    execution_time_ms: float
    history_id: int | None = None


class ComponentHealth(BaseModel):
    status: str  # ok | degraded | down
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    components: dict[str, ComponentHealth]
    version: str = "1.0.0"


class SettingsResponse(BaseModel):
    app_env: str
    llm_provider: str
    llm_model: str
    llm_api_key_configured: bool
    embedding_provider: str
    embedding_model: str
    retrieval_top_k: int
    retrieval_max_tables: int
    max_result_rows: int
    statement_timeout_ms: int
    generation_max_attempts: int
    conversation_context_turns: int
    allowed_schemas: list[str]
