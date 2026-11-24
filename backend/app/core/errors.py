"""Application error types. Messages are user-safe: no secrets, no stack traces."""
from __future__ import annotations


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class SQLRejectedError(AppError):
    status_code = 422
    code = "sql_rejected"


class DatabaseUnavailableError(AppError):
    status_code = 503
    code = "database_unavailable"


class QueryTimeoutError(AppError):
    status_code = 408
    code = "query_timeout"


class QueryExecutionError(AppError):
    status_code = 400
    code = "query_failed"


class LLMNotConfiguredError(AppError):
    status_code = 503
    code = "llm_not_configured"


class LLMAuthError(AppError):
    status_code = 502
    code = "llm_auth_failed"


class LLMOverloadedError(AppError):
    status_code = 503
    code = "llm_overloaded"


class LLMModelNotFoundError(AppError):
    status_code = 502
    code = "llm_model_not_found"


class LLMRateLimitError(AppError):
    status_code = 429
    code = "llm_rate_limited"


class LLMQuotaExhaustedError(LLMRateLimitError):
    """The provider says the daily quota is used up: waiting a few seconds will not help."""

    code = "llm_quota_exhausted"


class LLMTimeoutError(AppError):
    status_code = 504
    code = "llm_timeout"


class LLMError(AppError):
    status_code = 502
    code = "llm_error"


class LLMOutputError(AppError):
    status_code = 502
    code = "llm_invalid_output"


class EmbeddingError(AppError):
    status_code = 503
    code = "embedding_error"


class VectorStoreError(AppError):
    status_code = 503
    code = "vector_store_error"


class IndexNotReadyError(AppError):
    status_code = 409
    code = "index_not_ready"
