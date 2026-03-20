"""
search.py — Multi-source search pipeline

Sources used per topic (all free, no extra API keys needed):
  1. Tavily API        — deep web search, news, blogs, docs
  2. DuckDuckGo        — diverse web results (no API key needed)
  3. Wikipedia         — structured factual baseline, always reliable

How it works:
  - Each source runs TWO searches: general + limitations-focused
  - All results combined and deduplicated by URL
  - Low quality domains filtered out (Reddit, Quora, social media)
  - Thin content filtered out (< 200 chars)
  - Final clean sources passed as one context string to the researcher

Install requirements:
  pip install tavily-python duckduckgo-search wikipedia-api
"""

import os
import time
import re
import wikipedia
from tavily import TavilyClient
from ddgs import DDGS

# ================================================================
# LOW QUALITY DOMAINS — filtered before passing to agents
# ================================================================

LOW_QUALITY_DOMAINS = [
    "reddit.com",
    "quora.com",
    "yahoo.com",
    "answers.com",
    "ask.com",
    "pinterest.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "instagram.com",
    "stackexchange.com",
]

# ================================================================
# SETTINGS
# ================================================================

TAVILY_MAX_RESULTS   = 7
DDG_MAX_RESULTS      = 5
MIN_CONTENT_LENGTH   = 200
CONTENT_LIMIT        = 3000   # chars per source passed to researcher
SEARCH_DELAY_SECONDS = 2      # delay between searches (rate limit safety)


# ================================================================
# HELPERS
# ================================================================

def _is_low_quality(url: str) -> bool:
    if not url:
        return False
    return any(domain in url.lower() for domain in LOW_QUALITY_DOMAINS)


def _is_thin(content: str) -> bool:
    return len(content.strip()) < MIN_CONTENT_LENGTH


def _clean_text(text: str) -> str:
    """Remove excessive whitespace and normalize line breaks."""
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ================================================================
# SOURCE 1 — TAVILY
# ================================================================

def _tavily_search(query: str) -> list:
    """
    Runs Tavily advanced search.
    Returns list of {title, url, content} dicts.
    """
    try:
        client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
        response = client.search(
            query,
            max_results=TAVILY_MAX_RESULTS,
            search_depth="advanced",
            include_raw_content=True,
        )
        results = []
        for r in response.get("results", []):
            content = r.get("raw_content") or r.get("content", "")
            results.append({
                "title":   r.get("title", "No Title"),
                "url":     r.get("url", ""),
                "content": content,
                "source":  "Tavily",
            })
        return results
    except Exception as e:
        print(f"⚠ Tavily error: {e}")
        return []


# ================================================================
# SOURCE 2 — DUCKDUCKGO
# ================================================================

def _ddg_search(query: str) -> list:
    """
    Runs DuckDuckGo text search.
    Returns list of {title, url, content} dicts.
    No API key required.
    """
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=DDG_MAX_RESULTS):
                content = r.get("body", "")
                results.append({
                    "title":   r.get("title", "No Title"),
                    "url":     r.get("href", ""),
                    "content": content,
                    "source":  "DuckDuckGo",
                })
        return results
    except Exception as e:
        print(f"⚠ DuckDuckGo error: {e}")
        return []


# ================================================================
# SOURCE 3 — WIKIPEDIA
# ================================================================

def _wikipedia_search(query: str) -> list:
    """
    Fetches Wikipedia article for the topic.
    Wikipedia is structured, factual, and always has:
    - Overview
    - How it works
    - Applications/Use Cases
    - Criticism/Limitations

    This makes it perfect for filling all 4 researcher categories.
    No API key required.
    """
    try:
        wikipedia.set_lang("en")

        # Try exact search first
        search_results = wikipedia.search(query, results=3)
        if not search_results:
            return []

        articles = []
        for title in search_results[:2]:  # top 2 Wikipedia matches
            try:
                page = wikipedia.page(title, auto_suggest=False)
                content = _clean_text(page.content)

                if _is_thin(content):
                    continue

                articles.append({
                    "title":   f"Wikipedia: {page.title}",
                    "url":     page.url,
                    "content": content,
                    "source":  "Wikipedia",
                })
            except wikipedia.exceptions.DisambiguationError as e:
                # Pick first option from disambiguation
                try:
                    page = wikipedia.page(e.options[0], auto_suggest=False)
                    content = _clean_text(page.content)
                    if not _is_thin(content):
                        articles.append({
                            "title":   f"Wikipedia: {page.title}",
                            "url":     page.url,
                            "content": content,
                            "source":  "Wikipedia",
                        })
                except Exception:
                    continue
            except Exception:
                continue

        return articles

    except Exception as e:
        print(f"⚠ Wikipedia error: {e}")
        return []


# ================================================================
# COMBINE + DEDUPLICATE + FILTER
# ================================================================

def _merge_results(all_results: list) -> list:
    """
    Deduplicates by URL, filters low quality domains and thin content.
    Returns clean, unique list of results.
    """
    seen_urls = set()
    clean = []
    skipped_duplicate = 0
    skipped_domain = 0
    skipped_thin = 0

    for r in all_results:
        url = r.get("url", "")

        # Deduplicate
        if url and url in seen_urls:
            skipped_duplicate += 1
            continue
        if url:
            seen_urls.add(url)

        # Domain quality filter
        if _is_low_quality(url):
            skipped_domain += 1
            continue

        # Thin content filter
        if _is_thin(r.get("content", "")):
            skipped_thin += 1
            continue

        clean.append(r)

    if skipped_duplicate > 0:
        print(f"   ↩ Removed {skipped_duplicate} duplicate URL(s)")
    if skipped_domain > 0:
        print(f"   🚫 Removed {skipped_domain} low-quality domain(s)")
    if skipped_thin > 0:
        print(f"   ✂ Removed {skipped_thin} thin/TOC source(s)")

    return clean


# ================================================================
# BUILD CONTEXT STRING
# ================================================================

def _build_context(results: list) -> tuple[str, int]:
    """
    Converts clean result list into numbered [SOURCE N] context string
    for the researcher agent.
    Returns (context_string, source_count).
    """
    context = ""
    source_count = 0

    for r in results:
        content = r["content"][:CONTENT_LIMIT]
        source_count += 1

        context += f"[SOURCE {source_count}] {r['title']}\n"
        context += f"URL: {r['url']}\n"
        context += f"Provider: {r['source']}\n"
        context += f"CONTENT:\n{content}\n\n"
        context += f"{'─' * 60}\n\n"

    return context, source_count


# ================================================================
# MAIN ENTRY POINT
# ================================================================

def search_web(query: str) -> tuple[str, int]:
    """
    Multi-source search pipeline:
      Tavily + DuckDuckGo + Wikipedia

    Runs TWO searches per source:
      1. General: "{query}"
      2. Limitations: "{query} limitations disadvantages problems"

    Returns:
      - context string (for researcher agent)
      - source_count int (for metrics)
    """

    limitations_query = f"{query} limitations disadvantages problems weaknesses"

    print(f"\n{'─'*55}")
    print(f"🔍 MULTI-SOURCE SEARCH: '{query}'")
    print(f"{'─'*55}")

    all_results = []

    # ----------------------------------------------------------------
    # TAVILY — General + Limitations
    # ----------------------------------------------------------------
    print(f"\n[1/3] Tavily — general search...")
    tavily_general = _tavily_search(query)
    print(f"      → {len(tavily_general)} results")
    all_results.extend(tavily_general)

    time.sleep(SEARCH_DELAY_SECONDS)

    print(f"[1/3] Tavily — limitations search...")
    tavily_limits = _tavily_search(limitations_query)
    print(f"      → {len(tavily_limits)} results")
    all_results.extend(tavily_limits)

    time.sleep(SEARCH_DELAY_SECONDS)

    # ----------------------------------------------------------------
    # DUCKDUCKGO — General + Limitations
    # ----------------------------------------------------------------
    print(f"\n[2/3] DuckDuckGo — general search...")
    ddg_general = _ddg_search(query)
    print(f"      → {len(ddg_general)} results")
    all_results.extend(ddg_general)

    time.sleep(SEARCH_DELAY_SECONDS)

    print(f"[2/3] DuckDuckGo — limitations search...")
    ddg_limits = _ddg_search(limitations_query)
    print(f"      → {len(ddg_limits)} results")
    all_results.extend(ddg_limits)

    time.sleep(SEARCH_DELAY_SECONDS)

    # ----------------------------------------------------------------
    # WIKIPEDIA — fetches top 2 articles for the topic
    # Wikipedia already covers limitations/criticism internally
    # so only one search needed
    # ----------------------------------------------------------------
    print(f"\n[3/3] Wikipedia — fetching articles...")
    wiki_results = _wikipedia_search(query)
    print(f"      → {len(wiki_results)} article(s)")
    all_results.extend(wiki_results)

    # ----------------------------------------------------------------
    # MERGE + FILTER
    # ----------------------------------------------------------------
    print(f"\n📊 Raw sources collected: {len(all_results)}")
    print(f"   Filtering duplicates, low-quality domains, thin content...")

    clean_results = _merge_results(all_results)

    print(f"   ✅ Clean sources after filtering: {len(clean_results)}")

    # ----------------------------------------------------------------
    # SOURCE BREAKDOWN
    # ----------------------------------------------------------------
    tavily_count = sum(1 for r in clean_results if r["source"] == "Tavily")
    ddg_count    = sum(1 for r in clean_results if r["source"] == "DuckDuckGo")
    wiki_count   = sum(1 for r in clean_results if r["source"] == "Wikipedia")

    print(f"   📌 Tavily: {tavily_count} | DuckDuckGo: {ddg_count} | Wikipedia: {wiki_count}")

    # ----------------------------------------------------------------
    # BUILD CONTEXT
    # ----------------------------------------------------------------
    if not clean_results:
        print("⚠ No clean sources found after filtering.")
        return "No search results found.", 0

    context, source_count = _build_context(clean_results)

    print(f"\n✅ {source_count} sources passed to researcher agent\n")

    return context, source_count