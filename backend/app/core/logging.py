"""Structured (JSON) logging with secret redaction."""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone

_URL_CREDENTIALS = re.compile(r"((?:postgres(?:ql)?(?:\+\w+)?|mysql|redis)://[^:/\s]+):([^@\s]+)@")
_GOOGLE_KEY = re.compile(r"AIza[0-9A-Za-z_\-]{20,}")
_KV_SECRET = re.compile(r"(?i)\b(password|passwd|pwd|api[_-]?key|secret|token)\b(\s*[=:]\s*)([^\s,;'\"]+)")

_extra_secrets: list[str] = []


def register_secrets(values: list[str]) -> None:
    """Register literal secret values that must be masked wherever they appear."""
    _extra_secrets[:] = [v for v in values if v and len(v) >= 4]


def redact(text: str) -> str:
    if not text:
        return text
    for secret in _extra_secrets:
        text = text.replace(secret, "***")
    text = _URL_CREDENTIALS.sub(r"\1:***@", text)
    text = _GOOGLE_KEY.sub("***", text)
    text = _KV_SECRET.sub(r"\1\2***", text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(record.getMessage())
            record.args = None
            if record.exc_info:
                record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
                record.exc_info = None
        except Exception:  # never break logging
            pass
        return True


class JsonFormatter(logging.Formatter):
    _RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in self._RESERVED and not key.startswith("_"):
                payload[key] = value if isinstance(value, (int, float, bool, type(None))) else redact(str(value))
        if record.exc_text:
            payload["exception"] = record.exc_text
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", secrets: list[str] | None = None) -> None:
    register_secrets(secrets or [])
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("httpx", "httpcore", "chromadb", "sentence_transformers", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
