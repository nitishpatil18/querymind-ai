from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import psycopg
import pytest
from sqlalchemy.engine import make_url

from app.api.deps import build_container
from app.config import Settings
from app.database.connection import build_engine
from app.database.initialization import initialize, to_psycopg_dsn
from app.database.inspector import SchemaInspector
from app.main import create_app
from app.rag.embeddings import HashingEmbedder
from tests.helpers import ScriptedLLM, make_schema

RO_USER, RO_PASSWORD = "querymind_ro", "ro_test_pass"
TEST_DB = "querymind_test"


@pytest.fixture(scope="session")
def admin_server_url():
    """Admin URL (database 'postgres') of a throwaway PostgreSQL server.

    Uses TEST_DATABASE_ADMIN_URL when set (for example the docker-compose Postgres on localhost); otherwise starts
    an ephemeral embedded server (pixeltable-pgserver). Tests are skipped when neither is available.
    """
    env = os.environ.get("TEST_DATABASE_ADMIN_URL")
    if env:
        yield env
        return
    try:
        import pixeltable_pgserver
    except ImportError:
        pytest.skip("set TEST_DATABASE_ADMIN_URL or install pixeltable-pgserver for database tests")
    path = Path(tempfile.mkdtemp(prefix="qm_pg_"))
    server = pixeltable_pgserver.get_server(path, cleanup_mode="stop")
    uri = server.get_uri()  # postgresql://postgres:@/postgres?host=/path
    url = make_url(uri).set(drivername="postgresql+psycopg")
    yield url.render_as_string(hide_password=False)
    server.cleanup()
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(scope="session")
def test_database(admin_server_url):
    """Fresh `querymind_test` database with schema, deterministic seed data and the read-only role."""
    base = make_url(admin_server_url)
    assert TEST_DB.endswith("_test")  # safety: only ever (re)create a *_test database
    with psycopg.connect(to_psycopg_dsn(base.set(database="postgres").render_as_string(hide_password=False)), autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{TEST_DB}"')
    admin_db_url = base.set(database=TEST_DB).render_as_string(hide_password=False)
    initialize(admin_db_url, RO_USER, RO_PASSWORD, seed=True, force=True)
    ro_url = base.set(database=TEST_DB, username=RO_USER, password=RO_PASSWORD).render_as_string(hide_password=False)
    return {"admin": admin_db_url, "ro": ro_url}


@pytest.fixture()
def settings(test_database, tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=test_database["ro"],
        database_admin_url=test_database["admin"],
        data_dir=tmp_path,
        chroma_path=tmp_path / "chroma",
        history_db_url=f"sqlite:///{tmp_path / 'history.sqlite'}",
        embedding_provider="hashing",
        evaluation_reports_dir=tmp_path / "reports",
        golden_questions_path=Path(__file__).resolve().parents[1] / "evaluation" / "golden_questions.json",
        statement_timeout_ms=3000,
        max_result_rows=50,
        google_api_key=None,
    )


@pytest.fixture()
def engine(settings):
    eng = build_engine(settings.database_url.get_secret_value(), settings)
    yield eng
    eng.dispose()


@pytest.fixture()
def real_schema(engine, settings):
    return SchemaInspector(engine, settings.allowed_schemas).inspect()


@pytest.fixture()
def mini_schema():
    return make_schema()


@pytest.fixture()
def llm():
    return ScriptedLLM()


@pytest.fixture()
def container(settings, engine, llm):
    return build_container(settings, engine=engine, embedder=HashingEmbedder(), llm=llm)


@pytest.fixture()
def client(container):
    from fastapi.testclient import TestClient

    app = create_app(container, warm_up=False)
    with TestClient(app) as c:
        yield c
