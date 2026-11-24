"""End-to-end API tests: real PostgreSQL + real ChromaDB + hashing embedder + scripted LLM."""
import json
import time

import pytest

from app.api.deps import build_container
from app.main import create_app
from app.rag.embeddings import HashingEmbedder
from tests.helpers import gen_json

TOP_SPENDERS = (
    "SELECT c.customer_id, c.first_name, SUM(o.total_amount) AS total_spent FROM customers c "
    "JOIN orders o ON o.customer_id = c.customer_id GROUP BY c.customer_id, c.first_name ORDER BY total_spent DESC LIMIT 10"
)
KARNATAKA = (
    "SELECT c.customer_id, c.first_name, SUM(o.total_amount) AS total_spent FROM customers c "
    "JOIN orders o ON o.customer_id = c.customer_id WHERE c.state = 'Karnataka' "
    "GROUP BY c.customer_id, c.first_name ORDER BY total_spent DESC LIMIT 10"
)


def question_of(prompt: str) -> str:
    return prompt.rsplit("Question:", 1)[1].strip() if "Question:" in prompt else prompt


# ---------------------------------------------------------------- health, database, schema
def test_health_reports_components_and_degrades_without_llm_key(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["components"]["database"]["status"] == "ok" and body["components"]["api"]["status"] == "ok"
    assert body["components"]["llm"]["status"] == "degraded" and body["status"] == "degraded"
    assert "ro_test_pass" not in r.text


def test_database_status_endpoint(client):
    body = client.get("/api/database/status").json()
    assert body["connected"] and body["read_only"] and body["database"] == "querymind_test"


def test_schema_endpoints(client):
    schema = client.get("/api/schema").json()
    assert len(schema["tables"]) == 6 and len(schema["relationships"]) == 5
    detail = client.get("/api/schema/tables/orders").json()
    assert detail["table"]["name"] == "orders" and "Table: orders" in detail["document"] and detail["relationships"]
    assert client.get("/api/schema/tables/nonexistent").status_code == 404
    bad = client.get("/api/schema/tables/bad;name")
    assert bad.status_code in (400, 404)


def test_schema_refresh_builds_index_and_status_reflects_it(client):
    assert client.get("/api/schema/status").json()["index"]["status"] == "not_indexed"
    st = client.post("/api/schema/refresh").json()
    assert st["index"]["status"] == "ready" and st["index"]["tables_indexed"] == 6 and st["index"]["documents_indexed"] == 6 + 5
    assert st["index_is_current"] is True and st["vector_documents"] == 11
    assert st["index"]["embedding_provider"] == "hashing" and st["index"]["last_indexed_at"]


# ---------------------------------------------------------------- generate / validate / execute
def test_generate_validate_execute_happy_path(client, llm):
    llm.queue = [gen_json(TOP_SPENDERS, explanation="Sums order totals per customer.", assumptions=["Spending = sum of orders.total_amount"], confidence="high")]
    g = client.post("/api/query/generate", json={"question": "Show the top 10 customers by total spending."})
    assert g.status_code == 200
    body = g.json()
    assert body["status"] == "ok" and body["validation"]["valid"] is True
    assert set(body["tables_used"]) == {"customers", "orders"}
    assert body["assumptions"] == ["Spending = sum of orders.total_amount"] and body["confidence"] == "high"
    assert {"customers", "orders"} <= {t["name"] for t in body["retrieval"]["tables"]}
    assert body["retrieval"]["hits"] and all("score" in h for h in body["retrieval"]["hits"])
    assert any("orders.customer_id = customers.customer_id" in llm.calls[0] for _ in [0])  # verified join was in the prompt
    assert body["latency"]["total_ms"] > 0 and body["history_id"] > 0

    v = client.post("/api/query/validate", json={"sql": body["sql"]}).json()
    assert v["valid"] is True

    ex = client.post("/api/query/execute", json={"sql": body["sql"], "history_id": body["history_id"]})
    assert ex.status_code == 200
    res = ex.json()
    assert res["status"] == "success" and res["row_count"] == 10 and res["columns"] == ["customer_id", "first_name", "total_spent"]
    assert res["rows"][0][2] >= res["rows"][-1][2] and res["execution_time_ms"] > 0 and res["truncated"] is False
    json.dumps(res)  # JSON-safe

    h = client.get(f"/api/history/{body['history_id']}").json()
    assert h["execution_status"] == "success" and h["row_count"] == 10 and h["sql"] == body["sql"]


def test_unsafe_model_output_is_never_returned_as_sql(client, llm):
    llm.queue = [gen_json("DROP TABLE customers")] * 3
    body = client.post("/api/query/generate", json={"question": "get rid of customers"}).json()
    assert body["status"] == "invalid_sql" and body["sql"] is None and body["validation"]["valid"] is False
    assert body["attempts"] == 3


def test_model_refusal_and_clarification_statuses(client, llm):
    llm.queue = [gen_json(None, status="cannot_answer", explanation="There is no phone column.")]
    r = client.post("/api/query/generate", json={"question": "Show customer phone numbers"}).json()
    assert r["status"] == "cannot_answer" and r["sql"] is None and "phone" in r["message"]
    llm.queue = [gen_json(None, status="clarification_needed", clarification="Best by revenue or by order count?")]
    r = client.post("/api/query/generate", json={"question": "Show the best customers"}).json()
    assert r["status"] == "clarification_needed" and r["clarification_question"].startswith("Best by")


def test_validate_endpoint_reports_rules(client):
    ok = client.post("/api/query/validate", json={"sql": "SELECT * FROM customers LIMIT 3"}).json()
    assert ok["valid"] and ok["normalized_sql"]
    bad = client.post("/api/query/validate", json={"sql": "DELETE FROM customers"}).json()
    assert bad["valid"] is False and bad["errors"][0]["code"] in ("not_read_only", "forbidden_statement")


def test_execute_rejects_unsafe_sql_even_without_the_frontend(client):
    r = client.post("/api/query/execute", json={"sql": "DROP TABLE customers"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "sql_rejected" and err["details"]["validation"]["valid"] is False
    assert client.post("/api/query/execute", json={"sql": "SELECT 1; DELETE FROM orders"}).status_code == 422
    assert client.get("/api/schema").json()["tables"]  # still intact


def test_execute_reports_database_and_timeout_errors_cleanly(client, container):
    r = client.post("/api/query/execute", json={"sql": "SELECT 1/0"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "query_failed" and "division by zero" in r.json()["error"]["message"]
    t = client.post("/api/query/execute", json={"sql": "SELECT COUNT(*) FROM generate_series(1, 400000000) g(i)"})
    assert t.status_code == 408 and t.json()["error"]["code"] == "query_timeout"
    for resp in (r, t):
        for leak in ("ro_test_pass", "postgresql://", "Traceback", "psycopg"):
            assert leak not in resp.text


def test_empty_result_set_is_a_normal_success(client):
    r = client.post("/api/query/execute", json={"sql": "SELECT * FROM customers WHERE state = 'Atlantis'"}).json()
    assert r["status"] == "success" and r["row_count"] == 0 and r["rows"] == [] and r["columns"][0] == "customer_id"


def test_request_validation_errors(client):
    assert client.post("/api/query/generate", json={"question": ""}).status_code == 422
    assert client.post("/api/query/generate", json={}).json()["error"]["code"] == "invalid_request"
    assert client.post("/api/query/generate", json={"question": "x" * 2500}).status_code == 422
    assert client.post("/api/query/execute", json={"sql": "SELECT 1", "max_rows": 0}).status_code == 422


def test_missing_api_key_is_reported_clearly(settings, engine):
    c = build_container(settings, engine=engine, embedder=HashingEmbedder())  # no injected LLM, no GOOGLE_API_KEY
    from fastapi.testclient import TestClient

    with TestClient(create_app(c, warm_up=False)) as cl:
        r = cl.post("/api/query/generate", json={"question": "How many customers?"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "llm_not_configured"
    assert "GOOGLE_API_KEY" in r.json()["error"]["message"]


@pytest.mark.parametrize("exc_text, status, code", [
    ("429 RESOURCE_EXHAUSTED", 429, "llm_rate_limited"),
    ("API key not valid. Please pass a valid API key.", 502, "llm_auth_failed"),
    ("Deadline Exceeded while waiting", 504, "llm_timeout"),
])
def test_llm_failures_map_to_http_errors(client, llm, exc_text, status, code):
    llm.queue = [Exception(exc_text)]
    r = client.post("/api/query/generate", json={"question": "How many customers?"})
    assert r.status_code == status and r.json()["error"]["code"] == code
    assert "AIza" not in r.text


# ---------------------------------------------------------------- conversation + history
def test_conversational_follow_ups_use_rewritten_question_and_do_not_leak_unrelated_context(client, llm):
    # turn 1
    llm.queue = [gen_json(TOP_SPENDERS)]
    t1 = client.post("/api/chat", json={"question": "Show the top 10 customers by spending."}).json()
    cid = t1["conversation_id"]
    assert t1["status"] == "ok" and t1["standalone_question"] == "Show the top 10 customers by spending."

    # turn 2: follow-up -> rewrite call, then SQL call with the earlier SQL as reference
    llm.queue = ["Show the top 10 customers by spending who live in Karnataka.", gen_json(KARNATAKA)]
    t2 = client.post("/api/chat", json={"question": "Show only customers from Karnataka.", "conversation_id": cid}).json()
    assert t2["conversation_id"] == cid and t2["status"] == "ok"
    assert t2["standalone_question"] == "Show the top 10 customers by spending who live in Karnataka."
    assert "Karnataka" in t2["sql"]
    sql_prompt = llm.calls[-1]
    assert "Earlier SQL" in sql_prompt and "Karnataka" in sql_prompt.rsplit("Question:", 1)[1]

    # turn 3: unrelated question -> the rewriter returns it unchanged -> no earlier SQL in the prompt
    llm.queue = ["How many products are in stock?", gen_json("SELECT COUNT(*) FROM products WHERE stock_quantity > 0")]
    t3 = client.post("/api/chat", json={"question": "How many products are in stock?", "conversation_id": cid}).json()
    assert t3["status"] == "ok" and t3["standalone_question"] == "How many products are in stock?"
    assert "Earlier SQL" not in llm.calls[-1] and "total_spent" not in llm.calls[-1]
    assert {t["name"] for t in t3["retrieval"]["semantic_tables"]} & {"products"}  # retrieval ran on the standalone question

    hist = client.get("/api/history", params={"conversation_id": cid}).json()
    assert hist["total"] == 3 and [h["question"] for h in hist["items"]][0] == "How many products are in stock?"


def test_new_conversation_has_no_context(client, llm):
    llm.queue = [gen_json(TOP_SPENDERS)]
    a = client.post("/api/chat", json={"question": "Show the top 10 customers by spending."}).json()
    llm.queue = [gen_json("SELECT COUNT(*) FROM customers")]
    b = client.post("/api/chat", json={"question": "How many customers?"}).json()  # no conversation_id -> new
    assert a["conversation_id"] != b["conversation_id"] and len(llm.calls) == 2  # no rewrite call was made


def test_clarification_answer_is_resolved_with_the_clarification_turn(client, llm):
    llm.queue = [gen_json(None, status="clarification_needed", clarification="Best by revenue or by order count?")]
    c1 = client.post("/api/chat", json={"question": "Show the best customers."}).json()
    llm.queue = ["Show the best customers ranked by total revenue.", gen_json(TOP_SPENDERS)]
    c2 = client.post("/api/chat", json={"question": "by revenue", "conversation_id": c1["conversation_id"]}).json()
    assert c2["status"] == "ok" and c2["standalone_question"] == "Show the best customers ranked by total revenue."
    assert "assistant asked for clarification: Best by revenue or by order count?" in llm.calls[1]


def test_context_window_is_bounded(client, llm, settings):
    cid = None
    for i in range(settings.conversation_context_turns + 3):
        llm.queue = [gen_json("SELECT COUNT(*) FROM customers")] if cid is None else ["How many customers?", gen_json("SELECT COUNT(*) FROM customers")]
        cid = client.post("/api/chat", json={"question": f"Q{i}: how many customers?", "conversation_id": cid}).json()["conversation_id"]
    rewrite_prompt = next(c for c in reversed(llm.calls) if "Conversation history" in c)
    assert rewrite_prompt.count("User:") <= settings.conversation_context_turns


def test_regenerate_supersedes_previous_answer(client, llm):
    llm.queue = [gen_json("SELECT COUNT(*) FROM customers")]
    first = client.post("/api/chat", json={"question": "How many customers?"}).json()
    llm.queue = [gen_json("SELECT COUNT(customer_id) FROM customers")]
    second = client.post("/api/chat", json={"question": "How many customers?", "conversation_id": first["conversation_id"], "regenerate_of": first["history_id"]}).json()
    ids = [h["id"] for h in client.get("/api/history").json()["items"]]
    assert second["history_id"] in ids and first["history_id"] not in ids


def test_history_listing_and_pagination(client, llm):
    for i in range(5):
        llm.queue = [gen_json("SELECT COUNT(*) FROM customers")]
        client.post("/api/query/generate", json={"question": f"How many customers? #{i}"})
    page = client.get("/api/history", params={"limit": 2, "offset": 1}).json()
    assert page["total"] == 5 and len(page["items"]) == 2 and page["items"][0]["question"].endswith("#3")
    assert client.get("/api/history/999999").status_code == 404
    assert client.get("/api/history", params={"limit": 0}).status_code == 422
