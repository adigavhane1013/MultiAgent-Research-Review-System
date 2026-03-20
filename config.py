import os
from dotenv import load_dotenv

load_dotenv()

# ===============================
# API KEYS
# ===============================

GOOGLE_API_KEY       = os.getenv("GOOGLE_API_KEY")
TAVILY_API_KEY       = os.getenv("TAVILY_API_KEY")
OPENROUTER_API_KEY   = os.getenv("OPENROUTER_API_KEY")
GROQ_API_KEY         = os.getenv("GROQ_API_KEY")

# ===============================
# PRIMARY MODELS
# ===============================
# All 3 agents use Arcee Trinity — confirmed working on OpenRouter free tier

RESEARCH_MODEL  = "openrouter/arcee-ai/trinity-large-preview:free"
WRITER_MODEL    = "openrouter/arcee-ai/trinity-large-preview:free"
VALIDATOR_MODEL = "openrouter/arcee-ai/trinity-large-preview:free"

# ===============================
# MODEL FALLBACK LISTS
# ===============================
# When primary model hits 429 rate limit or 404, system tries these in order.
# All confirmed present on your OpenRouter account free tier.
# Ordered by capability — strongest first.
#
# How it works:
#   llms.py tries RESEARCH_MODEL first.
#   On RateLimitError or APIError, it tries RESEARCH_FALLBACKS[0], then [1], etc.
#   If all fallbacks fail, raises exception and triggers main.py retry logic.

RESEARCH_FALLBACKS = [
    "openrouter/meta-llama/llama-3.3-70b-instruct:free",   # 70B — strong structured output
    "openrouter/mistralai/mistral-small-3.1-24b-instruct:free",  # 24B — reliable
    "openrouter/google/gemma-3-27b-it:free",               # 27B — Google, different provider
    "openrouter/nousresearch/hermes-3-llama-3.1-405b:free", # 405B — largest available
]

WRITER_FALLBACKS = [
    "openrouter/meta-llama/llama-3.3-70b-instruct:free",
    "openrouter/mistralai/mistral-small-3.1-24b-instruct:free",
    "openrouter/google/gemma-3-27b-it:free",
    "openrouter/nousresearch/hermes-3-llama-3.1-405b:free",
]

VALIDATOR_FALLBACKS = [
    "openrouter/mistralai/mistral-small-3.1-24b-instruct:free",  # consistent, logical
    "openrouter/meta-llama/llama-3.3-70b-instruct:free",
    "openrouter/google/gemma-3-27b-it:free",
    "openrouter/nousresearch/hermes-3-llama-3.1-405b:free",
]

# ===============================
# LLM SETTINGS
# ===============================

MAX_TOKENS  = 2000
TEMPERATURE = 0.1

# ===============================
# SYSTEM SETTINGS
# ===============================

STRICT_VERBATIM_MODE = True
ENABLE_RETRY         = True
MAX_RETRY_ATTEMPTS   = 1

# ===============================
# SEARCH SETTINGS
# ===============================

# Tavily
SEARCH_MAX_RESULTS        = 7
SEARCH_CONTENT_LIMIT      = 3000   # chars per source
SEARCH_MIN_CONTENT_LENGTH = 200    # skip thin/TOC pages

# DuckDuckGo
DDG_MAX_RESULTS = 5

# All sources
SEARCH_DELAY_SECONDS = 2           # delay between API calls

# Retry / backoff
RETRY_BASE_DELAY_SECONDS  = 5
RETRY_MAX_ATTEMPTS        = 3
RETRY_BACKOFF_MULTIPLIER  = 2

# Agent delays — protects free tier per-minute token limits
AGENT_CALL_DELAY_SECONDS  = 15