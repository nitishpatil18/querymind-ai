"""Index + retrieval against the real schema, and the evaluation harness itself."""
import json
import time

import pytest
from pydantic import SecretStr

from app.services.evaluation_service import EvalDataset, EvaluationService
from tests.helpers import gen_json

EXAMPLE_QUERIES = {  # generic valid SQL for the open-definition acceptance questions
    "Show the top 10 customers by total spending.": "SELECT c.customer_id, SUM(o.total_amount) AS spent FROM customers c JOIN orders o ON o.customer_id = c.customer_id GROUP BY c.customer_id ORDER BY spent DESC LIMIT 10",
    "Which products have the highest total sales?": "SELECT p.product_name, SUM(oi.quantity * oi.unit_price) AS sales FROM order_items oi JOIN products p ON p.product_id = oi.product_id GROUP BY p.product_name ORDER BY sales DESC LIMIT 10",
    "Find the top-selling product in each category.": "SELECT 1 AS placeholder FROM categories",
    "Calculate monthly revenue for the last six months.": "SELECT DATE_TRUNC('month', order_date) AS m, SUM(total_amount) FROM orders WHERE order_date >= CURRENT_DATE - INTERVAL '6 months' GROUP BY 1",
    "Find customers who made more than five purchases.": "SELECT customer_id FROM orders GROUP BY customer_id HAVING COUNT(*) > 5",
    "Show pending payments and their associated customers.": "SELECT c.first_name, p.amount FROM payments p JOIN orders o ON o.order_id = p.order_id JOIN customers c ON c.customer_id = o.customer_id WHERE p.payment_status = 'pending'",
    "Find the average order value for each state.": "SELECT c.state, AVG(o.total_amount) FROM orders o JOIN customers c ON c.customer_id = o.customer_id GROUP BY c.state",
    "Compare the number of completed and cancelled orders.": "SELECT order_status, COUNT(*) FROM orders WHERE order_status IN ('completed','cancelled') GROUP BY order_status",
    "Find the number of orders placed in each month.": "SELECT DATE_TRUNC('month', order_date) AS m, COUNT(*) FROM orders GROUP BY 1",
    "Show customers who have never placed an order.": "SELECT customer_id FROM customers c WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.customer_id)",
}


def oracle_llm(dataset: EvalDataset):
    """A scripted 'perfect' model built from the dataset: it only proves the harness scores correctly."""
    by_q = {q.question: q for q in dataset.questions}

    def reply(prompt: str) -> str:
        q = by_q[prompt.rsplit("Question:", 1)[1].strip()]
        if q.expected_behavior == "refuse":
            return gen_json(None, status="cannot_answer", explanation="Not possible with this schema.")
        if q.expected_behavior == "clarify_or_assume":
            return gen_json(None, status="clarification_needed", clarification="What do you mean?")
        return gen_json(q.expected_sql or EXAMPLE_QUERIES[q.question])

    return reply


def test_index_and_retrieval_on_real_schema(container):
    state = container.schema_service.refresh().index
    assert state.status == "ready" and state.documents_indexed == 11
    r = container.retriever.retrieve("Which customers have never placed an order?")
    assert {t.name for t in r.semantic_tables} & {"customers", "orders"}
    assert r.context and all(rel.child_table in r.table_names for rel in r.relationships)
    assert r.hits[0].score >= r.hits[-1].score


def test_ensure_index_rebuilds_only_when_stale(container):
    container.schema_service.refresh()
    built = container.indexer.state.last_indexed_at
    time.sleep(0.01)
    container.schema_service.ensure_index()
    assert container.indexer.state.last_indexed_at == built  # unchanged schema: no rebuild
    container.indexer._state = container.indexer._state.model_copy(update={"schema_fingerprint": "old"})
    container.schema_service.ensure_index()
    assert container.indexer.state.last_indexed_at > built


def test_golden_dataset_is_well_formed():
    from app.config import Settings
    from pathlib import Path

    ds = EvalDataset.model_validate_json((Path(__file__).resolve().parents[2] / "evaluation" / "golden_questions.json").read_text())
    ids = [q.id for q in ds.questions]
    assert len(ids) == len(set(ids)) and len(ds.questions) >= 30
    cats = {q.category for q in ds.questions}
    assert {"simple_select", "where", "order_by", "group_by", "aggregate", "join", "multi_join", "date_filter", "subquery", "cte",
            "complex", "ambiguous", "nonexistent_column", "nonexistent_table", "out_of_scope"} <= cats
    assert all(q.expected_sql for q in ds.questions if q.expected_behavior == "answer" and q.scoring == "result")
    assert len(ds.adversarial_sql) >= 20


def test_retrieval_only_evaluation_measures_without_an_llm(container):
    ev = container.evaluation_service
    assert ev.default_mode() == "retrieval_only"
    report = ev.run()
    m = report.metrics
    assert report.mode == "retrieval_only" and m["questions_total"] >= 30
    assert 0 <= m["recall_at_k_semantic"] <= 1 and 0 <= m["precision_at_k_semantic"] <= 1
    assert m["recall_after_expansion"] >= m["recall_at_k_semantic"]
    assert m["invalid_query_rejection_rate_validator"] == 1.0 and m["invalid_query_blocked_end_to_end"] == 1.0
    assert m["golden_sql_valid_rate"] == 1.0 and m["golden_sql_execution_rate"] == 1.0
    for key in ("execution_accuracy", "sql_validity_rate", "avg_generation_latency_ms"):
        assert key not in m  # LLM metrics are never invented
    assert any("hashing" in n for n in report.notes) and any("LLM was not configured" in n for n in report.notes)
    md = (container.settings.evaluation_reports_dir / "latest.md").read_text()
    assert "n/a (not measured)" in md and "retrieval_only" in md
    assert ev.latest().run_id == report.run_id


def test_full_evaluation_scores_a_scripted_oracle_perfectly(container, llm):
    ev = container.evaluation_service
    ev.settings.google_api_key = SecretStr("unit-test-key")  # makes mode "full"; the scripted LLM is injected, no network call happens
    llm.rules = [("Question:", oracle_llm(ev.load_dataset()))]
    report = ev.run("full")
    m = report.metrics
    assert report.mode == "full"
    assert m["sql_validity_rate"] == 1.0 and m["execution_success_rate"] == 1.0
    assert m["execution_accuracy"] == 1.0 and m["refusal_correct_rate"] == 1.0 and m["ambiguity_handled_rate"] == 1.0
    assert m["exact_sql_match_rate"] == 1.0 and m["questions_with_errors"] == 0
    assert m["avg_generation_latency_ms"] > 0 and m["avg_execution_ms"] is not None
    assert not [r for r in report.results if r.error]
    assert report.by_category["join"]["execution_accuracy"] == 1.0


def test_full_evaluation_detects_wrong_results_and_unsafe_answers(container, llm):
    ev = container.evaluation_service
    ev.settings.google_api_key = SecretStr("unit-test-key")
    ds = ev.load_dataset()
    good = oracle_llm(ds)

    def flawed(prompt: str) -> str:
        q = prompt.rsplit("Question:", 1)[1].strip()
        if q == "How many customers are registered?":
            return gen_json("SELECT COUNT(*) FROM customers WHERE state = 'Karnataka'")  # runs, wrong result
        if q == "Show the phone numbers of all customers.":
            return gen_json("SELECT email FROM customers")  # should have refused
        return good(prompt)

    llm.rules = [("Question:", flawed)]
    report = ev.run("full")
    by_id = {r.id: r for r in report.results}
    assert by_id["s02"].executed is True and by_id["s02"].execution_match is False
    assert by_id["n01"].behavior_ok is False
    assert report.metrics["execution_accuracy"] < 1.0 and report.metrics["refusal_correct_rate"] < 1.0
    assert "Failures" in (ev.settings.evaluation_reports_dir / "latest.md").read_text()


def test_full_mode_requires_an_llm(container):
    from app.core.errors import BadRequestError

    with pytest.raises(BadRequestError):
        container.evaluation_service.run("full")


def test_evaluation_api_runs_in_background(client, container):
    r = client.post("/api/evaluation/run", json={"mode": "retrieval_only"})
    assert r.status_code == 202 and r.json()["status"] == "running"
    for _ in range(100):
        res = client.get("/api/evaluation/results").json()
        if res["progress"]["status"] in ("completed", "failed"):
            break
        time.sleep(0.2)
    assert res["progress"]["status"] == "completed" and res["report"]["mode"] == "retrieval_only"
    assert res["report"]["metrics"]["questions_total"] >= 30


def test_provider_errors_are_reported_not_scored_as_wrong(container, llm):
    ev = container.evaluation_service
    ev.settings.google_api_key = SecretStr("unit-test-key")
    ev._sleep = lambda seconds: None  # do not wait out the rate limit backoff in tests
    good = oracle_llm(ev.load_dataset())
    blocked = {"How many customers are registered?", "Delete all cancelled orders from the database.", "Show recent orders."}

    def limited(prompt: str) -> str:
        if prompt.rsplit("Question:", 1)[1].strip() in blocked:
            raise Exception("429 RESOURCE_EXHAUSTED quota exceeded")
        return good(prompt)

    llm.rules = [("Question:", limited)]
    report = ev.run("full")
    by_id = {r.id: r for r in report.results}
    m = report.metrics

    assert m["questions_with_errors"] == 3 and m["questions_evaluated"] == m["questions_total"] - 3
    assert {by_id[i].status for i in ("s02", "u01", "am03")} == {"error"}
    # the other questions were all answered correctly, so errors must not drag the rates down
    assert m["execution_accuracy"] == 1.0 and m["refusal_correct_rate"] == 1.0 and m["ambiguity_handled_rate"] == 1.0
    # retrieval does not need the model, so it is still measured for the errored questions
    assert by_id["s02"].semantic_tables and by_id["s02"].recall_at_k is not None
    assert any("could not be evaluated" in n for n in report.notes)


def test_generation_retries_rate_limits_then_gives_up(container):
    from app.core.errors import LLMOverloadedError, LLMRateLimitError

    ev = container.evaluation_service
    waits = []
    ev._sleep = waits.append

    class Flaky:
        def __init__(self, failures, error):
            self.failures, self.error, self.calls = failures, error, 0

        def generate(self, question, record=False):
            self.calls += 1
            if self.calls <= self.failures:
                raise self.error
            return "answered"

    ev.qs = Flaky(3, LLMRateLimitError("slow down"))
    assert ev._generate_with_retry("q") == "answered" and waits == [10.0, 20.0, 40.0]

    waits.clear()
    ev.qs = Flaky(99, LLMRateLimitError("slow down"))
    with pytest.raises(LLMRateLimitError):
        ev._generate_with_retry("q")
    assert waits == [10.0, 20.0, 40.0, 60.0, 60.0, 60.0] and ev.qs.calls == 7

    waits.clear()
    ev.qs = Flaky(99, LLMOverloadedError("busy"))
    with pytest.raises(LLMOverloadedError):
        ev._generate_with_retry("q")
    assert waits == [30.0] and ev.qs.calls == 2


def test_quota_exhaustion_stops_calling_the_model(container, llm):
    ev = container.evaluation_service
    ev.settings.google_api_key = SecretStr("unit-test-key")
    waits = []
    ev._sleep = waits.append
    calls = {"n": 0}

    def always_limited(prompt: str) -> str:
        calls["n"] += 1
        raise Exception("429 RESOURCE_EXHAUSTED quota exceeded")

    llm.rules = [("Question:", always_limited)]
    report = ev.run("full")
    total = report.metrics["questions_total"]

    assert report.metrics["questions_with_errors"] == total and report.metrics["questions_evaluated"] == 0
    assert calls["n"] == 2 * (ev.rate_limit_retries + 1)  # only two questions were tried before giving up
    assert len(waits) == 2 * ev.rate_limit_retries
    assert any("quota" in n for n in report.notes)
    assert all(r.semantic_tables for r in report.results)  # retrieval is still measured


def test_daily_quota_stops_at_once(container, llm):
    ev = container.evaluation_service
    ev.settings.google_api_key = SecretStr("unit-test-key")
    waits = []
    ev._sleep = waits.append
    calls = {"n": 0}

    def daily(prompt: str) -> str:
        calls["n"] += 1
        raise Exception("429 RESOURCE_EXHAUSTED GenerateRequestsPerDayPerProjectPerModel-FreeTier")

    llm.rules = [("Question:", daily)]
    report = ev.run("full")
    assert calls["n"] == 1 and waits == []  # no waiting, no further model calls
    assert report.metrics["questions_evaluated"] == 0
    assert any("quota" in n for n in report.notes)


def test_resume_keeps_finished_answers_and_runs_only_the_rest(container, llm):
    ev = container.evaluation_service
    ev.settings.google_api_key = SecretStr("unit-test-key")
    ev._sleep = lambda s: None
    llm.rules = [("Question:", oracle_llm(ev.load_dataset()))]
    first = ev.run("full")  # the stand-in model answers every question
    ids = [r.id for r in first.results]
    # make two answers look like provider failures in the stored report
    broken = {ids[0], ids[1]}
    for r in first.results:
        if r.id in broken:
            r.status, r.error = "error", "The language model rate limit was reached."
    ev._persist(first)

    calls = {"n": 0}
    orig = ev.qs.generate

    def counting(question, **kw):
        calls["n"] += 1
        return orig(question, **kw)

    ev.qs.generate = counting
    second = ev.run("full", resume=True)
    assert calls["n"] == len(broken)
    assert [r.id for r in second.results] == ids
    assert all(r.status != "error" for r in second.results if r.id in broken)
    assert any("Resumed run" in n for n in second.notes)


def test_resume_backfills_extra_columns_check_for_old_answers(container, llm):
    ev = container.evaluation_service
    ev.settings.google_api_key = SecretStr("unit-test-key")
    ev._sleep = lambda s: None
    llm.rules = [("Question:", oracle_llm(ev.load_dataset()))]
    first = ev.run("full")
    for r in first.results:  # simulate a report written before the lenient metric existed
        r.execution_match_extra_columns = None
    ev._persist(first)
    ev.qs.generate = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no model call expected"))
    second = ev.run("full", resume=True)
    m = second.metrics
    assert m["execution_accuracy_extra_columns_allowed"] >= m["execution_accuracy"] == 1.0


def test_repeated_overload_stops_calling_the_model(container, llm):
    ev = container.evaluation_service
    ev.settings.google_api_key = SecretStr("unit-test-key")
    waits = []
    ev._sleep = waits.append
    calls = {"n": 0}

    def busy(prompt: str) -> str:
        calls["n"] += 1
        raise Exception("503 UNAVAILABLE high demand")

    llm.rules = [("Question:", busy)]
    report = ev.run("full")
    assert report.metrics["questions_evaluated"] == 0
    assert any("overloaded" in n for n in report.notes)
    assert len(waits) == 2  # one 30 s pause for each of the two questions that were tried


def test_repeated_timeouts_stop_calling_the_model(container, llm):
    ev = container.evaluation_service
    ev.settings.google_api_key = SecretStr("unit-test-key")
    ev._sleep = lambda s: None
    calls = {"n": 0}

    def slow(prompt: str) -> str:
        calls["n"] += 1
        raise Exception("Request timed out")

    llm.rules = [("Question:", slow)]
    report = ev.run("full")
    assert report.metrics["questions_evaluated"] == 0
    assert calls["n"] == 4  # two questions, one retry each, then the run stops
