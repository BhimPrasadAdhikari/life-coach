"""
LLM factory with multi-provider support.

Usage
-----
    from graph.utils.llm import get_chat_model, make_llm

    # Direct model creation
    model = get_chat_model("groq-llama3.3", temperature=0.3)

    # From LangGraph config (reads configurable["model_key"])
    model = get_chat_model_from_config(config, temperature=0.3)
"""
from __future__ import annotations

import logging
import os
from typing import Any

from langchain_core.runnables import RunnableConfig
from core.config import (
    DEFAULT_MODEL_KEY as CONFIG_DEFAULT_MODEL_KEY,
    FALLBACK_MODEL_KEY,
    LLM_RETRY_ATTEMPTS,
    LLM_RETRY_MAX_SECONDS,
    LLM_RETRY_MIN_SECONDS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model catalogue
# ---------------------------------------------------------------------------

MODELS: dict[str, dict] = {
    "groq-llama3.1": {
        "provider": "groq",
        "model": "openai/gpt-oss-20b",
        "label": "GPT-OSS 20B (Groq — fast)",
    },
    "groq-llama3.3": {
        "provider": "groq",
        "model": "openai/gpt-oss-120b",
        "label": "GPT-OSS 120B (Groq — best)",
    },
    "groq-qwen27b": {
        "provider": "groq",
        "model": "qwen/qwen3.8-27b",
        "label": "Qwen 3.8 27B (Groq — balanced)",
    },
}

DEFAULT_MODEL_KEY = CONFIG_DEFAULT_MODEL_KEY


# ---------------------------------------------------------------------------
# Low-level builders
# ---------------------------------------------------------------------------

def _build_groq(model: str, temperature: float) -> Any:
    from langchain_groq import ChatGroq
    return ChatGroq(
        api_key=os.getenv("GROQ_API_KEY"),
        model=model,
        temperature=temperature,
    )


def _build(model_key: str, temperature: float) -> Any:
    cfg = MODELS.get(model_key)
    if cfg is None:
        logger.warning(f"Unknown model key '{model_key}', falling back to {DEFAULT_MODEL_KEY}")
        cfg = MODELS[DEFAULT_MODEL_KEY]

    return _build_groq(cfg["model"], temperature)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_chat_model(
    model_key: str = DEFAULT_MODEL_KEY,
    temperature: float = 0.7,
) -> Any:
    """Return a LangChain chat model for the requested model_key."""
    return _build(model_key, temperature)


def make_llm(
    model_key: str = DEFAULT_MODEL_KEY,
    temperature: float = 0.7,
    with_fallback: bool = False,
) -> Any:
    """Return the native chat model so callers can bind tools or schemas."""
    return _build(model_key, temperature)


def with_resilience(
    runnable: Any,
    model_key: str,
    temperature: float = 0.7,
    with_fallback: bool = False,
) -> Any:
    """Apply retries/fallbacks after composing a model-specific runnable."""
    primary = runnable.with_retry(
        stop_after_attempt=LLM_RETRY_ATTEMPTS,
        wait_exponential_jitter=True,
        exponential_jitter_params={
            "initial": LLM_RETRY_MIN_SECONDS,
            "max": LLM_RETRY_MAX_SECONDS,
        },
    )
    if not with_fallback or model_key == FALLBACK_MODEL_KEY:
        return primary

    fallback = _build(FALLBACK_MODEL_KEY, temperature)
    return primary.with_fallbacks([fallback])


def get_chat_model_from_config(
    config: RunnableConfig | None,
    temperature: float = 0.7,
    with_fallback: bool = False,
) -> Any:
    """Read model_key from LangGraph configurable dict and return the corresponding LLM."""
    model_key = DEFAULT_MODEL_KEY
    if config:
        model_key = (config.get("configurable") or {}).get("model_key", DEFAULT_MODEL_KEY)
    model = make_llm(model_key, temperature)
    return with_resilience(model, model_key, temperature, True) if with_fallback else model
