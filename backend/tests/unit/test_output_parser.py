import json

import pytest

from app.core.errors import LLMOutputError
from app.llm.output_parser import SQLGeneration, parse_generation
from tests.helpers import gen_json


def test_parses_clean_json():
    g = parse_generation(gen_json("SELECT 1;", tables=["customers"], assumptions=["a"]))
    assert g.status == "ok" and g.sql == "SELECT 1" and g.tables_used == ["customers"] and g.assumptions == ["a"]


def test_parses_fenced_json_with_prose():
    raw = "Sure! Here you go:\n```json\n" + gen_json("SELECT 2") + "\n```\nHope that helps."
    assert parse_generation(raw).sql == "SELECT 2"


def test_parses_json_embedded_in_text_and_braces_in_strings():
    obj = {"status": "ok", "sql": "SELECT '{x}' AS t", "explanation": "uses } brace", "confidence": "HIGH"}
    g = parse_generation("noise " + json.dumps(obj) + " trailing")
    assert g.sql == "SELECT '{x}' AS t" and g.confidence == "high"


def test_strips_sql_code_fences_inside_field():
    obj = {"status": "ok", "sql": "```sql\nSELECT 3;\n```", "explanation": "x"}
    assert parse_generation(json.dumps(obj)).sql == "SELECT 3"


@pytest.mark.parametrize("raw", ["no json here", '{"status": "ok", "sql": ', "[1, 2]", '{"status": "ok", "sql": ""}',
                                 '{"status": "maybe", "sql": "SELECT 1"}', '{"status": "clarification_needed"}'])
def test_invalid_outputs_raise_llm_output_error(raw):
    with pytest.raises(LLMOutputError):
        parse_generation(raw)


def test_ok_requires_sql_but_refusal_does_not():
    assert SQLGeneration(status="cannot_answer", explanation="no such data").sql is None
    g = parse_generation(gen_json(None, status="clarification_needed", clarification="Which metric?"))
    assert g.clarification_question == "Which metric?"


def test_message_content_blocks_are_flattened():
    class Msg:
        content = [{"type": "text", "text": gen_json("SELECT 4")}]

    assert parse_generation(Msg()).sql == "SELECT 4"
