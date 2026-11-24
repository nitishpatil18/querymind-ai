"""Structured model output: Pydantic schema + tolerant JSON extraction."""
from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from app.core.errors import LLMOutputError


class SQLGeneration(BaseModel):
    """What the LLM must return for every question."""

    status: Literal["ok", "clarification_needed", "cannot_answer"] = "ok"
    sql: str | None = None
    explanation: str = ""
    tables_used: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"
    clarification_question: str | None = None

    @field_validator("sql")
    @classmethod
    def _clean_sql(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        v = re.sub(r"^```(?:sql)?\s*|\s*```$", "", v, flags=re.IGNORECASE).strip()
        v = v.rstrip(";").strip()
        return v or None

    @field_validator("confidence", mode="before")
    @classmethod
    def _norm_conf(cls, v):
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("assumptions", "tables_used", mode="before")
    @classmethod
    def _none_to_list(cls, v):
        return [] if v is None else v

    @model_validator(mode="after")
    def _consistency(self):
        if self.status == "ok" and not self.sql:
            raise ValueError("status 'ok' requires a non-empty sql")
        if self.status == "clarification_needed" and not self.clarification_question:
            raise ValueError("status 'clarification_needed' requires clarification_question")
        return self


def _extract_json_object(text: str) -> str:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1)
    start = text.find("{")
    if start == -1:
        raise LLMOutputError("The model did not return a JSON object.")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise LLMOutputError("The model returned an incomplete JSON object.")


def message_text(content) -> str:
    """Normalise LangChain message content (str or list of content blocks) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") in (None, "text"):
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content)


def parse_generation(raw) -> SQLGeneration:
    text = message_text(getattr(raw, "content", raw))
    try:
        obj = json.loads(_extract_json_object(text))
    except json.JSONDecodeError as exc:
        raise LLMOutputError(f"The model returned malformed JSON ({exc.msg}).") from exc
    if not isinstance(obj, dict):
        raise LLMOutputError("The model output must be a JSON object.")
    try:
        return SQLGeneration.model_validate(obj)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first["loc"]) or "output"
        raise LLMOutputError(f"The model output did not match the required format ({loc}: {first['msg']}).") from exc
