"""Security tests that need a real PostgreSQL (the disposable *_test database created by conftest)."""
import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.errors import QueryTimeoutError, SQLRejectedError
from app.database.initialization import to_psycopg_dsn
from app.services.execution_service import ExecutionService
from app.services.validation_service import ValidationService


@pytest.fixture()
def executor(engine, settings, real_schema):
    return ExecutionService(engine, ValidationService(settings), lambda: real_schema, settings)


# --- the database role itself is read-only, independent of the application code --------------------------------
@pytest.mark.parametrize("stmt", [
    "DELETE FROM customers",
    "UPDATE products SET price = 0",
    "INSERT INTO categories (category_name) VALUES ('x')",
    "DROP TABLE orders",
    "TRUNCATE payments",
    "CREATE TABLE evil (i int)",
    "ALTER TABLE customers ADD COLUMN x int",
])
def test_read_only_role_cannot_write_even_if_validation_is_bypassed(engine, stmt):
    with pytest.raises(DBAPIError):
        with engine.connect() as conn:
            conn.exec_driver_sql(stmt)


def test_read_only_role_is_not_superuser_and_cannot_create_in_schema(test_database):
    with psycopg.connect(to_psycopg_dsn(test_database["ro"]), autocommit=True) as conn:
        assert conn.execute("SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = current_user").fetchone() == (False, False, False)
        assert conn.execute("SELECT has_schema_privilege(current_user, 'public', 'CREATE')").fetchone()[0] is False
        assert conn.execute("SELECT has_table_privilege(current_user, 'customers', 'INSERT')").fetchone()[0] is False
        assert conn.execute("SELECT has_table_privilege(current_user, 'customers', 'SELECT')").fetchone()[0] is True
        assert conn.execute("SHOW default_transaction_read_only").fetchone()[0] == "on"


def test_read_only_role_survives_attempt_to_switch_transaction_mode(engine):
    # even an explicit READ WRITE transaction request cannot make the role able to write: it lacks privileges
    with pytest.raises(DBAPIError):
        with engine.connect() as conn:
            conn.exec_driver_sql("SET TRANSACTION READ WRITE")
            conn.exec_driver_sql("DELETE FROM customers")


# --- the backend refuses before the database is even reached ------------------------------------------------
@pytest.mark.parametrize("sql", ["DROP TABLE customers", "DELETE FROM orders", "UPDATE customers SET city='x'",
                                 "INSERT INTO categories (category_name) VALUES ('x')", "SELECT 1; DELETE FROM orders",
                                 "SELECT pg_sleep(5)", "SELECT * FROM pg_shadow"])
def test_executor_rejects_unsafe_sql_with_validation_details(executor, sql):
    with pytest.raises(SQLRejectedError) as err:
        executor.execute(sql)
    assert err.value.details["validation"]["valid"] is False


def test_data_is_untouched_after_attack_attempts(executor, test_database):
    for sql in ["DELETE FROM customers", "DROP TABLE orders", "TRUNCATE payments"]:
        with pytest.raises(SQLRejectedError):
            executor.execute(sql)
    with psycopg.connect(to_psycopg_dsn(test_database["admin"])) as conn:
        assert conn.execute("SELECT count(*) FROM customers").fetchone()[0] == 520
        assert conn.execute("SELECT count(*) FROM orders").fetchone()[0] == 1650


# --- limits ----------------------------------------------------------------------------------------------------------
def test_result_row_limit_is_enforced_and_flagged(executor, settings):
    r = executor.execute("SELECT * FROM customers ORDER BY customer_id")
    assert r.row_count == settings.max_result_rows == 50 and r.truncated is True
    assert r.rows[0][0] == 1


def test_caller_cannot_raise_the_server_side_row_limit(executor, settings):
    assert executor.execute("SELECT * FROM customers", max_rows=100000).row_count == settings.max_result_rows


def test_smaller_limit_and_small_results_are_not_truncated(executor):
    assert executor.execute("SELECT * FROM customers", max_rows=7).row_count == 7
    r = executor.execute("SELECT category_name FROM categories")
    assert r.row_count == 12 and r.truncated is False


def test_statement_timeout_cancels_long_queries(executor):
    with pytest.raises(QueryTimeoutError):
        executor.execute("SELECT COUNT(*) FROM generate_series(1, 400000000) g(i)")


def test_expensive_plans_are_refused_before_running(executor, settings):
    settings.max_plan_cost = 1000.0
    with pytest.raises(SQLRejectedError) as err:
        executor.execute("SELECT COUNT(*) FROM orders a, orders b, orders c")
    assert "too expensive" in err.value.message


def test_connection_is_reusable_after_errors(executor):
    with pytest.raises(Exception):
        executor.execute("SELECT 1/0")
    assert executor.execute("SELECT 1 AS one").rows == [[1]]


def test_literals_with_percent_and_colon_reach_the_database_unchanged(executor):
    r = executor.execute("SELECT 'a:b %s %%' AS t, 5 % 3 AS m")
    assert r.rows == [["a:b %s %%", 2]]
    assert executor.execute("SELECT COUNT(*) FROM customers WHERE email LIKE '%@example.com'").rows[0][0] == 520


def test_errors_do_not_leak_credentials_or_internals(executor):
    with pytest.raises(Exception) as err:
        executor.execute("SELECT 1/0")
    msg = str(getattr(err.value, "message", err.value))
    for secret in ("ro_test_pass", "postgresql", "Traceback", "psycopg"):
        assert secret not in msg
