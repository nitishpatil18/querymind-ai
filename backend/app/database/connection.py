"""SQLAlchemy engine management and connectivity checks."""
from __future__ import annotations

import logging
import time
from functools import lru_cache

from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

from app.config import Settings, get_settings
from app.core.logging import redact

logger = logging.getLogger(__name__)


class DatabaseStatus(BaseModel):
    connected: bool
    database: str | None = None
    server_version: str | None = None
    user: str | None = None
    read_only: bool | None = None
    schemas: list[str] = []
    latency_ms: float | None = None
    error: str | None = None


def build_engine(url: str, settings: Settings, *, read_only: bool = True) -> Engine:
    options = []
    if read_only:
        options.append("-c default_transaction_read_only=on")
        options.append(f"-c statement_timeout={settings.statement_timeout_ms}")
        options.append("-c idle_in_transaction_session_timeout=30000")
    connect_args = {"connect_timeout": 5, "application_name": "querymind-ai"}
    if options:
        connect_args["options"] = " ".join(options)
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5, connect_args=connect_args, future=True)


@lru_cache
def get_engine() -> Engine:
    """Read-only engine used by the running application."""
    settings = get_settings()
    return build_engine(settings.database_url.get_secret_value(), settings, read_only=True)


def reset_engine() -> None:
    try:
        get_engine().dispose()
    finally:
        get_engine.cache_clear()


def check_connection(engine: Engine | None = None, settings: Settings | None = None) -> DatabaseStatus:
    settings = settings or get_settings()
    engine = engine or get_engine()
    started = time.perf_counter()
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT current_database(), current_user, current_setting('server_version'), "
                    "current_setting('transaction_read_only')"
                )
            ).one()
        return DatabaseStatus(
            connected=True,
            database=row[0],
            user=row[1],
            server_version=row[2],
            read_only=str(row[3]).lower() == "on",
            schemas=settings.allowed_schemas,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )
    except Exception as exc:  # connection refused, auth failure, DNS...
        logger.warning("database connectivity check failed: %s", redact(str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__))
        return DatabaseStatus(connected=False, error="Cannot connect to the database. Check that PostgreSQL is running and DATABASE_URL is correct.")


def describe_target(url: str) -> str:
    """Host/db description safe to show to users (no credentials)."""
    u = make_url(url)
    return f"{u.host or 'localhost'}:{u.port or 5432}/{u.database}"
