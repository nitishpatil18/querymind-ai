"""Application-state ORM models (query history). Stored in a separate SQLite file, never in the analytics database."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class QueryRecord(Base):
    __tablename__ = "query_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    question: Mapped[str] = mapped_column(Text)
    standalone_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32))  # ok | clarification_needed | cannot_answer | invalid_sql
    sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    clarification_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    tables_json: Mapped[str] = mapped_column(Text, default="[]")
    assumptions_json: Mapped[str] = mapped_column(Text, default="[]")
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    validation_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    generation_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    # execution (filled in when the user runs the query)
    execution_status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # success | rejected | timeout | error
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    execution_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    execution_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded: Mapped[bool] = mapped_column(Boolean, default=False)  # replaced by a regenerated answer
