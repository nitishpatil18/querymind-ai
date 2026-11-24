"""Security tests for the AST validator (no database needed)."""
import pytest

from app.config import Settings
from app.services.validation_service import ValidationService
from tests.helpers import make_schema

V = ValidationService(Settings(_env_file=None))
SCHEMA = make_schema()


def check(sql):
    return V.validate(sql, SCHEMA)


@pytest.mark.parametrize("sql", [
    "DROP TABLE customers",
    "DELETE FROM customers",
    "DELETE FROM customers WHERE 1=1",
    "UPDATE customers SET city = 'x'",
    "INSERT INTO customers (first_name) VALUES ('x')",
    "TRUNCATE TABLE orders",
    "ALTER TABLE customers ADD COLUMN x int",
    "CREATE TABLE t AS SELECT * FROM customers",
    "CREATE INDEX i ON customers (city)",
    "GRANT ALL ON customers TO PUBLIC",
    "REVOKE ALL ON customers FROM PUBLIC",
    "COPY customers TO '/tmp/x'",
    "SET ROLE postgres",
    "EXPLAIN ANALYZE SELECT 1",
    "VALUES (1)",
])
def test_non_select_statements_rejected(sql):
    r = check(sql)
    assert not r.valid and r.errors[0].code in ("not_read_only", "forbidden_statement")


@pytest.mark.parametrize("sql", [
    "SELECT 1; DROP TABLE customers",
    "SELECT * FROM customers; SELECT * FROM orders",
    "SELECT 1;; DELETE FROM customers",
])
def test_multiple_statements_rejected(sql):
    r = check(sql)
    assert not r.valid and r.errors[0].code == "multiple_statements"


@pytest.mark.parametrize("sql", [
    "WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d",
    "WITH u AS (UPDATE customers SET city='x' RETURNING *) SELECT * FROM u",
    "WITH i AS (INSERT INTO customers (first_name) VALUES ('x') RETURNING *) SELECT * FROM i",
    "SELECT * INTO backup FROM customers",
    "SELECT * FROM customers FOR UPDATE",
    "SELECT * FROM customers FOR SHARE",
])
def test_data_modifying_or_locking_selects_rejected(sql):
    r = check(sql)
    assert not r.valid and r.errors[0].code == "forbidden_statement"


@pytest.mark.parametrize("sql", [
    "SELECT pg_sleep(10)",
    "SELECT pg_catalog.pg_sleep(10)",
    'SELECT "pg_sleep"(10)',
    "SELECT PG_SLEEP(10)",
    "SELECT pg_read_file('/etc/passwd')",
    "SELECT pg_ls_dir('/')",
    "SELECT lo_import('/etc/passwd')",
    "SELECT * FROM dblink('host=x', 'select 1') AS t(a int)",
    "SELECT set_config('statement_timeout', '0', false)",
    "SELECT current_setting('data_directory')",
    "SELECT nextval('seq')",
    "SELECT pg_terminate_backend(1)",
    "SELECT query_to_xml('select * from customers', true, false, '')",
    "SELECT customer_id FROM customers WHERE pg_sleep(1) IS NOT NULL",
    "SELECT unknown_udf(1)",
])
def test_dangerous_or_unlisted_functions_rejected(sql):
    r = check(sql)
    assert not r.valid and r.errors[0].code == "forbidden_function"


@pytest.mark.parametrize("sql", [
    "SELECT * FROM pg_catalog.pg_user",
    "SELECT * FROM pg_user",
    "SELECT * FROM pg_shadow",
    "SELECT * FROM pg_stat_activity",
    "SELECT * FROM information_schema.tables",
    "SELECT * FROM information_schema.columns",
    "SELECT * FROM pg_catalog.pg_class",
])
def test_system_catalogs_rejected(sql):
    r = check(sql)
    assert not r.valid and r.errors[0].code == "system_catalog"


def test_unauthorised_schema_and_database_rejected():
    assert check("SELECT * FROM secret.customers").errors[0].code == "unauthorized_schema"
    assert check("SELECT * FROM otherdb.public.customers").errors[0].code == "unauthorized_schema"


def test_unknown_table_and_column_rejected():
    assert check("SELECT * FROM users").errors[0].code == "unknown_table"
    assert check("SELECT phone FROM customers").errors[0].code == "unknown_column"
    assert check("SELECT c.phone FROM customers c").errors[0].code == "unknown_column"
    assert check("SELECT customer_id FROM customers c JOIN orders o ON c.customer_id = o.customer_id").errors[0].code == "unknown_column"


@pytest.mark.parametrize("sql", ["", "   ", "SELEC * FROM customers", "SELECT * FROM", "SELECT 'unterminated FROM customers"])
def test_empty_and_syntactically_invalid_rejected(sql):
    r = check(sql)
    assert not r.valid and r.errors[0].code in ("empty", "syntax_error")


def test_oversized_statement_rejected():
    assert check("SELECT " + "1," * 6000 + "1").errors[0].code == "too_long"


def test_comment_tricks_do_not_hide_statements():
    assert not check("SELECT 1 /* */; DROP TABLE customers --").valid
    assert check("SELECT 1 /* ; DROP TABLE customers */").valid  # a comment is only a comment


def test_excessive_joins_rejected():
    joins = " ".join(f"JOIN orders o{i} ON o{i}.customer_id = c.customer_id" for i in range(12))
    assert check(f"SELECT c.customer_id FROM customers c {joins}").errors[0].code == "too_complex"


@pytest.mark.parametrize("sql", [
    "SELECT c.first_name, SUM(o.total_amount) AS total FROM customers c JOIN orders o ON o.customer_id = c.customer_id GROUP BY c.first_name ORDER BY total DESC LIMIT 10",
    "WITH m AS (SELECT DATE_TRUNC('month', order_date) AS mon, SUM(total_amount) AS rev FROM orders GROUP BY 1) SELECT * FROM m",
    "SELECT customer_id FROM customers EXCEPT SELECT customer_id FROM orders",
    "SELECT product_name, RANK() OVER (PARTITION BY category_id ORDER BY price DESC) FROM products",
    "SELECT * FROM customers WHERE email LIKE '%@example.com' AND state ILIKE 'kar%'",
    "SELECT COUNT(DISTINCT customer_id), AVG(total_amount), MIN(order_date) FROM orders WHERE order_date >= CURRENT_DATE - INTERVAL '6 months'",
    "SELECT * FROM public.customers",
    "(SELECT 1)",
])
def test_legitimate_analytical_queries_accepted(sql):
    r = check(sql)
    assert r.valid, r.error_summary
    assert r.normalized_sql and r.statement_type in ("SELECT", "UNION", "EXCEPT", "SUBQUERY", "INTERSECT")


def test_result_reports_tables_used():
    r = check("SELECT c.first_name FROM customers c JOIN orders o ON o.customer_id = c.customer_id")
    assert r.tables == ["customers", "orders"]


def test_cte_names_are_not_treated_as_tables():
    r = check("WITH recent AS (SELECT * FROM orders) SELECT * FROM recent")
    assert r.valid and r.tables == ["orders"]
