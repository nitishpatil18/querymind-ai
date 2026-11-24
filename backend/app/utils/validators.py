"""Small input validators shared by routes and services."""
from __future__ import annotations

import re

from app.core.errors import BadRequestError

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]{0,62}$")


def validate_identifier(value: str, what: str = "identifier") -> str:
    if not _IDENTIFIER.match(value or ""):
        raise BadRequestError(f"Invalid {what}.")
    return value


def clean_question(question: str, max_length: int = 2000) -> str:
    q = " ".join((question or "").split())
    if not q:
        raise BadRequestError("The question must not be empty.")
    if len(q) > max_length:
        raise BadRequestError(f"The question is too long (limit {max_length} characters).")
    return q
