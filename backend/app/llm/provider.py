"""Pluggable chat-model providers + translation of provider errors into user-safe application errors."""
from __future__ import annotations

import logging
import time
from typing import Callable

from langchain_core.language_models.chat_models import BaseChatModel

from app.config import Settings, get_settings
from app.core.errors import (
    AppError,
    LLMAuthError,
    LLMError,
    LLMModelNotFoundError,
    LLMOverloadedError,
    LLMNotConfiguredError,
    LLMQuotaExhaustedError,
    LLMRateLimitError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)

ProviderFactory = Callable[[Settings], BaseChatModel]
_PROVIDERS: dict[str, ProviderFactory] = {}


def register_provider(name: str, factory: ProviderFactory) -> None:
    """Add a new LLM provider (e.g. another hosted API) without touching the pipeline."""
    _PROVIDERS[name.lower()] = factory


def _gemini(settings: Settings) -> BaseChatModel:
    if not settings.llm_configured:
        raise LLMNotConfiguredError("GOOGLE_API_KEY is not set. Add your Gemini API key to the .env file and restart the backend.")
    from langchain_google_genai import ChatGoogleGenerativeAI

    extra: dict = {}
    level = (settings.llm_thinking_level or "").strip().lower()
    if level:
        if level not in {"minimal", "low", "medium", "high"}:
            raise LLMNotConfiguredError("LLM_THINKING_LEVEL must be one of: minimal, low, medium, high (or empty).")
        extra["thinking_level"] = level
    return ChatGoogleGenerativeAI(
        model=settings.llm_model,
        google_api_key=settings.google_api_key.get_secret_value(),
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        response_mime_type="application/json",
        **extra,
    )


def _ollama(settings: Settings) -> BaseChatModel:
    try:
        from langchain_ollama import ChatOllama
    except ImportError as exc:
        raise LLMNotConfiguredError("Install 'langchain-ollama' to use LLM_PROVIDER=ollama.") from exc
    return ChatOllama(model=settings.llm_model, base_url=settings.ollama_base_url, temperature=settings.llm_temperature, format="json")


register_provider("gemini", _gemini)
register_provider("ollama", _ollama)


def get_chat_model(settings: Settings | None = None) -> BaseChatModel:
    s = settings or get_settings()
    factory = _PROVIDERS.get(s.llm_provider.lower())
    if factory is None:
        raise LLMNotConfiguredError(f"Unknown LLM_PROVIDER '{s.llm_provider}'. Available: {', '.join(sorted(_PROVIDERS))}.")
    return factory(s)


def translate_llm_exception(exc: Exception) -> AppError:
    """Map vendor exceptions to stable, user-safe errors (never leaks keys or raw payloads)."""
    if isinstance(exc, AppError):
        return exc
    name = exc.__class__.__name__.lower()
    msg = str(exc).lower()
    if any(k in name for k in ("timeout", "deadline")) or "timed out" in msg or "deadline" in msg:
        return LLMTimeoutError("The language model took too long to respond. Please try again.")
    if "modelnotfound" in name or "model not found" in msg or ("404" in msg and "model" in msg):
        model = get_settings().llm_model
        return LLMModelNotFoundError(
            f"The model '{model}' is not available for this API key. Set LLM_MODEL in your .env file to a model your key can use."
        )
    if "unavailable" in msg or "503" in msg or "overloaded" in msg or "high demand" in msg:
        return LLMOverloadedError("The language model is temporarily overloaded. Please try again in a moment.")
    if any(k in name for k in ("resourceexhausted", "ratelimit", "toomanyrequests")) or "429" in msg or "quota" in msg or "rate limit" in msg:
        logger.warning("llm rate limited: %s", str(exc)[:1500])
        per_day = "perday" in msg or "per day" in msg or "per_day" in msg
        per_minute = "perminute" in msg or "per minute" in msg or "per_minute" in msg
        if per_day and not per_minute:
            return LLMQuotaExhaustedError("The daily quota of the language model is used up. It resets once a day, or use another model or key.")
        return LLMRateLimitError("The language model rate limit was reached. Wait a moment and try again.")
    if (
        any(k in name for k in ("permissiondenied", "unauthenticated", "authentication"))
        or "api key" in msg and ("invalid" in msg or "not valid" in msg)
        or "api_key_invalid" in msg
        or "401" in msg
        or "403" in msg
    ):
        return LLMAuthError("The language model rejected the API key. Check GOOGLE_API_KEY in your .env file.")
    logger.warning("llm call failed: %s: %s", exc.__class__.__name__, str(exc)[:300])
    return LLMError("The language model request failed. Please try again.")


TRANSIENT_RETRY_DELAYS = (2.0, 5.0)


def invoke_with_retry(runnable, payload, *, delays: tuple[float, ...] = TRANSIENT_RETRY_DELAYS):
    """Invoke a LangChain runnable; retry briefly when the provider reports a temporary overload (HTTP 503)."""
    for attempt in range(len(delays) + 1):
        try:
            return runnable.invoke(payload)
        except Exception as exc:
            err = translate_llm_exception(exc)
            if isinstance(err, LLMOverloadedError) and attempt < len(delays):
                logger.info("language model overloaded; retrying in %.0fs", delays[attempt])
                time.sleep(delays[attempt])
                continue
            raise err from exc
