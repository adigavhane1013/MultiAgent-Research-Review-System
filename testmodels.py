"""
test_models.py — Tests primary + fallback models via OpenRouter REST API.
No CrewAI, no LiteLLM — raw requests only for accurate connectivity testing.

Tests every model in config.py (primary + all fallbacks) so you know
exactly which models are reachable before starting a run.

Usage:
    python test_models.py
"""

import os
import requests
from dotenv import load_dotenv
load_dotenv()

from config import (
    RESEARCH_MODEL,   RESEARCH_FALLBACKS,
    WRITER_MODEL,     WRITER_FALLBACKS,
    VALIDATOR_MODEL,  VALIDATOR_FALLBACKS,
)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()

# Strip the "openrouter/" prefix — raw API doesn't need it
def _raw(model: str) -> str:
    return model.replace("openrouter/", "")


def test_model(model_id: str, label: str) -> bool:
    """
    Tests a single model via raw OpenRouter REST call.
    Returns True if reachable, False if rate limited or unavailable.
    """
    raw_id = _raw(model_id)
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": raw_id,
                "messages": [{"role": "user", "content": "Reply with one word: OK"}],
                "max_tokens": 10,
            },
            timeout=30,
        )
        data = response.json()

        if response.status_code == 200:
            reply = data["choices"][0]["message"]["content"].strip()
            print(f"   ✅ PASS  {label:<14} {raw_id}  →  '{reply[:30]}'")
            return True
        else:
            error_msg = data.get("error", {}).get("message", str(data))
            status = response.status_code
            tag = "RATE LIMIT" if status == 429 else ("NOT FOUND" if status == 404 else str(status))
            print(f"   ❌ {tag:<10} {label:<14} {raw_id}")
            print(f"              {error_msg[:120]}")
            return False

    except Exception as e:
        print(f"   ❌ ERROR   {label:<14} {raw_id}")
        print(f"              {str(e)[:120]}")
        return False


def test_agent_group(agent_name: str, primary: str, fallbacks: list) -> dict:
    """
    Tests primary + all fallbacks for one agent.
    Returns dict with model → bool results.
    """
    print(f"\n{'─'*58}")
    print(f"  {agent_name}")
    print(f"{'─'*58}")

    results = {}

    # Primary
    passed = test_model(primary, "PRIMARY")
    results[primary] = passed

    # Fallbacks
    for i, model in enumerate(fallbacks, 1):
        passed = test_model(model, f"FALLBACK {i}")
        results[model] = passed

    return results


def run():
    if not OPENROUTER_API_KEY:
        print("❌ OPENROUTER_API_KEY missing from .env")
        return

    print("\n" + "=" * 58)
    print("🧪 MODEL CONNECTIVITY TEST — PRIMARY + FALLBACKS")
    print("=" * 58)
    print(f"  OpenRouter key: {OPENROUTER_API_KEY[:12]}...{OPENROUTER_API_KEY[-4:]}")

    # Test all 3 agent groups
    research_results  = test_agent_group(
        "RESEARCH AGENT",  RESEARCH_MODEL,  RESEARCH_FALLBACKS
    )
    writer_results    = test_agent_group(
        "WRITER AGENT",    WRITER_MODEL,    WRITER_FALLBACKS
    )
    validator_results = test_agent_group(
        "VALIDATOR AGENT", VALIDATOR_MODEL, VALIDATOR_FALLBACKS
    )

    all_results = {**research_results, **writer_results, **validator_results}

    # ── Summary ───────────────────────────────────────────────
    print(f"\n{'='*58}")
    print("📊 SUMMARY")
    print(f"{'='*58}")

    passing = [m for m, ok in all_results.items() if ok]
    failing = [m for m, ok in all_results.items() if not ok]

    # Deduplicate (same model appears in multiple agent groups)
    unique_passing = list(dict.fromkeys(_raw(m) for m in passing))
    unique_failing = list(dict.fromkeys(_raw(m) for m in failing))

    print(f"\n  ✅ Reachable ({len(unique_passing)}):")
    for m in unique_passing:
        print(f"     - {m}")

    if unique_failing:
        print(f"\n  ❌ Unreachable ({len(unique_failing)}):")
        for m in unique_failing:
            print(f"     - {m}")

    # ── Recommendation ────────────────────────────────────────
    print(f"\n{'─'*58}")
    primary_raw = _raw(RESEARCH_MODEL)
    primary_ok  = research_results.get(RESEARCH_MODEL, False)
    any_fallback_ok = any(
        research_results.get(m, False) for m in RESEARCH_FALLBACKS
    )

    if primary_ok:
        print(f"  ✅ Primary model is UP — safe to run main.py")
    elif any_fallback_ok:
        first_ok = next(
            m for m in RESEARCH_FALLBACKS
            if research_results.get(m, False)
        )
        print(f"  ⚠ Primary DOWN — but fallback available: {_raw(first_ok)}")
        print(f"     System will auto-switch. Safe to run main.py")
    else:
        print(f"  ❌ PRIMARY and ALL FALLBACKS are down.")
        print(f"     Wait for rate limits to reset or add new models to config.py")

    print()


if __name__ == "__main__":
    run()