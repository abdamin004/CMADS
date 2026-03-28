"""LLM Adapter — Provider-agnostic LLM factory.

Supports any LangChain-compatible provider via a single .env configuration.
No code changes needed to switch between Groq, OpenAI, Gemini, Anthropic,
Ollama, or any other provider.

Supported providers (install the corresponding package):
    groq       → pip install langchain-groq        (GROQ_API_KEY)
    openai     → pip install langchain-openai       (OPENAI_API_KEY)
    anthropic  → pip install langchain-anthropic    (ANTHROPIC_API_KEY)
    gemini     → pip install langchain-google-genai (GOOGLE_API_KEY)
    ollama     → pip install langchain-ollama       (no key, local)

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
DEFAULT_PROVIDER = os.environ.get("LLM_PROVIDER", "groq")
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "openai/gpt-oss-120b")
DEFAULT_EVALUATOR_MODEL = os.environ.get("LLM_EVALUATOR_MODEL", "qwen/qwen3-32b")
DEFAULT_OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# ── Provider Registry ─────────────────────────────────────────────────
# Each provider entry: (package_import, class_name, api_key_env, extra_kwargs_fn)

def _groq_kwargs(model, temperature, max_tokens, json_mode):
    """Build kwargs for ChatGroq."""
    kwargs = {
        "model": model,
        "api_key": os.environ.get("GROQ_API_KEY", ""),
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
    return kwargs


def _openai_kwargs(model, temperature, max_tokens, json_mode):
    """Build kwargs for ChatOpenAI."""
    kwargs = {
        "model": model,
        "api_key": os.environ.get("OPENAI_API_KEY", ""),
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
    # Support custom base URL (e.g., Azure OpenAI, OpenRouter, local vLLM)
    base_url = os.environ.get("OPENAI_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url
    return kwargs


def _anthropic_kwargs(model, temperature, max_tokens, json_mode):
    """Build kwargs for ChatAnthropic."""
    kwargs = {
        "model": model,
        "api_key": os.environ.get("ANTHROPIC_API_KEY", ""),
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    # Anthropic doesn't have json_mode — JSON repair in base.py handles it
    return kwargs


def _gemini_kwargs(model, temperature, max_tokens, json_mode):
    """Build kwargs for ChatGoogleGenerativeAI."""
    kwargs = {
        "model": model,
        "google_api_key": os.environ.get("GOOGLE_API_KEY", ""),
        "temperature": temperature,
        "max_output_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_mime_type"] = "application/json"
    return kwargs


def _ollama_kwargs(model, temperature, max_tokens, json_mode):
    """Build kwargs for ChatOllama."""
    kwargs = {
        "model": model,
        "base_url": DEFAULT_OLLAMA_URL,
        "temperature": temperature,
        "num_predict": max_tokens,
        "num_ctx": 16384,
    }
    if json_mode:
        kwargs["format"] = "json"
    return kwargs


# Registry: provider name → (module_path, class_name, kwargs_builder)
PROVIDERS = {
    "groq":      ("langchain_groq",            "ChatGroq",                  _groq_kwargs),
    "openai":    ("langchain_openai",          "ChatOpenAI",                _openai_kwargs),
    "anthropic": ("langchain_anthropic",       "ChatAnthropic",             _anthropic_kwargs),
    "gemini":    ("langchain_google_genai",    "ChatGoogleGenerativeAI",    _gemini_kwargs),
    "ollama":    ("langchain_ollama",          "ChatOllama",                _ollama_kwargs),
}

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
    """Return a configured LLM instance for any supported provider.

    All defaults are read from environment variables (see .env.example):
        LLM_PROVIDER → "groq", "openai", "anthropic", "gemini", "ollama"
        LLM_MODEL    → model name for the chosen provider

    Args:
        temperature: Sampling temperature (lower = more deterministic).
        max_tokens: Maximum tokens to generate.
        model: Model name override (takes precedence over LLM_MODEL env var).
        provider: Provider override (takes precedence over LLM_PROVIDER env var).
        json_mode: If True, request JSON output (provider-specific implementation).

    Returns:
        A LangChain BaseChatModel instance.

    Raises:
        ValueError: If the provider is not in the registry.
        ImportError: If the provider's LangChain package is not installed.
    """
    provider = provider or DEFAULT_PROVIDER
    model_name = model or DEFAULT_MODEL

    if provider not in PROVIDERS:
        available = ", ".join(sorted(PROVIDERS.keys()))
        raise ValueError(
            f"Unknown LLM provider '{provider}'. "
            f"Supported: {available}. "
            f"Set LLM_PROVIDER in .env to one of these."
        )

    module_path, class_name, kwargs_fn = PROVIDERS[provider]

    # Lazy import — only loads the package for the chosen provider
    try:
        import importlib
        module = importlib.import_module(module_path)
        llm_class = getattr(module, class_name)
    except ImportError:
        raise ImportError(
            f"Provider '{provider}' requires package '{module_path}'. "
            f"Install it: pip install {module_path}"
        )

    kwargs = kwargs_fn(model_name, temperature, max_tokens, json_mode)

    logger.info("llm_init", provider=provider, model=model_name,
                temperature=temperature, json_mode=json_mode)

    return llm_class(**kwargs)


def get_evaluator_llm(temperature: float = 0.0, max_tokens: int = 1024) -> BaseChatModel:
    """Return the LLM used for evaluation (LLM-as-Judge).

    Configured via LLM_EVALUATOR_MODEL env var (default: qwen/qwen3-32b).
    Uses the same provider as the main LLM unless LLM_EVALUATOR_PROVIDER is set.
    """
    eval_provider = os.environ.get("LLM_EVALUATOR_PROVIDER")
    return get_llm(
        temperature=temperature,
        max_tokens=max_tokens,
        model=DEFAULT_EVALUATOR_MODEL,
        provider=eval_provider,
    )


def invoke_with_retry(
    llm: BaseChatModel,
    messages: list,
    max_retries: int = 3,
    agent_id: str = "unknown",
) -> Any:
    """Invoke LLM with exponential backoff retry.

    Handles json_mode validation failures by falling back to
    non-json_mode on the final attempt.

    Implements NF-040 (graceful failure) and TECH_STACK §3.2 retry policy.
    """
    for attempt in range(1, max_retries + 1):
        try:
            start = time.time()
            response = llm.invoke(messages)
            duration = time.time() - start

            # Check for empty response (some providers return empty on json_mode failure)
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
