"""Re-discover the database schema and rebuild the ChromaDB vector index.

Usage (from backend/):  python -m scripts.rebuild_index
"""
from app.api.deps import build_container
from app.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level, settings.secret_values())
    container = build_container(settings)
    try:
        status = container.schema_service.refresh(reindex=True)
    except AppError as exc:
        print(f"Indexing failed: {exc.message}")
        return 1
    i = status.index
    print(
        f"indexed {i.tables_indexed} tables as {i.documents_indexed} documents "
        f"with {i.embedding_provider}/{i.embedding_model} in {i.duration_ms} ms (fingerprint {status.schema_fingerprint})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
