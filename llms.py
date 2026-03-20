import os
import time
from crewai import LLM
from dotenv import load_dotenv
from config import (
    TEMPERATURE,
    MAX_TOKENS,
    RESEARCH_MODEL,
    WRITER_MODEL,
    VALIDATOR_MODEL,
    RESEARCH_FALLBACKS,
    WRITER_FALLBACKS,
    VALIDATOR_FALLBACKS,
)

load_dotenv()

# ===============================
# Load & Validate API Key
# ===============================

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip().strip('"').strip("'")

if not OPENROUTER_API_KEY:
    raise EnvironmentError(
        "❌ OPENROUTER_API_KEY is missing from your .env file. "
        "Please add it and restart."
    )

os.environ["OPENROUTER_API_KEY"] = OPENROUTER_API_KEY
os.environ["OR_API_KEY"]         = OPENROUTER_API_KEY

print(f"✅ OpenRouter key loaded: {OPENROUTER_API_KEY[:12]}...{OPENROUTER_API_KEY[-4:]}")


# ===============================
# LLM Factory With Fallback
# ===============================

def _make_llm_with_fallback(
    primary_model: str,
    fallbacks: list,
    temperature: float,
    max_tokens: int,
    agent_name: str,
) -> LLM:
    """
    Tries to instantiate primary model first.
    On any exception, tries each fallback in order.
    No smoke test API calls — just clean instantiation.

    If ALL models fail to instantiate, raises RuntimeError
    which triggers main.py retry logic.
    """
    models_to_try = [primary_model] + fallbacks
    last_exception = None

    for i, model in enumerate(models_to_try):
        label = "PRIMARY" if i == 0 else f"FALLBACK {i}"
        try:
            llm = LLM(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=OPENROUTER_API_KEY,
            )
            if i > 0:
                print(f"   ✅ {agent_name} — using {label}: {model}")
            else:
                print(f"   ✅ {agent_name} — primary ready: {model}")
            return llm

        except Exception as e:
            error_str = str(e).lower()
            is_rate_limit = any(p in error_str for p in [
                "429", "rate limit", "quota", "too many requests",
                "resource exhausted", "temporarily",
            ])
            is_not_found = any(p in error_str for p in [
                "404", "not found", "no endpoints", "model not found",
            ])

            if is_rate_limit:
                print(f"   ⚠ {agent_name} — {label} rate limited (429): {model}")
            elif is_not_found:
                print(f"   ⚠ {agent_name} — {label} not available (404): {model}")
            else:
                print(f"   ⚠ {agent_name} — {label} failed ({type(e).__name__}): {model}")

            last_exception = e
            time.sleep(2)
            continue

    raise RuntimeError(
        f"❌ {agent_name} — all {len(models_to_try)} models failed. "
        f"Last error: {last_exception}"
    )


# ===============================
# LLM Factories
# ===============================

def get_gemini_llm() -> LLM:
    """Research Agent LLM — with automatic fallback."""
    return _make_llm_with_fallback(
        primary_model=RESEARCH_MODEL,
        fallbacks=RESEARCH_FALLBACKS,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        agent_name="Research Agent",
    )


def get_writer_llm() -> LLM:
    """Writer Agent LLM — with automatic fallback."""
    return _make_llm_with_fallback(
        primary_model=WRITER_MODEL,
        fallbacks=WRITER_FALLBACKS,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        agent_name="Writer Agent",
    )


def get_validator_llm() -> LLM:
    """Validator Agent LLM — temperature 0.0 for consistency, with automatic fallback."""
    return _make_llm_with_fallback(
        primary_model=VALIDATOR_MODEL,
        fallbacks=VALIDATOR_FALLBACKS,
        temperature=0.0,
        max_tokens=MAX_TOKENS,
        agent_name="Validator Agent",
    )