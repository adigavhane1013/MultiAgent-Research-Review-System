"""
test_guards.py — Automated tests for all quality guards in main.py

Tests verify that every guard correctly catches the exact failure
modes that have occurred in real runs.

Run with:
    pytest test_guards.py -v

Real bugs these tests are based on:
- Guard 1: MoE run returned "!!!!!!!" garbage
- Guard 1: Agentic AI run — researcher returned filler only, zero SOURCE_QUOTEs
- Guard 1: Fix 3 — compact [Category|N] format was not recognised by Guard 1,
           causing every valid compact researcher output to fail Guard 1
- Guard 2: Prompt Engineering run — writer returned filler with no document
- Guard 2: Agentic AI run — writer invented document with only 1 citation
- Guard 3: RLHF run — validator said PASS but 3 claims had VERIFIED: NO
- Guard 3: Neural Networks — DUPLICATE_EVIDENCE abuse passed validator
- Guard 3: Agentic AI — QUOTE_IN_SOURCES: NO (fabricated quotes)
- Guard 3: Fix 5 — compact Q:/D:/S:/V: signals must also trigger verdict override
- Guard 4: Kubernetes run — validator output truncated by MAX_TOKENS
- Guard 4: Fix 5 — compact C: claim lines must be accepted (not just CLAIM:)
"""
import os
os.environ["TESTING"] = "1"  # add right after the imports

import pytest
from main import (
    _is_valid_research_output,
    _is_valid_writer_output,
    _get_true_verdict,
    _is_valid_validator_output,
)


# ================================================================
# GUARD 1 — Research Output Quality
# ================================================================

def test_guard1_passes_valid_research():
    """✅ Real structured research output with 2+ SOURCE_QUOTEs should pass"""
    valid = """
    FACT: LangChain is an open-source framework for building LLM applications.
    SOURCE_QUOTE: "LangChain is an open-source framework for building LLM applications."
    SOURCE_NUM: [SOURCE 1]
    CATEGORY: General

    FACT: LangChain supports both Python and JavaScript.
    SOURCE_QUOTE: "It comes in both Python and JavaScript versions."
    SOURCE_NUM: [SOURCE 2]
    CATEGORY: Features
    """
    assert _is_valid_research_output(valid) is True


def test_guard1_catches_exclamation_garbage():
    """❌ MoE failure — 1000 exclamation marks should fail"""
    garbage = "!" * 1000
    assert _is_valid_research_output(garbage) is False


def test_guard1_catches_empty_output():
    """❌ Empty string should fail"""
    assert _is_valid_research_output("") is False


def test_guard1_catches_none_output():
    """❌ None should fail"""
    assert _is_valid_research_output(None) is False


def test_guard1_catches_near_empty_output():
    """❌ Less than 100 chars should fail"""
    assert _is_valid_research_output("Some short text.") is False


def test_guard1_catches_missing_signals():
    """❌ Long text but missing all of FACT/SOURCE_QUOTE/SOURCE_NUM/CATEGORY"""
    long_but_wrong = "This is a very long response with no structure at all. " * 20
    assert _is_valid_research_output(long_but_wrong) is False


def test_guard1_catches_filler_only_no_source_quotes():
    """❌ Agentic AI root cause — filler phrase + zero SOURCE_QUOTEs"""
    filler = "Thought: I now can give a great answer\n\nAgentic AI is very interesting."
    assert _is_valid_research_output(filler) is False


def test_guard1_catches_only_one_source_quote():
    """❌ Only 1 SOURCE_QUOTE — minimum is 2 for a real run"""
    one_quote = """
    FACT: LangChain is a framework.
    SOURCE_QUOTE: "LangChain is a framework."
    SOURCE_NUM: [SOURCE 1]
    CATEGORY: General
    """ + "Some extra content to make it long enough. " * 5
    assert _is_valid_research_output(one_quote) is False


def test_guard1_passes_with_two_source_quotes():
    """✅ Exactly 2 SOURCE_QUOTEs should pass"""
    two_quotes = """
    FACT: LangChain is a framework.
    SOURCE_QUOTE: "LangChain is a framework for LLM apps."
    SOURCE_NUM: [SOURCE 1]
    CATEGORY: General

    FACT: LangChain supports agents.
    SOURCE_QUOTE: "LangChain supports building autonomous agents."
    SOURCE_NUM: [SOURCE 2]
    CATEGORY: Features
    """
    assert _is_valid_research_output(two_quotes) is True


# ----------------------------------------------------------------
# GUARD 1 — Compact format tests (Fix 3: [Category|N] format)
# ----------------------------------------------------------------

def test_guard1_passes_compact_format():
    """✅ Fix 3 — compact [Category|N] lines should pass Guard 1"""
    compact = (
        '[General|1] "Redis is an open-source in-memory data structure store used as a database cache."\n'
        '[Features|2] "Redis supports strings, hashes, lists, sets, and sorted sets with range queries."\n'
        '[UseCases|3] "Uber uses Redis for real-time trip tracking and driver dispatching at scale."\n'
    )
    assert _is_valid_research_output(compact) is True


def test_guard1_compact_all_four_categories_recognised():
    """✅ All four category prefixes (General/Features/UseCases/Limitations) must be valid"""
    for cat in ["General", "Features", "UseCases", "Limitations"]:
        output = (
            f'[{cat}|1] "Some specific verifiable fact extracted directly from a real source."\n'
            f'[{cat}|2] "Another specific fact about a named company or domain with enough detail."\n'
        )
        assert _is_valid_research_output(output) is True, f"Category '{cat}' not recognised by Guard 1"


def test_guard1_compact_invalid_category_not_counted():
    """❌ Unknown category prefix must NOT count as a valid signal"""
    invalid = (
        '[Unknown|1] "This should not count as a valid compact signal at all here."\n'
        '[Random|2] "Neither should this one count as a valid structured fact output."\n'
    )
    assert _is_valid_research_output(invalid) is False


def test_guard1_compact_single_signal_fails():
    """❌ Only 1 compact signal — minimum is 2 (same threshold as legacy format)"""
    one_signal = '[General|1] "Redis is a fast in-memory database widely used in production systems."\n'
    assert _is_valid_research_output(one_signal) is False


def test_guard1_mixed_format_passes():
    """✅ Mix of legacy SOURCE_QUOTE and compact [Category|N] both count toward minimum"""
    mixed = (
        'SOURCE_QUOTE: "Redis was created by Salvatore Sanfilippo in 2009 as an in-memory key-value store."\n'
        '[Features|2] "Redis supports pub/sub messaging, atomic operations, and Lua scripting natively."\n'
    )
    assert _is_valid_research_output(mixed) is True


def test_guard1_compact_filler_still_fails():
    """❌ Compact signals present but filler phrase at start — must still fail"""
    filler_with_compact = (
        'I now can give a great answer about Redis performance.\n'
        '[General|1] "Redis is an in-memory data structure store used as a database and cache."\n'
        '[Features|2] "Redis supports atomic operations on strings, hashes, lists, sets and sorted sets."\n'
    )
    assert _is_valid_research_output(filler_with_compact) is False


# ================================================================
# GUARD 2 — Writer Output Quality
# ================================================================

def test_guard2_passes_valid_writer_output():
    """✅ Real structured document with 4+ citations should pass"""
    valid = """# LANGCHAIN

## Overview
LangChain is an open-source framework. [CITE: "LangChain is an open-source framework for building LLM applications."]

## Key Concepts
- It supports Python and JavaScript. [CITE: "It comes in both Python and JavaScript versions."]

## Real-World Use Cases
- Used to build chatbots and agents. [CITE: "Used to build chatbots and autonomous agents."]

## Limitations
- Can be slow to optimize for production. [CITE: "Can be slow to optimize for production use cases."]
"""
    assert _is_valid_writer_output(valid) is True


def test_guard2_catches_filler_phrase_thought():
    """❌ Prompt Engineering failure — 'I now can give a great answer' filler"""
    filler = "I now can give a great answer\n\nSome more text here that goes on."
    assert _is_valid_writer_output(filler) is False


def test_guard2_catches_filler_phrase_here_is():
    """❌ 'Here is the document' filler at start should fail"""
    filler = "Here is the document you requested:\n\n## Overview\nSomething [CITE: 'x']\n## Key Concepts\n- x [CITE: 'x']\n## Real-World Use Cases\n- x [CITE: 'x']\n## Limitations\n- x [CITE: 'x']"
    assert _is_valid_writer_output(filler) is False


def test_guard2_catches_empty_output():
    """❌ Empty output should fail"""
    assert _is_valid_writer_output("") is False


def test_guard2_catches_none_output():
    """❌ None should fail"""
    assert _is_valid_writer_output(None) is False


def test_guard2_catches_missing_overview():
    """❌ Missing ## Overview section should fail"""
    missing_section = """# LANGCHAIN

## Key Concepts
- Something [CITE: "Something real from source"]

## Real-World Use Cases
- Something [CITE: "Something real from source"]

## Limitations
- Something [CITE: "Something real from source"]
"""
    assert _is_valid_writer_output(missing_section) is False


def test_guard2_catches_missing_limitations():
    """❌ Missing ## Limitations section should fail"""
    missing_section = """# LANGCHAIN

## Overview
Something [CITE: "Something real from source"]

## Key Concepts
- Something [CITE: "Something real from source"]

## Real-World Use Cases
- Something [CITE: "Something real from source"]
"""
    assert _is_valid_writer_output(missing_section) is False


def test_guard2_catches_missing_key_concepts():
    """❌ Missing ## Key Concepts section should fail"""
    missing_section = """# LANGCHAIN

## Overview
Something [CITE: "Something real"]

## Real-World Use Cases
- Something [CITE: "Something real"]

## Limitations
- Something [CITE: "Something real"]
"""
    assert _is_valid_writer_output(missing_section) is False


def test_guard2_catches_missing_use_cases():
    """❌ Missing ## Real-World Use Cases section should fail"""
    missing_section = """# LANGCHAIN

## Overview
Something [CITE: "Something real"]

## Key Concepts
- Something [CITE: "Something real"]

## Limitations
- Something [CITE: "Something real"]
"""
    assert _is_valid_writer_output(missing_section) is False


def test_guard2_catches_no_cite_tags():
    """❌ Agentic AI failure — document with no [CITE: tags (pure hallucination)"""
    no_cites = """# LANGCHAIN

## Overview
LangChain is a framework for building LLM applications.

## Key Concepts
- It supports Python and JavaScript development.

## Real-World Use Cases
- Used for building chatbots and agents.

## Limitations
- Can be slow in production environments.
"""
    assert _is_valid_writer_output(no_cites) is False


def test_guard2_catches_too_few_citations():
    """❌ Agentic AI failure — only 1-3 citations (thin hallucinated document)"""
    thin_doc = """# LANGCHAIN

## Overview
LangChain is a framework. [CITE: "LangChain is a framework."]
It supports agents.
It works with Python.

## Key Concepts
- Supports chaining of LLM calls.

## Real-World Use Cases
- Used for chatbots.

## Limitations
- Can be complex to configure.
"""
    assert _is_valid_writer_output(thin_doc) is False


def test_guard2_catches_too_short():
    """❌ Under 200 chars even with section headers should fail"""
    too_short = "## Overview\n## Key Concepts\n## Real-World Use Cases\n## Limitations"
    assert _is_valid_writer_output(too_short) is False


# ================================================================
# GUARD 3 — Verdict Override
# ================================================================

def test_guard3_keeps_clean_pass():
    """✅ All claims verified, no failures — should stay PASS"""
    clean_pass = """
CLAIM: LangChain is a framework.
CITE_TAG_PRESENT: YES
EVIDENCE: "LangChain is a framework."
QUOTE_IN_SOURCES: YES
DUPLICATE_EVIDENCE: NO
VERIFIED: YES
VERDICT: PASS

Structure Score: 10/10
Clarity Score: 10/10
Factual Confidence: 10/10
Verdict: PASS
"""
    assert _get_true_verdict(clean_pass) == "PASS"


def test_guard3_overrides_false_pass_verified_no():
    """❌ RLHF failure — validator said PASS but VERIFIED: NO exists"""
    contradictory = """
CLAIM: Some claim.
CITE_TAG_PRESENT: YES
VERIFIED: NO
VERDICT: FAIL

Structure Score: 8/10
Clarity Score: 8/10
Factual Confidence: 8/10
Verdict: PASS
"""
    assert _get_true_verdict(contradictory) == "FAIL"


def test_guard3_overrides_false_pass_cite_missing():
    """❌ Validator said PASS but CITE_TAG_PRESENT: NO exists"""
    contradictory = """
CLAIM: Some claim.
CITE_TAG_PRESENT: NO
VERIFIED: YES
VERDICT: FAIL

Verdict: PASS
"""
    assert _get_true_verdict(contradictory) == "FAIL"


def test_guard3_overrides_false_pass_duplicate_evidence():
    """❌ Neural Networks failure — DUPLICATE_EVIDENCE: YES should override to FAIL"""
    duplicate = """
CLAIM: First claim.
CITE_TAG_PRESENT: YES
EVIDENCE: "Same quote used twice."
QUOTE_IN_SOURCES: YES
DUPLICATE_EVIDENCE: NO
VERIFIED: YES
VERDICT: PASS

CLAIM: Second claim.
CITE_TAG_PRESENT: YES
EVIDENCE: "Same quote used twice."
QUOTE_IN_SOURCES: YES
DUPLICATE_EVIDENCE: YES
VERIFIED: NO
VERDICT: FAIL

Structure Score: 10/10
Clarity Score: 10/10
Factual Confidence: 10/10
Verdict: PASS
"""
    assert _get_true_verdict(duplicate) == "FAIL"


def test_guard3_overrides_false_pass_quote_not_in_sources():
    """❌ Agentic AI failure — QUOTE_IN_SOURCES: NO means fabricated quote"""
    fabricated = """
CLAIM: Agentic AI refers to autonomous software agents.
CITE_TAG_PRESENT: YES
EVIDENCE: "Agentic AI refers to autonomous software agents."
QUOTE_IN_SOURCES: NO
DUPLICATE_EVIDENCE: NO
VERIFIED: NO
VERDICT: FAIL

Structure Score: 10/10
Clarity Score: 10/10
Factual Confidence: 10/10
Verdict: PASS
"""
    assert _get_true_verdict(fabricated) == "FAIL"


def test_guard3_keeps_real_fail():
    """✅ Real FAIL should stay FAIL"""
    real_fail = """
CLAIM: Some claim.
VERIFIED: NO
Verdict: FAIL
"""
    assert _get_true_verdict(real_fail) == "FAIL"


def test_guard3_multiple_verified_no_overrides():
    """❌ Multiple VERIFIED: NO — should override to FAIL"""
    multiple_failures = """
VERIFIED: NO
VERIFIED: NO
VERIFIED: NO
Verdict: PASS
"""
    assert _get_true_verdict(multiple_failures) == "FAIL"


def test_guard3_multiple_fabricated_overrides():
    """❌ Multiple QUOTE_IN_SOURCES: NO — should override to FAIL"""
    multiple_fabricated = """
QUOTE_IN_SOURCES: NO
QUOTE_IN_SOURCES: NO
Verdict: PASS
"""
    assert _get_true_verdict(multiple_fabricated) == "FAIL"


def test_guard3_overrides_false_pass_semantic_mismatch():
    """❌ Cyber Security failure — positive quote used as limitation evidence"""
    semantic_mismatch = """
CLAIM: The world of cybersecurity is doing incredibly well in tough circumstances, implying there are inherent limitations and weaknesses.
CITE_TAG_PRESENT: YES
EVIDENCE: "In my mind, the world of cybersecurity is doing incredibly well in tough circumstances."
QUOTE_IN_SOURCES: YES
DUPLICATE_EVIDENCE: NO
SEMANTIC_MATCH: NO
VERIFIED: NO
VERDICT: FAIL

Structure Score: 10/10
Clarity Score: 10/10
Factual Confidence: 10/10
Verdict: PASS
"""
    assert _get_true_verdict(semantic_mismatch) == "FAIL"


def test_guard3_overrides_false_pass_repetition_fail():
    """❌ Cyber Security failure — repeated definition sentences in Overview"""
    repetition = """
REPETITION_FAIL: YES

Structure Score: 10/10
Clarity Score: 10/10
Factual Confidence: 10/10
Verdict: PASS
"""
    assert _get_true_verdict(repetition) == "FAIL"


def test_guard3_keeps_pass_with_semantic_match():
    """✅ Claim and evidence semantically aligned — should stay PASS"""
    semantic_pass = """
CLAIM: Kafka has a steep learning curve for new developers.
CITE_TAG_PRESENT: YES
EVIDENCE: "Kafka has a steep learning curve due to its distributed nature."
QUOTE_IN_SOURCES: YES
DUPLICATE_EVIDENCE: NO
SEMANTIC_MATCH: YES
VERIFIED: YES
VERDICT: PASS

Structure Score: 10/10
Clarity Score: 10/10
Factual Confidence: 10/10
Verdict: PASS
"""
    assert _get_true_verdict(semantic_pass) == "PASS"


# ----------------------------------------------------------------
# GUARD 3 — Compact format signal tests (Fix 5: Q:/D:/S:/V: format)
# ----------------------------------------------------------------

def test_guard3_compact_q_no_overrides_pass():
    """❌ Fix 5 — compact Q: NO (fabricated quote) must override stated PASS"""
    compact_fabricated = """
C: Redis was invented in 2005 by engineers at Twitter for caching tweets.
Q: NO | D: NO | S: NO | V: FAIL

Structure Score: 10/10
Clarity Score: 10/10
Factual Confidence: 10/10
Verdict: PASS
"""
    assert _get_true_verdict(compact_fabricated) == "FAIL"


def test_guard3_compact_d_yes_overrides_pass():
    """❌ Fix 5 — compact D: YES (duplicate evidence) must override stated PASS"""
    compact_duplicate = """
C: Redis supports pub/sub messaging for event-driven architectures.
Q: YES | D: YES | S: YES | V: PASS

Structure Score: 10/10
Clarity Score: 10/10
Factual Confidence: 10/10
Verdict: PASS
"""
    assert _get_true_verdict(compact_duplicate) == "FAIL"


def test_guard3_compact_s_no_overrides_pass():
    """❌ Fix 5 — compact S: NO (semantic mismatch) must override stated PASS"""
    compact_semantic = """
C: Redis has significant limitations and is known to be slow in production.
Q: YES | D: NO | S: NO | V: FAIL

Structure Score: 10/10
Clarity Score: 10/10
Factual Confidence: 10/10
Verdict: PASS
"""
    assert _get_true_verdict(compact_semantic) == "FAIL"


def test_guard3_compact_v_fail_overrides_pass():
    """❌ Fix 5 — compact V: FAIL must override stated PASS"""
    compact_verdict_fail = """
C: Redis was originally designed for PostgreSQL as a caching layer only.
Q: NO | D: NO | S: NO | V: FAIL

Structure Score: 10/10
Clarity Score: 10/10
Factual Confidence: 10/10
Verdict: PASS
"""
    assert _get_true_verdict(compact_verdict_fail) == "FAIL"


def test_guard3_compact_all_pass_stays_pass():
    """✅ Fix 5 — all compact signals passing (Q:YES D:NO S:YES V:PASS) stays PASS"""
    clean_compact = """
C: Redis stores data in memory for fast read and write operations.
Q: YES | D: NO | S: YES | V: PASS
C: Redis was created by Salvatore Sanfilippo and released in 2009.
Q: YES | D: NO | S: YES | V: PASS
C: Uber uses Redis for real-time trip tracking and driver location caching.
Q: YES | D: NO | S: YES | V: PASS

Structure Score: 10/10
Clarity Score: 10/10
Factual Confidence: 10/10
Verdict: PASS
"""
    assert _get_true_verdict(clean_compact) == "PASS"


def test_guard3_compact_backward_compat_with_legacy():
    """✅ Fix 5 — mixed compact + legacy signals in same output both detected"""
    mixed_signals = """
CLAIM: Some legacy-format claim here.
QUOTE_IN_SOURCES: NO
VERIFIED: NO
VERDICT: FAIL

C: Some compact-format claim here with a fabricated quote added.
Q: NO | D: NO | S: NO | V: FAIL

Structure Score: 10/10
Clarity Score: 10/10
Factual Confidence: 10/10
Verdict: PASS
"""
    assert _get_true_verdict(mixed_signals) == "FAIL"


# ================================================================
# GUARD 4 — Validator Output Quality
# ================================================================

def test_guard4_passes_complete_validator_output():
    """✅ Complete validator output with all required fields should pass"""
    complete = """
CLAIM: LangChain is a framework.
CITE_TAG_PRESENT: YES
EVIDENCE: "LangChain is a framework."
QUOTE_IN_SOURCES: YES
DUPLICATE_EVIDENCE: NO
VERIFIED: YES
VERDICT: PASS

Structure Score: 10/10
Clarity Score: 10/10
Factual Confidence: 10/10
Verdict: PASS
"""
    assert _is_valid_validator_output(complete) is True


def test_guard4_catches_empty_output():
    """❌ Empty validator output should fail"""
    assert _is_valid_validator_output("") is False


def test_guard4_catches_none_output():
    """❌ None should fail"""
    assert _is_valid_validator_output(None) is False


def test_guard4_catches_missing_structure_score():
    """❌ Kubernetes failure — missing Structure Score means truncated by MAX_TOKENS"""
    missing_score = """
CLAIM: Something.
CITE_TAG_PRESENT: YES
VERIFIED: YES
Verdict: PASS
"""
    assert _is_valid_validator_output(missing_score) is False


def test_guard4_catches_missing_verdict():
    """❌ Missing Verdict line — validator didn't finish"""
    missing_verdict = """
CLAIM: Something.
CITE_TAG_PRESENT: YES
VERIFIED: YES
Structure Score: 10/10
Clarity Score: 10/10
Factual Confidence: 10/10
"""
    assert _is_valid_validator_output(missing_verdict) is False


def test_guard4_catches_too_short():
    """❌ Under 100 chars should fail"""
    too_short = "Verdict: PASS"
    assert _is_valid_validator_output(too_short) is False


def test_guard4_catches_no_claim_entries():
    """❌ Validator skipped audit entirely — no CLAIM: entries"""
    no_audit = """
The document looks good overall and covers all required sections.

Structure Score: 10/10
Clarity Score: 10/10
Factual Confidence: 10/10
Verdict: PASS
"""
    assert _is_valid_validator_output(no_audit) is False


def test_guard4_catches_filler_at_start():
    """❌ Validator starting with filler instead of audit"""
    filler = """I now can give a great answer

CLAIM: Something.
CITE_TAG_PRESENT: YES
VERIFIED: YES
Structure Score: 10/10
Verdict: PASS
"""
    assert _is_valid_validator_output(filler) is False


# ----------------------------------------------------------------
# GUARD 4 — Compact format tests (Fix 5: C: claim line format)
# ----------------------------------------------------------------

def test_guard4_passes_compact_validator_output():
    """✅ Fix 5 — compact C: claim lines should be accepted by Guard 4"""
    compact = (
        'C: Redis stores data in memory for extremely fast read and write operations.\n'
        'Q: YES | D: NO | S: YES | V: PASS\n'
        'C: Redis was created by Salvatore Sanfilippo and first released publicly in 2009.\n'
        'Q: YES | D: NO | S: YES | V: PASS\n'
        'Structure Score: 10/10\n'
        'Clarity Score: 10/10\n'
        'Factual Confidence: 10/10\n'
        'Verdict: PASS\n'
    )
    assert _is_valid_validator_output(compact) is True


def test_guard4_compact_missing_score_lines_fails():
    """❌ Fix 5 — compact C: audit present but score lines truncated — must fail"""
    truncated_compact = (
        'C: Redis stores data in memory for fast access.\n'
        'Q: YES | D: NO | S: YES | V: PASS\n'
        'C: Redis supports atomic operations on multiple data types natively.\n'
        'Q: YES | D: NO | S: YES | V: PASS\n'
    )
    assert _is_valid_validator_output(truncated_compact) is False


def test_guard4_compact_no_claim_lines_fails():
    """❌ Fix 5 — score lines present but zero C: or CLAIM: entries — audit was skipped"""
    no_audit = (
        'The document appears well-structured with adequate sourcing throughout.\n'
        'All claims seem reasonable based on the provided search context available.\n'
        'Structure Score: 10/10\n'
        'Clarity Score: 10/10\n'
        'Factual Confidence: 10/10\n'
        'Verdict: PASS\n'
    )
    assert _is_valid_validator_output(no_audit) is False


def test_guard4_legacy_claim_still_accepted():
    """✅ Fix 5 — legacy CLAIM: format must still pass Guard 4 (backward compat)"""
    legacy = (
        'CLAIM: Redis is a fast in-memory data structure store.\n'
        'CITE_TAG_PRESENT: YES\n'
        'EVIDENCE: "Redis is a fast in-memory data structure store."\n'
        'QUOTE_IN_SOURCES: YES\n'
        'DUPLICATE_EVIDENCE: NO\n'
        'VERIFIED: YES\n'
        'VERDICT: PASS\n'
        'Structure Score: 10/10\n'
        'Clarity Score: 10/10\n'
        'Factual Confidence: 10/10\n'
        'Verdict: PASS\n'
    )
    assert _is_valid_validator_output(legacy) is True


def test_guard4_mixed_compact_and_legacy_accepted():
    """✅ Fix 5 — validator output mixing CLAIM: and C: lines must pass Guard 4"""
    mixed = (
        'CLAIM: Redis is widely used as a caching layer in production systems.\n'
        'CITE_TAG_PRESENT: YES\n'
        'VERIFIED: YES\n'
        'VERDICT: PASS\n'
        'C: Redis was released in 2009 and has grown to millions of deployments worldwide.\n'
        'Q: YES | D: NO | S: YES | V: PASS\n'
        'Structure Score: 10/10\n'
        'Clarity Score: 10/10\n'
        'Factual Confidence: 10/10\n'
        'Verdict: PASS\n'
    )
    assert _is_valid_validator_output(mixed) is True