from app.database.connection import check_connection
from app.database.inspector import SchemaInspector
from app.rag.document_generator import generate_documents


def test_connection_reports_read_only_role(engine, settings):
    st = check_connection(engine, settings)
    assert st.connected and st.database == "querymind_test" and st.user == "querymind_ro" and st.read_only is True
    assert "ro_test_pass" not in st.model_dump_json()


def test_connection_failure_is_reported_without_credentials(settings):
    from app.database.connection import build_engine

    bad = build_engine("postgresql+psycopg://querymind_ro:s3cr3tpw@127.0.0.1:1/nope", settings)
    st = check_connection(bad, settings)
    assert not st.connected and "s3cr3tpw" not in st.model_dump_json() and "Cannot connect" in st.error


def test_schema_discovery_finds_all_tables_keys_and_relationships(real_schema):
    assert real_schema.database == "querymind_test"
    assert set(real_schema.table_names) == {"customers", "categories", "products", "orders", "order_items", "payments"}
    orders = real_schema.table("orders")
    assert orders.primary_key == ["order_id"]
    assert [(f.columns, f.referred_table) for f in orders.foreign_keys] == [(["customer_id"], "customers")]
    pairs = {(r.child_table, r.parent_table) for r in real_schema.relationships}
    assert pairs == {("orders", "customers"), ("order_items", "orders"), ("order_items", "products"), ("payments", "orders"), ("products", "categories")}


def test_schema_discovery_reads_types_comments_indexes_and_constraints(real_schema):
    cust = real_schema.table("customers")
    cols = {c.name: c for c in cust.columns}
    assert cols["registration_date"].type == "DATE" and cols["registration_date"].comment == "Date the customer registered."
    assert cols["email"].unique and cols["customer_id"].primary_key and not cols["first_name"].nullable
    assert "Registered customers" in cust.comment or "customers" in cust.comment.lower()
    assert any(i.name == "idx_customers_state" for i in cust.indexes)
    status = {c.name: c for c in real_schema.table("orders").columns}["order_status"]
    assert set(status.allowed_values) == {"pending", "processing", "shipped", "completed", "cancelled"}
    assert any(c.kind == "check" for c in real_schema.table("orders").constraints)
    assert real_schema.table("payments").columns[0].type == "INTEGER"


def test_fingerprint_is_stable_and_changes_with_structure(engine, settings, test_database):
    import psycopg
    from app.database.initialization import to_psycopg_dsn

    a = SchemaInspector(engine, ["public"]).inspect()
    b = SchemaInspector(engine, ["public"]).inspect()
    assert a.fingerprint == b.fingerprint
    with psycopg.connect(to_psycopg_dsn(test_database["admin"]), autocommit=True) as conn:
        conn.execute("ALTER TABLE categories ADD COLUMN temp_col text")
    try:
        c = SchemaInspector(engine, ["public"]).inspect()
        assert c.fingerprint != a.fingerprint and "temp_col" in [x.name for x in c.table("categories").columns]
    finally:
        with psycopg.connect(to_psycopg_dsn(test_database["admin"]), autocommit=True) as conn:
            conn.execute("ALTER TABLE categories DROP COLUMN temp_col")


def test_inspection_works_on_an_unrelated_schema(test_database):
    """The inspector is not tied to the demo database: build a different schema and discover it."""
    import psycopg
    from sqlalchemy.engine import make_url
    from app.config import Settings
    from app.database.connection import build_engine
    from app.database.initialization import ensure_readonly_role, to_psycopg_dsn

    with psycopg.connect(to_psycopg_dsn(test_database["admin"]), autocommit=True) as conn:
        conn.execute("CREATE SCHEMA IF NOT EXISTS hr")
        conn.execute("CREATE TABLE hr.employees (id serial PRIMARY KEY, name text NOT NULL, manager_id int REFERENCES hr.employees(id))")
        conn.execute("COMMENT ON TABLE hr.employees IS 'Employees and their managers.'")
        conn.execute("GRANT USAGE ON SCHEMA hr TO querymind_ro")
        conn.execute("GRANT SELECT ON ALL TABLES IN SCHEMA hr TO querymind_ro")
    try:
        s = Settings(_env_file=None, database_url=test_database["ro"], app_schemas="hr")
        info = SchemaInspector(build_engine(test_database["ro"], s), ["hr"]).inspect()
        assert info.table_names == ["employees"] and info.table("employees").comment == "Employees and their managers."
        assert info.relationships[0].child_table == "employees" == info.relationships[0].parent_table
        docs = generate_documents(info)
        assert any("Table: employees" in d.text for d in docs)
    finally:
        with psycopg.connect(to_psycopg_dsn(test_database["admin"]), autocommit=True) as conn:
            conn.execute("DROP SCHEMA hr CASCADE")


def test_documents_for_real_schema(real_schema):
    docs = generate_documents(real_schema)
    ids = {d.doc_id for d in docs}
    assert "public.customers::table" in ids and len(docs) == 6 + 5
    orders_doc = next(d for d in docs if d.doc_id == "public.orders::table")
    assert "allowed values: 'pending', 'processing', 'shipped', 'completed', 'cancelled'" in orders_doc.text
    assert "Each order belongs to one customer" in orders_doc.text
