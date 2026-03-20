import os
import json
import re
from datetime import datetime


def calculate_metrics(
    topic: str,
    validation_output: str,
    verdict: str,
    elapsed_seconds: float = 0.0,
    retry_used: bool = False,
    source_count: int = 0,
) -> dict:
    """
    Parses validation output and computes structured metrics.
    Handles multiple LLM output formats:
    - Standard: "CLAIM:", "VERIFIED: YES", "CITE_TAG_PRESENT: YES"
    - Extended: "QUOTE_IN_SOURCES: YES/NO", "DUPLICATE_EVIDENCE: YES/NO"
    """

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ----------------------------------------------------------------
    # CLAIM METRICS — case-insensitive, whitespace-tolerant
    # ----------------------------------------------------------------
    total_claims  = _count_pattern(validation_output, r"CLAIM\s*:")
    verified_yes  = _count_pattern(validation_output, r"VERIFIED\s*:\s*YES")
    verified_no   = _count_pattern(validation_output, r"VERIFIED\s*:\s*NO")
    cite_present  = _count_pattern(validation_output, r"CITE_TAG_PRESENT\s*:\s*YES")
    cite_missing  = _count_pattern(validation_output, r"CITE_TAG_PRESENT\s*:\s*NO")

    # Fix 8 — track fabricated quotes (QUOTE_IN_SOURCES: NO)
    # These are quotes the writer invented from training knowledge
    # not found anywhere in the original search results
    quotes_in_sources     = _count_pattern(validation_output, r"QUOTE_IN_SOURCES\s*:\s*YES")
    quotes_not_in_sources = _count_pattern(validation_output, r"QUOTE_IN_SOURCES\s*:\s*NO")

    # Track duplicate evidence abuse (same quote used for multiple claims)
    duplicate_evidence = _count_pattern(validation_output, r"DUPLICATE_EVIDENCE\s*:\s*YES")

    # ----------------------------------------------------------------
    # FALLBACK 1: CLAIM: tags missing but VERIFIED counts exist
    # ----------------------------------------------------------------
    if total_claims == 0 and (verified_yes + verified_no) > 0:
        print(f"⚠ CLAIM: tags not found — using VERIFIED count as fallback "
              f"({verified_yes + verified_no} claims detected)")
        total_claims = verified_yes + verified_no

    # ----------------------------------------------------------------
    # FALLBACK 2: Count VERDICT lines if still 0
    # ----------------------------------------------------------------
    if total_claims == 0:
        verdict_count = _count_pattern(validation_output, r"VERDICT\s*:\s*(PASS|FAIL)")
        if verdict_count > 1:
            total_claims = verdict_count - 1
            print(f"⚠ Using VERDICT count as fallback ({total_claims} claims detected)")

    # ----------------------------------------------------------------
    # FIX: Verified > Total sanity check
    # ----------------------------------------------------------------
    if total_claims > 0 and verified_yes > total_claims:
        print(f"⚠ Verified ({verified_yes}) > Total ({total_claims}) — "
              f"capping verified at total.")
        verified_yes = total_claims
        verified_no  = 0

    # ----------------------------------------------------------------
    # FIX: cite_present > total_claims sanity check
    # ----------------------------------------------------------------
    if total_claims > 0 and cite_present > total_claims:
        print(f"⚠ cite_present ({cite_present}) > total_claims ({total_claims}) — "
              f"capping cite_present at total.")
        cite_present = total_claims

    # ----------------------------------------------------------------
    # RATES
    # ----------------------------------------------------------------
    if total_claims == 0:
        verification_rate = 0.0
        citation_coverage = 0.0
        source_grounding  = 0.0
    else:
        verification_rate = (verified_yes / total_claims) * 100

        if cite_present == 0 and cite_missing == 0:
            citation_coverage = verification_rate
        else:
            citation_coverage = (cite_present / total_claims) * 100

        # Source grounding rate — what % of claims had quotes found in real sources
        # Only calculated when QUOTE_IN_SOURCES fields are present in output
        total_quote_checks = quotes_in_sources + quotes_not_in_sources
        if total_quote_checks > 0:
            source_grounding = (quotes_in_sources / total_quote_checks) * 100
        else:
            # Old runs without QUOTE_IN_SOURCES field — mark as N/A (-1.0)
            source_grounding = -1.0

    # Final cap — neither rate can exceed 100%
    verification_rate = min(verification_rate, 100.0)
    citation_coverage = min(citation_coverage, 100.0)
    if source_grounding > 0:
        source_grounding = min(source_grounding, 100.0)

    # ----------------------------------------------------------------
    # VALIDATOR SCORES
    # ----------------------------------------------------------------
    structure_score = _extract_score(validation_output, [
        "Structure Score", "Structure", "Structural Score",
    ])
    clarity_score = _extract_score(validation_output, [
        "Clarity Score", "Clarity",
    ])
    factual_score = _extract_score(validation_output, [
        "Factual Confidence", "Factual Score",
        "Factual Accuracy", "Accuracy Score",
    ])

    # ----------------------------------------------------------------
    # LATENCY
    # ----------------------------------------------------------------
    elapsed_minutes = round(elapsed_seconds / 60, 2)

    # ----------------------------------------------------------------
    # PRINT REPORT
    # ----------------------------------------------------------------
    print("\n" + "═" * 55)
    print("📊 FINAL RUN METRICS")
    print("═" * 55)
    print(f"  Topic:                     {topic}")
    print(f"  Total Claims:              {total_claims}")
    print(f"  Verified Claims:           {verified_yes}")
    print(f"  Unsupported Claims:        {verified_no}")
    print(f"  Missing Citations:         {cite_missing}")
    print(f"  Fabricated Quotes:         {quotes_not_in_sources}")
    print(f"  Duplicate Evidence:        {duplicate_evidence}")
    print(f"  Verification Rate:         {verification_rate:.2f}%")
    print(f"  Citation Coverage:         {citation_coverage:.2f}%")
    if source_grounding >= 0:
        print(f"  Source Grounding Rate:     {source_grounding:.2f}%")
    else:
        print(f"  Source Grounding Rate:     N/A (old run, no QUOTE_IN_SOURCES data)")
    print(f"  Structure Score:           {structure_score}/10")
    print(f"  Clarity Score:             {clarity_score}/10")
    print(f"  Factual Confidence:        {factual_score}/10")
    print(f"  Sources Used:              {source_count}")
    print(f"  Run Duration:              {elapsed_minutes} mins")
    print(f"  Retry Used:                {'Yes' if retry_used else 'No'}")
    print(f"  Verdict:                   {verdict}")
    print("═" * 55)

    return {
        "topic":                        topic,
        "timestamp":                    timestamp,
        "total_claims":                 total_claims,
        "verified_claims":              verified_yes,
        "unsupported_claims":           verified_no,
        "missing_citations":            cite_missing,
        "fabricated_quotes":            quotes_not_in_sources,
        "duplicate_evidence":           duplicate_evidence,
        "verification_rate_percent":    round(verification_rate, 2),
        "citation_coverage_percent":    round(citation_coverage, 2),
        "source_grounding_rate_percent": round(source_grounding, 2),
        "structure_score":              structure_score,
        "clarity_score":                clarity_score,
        "factual_confidence_score":     factual_score,
        "sources_used":                 source_count,
        "run_duration_seconds":         round(elapsed_seconds, 2),
        "run_duration_minutes":         elapsed_minutes,
        "retry_used":                   retry_used,
        "verdict":                      verdict,
    }


def _count_pattern(text: str, pattern: str) -> int:
    """
    Case-insensitive regex count.
    More robust than plain str.count() for spacing/casing differences.
    """
    return len(re.findall(pattern, text, re.IGNORECASE))


def _extract_score(text: str, labels: list) -> float:
    """
    Extracts a score like 'Structure Score: 9/10' from validator output.
    Tries multiple label variants to handle different LLM output formats.
    Returns 0.0 if not found.
    """
    for label in labels:
        pattern = rf"{label}[:\s]+(\d+(?:\.\d+)?)\s*/\s*10"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1))
    return 0.0


def save_metrics(metrics_data: dict):
    """
    Saves per-run metrics JSON and appends to historical log.
    Only appends to history_log if data is mathematically valid.
    """

    os.makedirs("metrics", exist_ok=True)

    safe_topic = "".join(
        c if c.isalnum() or c == "_" else "_"
        for c in metrics_data["topic"].replace(" ", "_")
    )

    metrics_path = f"metrics/{safe_topic}_{metrics_data['timestamp']}.json"

    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics_data, f, indent=4)

    # ----------------------------------------------------------------
    # HISTORICAL LOG
    # Only append if verified <= total (no impossible math)
    # ----------------------------------------------------------------
    total    = metrics_data.get("total_claims", 0)
    verified = metrics_data.get("verified_claims", 0)

    if total > 0 and verified > total:
        print(f"⚠ Skipping history_log append — verified ({verified}) > total ({total}).")
        print(f"   Metrics saved to per-run file only: {metrics_path}")
        return

    history_file = "metrics/history_log.json"

    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8") as f:
            history = json.load(f)
    else:
        history = []

    history.append(metrics_data)

    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=4)

    print(f"💾 Metrics saved → {metrics_path}")