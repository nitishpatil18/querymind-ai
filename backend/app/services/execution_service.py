"""Controlled SQL execution: revalidate, read-only transaction, timeout, plan-cost guard, row cap."""
from __future__ import annotations

import json
import logging
import time
from typing import Callable

from pydantic import BaseModel
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, OperationalError

from app.config import Settings, get_settings
from app.core.errors import (
    DatabaseUnavailableError,
    QueryExecutionError,
    QueryTimeoutError,
    SQLRejectedError,
)
from app.database.inspector import SchemaInfo
from app.services.validation_service import ValidationService
from app.utils.serialization import to_json_safe

logger = logging.getLogger(__name__)


class ExecutionResult(BaseModel):
    status: str = "success"
    executed_sql: str
    columns: list[str]
    rows: list[list]
    row_count: int
    truncated: bool
    max_rows: int
    execution_time_ms: float
    plan_cost: float | None = None


class ExecutionService:
    def __init__(
        self,
        engine: Engine,
        validator: ValidationService,
        schema_provider: Callable[[], SchemaInfo],
        settings: Settings | None = None,
    ):
        self.engine = engine
        self.validator = validator
        self.schema_provider = schema_provider
        self.settings = settings or get_settings()

    def execute(self, sql: str, max_rows: int | None = None) -> ExecutionResult:
        # 1. always revalidate on the backend, whatever the client claims
        validation = self.validator.validate(sql, self.schema_provider())
        if not validation.valid:
            raise SQLRejectedError(
                f"The query was rejected: {validation.error_summary}",
                details={"validation": validation.model_dump(mode="json")},
            )
        run_sql = validation.normalized_sql  # exactly what was validated is what runs
        limit = min(max_rows or self.settings.max_result_rows, self.settings.max_result_rows)

        started = time.perf_counter()
        try:
            with self.engine.connect() as conn:
                # Raw psycopg cursors are used on purpose: no placeholder processing is applied to the SQL text,
                # so literals such as '%abc%' or 'a:b' reach PostgreSQL exactly as validated.
                raw = conn.connection.dbapi_connection
                setup = raw.cursor()
                setup.execute("SET TRANSACTION READ ONLY")
                setup.execute(f"SET LOCAL statement_timeout = {int(self.settings.statement_timeout_ms)}")
                plan_cost = self._plan_cost(setup, run_sql)
                setup.close()
                if plan_cost is not None and plan_cost > self.settings.max_plan_cost:
                    raise SQLRejectedError(
                        "The query was refused because the database estimates it as too expensive. "
                        "Add filters or a LIMIT and try again.",
                        details={"plan_cost": plan_cost},
                    )
                cur = raw.cursor(name="querymind_cursor")  # server-side: never pulls more than limit+1 rows
                try:
                    cur.execute(run_sql)
                    columns = [d.name for d in (cur.description or [])]
                    fetched = cur.fetchmany(limit + 1)
                finally:
                    cur.close()
                raw.rollback()
        except SQLRejectedError:
            raise
        except DBAPIError as exc:
            raise self._translate(exc) from exc
        except Exception as exc:
            if exc.__class__.__module__.startswith("psycopg"):
                raise self._translate_psycopg(exc) from exc
            raise
        elapsed = round((time.perf_counter() - started) * 1000, 2)

        truncated = len(fetched) > limit
        rows = [[to_json_safe(v) for v in row] for row in fetched[:limit]]
        logger.info("query executed", extra={"rows": len(rows), "ms": elapsed, "truncated": truncated})
        return ExecutionResult(
            executed_sql=run_sql,
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            max_rows=limit,
            execution_time_ms=elapsed,
            plan_cost=plan_cost,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _plan_cost(cursor, sql: str) -> float | None:
        cursor.execute("EXPLAIN (FORMAT JSON) " + sql)  # psycopg errors (timeout, bad SQL) propagate to the caller
        raw = cursor.fetchone()[0]
        try:
            plan = raw if isinstance(raw, list) else json.loads(raw)
            return float(plan[0]["Plan"]["Total Cost"])
        except (KeyError, IndexError, TypeError, ValueError):
            return None

    @classmethod
    def _translate(cls_, exc: DBAPIError):
        return cls_._classify(exc.orig, isinstance(exc, OperationalError))

    @classmethod
    def _translate_psycopg(cls_, exc: Exception):
        return cls_._classify(exc, exc.__class__.__name__ in ("OperationalError", "InterfaceError"))

    @staticmethod
    def _classify(orig, operational: bool):
        cls = orig.__class__.__name__ if orig is not None else ""
        primary = None
        diag = getattr(orig, "diag", None)
        if diag is not None:
            primary = getattr(diag, "message_primary", None)
        if cls == "QueryCanceled" or (primary and "statement timeout" in primary.lower()):
            return QueryTimeoutError("The query took too long and was cancelled. Try narrowing it with filters or a LIMIT.")
        if operational and not primary:
            return DatabaseUnavailableError("The database is not reachable right now.")
        if cls in ("InsufficientPrivilege", "ReadOnlySqlTransaction"):
            return SQLRejectedError("The database refused the operation: it is not permitted for the read-only account.")
        message = (primary or "The database could not run this query.")[:300]
        return QueryExecutionError(f"Database error: {message}")
