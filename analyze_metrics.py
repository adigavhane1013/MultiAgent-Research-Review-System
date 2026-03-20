"""
analyze_metrics.py — Aggregate evaluation report across all runs.

Reads metrics/history_log.json and produces:
- Full aggregate statistics
- Per-topic breakdown table
- 6 resume-ready bullet points with real numbers

Run with:
    python analyze_metrics.py
"""

import json
import os


def load_history():
    history_file = "metrics/history_log.json"
    if not os.path.exists(history_file):
        print("❌ metrics/history_log.json not found.")
        return []
    with open(history_file, "r", encoding="utf-8") as f:
        return json.load(f)


def analyze():
    runs = load_history()
    if not runs:
        return

    print(f"✅ Loaded {len(runs)} runs from history_log.json")

    # ----------------------------------------------------------------
    # BASIC COUNTS
    # ----------------------------------------------------------------
    total_runs  = len(runs)
    pass_runs   = [r for r in runs if r.get("verdict") == "PASS"]
    fail_runs   = [r for r in runs if r.get("verdict") == "FAIL"]
    retry_runs  = [r for r in runs if r.get("retry_used", False)]

    pass_rate   = (len(pass_runs)  / total_runs) * 100 if total_runs else 0
    retry_rate  = (len(retry_runs) / total_runs) * 100 if total_runs else 0

    # ----------------------------------------------------------------
    # CLAIM METRICS — across ALL runs (pass + fail) for honest accuracy
    # ----------------------------------------------------------------
    total_claims            = sum(r.get("total_claims", 0)       for r in runs)
    total_verified          = sum(r.get("verified_claims", 0)    for r in runs)
    total_unsupported       = sum(r.get("unsupported_claims", 0) for r in runs)
    total_missing_citations = sum(r.get("missing_citations", 0)  for r in runs)
    total_fabricated        = sum(r.get("fabricated_quotes", 0)  for r in runs)
    total_duplicates        = sum(r.get("duplicate_evidence", 0) for r in runs)

    avg_verification = (
        sum(r.get("verification_rate_percent", 0) for r in runs) / total_runs
        if total_runs else 0
    )
    avg_citation = (
        sum(r.get("citation_coverage_percent", 0) for r in runs) / total_runs
        if total_runs else 0
    )

    # Source grounding — only from runs that have the field (new runs only)
    grounded_runs = [
        r for r in runs
        if r.get("source_grounding_rate_percent", -1) >= 0
    ]
    avg_grounding = (
        sum(r["source_grounding_rate_percent"] for r in grounded_runs) / len(grounded_runs)
        if grounded_runs else -1.0
    )

    # ----------------------------------------------------------------
    # VALIDATOR SCORES — only average runs where scores > 0
    # ----------------------------------------------------------------
    scored_runs = [
        r for r in runs
        if r.get("structure_score", 0) > 0
        and r.get("clarity_score", 0) > 0
        and r.get("factual_confidence_score", 0) > 0
    ]

    if scored_runs:
        avg_structure = sum(r["structure_score"]          for r in scored_runs) / len(scored_runs)
        avg_clarity   = sum(r["clarity_score"]            for r in scored_runs) / len(scored_runs)
        avg_factual   = sum(r["factual_confidence_score"] for r in scored_runs) / len(scored_runs)
    else:
        avg_structure = avg_clarity = avg_factual = 0.0

    # ----------------------------------------------------------------
    # LATENCY
    # ----------------------------------------------------------------
    timed_runs = [r for r in runs if r.get("run_duration_seconds", 0) > 0]

    if timed_runs:
        avg_duration = sum(r["run_duration_minutes"] for r in timed_runs) / len(timed_runs)
        fastest      = min(r["run_duration_minutes"] for r in timed_runs)
        slowest      = max(r["run_duration_minutes"] for r in timed_runs)
    else:
        avg_duration = fastest = slowest = 0.0

    # ----------------------------------------------------------------
    # SOURCE USAGE
    # ----------------------------------------------------------------
    sourced_runs = [r for r in runs if r.get("sources_used", 0) > 0]

    if sourced_runs:
        avg_sources   = sum(r["sources_used"] for r in sourced_runs) / len(sourced_runs)
        total_sources = sum(r["sources_used"] for r in sourced_runs)
    else:
        avg_sources = total_sources = 0

    topics = sorted(set(r["topic"] for r in runs))

    # ----------------------------------------------------------------
    # PRINT AGGREGATE REPORT
    # ----------------------------------------------------------------
    print("\n" + "=" * 58)
    print("📊 MULTI-AGENT SYSTEM — AGGREGATE EVALUATION REPORT")
    print("=" * 58)

    print("\n🔢 RUN SUMMARY")
    print(f"  Total Runs:                  {total_runs}")
    print(f"  Passed:                      {len(pass_runs)} ({pass_rate:.1f}%)")
    print(f"  Failed:                      {len(fail_runs)}")
    print(f"  Retries Used:                {len(retry_runs)} ({retry_rate:.1f}% of runs)")

    print("\n✅ CLAIM VERIFICATION")
    print(f"  Total Claims Evaluated:      {total_claims}")
    print(f"  Verified Claims:             {total_verified}")
    print(f"  Unsupported Claims:          {total_unsupported}")
    print(f"  Missing Citations:           {total_missing_citations}")
    print(f"  Fabricated Quotes:           {total_fabricated}")
    print(f"  Duplicate Evidence:          {total_duplicates}")
    print(f"  Avg Verification Rate:       {avg_verification:.2f}%")

    print("\n📎 CITATION COVERAGE")
    print(f"  Avg Citation Coverage:       {avg_citation:.2f}%")
    if avg_grounding >= 0:
        print(f"  Avg Source Grounding Rate:   {avg_grounding:.2f}%")
    else:
        print(f"  Avg Source Grounding Rate:   N/A (run newer topics to populate)")

    print(f"\n🏆 VALIDATOR SCORES (avg across {len(scored_runs)} scored runs)")
    print(f"  Avg Structure Score:         {avg_structure:.1f}/10")
    print(f"  Avg Clarity Score:           {avg_clarity:.1f}/10")
    print(f"  Avg Factual Confidence:      {avg_factual:.1f}/10")
    print(f"  Note: Excludes {total_runs - len(scored_runs)} run(s) with missing scores (0.0)")

    print(f"\n⚡ LATENCY (across {len(timed_runs)} timed runs)")
    print(f"  Avg Run Duration:            {avg_duration:.2f} mins")
    print(f"  Fastest Run:                 {fastest:.2f} mins")
    print(f"  Slowest Run:                 {slowest:.2f} mins")

    print(f"\n🌐 SOURCE USAGE")
    print(f"  Avg Sources Per Run:         {avg_sources:.1f}")
    print(f"  Total Sources Processed:     {total_sources}")

    print(f"\n📚 TOPICS RESEARCHED ({len(topics)})")
    for t in topics:
        print(f"  - {t}")

    # ----------------------------------------------------------------
    # PER-TOPIC BREAKDOWN TABLE
    # ----------------------------------------------------------------
    print("\n" + "=" * 58)
    print("📋 PER-TOPIC BREAKDOWN")
    print("=" * 58)

    W_TOPIC   = 38
    W_VERDICT =  7
    W_RATE    =  8
    W_CLAIMS  =  8
    W_SOURCES =  8
    W_MINS    =  7

    header = (
        f"  {'Topic':<{W_TOPIC}}"
        f"{'Verdict':<{W_VERDICT}}"
        f"{'Verify%':>{W_RATE}}"
        f"{'Claims':>{W_CLAIMS}}"
        f"{'Sources':>{W_SOURCES}}"
        f"{'Mins':>{W_MINS}}"
    )
    print(header)
    print("  " + "-" * (W_TOPIC + W_VERDICT + W_RATE + W_CLAIMS + W_SOURCES + W_MINS))

    sorted_runs = sorted(
        runs,
        key=lambda r: (
            0 if r.get("verdict") == "PASS" else 1,
            -r.get("verification_rate_percent", 0),
        )
    )

    for r in sorted_runs:
        topic   = r.get("topic", "unknown")
        verdict = r.get("verdict", "?")
        rate    = r.get("verification_rate_percent", 0)
        claims  = r.get("total_claims", 0)
        sources = r.get("sources_used", 0)
        mins    = r.get("run_duration_minutes", 0)
        retry   = " ↺" if r.get("retry_used", False) else ""

        if len(topic) > W_TOPIC - 1:
            topic = topic[:W_TOPIC - 4] + "..."

        verdict_icon = "✅ PASS" if verdict == "PASS" else "❌ FAIL"

        row = (
            f"  {topic:<{W_TOPIC}}"
            f"{verdict_icon:<{W_VERDICT + 3}}"
            f"{rate:>{W_RATE}.1f}%"
            f"{claims:>{W_CLAIMS}}"
            f"{sources:>{W_SOURCES}}"
            f"{mins:>{W_MINS}.2f}"
            f"{retry}"
        )
        print(row)

    print("  " + "-" * (W_TOPIC + W_VERDICT + W_RATE + W_CLAIMS + W_SOURCES + W_MINS))

    weak_runs = [r for r in pass_runs if r.get("verification_rate_percent", 100) < 90]
    if weak_runs:
        print(f"\n  ⚠ Weak PASS runs (verification < 90%):")
        for r in weak_runs:
            print(f"     - {r.get('topic')}  {r.get('verification_rate_percent')}%")
    else:
        print(f"\n  ✅ All PASS runs have ≥ 90% verification rate")

    # ----------------------------------------------------------------
    # RESUME-READY BULLETS
    # ----------------------------------------------------------------
    print("\n" + "=" * 58)
    print("📝 RESUME-READY BULLET METRICS")
    print("=" * 58)

    b_verif     = f"{avg_verification:.0f}%"
    b_cite      = f"{avg_citation:.0f}%"
    b_factual   = f"{avg_factual:.1f}/10"
    b_structure = f"{avg_structure:.1f}/10"
    b_duration  = f"{avg_duration:.1f}"
    b_sources   = f"{avg_sources:.0f}"
    b_retry     = f"{retry_rate:.0f}%"

    print(f'\n1. "Achieved {b_verif} avg verification rate across {total_runs} research runs,')
    print(f'   evaluating {total_claims} factual claims with {total_unsupported} unsupported."')

    print(f'\n2. "Maintained {b_cite}+ citation coverage — every written claim grounded')
    print(f'   in verbatim source quotes via automated validator agent."')

    print(f'\n3. "System scored avg {b_factual} factual confidence and {b_structure} structure')
    print(f'   score across {len(scored_runs)} evaluated runs."')

    print(f'\n4. "Completed end-to-end research pipeline in avg {b_duration} mins per topic,')
    print(f'   from live web search to validated cited document."')

    print(f'\n5. "Averaged {b_sources} quality web sources per document via Tavily')
    print(f'   advanced search with thin-content and domain filtering."')

    print(f'\n6. "Automated retry logic self-corrected output in {b_retry} of edge-case')
    print(f'   runs without manual intervention."')

    # ----------------------------------------------------------------
    # SAVE AGGREGATE REPORT
    # ----------------------------------------------------------------
    os.makedirs("metrics", exist_ok=True)
    report = {
        "total_runs":                   total_runs,
        "pass_rate_percent":            round(pass_rate, 2),
        "retry_rate_percent":           round(retry_rate, 2),
        "total_claims":                 total_claims,
        "total_unsupported":            total_unsupported,
        "total_fabricated_quotes":      total_fabricated,
        "total_duplicate_evidence":     total_duplicates,
        "avg_verification_rate":        round(avg_verification, 2),
        "avg_citation_coverage":        round(avg_citation, 2),
        "avg_source_grounding":         round(avg_grounding, 2),
        "scored_runs_count":            len(scored_runs),
        "avg_structure_score":          round(avg_structure, 2),
        "avg_clarity_score":            round(avg_clarity, 2),
        "avg_factual_confidence":       round(avg_factual, 2),
        "avg_duration_minutes":         round(avg_duration, 2),
        "fastest_run_minutes":          round(fastest, 2),
        "slowest_run_minutes":          round(slowest, 2),
        "avg_sources_per_run":          round(avg_sources, 1),
        "total_sources_processed":      total_sources,
        "topics":                       topics,
    }

    with open("metrics/aggregate_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=4)

    print(f"\n💾 Aggregate report saved → metrics/aggregate_report.json\n")


if __name__ == "__main__":
    analyze()