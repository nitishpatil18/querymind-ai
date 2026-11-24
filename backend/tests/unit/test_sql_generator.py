"""Pipeline tests with a scripted LLM: they verify prompting, parsing, retries and validation, not model accuracy."""
import pytest

from app.config import Settings
from app.core.errors import LLMAuthError, LLMRateLimitError, LLMTimeoutError
from app.core.errors import LLMModelNotFoundError, LLMOverloadedError
from app.llm.provider import invoke_with_retry, translate_llm_exception
from app.llm.sql_generator import ContextTurn, SQLGenerator
from app.services.validation_service import ValidationService
from tests.helpers import ScriptedLLM, gen_json

CTX = "Table: customers\n- customer_id: INTEGER"
GOOD = "SELECT customer_id FROM customers"


@pytest.fixture()
def gen(mini_schema):
    s = Settings(_env_file=None, generation_max_attempts=3)
    llm = ScriptedLLM()
    return SQLGenerator(s, ValidationService(s), llm), llm, mini_schema


def run(g, schema, question="q", standalone=None, tables=("customers",), history=None):
    return g.generate(question, standalone or question, schema, CTX, list(tables), history=history)


def test_valid_first_attempt(gen):
    g, llm, schema = gen
    llm.queue = [gen_json(GOOD, tables=["customers"], assumptions=["a1"])]
    out = run(g, schema)
    assert out.status == "ok" and out.attempts == 1 and out.generation.assumptions == ["a1"]
    assert out.validation.valid and out.generation.tables_used == ["customers"]


def test_prompt_contains_schema_rules_and_question(gen):
    g, llm, schema = gen
    llm.queue = [gen_json(GOOD)]
    run(g, schema, question="How many customers?")
    prompt = llm.calls[0]
    assert "How many customers?" in prompt and CTX in prompt
    assert "PostgreSQL" in prompt and "Never invent tables" in prompt and "status" in prompt


def test_malformed_output_is_retried_with_feedback(gen):
    g, llm, schema = gen
    llm.queue = ["not json at all", gen_json(GOOD)]
    out = run(g, schema)
    assert out.status == "ok" and out.attempts == 2 and len(out.attempt_errors) == 1
    assert "previous attempt was rejected" in llm.calls[1]


def test_validation_failure_feeds_error_back_and_repairs(gen):
    g, llm, schema = gen
    llm.queue = [gen_json("SELECT nope FROM customers"), gen_json(GOOD)]
    out = run(g, schema)
    assert out.status == "ok" and out.attempts == 2
    assert "Validation failed" in llm.calls[1] and "nope" in llm.calls[1]


def test_attempts_are_bounded(gen):
    g, llm, schema = gen
    llm.queue = ["garbage"] * 10
    out = run(g, schema)
    assert out.status == "invalid_sql" and out.attempts == 3 and len(llm.queue) == 7  # exactly 3 calls were made
    assert "valid query" in out.message


def test_unsafe_sql_from_model_is_never_accepted(gen):
    g, llm, schema = gen
    llm.queue = [gen_json("DROP TABLE customers")] * 3
    out = run(g, schema)
    assert out.status == "invalid_sql" and out.validation is not None and not out.validation.valid


def test_table_outside_retrieved_context_is_rejected_then_repaired(gen):
    g, llm, schema = gen
    llm.queue = [gen_json("SELECT order_id FROM orders"), gen_json(GOOD)]
    out = run(g, schema, tables=("customers",))
    assert out.status == "ok" and out.attempts == 2
    assert "not part of the provided schema context" in llm.calls[1]


def test_clarification_and_refusal_pass_through_without_sql(gen):
    g, llm, schema = gen
    llm.queue = [gen_json(None, status="clarification_needed", clarification="Best by what measure?")]
    out = run(g, schema)
    assert out.status == "clarification_needed" and out.message == "Best by what measure?" and out.validation is None
    llm.queue = [gen_json(None, status="cannot_answer", explanation="No phone column.")]
    out = run(g, schema)
    assert out.status == "cannot_answer" and "phone" in out.message


def test_followup_rewriting_and_context_block(gen):
    g, llm, schema = gen
    hist = [ContextTurn("Show the top 10 customers by spending.", "SELECT 1")]
    llm.queue = ["Show the top 10 customers by spending who live in Karnataka."]
    standalone = g.rewrite_followup("Show only customers from Karnataka.", hist)
    assert "Karnataka" in standalone and "Conversation history" in llm.calls[0]
    llm.queue = [gen_json(GOOD)]
    run(g, schema, question="Show only customers from Karnataka.", standalone=standalone, history=hist)
    assert "Earlier SQL" in llm.calls[1] and "SELECT 1" in llm.calls[1]


def test_independent_question_does_not_include_earlier_sql(gen):
    g, llm, schema = gen
    hist = [ContextTurn("Show the top 10 customers by spending.", "SELECT 1")]
    llm.queue = [gen_json(GOOD)]
    run(g, schema, question="How many products exist?", standalone="How many products exist?", history=hist)
    assert "Earlier SQL" not in llm.calls[0]


def test_rewrite_without_history_makes_no_llm_call(gen):
    g, llm, _ = gen
    assert g.rewrite_followup("anything", []) == "anything" and llm.calls == []


def test_clarification_turn_is_part_of_rewrite_prompt(gen):
    g, llm, _ = gen
    llm.queue = ["Show the best customers by total order amount."]
    g.rewrite_followup("by order amount", [ContextTurn("Show the best customers.", None, note="Best by what measure?")])
    assert "assistant asked for clarification: Best by what measure?" in llm.calls[0]


@pytest.mark.parametrize("exc, expected", [
    (Exception("429 RESOURCE_EXHAUSTED quota exceeded"), LLMRateLimitError),
    (TimeoutError("request timed out"), LLMTimeoutError),
    (Exception("400 API key not valid. Please pass a valid API key."), LLMAuthError),
    (type("GoogleModelNotFoundError", (Exception,), {})("404 models/x is not found for API version v1"), LLMModelNotFoundError),
])
def test_provider_errors_are_translated_without_leaking_details(exc, expected):
    err = translate_llm_exception(exc)
    assert isinstance(err, expected) and "AIza" not in err.message


def test_llm_exception_during_generation_surfaces_as_app_error(gen):
    g, llm, schema = gen
    llm.queue = [Exception("429 quota exceeded")]
    with pytest.raises(LLMRateLimitError):
        run(g, schema)


class _Flaky:
    def __init__(self, failures, error):
        self.failures, self.error, self.calls = failures, error, 0

    def invoke(self, payload):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error
        return "ok"


def test_overload_is_translated():
    err = translate_llm_exception(Exception("503 UNAVAILABLE. This model is currently experiencing high demand."))
    assert isinstance(err, LLMOverloadedError)


def test_invoke_with_retry_recovers_from_temporary_overload():
    flaky = _Flaky(2, Exception("503 UNAVAILABLE high demand"))
    assert invoke_with_retry(flaky, {}, delays=(0, 0)) == "ok"
    assert flaky.calls == 3


def test_invoke_with_retry_gives_up_after_the_last_delay():
    flaky = _Flaky(10, Exception("503 UNAVAILABLE high demand"))
    with pytest.raises(LLMOverloadedError):
        invoke_with_retry(flaky, {}, delays=(0, 0))
    assert flaky.calls == 3


def test_invoke_with_retry_does_not_retry_other_errors():
    flaky = _Flaky(10, Exception("400 API key not valid"))
    with pytest.raises(LLMAuthError):
        invoke_with_retry(flaky, {}, delays=(0, 0))
    assert flaky.calls == 1


def test_gemini_thinking_level_is_passed_through_and_validated():
    from pydantic import SecretStr

    from app.config import Settings
    from app.core.errors import LLMNotConfiguredError
    from app.llm.provider import get_chat_model

    base = dict(_env_file=None, google_api_key=SecretStr("test-key"), llm_provider="gemini")  # ignore any local .env
    model = get_chat_model(Settings(**base, llm_thinking_level="low"))
    assert model.thinking_level == "low"
    assert get_chat_model(Settings(**base)).thinking_level is None
    with pytest.raises(LLMNotConfiguredError):
        get_chat_model(Settings(**base, llm_thinking_level="extreme"))


def test_per_minute_and_per_day_limits_are_told_apart():
    from app.core.errors import LLMQuotaExhaustedError, LLMRateLimitError
    from app.llm.provider import translate_llm_exception

    day = translate_llm_exception(Exception("429 RESOURCE_EXHAUSTED GenerateRequestsPerDayPerProjectPerModel-FreeTier"))
    minute = translate_llm_exception(Exception("429 RESOURCE_EXHAUSTED GenerateRequestsPerMinutePerProjectPerModel-FreeTier"))
    both = translate_llm_exception(Exception("429 GenerateRequestsPerMinutePerProjectPerModel-FreeTier GenerateRequestsPerDayPerProjectPerModel-FreeTier"))
    assert isinstance(day, LLMQuotaExhaustedError)
    assert type(minute) is LLMRateLimitError and type(both) is LLMRateLimitError
