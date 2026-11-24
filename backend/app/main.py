"""FastAPI application factory."""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.deps import Container, build_container
from app.api.routes import chat, database, evaluation, health, history, query, schema
from app.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging, redact

logger = logging.getLogger(__name__)


def _warm_up(container: Container) -> None:
    """Discover the schema and (re)build the vector index in the background; failures are recorded, not fatal."""
    try:
        container.schema_service.ensure_index()
    except AppError as exc:
        logger.warning("startup indexing skipped: %s", exc.message)
    except Exception:
        logger.exception("startup indexing failed")


def create_app(container: Container | None = None, *, warm_up: bool = True) -> FastAPI:
    settings = container.settings if container else get_settings()
    configure_logging(settings.log_level, settings.secret_values())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.container = container or build_container(settings)
        if warm_up:
            threading.Thread(target=_warm_up, args=(app.state.container,), daemon=True, name="warm-up").start()
        yield

    app = FastAPI(
        title="QueryMind AI",
        description="Schema-aware natural-language-to-SQL with retrieval-augmented generation. "
        "Generated SQL is validated by an AST-based safety layer and runs only on a read-only connection.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origin_list, allow_methods=["GET", "POST"], allow_headers=["Content-Type"]
    )

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        if exc.status_code >= 500:
            logger.warning("request failed: %s (%s)", exc.code, exc.message)
        return JSONResponse(
            status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}}
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        fields = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "invalid_request", "message": "The request is not valid.", "details": {"fields": fields}}},
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        logger.error("unhandled error: %s", redact(f"{exc.__class__.__name__}: {exc}"))
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "An unexpected error occurred.", "details": {}}},
        )

    for r in (health.router, database.router, schema.router, query.router, chat.router, history.router, evaluation.router):
        app.include_router(r)
    return app


app = create_app()
