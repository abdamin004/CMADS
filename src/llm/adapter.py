"""LLM Adapter — ChatGroq (cloud) with ChatOllama (local) fallback.

Provides a single get_llm() function that returns a configured LangChain
chat model. Defaults to Groq API for speed; falls back to local Ollama
if GROQ_API_KEY is not set.

Implements: IF-020–024, TECH_STACK §3.2
"""

from __future__ import annotations

import os
import time
from typing import Any

import structlog
from langchain_core.language_models import BaseChatModel

logger = structlog.get_logger()

# ── Configurable via .env ─────────────────────────────────────────────
# LLM_PROVIDER: "groq" (cloud) or "ollama" (local)
# LLM_MODEL: model name for the chosen provider
# LLM_EVALUATOR_MODEL: separate model for the LLM-as-Judge evaluator
# OLLAMA_URL: base URL for local Ollama server
DEFAULT_PROVIDER = os.environ.get("LLM_PROVIDER", "groq")
DEFAULT_GROQ_MODEL = os.environ.get("LLM_MODEL", "openai/gpt-oss-120b")
DEFAULT_OLLAMA_MODEL = os.environ.get("LLM_MODEL", "gpt-oss:120b")
DEFAULT_EVALUATOR_MODEL = os.environ.get("LLM_EVALUATOR_MODEL", "qwen/qwen3-32b")
DEFAULT_OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# LangSmith tracing — auto-enabled if LANGSMITH_API_KEY is set
if os.environ.get("LANGSMITH_API_KEY"):
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_PROJECT", "cmads-clinical-pipeline")
    os.environ.setdefault("LANGSMITH_ENDPOINT", "https://eu.api.smith.langchain.com")
    logger.info("langsmith_enabled",
                project=os.environ.get("LANGSMITH_PROJECT"),
                endpoint=os.environ.get("LANGSMITH_ENDPOINT"))


def get_llm(
    temperature: float = 0.2,
    max_tokens: int = 4096,
    model: str | None = None,
    provider: str | None = None,
    json_mode: bool = False,
) -> BaseChatModel:
    """Return a configured LLM instance.

    All defaults are read from environment variables (see .env.example):
        LLM_PROVIDER   → "groq" or "ollama"
        LLM_MODEL      → model name (e.g., "openai/gpt-oss-120b")
        OLLAMA_URL     → Ollama server URL (default localhost:11434)

    Args:
        temperature: Sampling temperature (lower = more deterministic).
        max_tokens: Maximum tokens to generate.
        model: Model name override (takes precedence over LLM_MODEL env var).
        provider: "groq" or "ollama" (defaults to LLM_PROVIDER env var).
        json_mode: If True, force JSON output (Groq only).

    Returns:
        A LangChain BaseChatModel (ChatOllama or ChatGroq).
    """
    provider = provider or DEFAULT_PROVIDER
    if provider == "groq":
        from langchain_groq import ChatGroq
        model_name = model or DEFAULT_GROQ_MODEL
        logger.info("llm_init", provider="groq", model=model_name,
                     temperature=temperature, json_mode=json_mode)
        kwargs = {}
        if json_mode:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        return ChatGroq(
            model=model_name,
            api_key=GROQ_API_KEY,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
    else:
        from langchain_ollama import ChatOllama
        model_name = model or DEFAULT_OLLAMA_MODEL
        logger.info("llm_init", provider="ollama", model=model_name,
                     temperature=temperature)
        return ChatOllama(
            model=model_name,
            base_url=DEFAULT_OLLAMA_URL,
            temperature=temperature,
            num_predict=max_tokens,
            num_ctx=16384,
        )


def get_evaluator_llm(temperature: float = 0.0, max_tokens: int = 1024) -> BaseChatModel:
    """Return the LLM used for evaluation (LLM-as-Judge).

    Configured via LLM_EVALUATOR_MODEL env var (default: qwen/qwen3-32b).
    Uses the same provider as the main LLM.
    """
    return get_llm(
        temperature=temperature,
        max_tokens=max_tokens,
        model=DEFAULT_EVALUATOR_MODEL,
    )


def invoke_with_retry(
    llm: BaseChatModel,
    messages: list,
    max_retries: int = 3,
    agent_id: str = "unknown",
) -> Any:
    """Invoke LLM with exponential backoff retry.

    Handles Groq json_mode validation failures by falling back to
    non-json_mode on retry.

    Implements NF-040 (graceful failure) and TECH_STACK §3.2 retry policy.
    """
    for attempt in range(1, max_retries + 1):
        try:
            start = time.time()
            response = llm.invoke(messages)
            duration = time.time() - start

            # Check for empty response (Groq json_mode can return empty)
            if not response.content or not response.content.strip():
                raise ValueError("LLM returned empty response")

            logger.info("llm_call_success",
                        agent_id=agent_id, attempt=attempt,
                        duration_s=round(duration, 2))
            return response
        except Exception as e:
            error_str = str(e)
            is_json_error = "json_validate_failed" in error_str or "Failed to validate JSON" in error_str
            wait = 2 ** attempt

            logger.warning("llm_call_retry",
                           agent_id=agent_id, attempt=attempt,
                           error=error_str[:200],
                           is_json_error=is_json_error,
                           retry_in=wait)

            if attempt == max_retries:
                # Last attempt: if json_mode caused it, try without json_mode
                if is_json_error:
                    logger.warning("llm_json_fallback",
                                   agent_id=agent_id,
                                   msg="Retrying without json_mode")
                    try:
                        fallback_llm = get_llm(
                            temperature=llm.temperature if hasattr(llm, 'temperature') else 0.2,
                            json_mode=False,
                        )
                        response = fallback_llm.invoke(messages)
                        if response.content and response.content.strip():
                            logger.info("llm_call_success",
                                        agent_id=agent_id, attempt=attempt,
                                        duration_s=0, fallback=True)
                            return response
                    except Exception:
                        pass
                logger.error("llm_call_failed",
                             agent_id=agent_id, attempts=max_retries,
                             error=error_str[:200])
                raise
            time.sleep(wait)
