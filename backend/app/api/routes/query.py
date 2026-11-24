from fastapi import APIRouter, Depends

from app.api.deps import Container, get_container
from app.schemas.request import ExecuteRequest, GenerateRequest, ValidateRequest
from app.schemas.response import ExecuteResponse, GenerateResponse
from app.services.validation_service import ValidationResult

router = APIRouter(prefix="/api/query", tags=["query"])


@router.post("/generate", response_model=GenerateResponse, summary="Generate SQL for a single question (no conversation context)")
def generate(body: GenerateRequest, c: Container = Depends(get_container)) -> GenerateResponse:
    return c.query_service.generate(body.question, top_k=body.top_k)


@router.post("/validate", response_model=ValidationResult, summary="Validate SQL without executing it")
def validate(body: ValidateRequest, c: Container = Depends(get_container)) -> ValidationResult:
    return c.query_service.validate(body.sql)


@router.post("/execute", response_model=ExecuteResponse, summary="Execute validated read-only SQL (explicit user action)")
def execute(body: ExecuteRequest, c: Container = Depends(get_container)) -> ExecuteResponse:
    return c.query_service.execute(body.sql, history_id=body.history_id, max_rows=body.max_rows)
