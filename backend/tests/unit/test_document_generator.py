from app.rag.document_generator import generate_documents, render_table_document, relationship_sentences


def test_one_document_per_narrow_table_plus_relationships(mini_schema):
    docs = generate_documents(mini_schema)
    table_docs = [d for d in docs if d.metadata["doc_type"] == "table"]
    rel_docs = [d for d in docs if d.metadata["doc_type"] == "relationship"]
    assert {d.metadata["table"] for d in table_docs} == set(mini_schema.table_names)
    assert len(rel_docs) == len(mini_schema.relationships) == 4


def test_table_document_has_columns_keys_and_allowed_values(mini_schema):
    text = render_table_document(mini_schema.table("orders"), mini_schema)
    assert text.startswith("Table: orders")
    assert "Description: Customer orders." in text
    assert "- order_id: INTEGER, PRIMARY KEY" in text
    assert "- customer_id: INTEGER, FOREIGN KEY, NOT NULL" in text
    assert "allowed values: 'pending', 'completed', 'cancelled'" in text
    assert "Foreign key: orders.customer_id references customers.customer_id." in text


def test_relationship_sentences_cover_both_directions(mini_schema):
    parent = relationship_sentences(mini_schema.table("customers"), mini_schema)
    child = relationship_sentences(mini_schema.table("orders"), mini_schema)
    assert any("One customer can have multiple orders" in s for s in parent)
    assert any("Each order belongs to one customer" in s for s in child)
    assert any("One order can have multiple order_items" in s for s in child)


def test_wide_tables_are_chunked_and_keep_table_context(mini_schema):
    docs = generate_documents(mini_schema, column_chunk_size=3)
    chunks = [d for d in docs if d.metadata["doc_type"] == "columns" and d.metadata["table"] == "customers"]
    assert len(chunks) == 3  # 7 columns / 3
    assert all(c.text.startswith("Table: customers") for c in chunks)
    overview = next(d for d in docs if d.doc_id.endswith("customers::table"))
    assert "Column names:" in overview.text and "registration_date" in overview.text


def test_documents_contain_schema_metadata_only(mini_schema):
    for d in generate_documents(mini_schema):
        assert set(d.metadata) >= {"schema", "table", "doc_type", "tables"}
        assert "@example.com" not in d.text  # no row data is ever indexed
