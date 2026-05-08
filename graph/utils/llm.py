"""
LLM factory with multi-provider support and automatic Groq → Gemini fallback.

Available model keys
--------------------
groq-llama3.1   llama-3.1-8b-instant        (Groq  — fast, cheap)
groq-llama3.3   llama-3.3-70b-versatile     (Groq  — best quality)
gemini-flash    gemini-2.0-flash             (Google — fast)
gemini-pro      gemini-1.5-pro               (Google — high quality)

Usage
-----
    from graph.utils.llm import get_chat_model, make_llm

    # Direct — no fallback
    model = get_chat_model("groq-llama3.3", temperature=0.3)

    # With automatic Groq→Gemini fallback on rate-limit
    model = make_llm("groq-llama3.3", temperature=0.3, with_fallback=True)

    # From LangGraph config (reads configurable["model_key"])
    model = get_chat_model_from_config(config, temperature=0.3)
"""
from __future__ import annotations

import logging
import os
from typing import Any

from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model catalogue
# ---------------------------------------------------------------------------

MODELS: dict[str, dict] = {
    "groq-llama3.1": {
        "provider": "groq",
        "model": "llama-3.1-8b-instant",
        "label": "Llama 3.1 8B (Groq — fast)",
    },
    "groq-llama3.3": {
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "label": "Llama 3.3 70B (Groq — best)",
    },
    "gemini-flash": {
        "provider": "gemini",
        "model": "gemini-2.0-flash",
        "label": "Gemini 2.0 Flash (Google)",
    },
    "gemini-pro": {
        "provider": "gemini",
        "model": "gemini-1.5-pro",
        "label": "Gemini 1.5 Pro (Google)",
    },
}

from core.config import DEFAULT_MODEL_KEY as CONFIG_DEFAULT_MODEL_KEY
from core.config import FALLBACK_MODEL_KEY as CONFIG_FALLBACK_MODEL_KEY

# Defaults (can be overridden by env through core.config)
DEFAULT_MODEL_KEY = CONFIG_DEFAULT_MODEL_KEY
DEFAULT_FALLBACK_KEY = CONFIG_FALLBACK_MODEL_KEY

# ---------------------------------------------------------------------------
# Rate-limit detection
# ---------------------------------------------------------------------------

_RATE_LIMIT_SIGNALS = (
    "rate_limit_exceeded",
    "429",
    "resource_exhausted",
    "quota",
    "too many requests",
    "rateLimitError",
)


def _is_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(sig.lower() in msg for sig in _RATE_LIMIT_SIGNALS)


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


def _build_gemini(model: str, temperature: float) -> Any:
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ModuleNotFoundError:
        logger.warning(
            "langchain_google_genai is not installed; falling back to Groq model. "
            "Install with: pip install langchain-google-genai"
        )
        return _build_groq(MODELS[DEFAULT_MODEL_KEY]["model"], temperature)

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.warning(
            "GEMINI_API_KEY/GOOGLE_API_KEY not set; falling back to Groq model."
        )
        return _build_groq(MODELS[DEFAULT_MODEL_KEY]["model"], temperature)

    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=api_key,
        temperature=temperature,
    )


def _build(model_key: str, temperature: float) -> Any:
    cfg = MODELS.get(model_key)
    if cfg is None:
        logger.warning(f"Unknown model key '{model_key}', falling back to {DEFAULT_MODEL_KEY}")
        cfg = MODELS[DEFAULT_MODEL_KEY]

    if cfg["provider"] == "gemini":
        return _build_gemini(cfg["model"], temperature)
    return _build_groq(cfg["model"], temperature)


# ---------------------------------------------------------------------------
# FallbackLLM wrapper
# ---------------------------------------------------------------------------

class FallbackLLM:
    """
    Transparent wrapper around a primary LLM.
    On Groq rate-limit errors it automatically retries with the fallback model
    and logs a clear warning so the operator knows what happened.
    """

    def __init__(self, primary_key: str, fallback_key: str, temperature: float):
        self._primary_key = primary_key
        self._fallback_key = fallback_key
        self._temperature = temperature
        self._primary = _build(primary_key, temperature)
        self._fallback: Any = None  # lazy — only built if needed

    @classmethod
    def _from_models(
        cls,
        *,
        primary: Any,
        fallback: Any,
        primary_key: str,
        fallback_key: str,
        temperature: float,
    ) -> "FallbackLLM":
        obj = cls.__new__(cls)
        obj._primary_key = primary_key
        obj._fallback_key = fallback_key
        obj._temperature = temperature
        obj._primary = primary
        obj._fallback = fallback
        return obj

    def _get_fallback(self):
        if self._fallback is None:
            self._fallback = _build(self._fallback_key, self._temperature)
        return self._fallback

    # ---- sync ----
    def invoke(self, *args, **kwargs):
        try:
            return self._primary.invoke(*args, **kwargs)
        except Exception as e:
            if _is_rate_limit(e):
                logger.warning(
                    f"[LLM] Rate limit on '{self._primary_key}' — "
                    f"falling back to '{self._fallback_key}'"
                )
                return self._get_fallback().invoke(*args, **kwargs)
            raise

    # ---- async ----
    async def ainvoke(self, *args, **kwargs):
        try:
            return await self._primary.ainvoke(*args, **kwargs)
        except Exception as e:
            if _is_rate_limit(e):
                logger.warning(
                    f"[LLM] Rate limit on '{self._primary_key}' — "
                    f"falling back to '{self._fallback_key}'"
                )
                return await self._get_fallback().ainvoke(*args, **kwargs)
            raise

    # ---- streaming ----
    def stream(self, *args, **kwargs):
        try:
            yield from self._primary.stream(*args, **kwargs)
        except Exception as e:
            if _is_rate_limit(e):
                logger.warning(
                    f"[LLM] Rate limit on '{self._primary_key}' (stream) — "
                    f"falling back to '{self._fallback_key}'"
                )
                yield from self._get_fallback().stream(*args, **kwargs)
            else:
                raise

    async def astream(self, *args, **kwargs):
        try:
            async for chunk in self._primary.astream(*args, **kwargs):
                yield chunk
        except Exception as e:
            if _is_rate_limit(e):
                logger.warning(
                    f"[LLM] Rate limit on '{self._primary_key}' (astream) — "
                    f"falling back to '{self._fallback_key}'"
                )
                async for chunk in self._get_fallback().astream(*args, **kwargs):
                    yield chunk
            else:
                raise

    # ---- callable interface so LangChain can coerce this into a Runnable ----
    def __call__(self, input, config=None, **kwargs):
        return self.invoke(input, config=config, **kwargs)

    # ---- preserve fallback when users call transform helpers ----
    def with_structured_output(self, *args, **kwargs):
        primary = self._primary.with_structured_output(*args, **kwargs)
        fallback = self._get_fallback().with_structured_output(*args, **kwargs)
        return FallbackLLM._from_models(
            primary=primary,
            fallback=fallback,
            primary_key=self._primary_key,
            fallback_key=self._fallback_key,
            temperature=self._temperature,
        )

    def bind_tools(self, *args, **kwargs):
        primary = self._primary.bind_tools(*args, **kwargs)
        fallback = self._get_fallback().bind_tools(*args, **kwargs)
        return FallbackLLM._from_models(
            primary=primary,
            fallback=fallback,
            primary_key=self._primary_key,
            fallback_key=self._fallback_key,
            temperature=self._temperature,
        )

    # ---- delegate everything else to primary (bind_tools, with_structured_output, etc.) ----
    def __getattr__(self, name: str):
        return getattr(self._primary, name)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_chat_model(
    model_key: str = DEFAULT_MODEL_KEY,
    temperature: float = 0.7,
) -> Any:
    """Return a raw LangChain chat model for the given model_key (no fallback)."""
    return _build(model_key, temperature)


def make_llm(
    model_key: str = DEFAULT_MODEL_KEY,
    temperature: float = 0.7,
    with_fallback: bool = True,
) -> Any:
    """
    Return an LLM instance.
    If with_fallback=True (default), wraps in FallbackLLM so Groq rate-limits
    transparently retry on Gemini.
    """
    if with_fallback and MODELS.get(model_key, {}).get("provider") == "groq":
        return FallbackLLM(model_key, DEFAULT_FALLBACK_KEY, temperature)
    return _build(model_key, temperature)


def get_chat_model_from_config(
    config: RunnableConfig | None,
    temperature: float = 0.7,
    with_fallback: bool = True,
) -> Any:
    """
    Read model_key from LangGraph configurable dict and return the right LLM.
    Defaults to DEFAULT_MODEL_KEY when no preference is set.
    """
    model_key = DEFAULT_MODEL_KEY
    if config:
        model_key = (config.get("configurable") or {}).get("model_key", DEFAULT_MODEL_KEY)
    return make_llm(model_key, temperature, with_fallback=with_fallback)
