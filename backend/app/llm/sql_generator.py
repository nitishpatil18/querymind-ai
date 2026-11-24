"""LangChain pipeline: (optional) question rewriting -> schema-grounded SQL generation -> validation/repair loop.

This is a fixed, controlled pipeline. The model only returns text; it never receives database credentials
or the ability to execute anything.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date

from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from langchain_core.runnables import Runnable

from app.config import Settings, get_settings
from app.core.errors import AppError, LLMOutputError
from app.database.inspector import SchemaInfo
from app.llm import prompts
from app.llm.output_parser import SQLGeneration, message_text, parse_generation
from app.llm.provider import get_chat_model, invoke_with_retry
from app.services.validation_service import ValidationResult, ValidationService

logger = logging.getLogger(__name__)


@dataclass
class ContextTurn:
    question: str
    sql: str | None = None
    note: str | None = None  # e.g. the clarification the assistant asked for


@dataclass
class GenerationOutcome:
    generation: SQLGeneration | None
    validation: ValidationResult | None
    status: str  # ok | clarification_needed | cannot_answer | invalid_sql
    attempts: int
    standalone_question: str
    attempt_errors: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    message: str | None = None


class SQLGenerator:
    def __init__(
        self,
        settings: Settings | None = None,
        validator: ValidationService | None = None,
        llm: Runnable | None = None,
    ):
        self.settings = settings or get_settings()
        self.validator = validator or ValidationService(self.settings)
        self._llm = llm  # injected in tests; otherwise built lazily from configuration
        self._format_instructions = PydanticOutputParser(pydantic_object=SQLGeneration).get_format_instructions()

    @property
    def llm(self) -> Runnable:
        if self._llm is None:
            self._llm = get_chat_model(self.settings)
        return self._llm

    # ------------------------------------------------------------------
    def rewrite_followup(self, question: str, history: list[ContextTurn]) -> str:
        """Turn a follow-up into a standalone question. Independent questions are returned unchanged."""
        if not history:
            return question
        lines = []
        for t in history:
            lines.append(f"User: {t.question}")
            if t.sql:
                lines.append(f"(answered with SQL: {' '.join(t.sql.split())[:400]})")
            elif t.note:
                lines.append(f"(assistant asked for clarification: {t.note})")
        chain = prompts.condense_prompt | self.llm | StrOutputParser()
        out = invoke_with_retry(chain, {"history": "\n".join(lines), "question": question})
        out = " ".join(message_text(out).split()).strip().strip('"')
        if not out or len(out) > 1000:
            return question
        return out

    def generate(
        self,
        question: str,
        standalone: str,
        schema: SchemaInfo,
        schema_context: str,
        context_tables: list[str],
        *,
        history: list[ContextTurn] | None = None,
    ) -> GenerationOutcome:
        """`standalone` is the (possibly rewritten) question that retrieval was run for."""
        started = time.perf_counter()
        history = history or []
        follow_up = standalone != question and any(t.sql for t in history)
        previous_block = ""
        if follow_up:
            last = next(t for t in reversed(history) if t.sql)
            previous_block = prompts.PREVIOUS_BLOCK.format(prev_question=last.question, prev_sql=last.sql)

        chain = prompts.sql_prompt | self.llm
        errors: list[str] = []
        feedback = ""
        last_gen: SQLGeneration | None = None
        last_validation: ValidationResult | None = None
        allowed_tables = {t.lower() for t in context_tables}

        for attempt in range(1, self.settings.generation_max_attempts + 1):
            payload = {
                "today": date.today().isoformat(),
                "format_instructions": self._format_instructions,
                "schema_context": schema_context,
                "previous_block": previous_block,
                "feedback_block": prompts.FEEDBACK_BLOCK.format(feedback=feedback) if feedback else "",
                "question": standalone,
            }
            raw = invoke_with_retry(chain, payload)

            try:
                gen = parse_generation(raw)
            except LLMOutputError as exc:
                errors.append(exc.message)
                feedback = exc.message + " Return a single valid JSON object that follows the format exactly."
                logger.info("generation attempt %d: unparsable output", attempt)
                continue

            last_gen = gen
            if gen.status != "ok":
                return GenerationOutcome(
                    gen, None, gen.status, attempt, standalone, errors, _ms(started),
                    message=gen.clarification_question if gen.status == "clarification_needed" else gen.explanation,
                )

            validation = self.validator.validate(gen.sql or "", schema)
            last_validation = validation
            if validation.valid:
                outside = [t for t in validation.tables if t.lower() not in allowed_tables]
                if outside:
                    msg = (
                        f"The query uses table(s) {', '.join(outside)} that are not part of the provided schema context. "
                        f"Use only: {', '.join(context_tables)}."
                    )
                    errors.append(msg)
                    feedback = msg
                    continue
                gen.tables_used = validation.tables  # verified by the parser, not self-reported
                return GenerationOutcome(gen, validation, "ok", attempt, standalone, errors, _ms(started))

            errors.append(validation.error_summary)
            feedback = f"Validation failed: {validation.error_summary}"
            logger.info("generation attempt %d: validation failed (%s)", attempt, validation.errors[0].code)

        return GenerationOutcome(
            last_gen,
            last_validation,
            "invalid_sql",
            self.settings.generation_max_attempts,
            standalone,
            errors,
            _ms(started),
            message="Could not produce a valid query after "
            f"{self.settings.generation_max_attempts} attempts. Try rephrasing the question.",
        )


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)
