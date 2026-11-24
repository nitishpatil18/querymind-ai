"""Orchestrates the NL -> SQL flow: context -> retrieval -> generation -> validation -> history."""
from __future__ import annotations

import logging
import time

from app.config import Settings, get_settings
from app.core.errors import AppError, BadRequestError
from app.llm.sql_generator import GenerationOutcome, SQLGenerator
from app.rag.retriever import SchemaRetriever
from app.schemas.response import ExecuteResponse, GenerateResponse, Latency, RetrievalDebug
from app.services.conversation_service import ConversationService
from app.services.execution_service import ExecutionService
from app.services.history_service import HistoryService
from app.services.schema_service import SchemaService
from app.services.validation_service import ValidationResult, ValidationService
from app.utils.validators import clean_question

logger = logging.getLogger(__name__)


class QueryService:
    def __init__(
        self,
        schema_service: SchemaService,
        retriever: SchemaRetriever,
        generator: SQLGenerator,
        validator: ValidationService,
        executor: ExecutionService,
        history: HistoryService,
        conversations: ConversationService,
        settings: Settings | None = None,
    ):
        self.schema_service = schema_service
        self.retriever = retriever
        self.generator = generator
        self.validator = validator
        self.executor = executor
        self.history = history
        self.conversations = conversations
        self.settings = settings or get_settings()

    # ------------------------------------------------------------------
    def generate(
        self,
        question: str,
        *,
        conversation_id: str | None = None,
        use_context: bool = False,
        top_k: int | None = None,
        regenerate_of: int | None = None,
        record: bool = True,
    ) -> GenerateResponse:
        started = time.perf_counter()
        question = clean_question(question)
        schema = self.schema_service.get_schema()
        self.schema_service.ensure_index()  # lazy (re)index when missing or stale
        conv_id = conversation_id or self.conversations.new_id()

        history = self.conversations.context(conv_id, exclude_history_id=regenerate_of) if use_context and conversation_id else []
        standalone = self.generator.rewrite_followup(question, history) if history else question

        retrieval = self.retriever.retrieve(standalone, top_k=top_k)
        t_retrieval = retrieval.latency_ms

        if retrieval.empty:
            outcome = GenerationOutcome(
                None, None, "cannot_answer", 0, standalone,
                message="No relevant tables were found for this question. Try mentioning the data you are interested in.",
            )
        else:
            outcome = self.generator.generate(
                question, standalone, schema, retrieval.context, retrieval.table_names, history=history
            )

        gen, validation = outcome.generation, outcome.validation
        status = outcome.status
        sql = validation.normalized_sql if (validation and validation.valid) else None

        response = GenerateResponse(
            history_id=0,
            conversation_id=conv_id,
            question=question,
            standalone_question=standalone,
            status=status,
            sql=sql,
            explanation=(gen.explanation if gen else "") or "",
            tables_used=(validation.tables if validation and validation.valid else (gen.tables_used if gen else [])),
            assumptions=gen.assumptions if gen else [],
            confidence=gen.confidence if gen else None,
            clarification_question=gen.clarification_question if gen and status == "clarification_needed" else None,
            message=outcome.message,
            validation=validation,
            retrieval=RetrievalDebug(
                query=retrieval.query, top_k=retrieval.top_k, embedding_model=retrieval.embedding_model,
                latency_ms=retrieval.latency_ms, hits=retrieval.hits, semantic_tables=retrieval.semantic_tables,
                tables=retrieval.tables, relationships=retrieval.relationships,
            ),
            attempts=outcome.attempts,
            attempt_errors=outcome.attempt_errors,
            latency=Latency(retrieval_ms=t_retrieval, generation_ms=outcome.latency_ms),
        )
        response.latency.total_ms = round((time.perf_counter() - started) * 1000, 1)

        if record:
            item = self.history.add_generation(
                conversation_id=conv_id, question=question, standalone_question=standalone, status=status, sql=sql,
                explanation=response.explanation, clarification_question=response.clarification_question,
                tables=response.tables_used, assumptions=response.assumptions, confidence=response.confidence,
                validation_valid=validation.valid if validation else None, generation_ms=response.latency.total_ms,
            )
            response.history_id = item.id
            if regenerate_of:
                self.history.mark_superseded(regenerate_of)
        return response

    # ------------------------------------------------------------------
    def validate(self, sql: str) -> ValidationResult:
        return self.validator.validate(sql, self.schema_service.get_schema())

    def execute(self, sql: str, *, history_id: int | None = None, max_rows: int | None = None) -> ExecuteResponse:
        try:
            result = self.executor.execute(sql, max_rows=max_rows)
        except AppError as exc:
            if history_id:
                status = {"query_timeout": "timeout", "sql_rejected": "rejected"}.get(exc.code, "error")
                try:
                    self.history.record_execution(history_id, status=status, error=exc.message)
                except AppError:
                    pass
            raise
        if history_id:
            try:
                self.history.record_execution(
                    history_id, status="success", row_count=result.row_count, execution_ms=result.execution_time_ms
                )
            except AppError:
                logger.warning("history item %s not found when recording execution", history_id)
        return ExecuteResponse(**result.model_dump(exclude={"status", "plan_cost"}), history_id=history_id)
