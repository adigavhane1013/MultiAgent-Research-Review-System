import os
from dotenv import load_dotenv
load_dotenv()

# Force LiteLLM to pick up OpenRouter key via its expected env var name
os.environ["OPENROUTER_API_KEY"] = os.getenv("OPENROUTER_API_KEY", "")
os.environ["OR_API_KEY"] = os.getenv("OPENROUTER_API_KEY", "")

import json
import re
import sys
import time

if not os.getenv("TESTING"):
    from crew_runner import build_crew
    from metrics import calculate_metrics, save_metrics
    from utils.file_utils import save_report, save_failed_report
    from config import AGENT_CALL_DELAY_SECONDS


# ================================================================
# TOKEN ESTIMATION
# Approximates token count per agent output.
# 1 token ≈ 0.75 words — standard industry approximation.
# Not exact but honest — better than nothing.
# ================================================================

def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return int(len(text.split()) * 1.3)


# ================================================================
# GUARD 1 — Research output quality check
# ================================================================

def _is_valid_research_output(research_output: str) -> bool:
    """
    Catches silent research failures before the writer runs.

    Supports BOTH output formats:
    - Legacy format:  FACT / SOURCE_QUOTE / SOURCE_NUM / CATEGORY keywords
    - Compact format: [General|N] / [Features|N] / [UseCases|N] / [Limitations|N]
                      (introduced in Fix 3 — this was the PENDING Guard 1 update)

    Fixes:
    - Agent returning '!!!!!!!' or empty garbage
    - Agent returning ONLY filler like 'Thought: I now can give a great answer'
      with zero actual facts — ROOT CAUSE of Agentic AI hallucination run
    - Agent returning output too short to contain real facts
    - Agent returning output with no structured fact signals at all
    - Minimum source signal count check (1 is not enough for a real run)
    - Guard 1 previously only checked SOURCE_QUOTE (legacy keyword).
      After Fix 3 changed researcher to compact [Category|N] format,
      Guard 1 was rejecting every good run. This fix resolves that.
    """
    if not research_output:
        print("⚠ Guard 1 FAIL — Research output is empty.")
        return False

    cleaned = research_output.strip().strip("!").strip("?").strip(".").strip()

    # Too short to contain real facts
    if len(cleaned) < 100:
        print(f"⚠ Guard 1 FAIL — Research output too short ({len(cleaned)} chars).")
        return False

    # --- Count signals from BOTH formats (backward compat + new compact) ---
    # Legacy format signals
    old_format_count = research_output.count("SOURCE_QUOTE")

    # Compact format: [General|2] / [Features|3] / [UseCases|1] / [Limitations|4]
    compact_matches = re.findall(
        r'\[(General|Features|UseCases|Limitations)\|\d+\]',
        research_output
    )
    compact_count = len(compact_matches)

    source_signal_count = old_format_count + compact_count

    # has_facts: true if EITHER old OR new format signals present
    old_signal    = any(sig in research_output for sig in ["FACT", "SOURCE_QUOTE", "SOURCE_NUM", "CATEGORY"])
    compact_signal = compact_count > 0
    has_facts      = old_signal or compact_signal

    if not has_facts:
        print("⚠ Guard 1 FAIL — Research output has no structured facts.")
        print("   Missing legacy signals (FACT/SOURCE_QUOTE/SOURCE_NUM/CATEGORY)")
        print("   AND no compact signals ([General|N], [Features|N], etc.).")
        print("   Likely cause: researcher produced filler instead of real extraction.")
        return False

    # Minimum 2 source signals required (combined count across both formats)
    if source_signal_count < 2:
        print(f"⚠ Guard 1 FAIL — Only {source_signal_count} source signal(s) found "
              f"(legacy={old_format_count}, compact={compact_count}). Minimum 2 required.")
        return False

    # Catch filler-only output
    filler_phrases = [
        "i now can give a great answer",
        "here is the answer",
        "here is my answer",
        "i'll now provide",
        "i will now provide",
        "let me provide",
    ]
    research_lower = research_output.lower()
    for phrase in filler_phrases:
        if phrase in research_lower[:300]:
            print(f"⚠ Guard 1 FAIL — Filler phrase at start: '{phrase}'")
            return False

    print(f"✅ Guard 1 PASS — {source_signal_count} source signal(s) found "
          f"(legacy={old_format_count}, compact={compact_count}).")
    return True


# ================================================================
# GUARD 2 — Writer output quality check
# ================================================================

def _is_valid_writer_output(writer_output: str) -> bool:
    """
    Catches silent writer failures before the validator runs.

    Fixes:
    - Writer returning filler like 'I now can give a great answer'
    - Writer returning empty output
    - Writer returning output with no actual document structure
    - Writer producing document with no citations (pure hallucination)
    - Writer producing too few citations (thin hallucinated document)
    """
    if not writer_output:
        print("⚠ Guard 2 FAIL — Writer output is empty.")
        return False

    cleaned = writer_output.strip()

    # Too short to be a real document
    if len(cleaned) < 200:
        print(f"⚠ Guard 2 FAIL — Writer output too short ({len(cleaned)} chars).")
        return False

    # All 4 required sections must be present
    required_sections = [
        "## Overview",
        "## Key Concepts",
        "## Real-World Use Cases",
        "## Limitations",
    ]
    missing = [s for s in required_sections if s not in writer_output]
    if missing:
        print(f"⚠ Guard 2 FAIL — Missing sections: {missing}")
        return False

    # Must have citation tags
    if "[CITE:" not in writer_output:
        print("⚠ Guard 2 FAIL — No [CITE: ...] tags found. Pure hallucination suspected.")
        return False

    # Minimum citation count
    cite_count = writer_output.count("[CITE:")
    if cite_count < 4:
        print(f"⚠ Guard 2 FAIL — Only {cite_count} citations found. Minimum 4 required.")
        return False

    # Catch filler phrases
    filler_phrases = [
        "i now can give a great answer",
        "here is the document",
        "here is my document",
        "here is the answer",
        "as requested",
        "i'll now write",
        "i will now write",
        "i'll now create",
        "let me write",
        "thought:",
    ]
    writer_lower = writer_output.lower()
    for phrase in filler_phrases:
        if phrase in writer_lower[:300]:
            print(f"⚠ Guard 2 FAIL — Filler phrase detected at start: '{phrase}'")
            return False

    return True


# ================================================================
# GUARD 3 — Verdict override (catches validator contradicting itself)
# ================================================================

def _get_true_verdict(validation_output: str) -> str:
    """
    Cross-checks the validator's final Verdict line against
    actual VERIFIED: NO, CITE_TAG_PRESENT: NO, DUPLICATE_EVIDENCE: YES,
    and QUOTE_IN_SOURCES: NO counts.

    Fixes:
    - Free tier models that write individual VERDICT: FAIL per claim
      but then write 'Verdict: PASS' at the end (self-contradiction)
    - Validator passing duplicate evidence abuse
    - Validator passing fabricated quotes not in search results
    - Any failure in claims means the run failed — period, no exceptions
    """
    stated_verdict = "PASS" if "Verdict: PASS" in validation_output else "FAIL"

    output_upper = validation_output.upper()

    def _count(pattern: str) -> int:
        """Count non-overlapping regex matches in uppercased output."""
        return len(re.findall(pattern, output_upper))

    # Fix 5 — compact format signals (Q/D/S/V) + legacy format signals for backward compat.
    # Use regex anchored patterns so single-letter prefixes (Q:, D:, S:, V:) don't match
    # mid-word substrings (e.g. "VERIFIED: YES" contains "D: YES" as a plain substring).
    fabricated_count      = _count(r'\bQ: NO\b')       + _count(r'\bQUOTE_IN_SOURCES: NO\b')
    duplicate_count       = _count(r'\bD: YES\b')      + _count(r'\bDUPLICATE_EVIDENCE: YES\b')
    semantic_fail_count   = _count(r'\bS: NO\b')       + _count(r'\bSEMANTIC_MATCH: NO\b')
    verdict_fail_count    = _count(r'\bV: FAIL\b')     + _count(r'\bVERIFIED: NO\b')
    cite_missing_count    = _count(r'\bCITE_TAG_PRESENT: NO\b')
    repetition_fail_count = _count(r'\bREPETITION_FAIL: YES\b')

    if stated_verdict == "PASS" and (
        fabricated_count      > 0 or
        duplicate_count       > 0 or
        semantic_fail_count   > 0 or
        verdict_fail_count    > 0 or
        cite_missing_count    > 0 or
        repetition_fail_count > 0
    ):
        print(f"\n⚠ Guard 3 — Verdict override: validator said PASS but found:")
        if fabricated_count > 0:
            print(f"   - {fabricated_count} fabricated quote(s) not in search results (Q: NO)")
        if duplicate_count > 0:
            print(f"   - {duplicate_count} duplicate evidence instance(s) (D: YES)")
        if semantic_fail_count > 0:
            print(f"   - {semantic_fail_count} semantic mismatch(es) (S: NO)")
        if verdict_fail_count > 0:
            print(f"   - {verdict_fail_count} failed claim(s) (V: FAIL)")
        if cite_missing_count > 0:
            print(f"   - {cite_missing_count} missing citation(s) (CITE_TAG_PRESENT: NO)")
        if repetition_fail_count > 0:
            print(f"   - {repetition_fail_count} repetition failure(s) (REPETITION_FAIL: YES)")
        print(f"   Overriding stated PASS → FAIL.\n")
        return "FAIL"

    return stated_verdict


# ================================================================
# GUARD 4 — Validator output quality check
# ================================================================

def _is_valid_validator_output(validator_output: str) -> bool:
    """
    Catches truncated or incomplete validator output.

    Supports BOTH validator output formats:
    - Legacy format:  CLAIM: / VERIFIED: / VERDICT: per claim (8 lines each)
    - Compact format: C: [claim] / Q: YES|NO | D: YES|NO | S: YES|NO | V: PASS|FAIL
                      (introduced in Fix 5)

    Fixes:
    - Kubernetes failure — validator output truncated by MAX_TOKENS
      (missing Structure Score / Clarity Score / Factual Confidence lines)
    - Validator skipping the audit entirely
    - Validator starting with filler instead of audit
    """
    if not validator_output:
        print("⚠ Guard 4 FAIL — Validator output is empty.")
        return False

    cleaned = validator_output.strip()

    # Too short to be a real validation
    if len(cleaned) < 100:
        print(f"⚠ Guard 4 FAIL — Validator output too short ({len(cleaned)} chars).")
        return False

    # Must have the final score lines (truncation check)
    required_endings = [
        "Structure Score",
        "Clarity Score",
        "Factual Confidence",
        "Verdict:",
    ]
    missing = [r for r in required_endings if r not in validator_output]
    if missing:
        print(f"⚠ Guard 4 FAIL — Validator output missing: {missing}")
        print("   Likely cause: output truncated by MAX_TOKENS limit.")
        return False

    # Must have at least one audit entry — accept BOTH formats:
    #   Legacy:  CLAIM: ...
    #   Compact: C: ...
    has_legacy_claims  = "CLAIM:" in validator_output
    has_compact_claims = bool(re.search(r'^C:\s+\S', validator_output, re.MULTILINE))
    if not has_legacy_claims and not has_compact_claims:
        print("⚠ Guard 4 FAIL — No audit entries found (no CLAIM: or C: lines).")
        print("   Validator appears to have skipped the audit entirely.")
        return False

    # Catch filler at start
    filler_phrases = [
        "i now can give a great answer",
        "here is",
        "thought:",
        "i'll now",
        "i will now",
        "let me",
    ]
    validator_lower = validator_output.lower()
    for phrase in filler_phrases:
        if validator_lower.strip().startswith(phrase):
            print(f"⚠ Guard 4 FAIL — Validator started with filler: '{phrase}'")
            return False

    return True


# ================================================================
# VALIDATE RESULT — runs all 4 guards
# ================================================================

def _validate_result(result, topic):
    """
    Runs all 4 quality guards on a crew result.
    Returns (validation_output, verdict, token_tracker).
    Never calls sys.exit — caller decides what to do with FAIL.
    """
    # Guard 1 — Research
    research_output = result.tasks_output[0].raw
    if not _is_valid_research_output(research_output):
        print("⚠ Guard 1 triggered — research output invalid.")
        return "", "FAIL", {}

    # Guard 2 — Writer
    writer_output = result.tasks_output[1].raw
    if not _is_valid_writer_output(writer_output):
        print("⚠ Guard 2 triggered — writer output invalid.")
        return "", "FAIL", {}

    # Guard 4 — Validator (check before Guard 3)
    validation_output = result.tasks_output[2].raw
    if not _is_valid_validator_output(validation_output):
        print("⚠ Guard 4 triggered — validator output invalid.")
        return validation_output, "FAIL", {}

    # Guard 3 — Verdict override
    verdict = _get_true_verdict(validation_output)

    # Token tracking — estimated per agent output
    r_tokens = estimate_tokens(research_output)
    w_tokens = estimate_tokens(writer_output)
    v_tokens = estimate_tokens(validation_output)
    token_tracker = {
        "researcher": r_tokens,
        "writer":     w_tokens,
        "validator":  v_tokens,
        "total":      r_tokens + w_tokens + v_tokens,
    }

    return validation_output, verdict, token_tracker


# ================================================================
# DEDUPLICATION — warn if topic already exists in history_log
# ================================================================

def _check_duplicate_topic(topic: str) -> bool:
    """
    Checks if topic already exists in history_log.json.
    Returns True if duplicate found, False if topic is new.
    """
    history_file = "metrics/history_log.json"
    if not os.path.exists(history_file):
        return False

    with open(history_file, "r", encoding="utf-8") as f:
        history = json.load(f)

    existing = {r["topic"].lower().strip(): r for r in history}
    key = topic.lower().strip()

    if key not in existing:
        return False

    existing_run = existing[key]
    verdict      = existing_run.get("verdict", "unknown")
    timestamp    = existing_run.get("timestamp", "unknown")
    rate         = existing_run.get("verification_rate_percent", 0)

    print(f"\n⚠ DUPLICATE TOPIC DETECTED")
    print(f"   Topic:     '{topic}'")
    print(f"   Already run at: {timestamp}")
    print(f"   Verdict:   {verdict}")
    print(f"   Verification rate: {rate}%")
    print(f"\n   Running again will add a second entry to history_log.")

    confirm = input("\n   Continue anyway? (y/n): ").strip().lower()
    if confirm != "y":
        print("\n⏭ Skipping. Run a different topic or edit history_log.json to remove the existing entry.\n")
        return True

    print("\n↪ Proceeding with re-run...\n")
    return False


# ================================================================
# CREW KICKOFF WITH RATE LIMIT DELAYS
# ================================================================

def _kickoff_with_delays(crew):
    """
    Runs crew with per-step delays between each agent call.
    Protects against free tier rate limits.
    """
    def step_callback(step_output):
        print(f"\n🔄 Waiting {AGENT_CALL_DELAY_SECONDS}s (rate limit protection)...\n")
        time.sleep(AGENT_CALL_DELAY_SECONDS)

    original_callbacks = []
    for agent in crew.agents:
        original_callbacks.append(getattr(agent, "step_callback", None))
        agent.step_callback = step_callback

    try:
        result = crew.kickoff()
    finally:
        for agent, cb in zip(crew.agents, original_callbacks):
            agent.step_callback = cb

    return result


# ================================================================
# FIX 4 — EARLY EXIT RESEARCH CHECK
# Runs researcher alone first.
# If Guard 1 fails — writer and validator never run.
# Saves ~20% tokens on all failed runs (currently 23% failure rate).
# ================================================================

def _run_research_only(topic: str):
    """
    Runs only the researcher agent as a standalone crew.
    Returns (research_output, crew, source_count) if Guard 1 passes.
    Returns (None, None, 0) if Guard 1 fails — caller saves failed run.
    """
    from crewai import Crew
    from agents import build_agents
    from tasks import create_tasks
    from search import search_web

    research_agent, writer_agent, validator_agent = build_agents()
    search_context, quotes_only, source_count = search_web(topic)

    research_task, writer_task, validator_task = create_tasks(
        research_agent,
        writer_agent,
        validator_agent,
        topic,
        search_context,
        quotes_only,
    )

    # Run researcher alone
    research_crew = Crew(
        agents=[research_agent],
        tasks=[research_task],
        verbose=True,
    )
    research_result = _kickoff_with_delays(research_crew)
    research_output = research_result.tasks_output[0].raw

    # Guard 1 — check immediately before writer runs
    if not _is_valid_research_output(research_output):
        print("⚠ Guard 1 triggered — aborting before writer runs. Tokens saved.")
        return None, None, source_count

    # Guard 1 passed — build full crew for writer + validator
    full_crew = Crew(
        agents=[research_agent, writer_agent, validator_agent],
        tasks=[research_task, writer_task, validator_task],
        verbose=True,
    )

    return research_output, full_crew, source_count


# ================================================================
# MAIN RUN
# ================================================================

def run():
    # ------------------------------------------------------------------
    # 1. TOPIC INPUT
    # ------------------------------------------------------------------
    topic = input("\nEnter a topic to research: ").strip()
    if not topic:
        sys.exit("Error: Topic cannot be empty.")

    if _check_duplicate_topic(topic):
        sys.exit(0)

    # ------------------------------------------------------------------
    # 2. FIX 4 — RUN RESEARCHER FIRST, EXIT EARLY IF GUARD 1 FAILS
    # ------------------------------------------------------------------
    print("\n🔬 Running researcher first (early exit optimization)...\n")
    research_output, crew, source_count = _run_research_only(topic)

    # Guard 1 failed — save failed run and exit
    if research_output is None:
        elapsed_seconds = 0
        print("\n❌ Guard 1 failed before writer ran. Saving failed run...\n")
        metrics_data = calculate_metrics(
            topic=topic,
            validation_output="",
            verdict="FAIL",
            elapsed_seconds=elapsed_seconds,
            retry_used=False,
            source_count=source_count,
        )
        save_metrics(metrics_data)
        sys.exit(1)

    print("\n✅ Guard 1 passed. Starting full crew execution...\n")

    # ------------------------------------------------------------------
    # 3. START TIMER
    # ------------------------------------------------------------------
    start_time = time.time()

    # ------------------------------------------------------------------
    # 4. FIRST FULL RUN (writer + validator)
    # ------------------------------------------------------------------
    result = _kickoff_with_delays(crew)
    validation_output, verdict, token_tracker = _validate_result(result, topic)

    retry_used = False

    # ------------------------------------------------------------------
    # 5. RETRY LOGIC
    # ------------------------------------------------------------------
    if verdict == "FAIL":
        print("\n⚠ First run failed. Retrying once...\n")
        retry_used = True

        retry_result = _kickoff_with_delays(crew)
        retry_validation_output, retry_verdict, retry_token_tracker = _validate_result(retry_result, topic)

        if retry_verdict == "PASS":
            print("✅ Retry succeeded.\n")
            result            = retry_result
            validation_output = retry_validation_output
            verdict           = "PASS"
            token_tracker     = retry_token_tracker
        else:
            elapsed_seconds = time.time() - start_time
            print("\n❌ Retry also failed. Saving failed run report...\n")
            save_failed_report(topic, retry_result)
            metrics_data = calculate_metrics(
                topic=topic,
                validation_output=retry_validation_output,
                verdict="FAIL",
                elapsed_seconds=elapsed_seconds,
                retry_used=retry_used,
                source_count=source_count,
                token_tracker=retry_token_tracker,
            )
            save_metrics(metrics_data)
            sys.exit(1)

    # ------------------------------------------------------------------
    # 6. STOP TIMER
    # ------------------------------------------------------------------
    elapsed_seconds = time.time() - start_time

    # ------------------------------------------------------------------
    # 7. FINAL METRICS + SAVE
    # ------------------------------------------------------------------
    metrics_data = calculate_metrics(
        topic=topic,
        validation_output=validation_output,
        verdict=verdict,
        elapsed_seconds=elapsed_seconds,
        retry_used=retry_used,
        source_count=source_count,
        token_tracker=token_tracker,
    )

    save_metrics(metrics_data)
    save_report(topic, result)

    print(f"\n✅ Job complete! Finished in {metrics_data['run_duration_minutes']} mins\n")


if __name__ == "__main__":
    run()