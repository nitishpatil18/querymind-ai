from fastapi import APIRouter, Depends

from app.api.deps import Container, get_container
from app.database.connection import check_connection
from app.schemas.response import ComponentHealth, HealthResponse, SettingsResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Backend and dependency health")
def health(c: Container = Depends(get_container)) -> HealthResponse:
    db = check_connection(c.engine, c.settings)
    state = c.indexer.state
    components = {
        "api": ComponentHealth(status="ok"),
        "database": ComponentHealth(status="ok" if db.connected else "down", detail=db.error),
        "vector_index": ComponentHealth(
            status="ok" if state.status == "ready" else "degraded",
            detail=None if state.status == "ready" else f"index status: {state.status}" + (f" ({state.error})" if state.error else ""),
        ),
        "llm": ComponentHealth(
            status="ok" if c.settings.llm_configured else "degraded",
            detail=None if c.settings.llm_configured else "GOOGLE_API_KEY is not configured",
        ),
    }
    overall = "down" if not db.connected else ("ok" if all(v.status == "ok" for v in components.values()) else "degraded")
    return HealthResponse(status=overall, components=components)


@router.get("/api/settings", response_model=SettingsResponse, summary="Non-secret runtime configuration")
def runtime_settings(c: Container = Depends(get_container)) -> SettingsResponse:
    s = c.settings
    return SettingsResponse(
        app_env=s.app_env, llm_provider=s.llm_provider, llm_model=s.llm_model, llm_api_key_configured=s.llm_configured,
        embedding_provider=s.embedding_provider, embedding_model=s.embedding_model, retrieval_top_k=s.retrieval_top_k,
        retrieval_max_tables=s.retrieval_max_tables, max_result_rows=s.max_result_rows,
        statement_timeout_ms=s.statement_timeout_ms, generation_max_attempts=s.generation_max_attempts,
        conversation_context_turns=s.conversation_context_turns, allowed_schemas=s.allowed_schemas,
    )
