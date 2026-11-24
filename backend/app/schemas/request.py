from __future__ import annotations

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, examples=["Show the top 10 customers by total spending."])
    top_k: int | None = Field(None, ge=1, le=50, description="Schema documents to retrieve (default from settings).")


class ChatRequest(GenerateRequest):
    conversation_id: str | None = Field(None, max_length=64, description="Omit to start a new conversation.")
    regenerate_of: int | None = Field(None, description="History id of the answer this request replaces.")


class ValidateRequest(BaseModel):
    sql: str = Field(..., min_length=1, max_length=20000)


class ExecuteRequest(BaseModel):
    sql: str = Field(..., min_length=1, max_length=20000)
    history_id: int | None = None
    max_rows: int | None = Field(None, ge=1, le=100000)


class RefreshRequest(BaseModel):
    reindex: bool = True
