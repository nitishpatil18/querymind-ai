"""Query history persistence (SQLAlchemy ORM over SQLite). All access is parameterised through the ORM."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from pydantic import BaseModel
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.core.errors import NotFoundError
from app.database.models import Base, QueryRecord


class HistoryItem(BaseModel):
    id: int
    conversation_id: str
    created_at: datetime
    question: str
    standalone_question: str | None = None
    status: str
    sql: str | None = None
    explanation: str | None = None
    clarification_question: str | None = None
    tables_used: list[str] = []
    assumptions: list[str] = []
    confidence: str | None = None
    validation_valid: bool | None = None
    generation_ms: float | None = None
    execution_status: str | None = None
    row_count: int | None = None
    execution_ms: float | None = None
    execution_error: str | None = None
    executed_at: datetime | None = None


class HistoryPage(BaseModel):
    items: list[HistoryItem]
    total: int
    limit: int
    offset: int


def _to_item(r: QueryRecord) -> HistoryItem:
    return HistoryItem(
        id=r.id, conversation_id=r.conversation_id, created_at=r.created_at, question=r.question,
        standalone_question=r.standalone_question, status=r.status, sql=r.sql, explanation=r.explanation,
        clarification_question=r.clarification_question, tables_used=json.loads(r.tables_json or "[]"),
        assumptions=json.loads(r.assumptions_json or "[]"), confidence=r.confidence,
        validation_valid=r.validation_valid, generation_ms=r.generation_ms, execution_status=r.execution_status,
        row_count=r.row_count, execution_ms=r.execution_ms, execution_error=r.execution_error, executed_at=r.executed_at,
    )


class HistoryService:
    def __init__(self, settings: Settings | None = None, url: str | None = None):
        self.settings = settings or get_settings()
        url = url or self.settings.history_url
        if url.startswith("sqlite:///") and ":memory:" not in url:
            self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
        if ":memory:" in url:
            from sqlalchemy.pool import StaticPool

            kwargs["poolclass"] = StaticPool
        self.engine = create_engine(url, future=True, **kwargs)
        Base.metadata.create_all(self.engine)
        self._session = sessionmaker(self.engine, expire_on_commit=False, class_=Session)

    # -- writes ---------------------------------------------------------------
    def add_generation(
        self, *, conversation_id: str, question: str, standalone_question: str | None, status: str,
        sql: str | None, explanation: str | None, clarification_question: str | None, tables: list[str],
        assumptions: list[str], confidence: str | None, validation_valid: bool | None, generation_ms: float | None,
    ) -> HistoryItem:
        with self._session() as s:
            rec = QueryRecord(
                conversation_id=conversation_id, question=question, standalone_question=standalone_question,
                status=status, sql=sql, explanation=explanation, clarification_question=clarification_question,
                tables_json=json.dumps(tables), assumptions_json=json.dumps(assumptions), confidence=confidence,
                validation_valid=validation_valid, generation_ms=generation_ms,
            )
            s.add(rec)
            s.commit()
            return _to_item(rec)

    def record_execution(
        self, history_id: int, *, status: str, row_count: int | None = None,
        execution_ms: float | None = None, error: str | None = None,
    ) -> None:
        with self._session() as s:
            res = s.execute(
                update(QueryRecord).where(QueryRecord.id == history_id).values(
                    execution_status=status, row_count=row_count, execution_ms=execution_ms,
                    execution_error=(error or None) and error[:500], executed_at=datetime.now(timezone.utc),
                )
            )
            s.commit()
            if res.rowcount == 0:
                raise NotFoundError(f"History item {history_id} was not found.")

    def mark_superseded(self, history_id: int) -> None:
        with self._session() as s:
            s.execute(update(QueryRecord).where(QueryRecord.id == history_id).values(superseded=True))
            s.commit()

    # -- reads ----------------------------------------------------------------
    def get(self, history_id: int) -> HistoryItem:
        with self._session() as s:
            rec = s.get(QueryRecord, history_id)
            if rec is None:
                raise NotFoundError(f"History item {history_id} was not found.")
            return _to_item(rec)

    def list(self, limit: int = 50, offset: int = 0, conversation_id: str | None = None) -> HistoryPage:
        with self._session() as s:
            base = select(QueryRecord).where(QueryRecord.superseded.is_(False))
            count = select(func.count()).select_from(QueryRecord).where(QueryRecord.superseded.is_(False))
            if conversation_id:
                base = base.where(QueryRecord.conversation_id == conversation_id)
                count = count.where(QueryRecord.conversation_id == conversation_id)
            rows = s.scalars(base.order_by(QueryRecord.id.desc()).limit(limit).offset(offset)).all()
            return HistoryPage(items=[_to_item(r) for r in rows], total=s.scalar(count) or 0, limit=limit, offset=offset)

    def recent_turns(self, conversation_id: str, limit: int, exclude_id: int | None = None) -> list[HistoryItem]:
        """Latest turns of a conversation (oldest first), skipping superseded and failed ones."""
        if limit <= 0:
            return []
        with self._session() as s:
            q = (
                select(QueryRecord)
                .where(QueryRecord.conversation_id == conversation_id, QueryRecord.superseded.is_(False))
                .where(QueryRecord.status.in_(["ok", "clarification_needed"]))
                .order_by(QueryRecord.id.desc())
                .limit(limit + (1 if exclude_id else 0))
            )
            rows = [r for r in s.scalars(q).all() if r.id != exclude_id][:limit]
        return [_to_item(r) for r in reversed(rows)]
