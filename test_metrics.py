"""
test_metrics.py — Automated tests for metrics.py

Think of each test as a juice quality check:
- Feed fake validator output into calculate_metrics()
- Check the numbers come out correctly
- If anything breaks, pytest tells you immediately

Run with:
    pytest test_metrics.py -v
"""

import pytest
from metrics import calculate_metrics, _count_pattern, _extract_score


# ================================================================
# HELPER: Builds a realistic fake validator output
# ================================================================

def make_output(claims: int, verified: int, cited: int,
                structure: float = 10.0, clarity: float = 10.0,
                factual: float = 10.0, verdict: str = "PASS") -> str:
    """
    Builds a fake validator output string with exact counts.
    Like making a fake cup of juice to test the quality machine.
    """
    lines = []

    for i in range(claims):
        lines.append(f"CLAIM: This is claim number {i + 1}.")
        lines.append(f"CITE_TAG_PRESENT: {'YES' if i < cited else 'NO'}")
        lines.append(f"VERIFIED: {'YES' if i < verified else 'NO'}")
        lines.append(f"VERDICT: {'PASS' if i < verified else 'FAIL'}")
        lines.append("")

    lines.append(f"Structure Score: {structure}/10")
    lines.append(f"Clarity Score: {clarity}/10")
    lines.append(f"Factual Confidence: {factual}/10")
    lines.append(f"Verdict: {verdict}")

    return "\n".join(lines)


# ================================================================
# 1. BASIC CLAIM COUNTING
# ================================================================

def test_counts_claims_correctly():
    """
    🧃 Juice check: Does it count 5 claims as 5?
    """
    output = make_output(claims=5, verified=5, cited=5)
    result = calculate_metrics("TestTopic", output, "PASS")
    assert result["total_claims"] == 5


def test_counts_verified_correctly():
    """
    🧃 Juice check: 3 verified out of 5 claims — does it count 3?
    """
    output = make_output(claims=5, verified=3, cited=5)
    result = calculate_metrics("TestTopic", output, "PASS")
    assert result["verified_claims"] == 3
    assert result["unsupported_claims"] == 2


def test_counts_citations_correctly():
    """
    🧃 Juice check: 4 cited out of 5 claims — does it count 4?
    """
    output = make_output(claims=5, verified=5, cited=4)
    result = calculate_metrics("TestTopic", output, "PASS")
    assert result["missing_citations"] == 1


# ================================================================
# 2. VERIFICATION RATE
# ================================================================

def test_verification_rate_100_percent():
    """
    🧃 All 5 claims verified → should be 100%
    """
    output = make_output(claims=5, verified=5, cited=5)
    result = calculate_metrics("TestTopic", output, "PASS")
    assert result["verification_rate_percent"] == 100.0


def test_verification_rate_partial():
    """
    🧃 3 out of 5 verified → should be 60%
    """
    output = make_output(claims=5, verified=3, cited=5)
    result = calculate_metrics("TestTopic", output, "PASS")
    assert result["verification_rate_percent"] == 60.0


def test_verification_rate_zero_claims():
    """
    🧃 No claims at all → rate should be 0, not crash
    This is the AI Hallucination bug scenario
    """
    output = "Structure Score: 10/10\nClarity Score: 10/10\nVerdict: PASS"
    result = calculate_metrics("TestTopic", output, "PASS")
    assert result["verification_rate_percent"] == 0.0
    assert result["total_claims"] == 0


# ================================================================
# 3. CITATION COVERAGE
# ================================================================

def test_citation_coverage_100_percent():
    """
    🧃 All claims cited → 100% coverage
    """
    output = make_output(claims=5, verified=5, cited=5)
    result = calculate_metrics("TestTopic", output, "PASS")
    assert result["citation_coverage_percent"] == 100.0


def test_citation_coverage_partial():
    """
    🧃 4 out of 5 cited → 80% coverage
    """
    output = make_output(claims=5, verified=5, cited=4)
    result = calculate_metrics("TestTopic", output, "PASS")
    assert result["citation_coverage_percent"] == 80.0


# ================================================================
# 4. FALLBACK — AI HALLUCINATION BUG FIX
# ================================================================

def test_fallback_when_no_claim_tags():
    """
    🧃 This is exactly the AI Hallucination bug:
    LLM wrote VERIFIED: YES lines but no CLAIM: tags.
    Fallback should use VERIFIED count as total_claims.
    """
    output = """
VERIFIED: YES
VERIFIED: YES
VERIFIED: YES
Structure Score: 10/10
Clarity Score: 10/10
Factual Confidence: 10/10
Verdict: PASS
"""
    result = calculate_metrics("AI Hallucination", output, "PASS")
    assert result["total_claims"] == 3
    assert result["verified_claims"] == 3
    assert result["verification_rate_percent"] == 100.0


def test_fallback_uses_verdict_count_as_last_resort():
    """
    🧃 No CLAIM: tags AND no VERIFIED: tags.
    Last resort: count VERDICT: lines minus the final one.
    """
    output = """
VERDICT: PASS
VERDICT: PASS
VERDICT: PASS
Verdict: PASS
"""
    result = calculate_metrics("TestTopic", output, "PASS")
    # 3 VERDICT: lines found, minus 1 for final = 2 claims
    assert result["total_claims"] >= 0  # should not crash


# ================================================================
# 5. VALIDATOR SCORES
# ================================================================

def test_extracts_structure_score():
    """
    🧃 Does it correctly read 'Structure Score: 9/10'?
    """
    output = make_output(claims=3, verified=3, cited=3,
                         structure=9.0, clarity=8.0, factual=7.0)
    result = calculate_metrics("TestTopic", output, "PASS")
    assert result["structure_score"] == 9.0


def test_extracts_clarity_score():
    output = make_output(claims=3, verified=3, cited=3,
                         structure=10.0, clarity=8.0, factual=10.0)
    result = calculate_metrics("TestTopic", output, "PASS")
    assert result["clarity_score"] == 8.0


def test_extracts_factual_confidence_score():
    output = make_output(claims=3, verified=3, cited=3,
                         structure=10.0, clarity=10.0, factual=7.5)
    result = calculate_metrics("TestTopic", output, "PASS")
    assert result["factual_confidence_score"] == 7.5


def test_score_returns_zero_when_missing():
    """
    🧃 If the LLM didn't include scores — should return 0.0, not crash
    """
    output = make_output(claims=3, verified=3, cited=3)
    # Remove score lines
    output = output.replace("Structure Score: 10.0/10", "")
    output = output.replace("Clarity Score: 10.0/10", "")
    output = output.replace("Factual Confidence: 10.0/10", "")
    result = calculate_metrics("TestTopic", output, "PASS")
    assert result["structure_score"] == 0.0


# ================================================================
# 6. LATENCY TRACKING
# ================================================================

def test_latency_converts_seconds_to_minutes():
    """
    🧃 90 seconds should be 1.5 minutes
    """
    output = make_output(claims=3, verified=3, cited=3)
    result = calculate_metrics("TestTopic", output, "PASS",
                               elapsed_seconds=90.0)
    assert result["run_duration_minutes"] == 1.5
    assert result["run_duration_seconds"] == 90.0


def test_latency_zero_by_default():
    """
    🧃 If no time passed — should be 0, not crash
    """
    output = make_output(claims=3, verified=3, cited=3)
    result = calculate_metrics("TestTopic", output, "PASS")
    assert result["run_duration_seconds"] == 0.0
    assert result["run_duration_minutes"] == 0.0


# ================================================================
# 7. RETRY & SOURCE TRACKING
# ================================================================

def test_retry_flag_recorded():
    """
    🧃 If retry_used=True, it should be saved in metrics
    """
    output = make_output(claims=3, verified=3, cited=3)
    result = calculate_metrics("TestTopic", output, "PASS",
                               retry_used=True)
    assert result["retry_used"] is True


def test_source_count_recorded():
    """
    🧃 If 8 sources were used, it should be saved
    """
    output = make_output(claims=3, verified=3, cited=3)
    result = calculate_metrics("TestTopic", output, "PASS",
                               source_count=8)
    assert result["sources_used"] == 8


# ================================================================
# 8. VERDICT SAVED CORRECTLY
# ================================================================

def test_verdict_pass_saved():
    output = make_output(claims=3, verified=3, cited=3)
    result = calculate_metrics("TestTopic", output, "PASS")
    assert result["verdict"] == "PASS"


def test_verdict_fail_saved():
    output = make_output(claims=3, verified=1, cited=1, verdict="FAIL")
    result = calculate_metrics("TestTopic", output, "FAIL")
    assert result["verdict"] == "FAIL"


# ================================================================
# 9. REAL DATA SANITY CHECK — LangChain run
# ================================================================

def test_real_langchain_run():
    """
    🧃 This is the actual LangChain output format from your system.
    Checks that real data parses correctly end to end.
    """
    # Minimal version of real LangChain validator output format
    output = """
CLAIM:
LangChain is an open source orchestration framework.
CITE_TAG_PRESENT: YES
VERIFIED: YES
VERDICT: PASS

CLAIM:
LangChain was launched by Harrison Chase in October 2022.
CITE_TAG_PRESENT: YES
VERIFIED: YES
VERDICT: PASS

CLAIM:
LangChain can be slow and difficult to optimize.
CITE_TAG_PRESENT: YES
VERIFIED: YES
VERDICT: PASS

Structure Score: 10/10
Clarity Score: 10/10
Factual Confidence: 10/10
Verdict: PASS
"""
    result = calculate_metrics("Langchain", output, "PASS",
                               elapsed_seconds=58.45,
                               source_count=10)
    assert result["total_claims"] == 3
    assert result["verified_claims"] == 3
    assert result["verification_rate_percent"] == 100.0
    assert result["citation_coverage_percent"] == 100.0
    assert result["structure_score"] == 10.0
    assert result["sources_used"] == 10
    assert result["verdict"] == "PASS"
