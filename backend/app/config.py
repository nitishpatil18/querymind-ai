"""Centralised application configuration (environment variables / .env)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # --- application -----------------------------------------------------
    app_name: str = "QueryMind AI"
    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    data_dir: Path = Path("data")

    # --- database ------------------------------------------------------------
    # Runtime connection: must be the READ-ONLY role. Used for schema inspection and query execution.
    database_url: SecretStr = SecretStr("postgresql+psycopg://querymind_ro:change_me_ro@localhost:5432/querymind")
    # Admin connection: only used by init / seed scripts, never by the running API.
    database_admin_url: SecretStr | None = None
    app_schemas: str = "public"  # comma separated list of schemas the app may query

    # --- LLM -------------------------------------------------------------------
    llm_provider: str = "gemini"  # gemini | ollama
    llm_model: str = "gemini-3.8-flash"
    # Gemini 3+ only: minimal | low | medium | high. Empty keeps the model default. Lower is faster, high is slower.
    llm_thinking_level: str | None = None
    google_api_key: SecretStr | None = None
    ollama_base_url: str = "http://localhost:11434"
    llm_temperature: float = 0.0
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 1  # transport-level retries inside the client
    generation_max_attempts: int = Field(3, ge=1, le=6)  # parse/validation repair attempts

    # --- embeddings / RAG ----------------------------------------------------
    embedding_provider: str = "sentence-transformers"  # sentence-transformers | hashing (offline tests only)
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    chroma_path: Path | None = None  # defaults to <data_dir>/chroma
    chroma_collection: str = "schema_docs"
    retrieval_top_k: int = Field(10, ge=1, le=50)  # schema documents fetched from the vector store
    retrieval_max_tables: int = Field(4, ge=1, le=20)  # tables kept from the ranked documents
    retrieval_expand_max: int = Field(3, ge=0, le=10)  # extra tables added via foreign-key expansion
    column_chunk_size: int = Field(12, ge=4)  # wide tables are split into column chunks of this size

    # --- execution limits ----------------------------------------------------
    max_result_rows: int = Field(1000, ge=1, le=100000)
    statement_timeout_ms: int = Field(15000, ge=100)
    max_plan_cost: float = 10_000_000.0  # planner cost above which a query is refused
    max_sql_length: int = 10000

    # --- conversation / history ----------------------------------------------
    conversation_context_turns: int = Field(4, ge=0, le=20)
    history_db_url: str | None = None  # defaults to sqlite in data_dir

    # --- evaluation ----------------------------------------------------------
    golden_questions_path: Path = Path("evaluation/golden_questions.json")
    evaluation_reports_dir: Path = Path("evaluation/reports")

    # --- derived helpers -------------------------------------------------------
    @property
    def allowed_schemas(self) -> list[str]:
        return [s.strip() for s in self.app_schemas.split(",") if s.strip()] or ["public"]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def chroma_dir(self) -> Path:
        return self.chroma_path or (self.data_dir / "chroma")

    @property
    def history_url(self) -> str:
        return self.history_db_url or f"sqlite:///{(self.data_dir / 'app_state.sqlite').resolve()}"

    @property
    def llm_configured(self) -> bool:
        if self.llm_provider == "gemini":
            return bool(self.google_api_key and self.google_api_key.get_secret_value().strip())
        return True  # local providers need no key

    def secret_values(self) -> list[str]:
        """Secrets that must never appear in logs or API responses."""
        vals: list[str] = []
        for s in (self.database_url, self.database_admin_url, self.google_api_key):
            if s is not None and s.get_secret_value():
                vals.append(s.get_secret_value())
        return vals


@lru_cache
def get_settings() -> Settings:
    return Settings()
