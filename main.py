import os
from dotenv import load_dotenv
load_dotenv()

# Force LiteLLM to pick up OpenRouter key via its expected env var name
os.environ["OPENROUTER_API_KEY"] = os.getenv("OPENROUTER_API_KEY", "")
os.environ["OR_API_KEY"] = os.getenv("OPENROUTER_API_KEY", "")

import json
import sys
import time

from crew_runner import build_crew
from metrics import calculate_metrics, save_metrics
from utils.file_utils import save_report, save_failed_report
from config import AGENT_CALL_DELAY_SECONDS


# ================================================================
# GUARD 1 — Research output quality check
# ================================================================

def _is_valid_research_output(research_output: str) -> bool:
    """
    Catches silent research failures before the writer runs.

    Fixes:
    - Agent returning '!!!!!!!' or empty garbage
    - Agent returning ONLY filler like 'Thought: I now can give a great answer'
      with zero actual facts — ROOT CAUSE of Agentic AI hallucination run
    - Agent returning output too short to contain real facts
    - Agent returning output with no structured fact signals at all
    - Minimum SOURCE_QUOTE count check (1 is not enough for a real run)
    """
    if not research_output:
        print("⚠ Guard 1 FAIL — Research output is empty.")
        return False

    cleaned = research_output.strip().strip("!").strip("?").strip(".").strip()

    # Too short to contain real facts
    if len(cleaned) < 100:
        print(f"⚠ Guard 1 FAIL — Research output too short ({len(cleaned)} chars).")
        return False

    # Must contain structured fact signals
    # If ALL are missing, researcher produced filler only — not real extraction
    required_signals = ["FACT", "SOURCE_QUOTE", "SOURCE_NUM", "CATEGORY"]
    has_facts = any(signal in research_output for signal in required_signals)
    if not has_facts:
        print("⚠ Guard 1 FAIL — Research output has no structured facts.")
        print("   Missing all of: FACT, SOURCE_QUOTE, SOURCE_NUM, CATEGORY.")
        print("   Likely cause: researcher produced filler instead of real extraction.")
        return False

    # Must have at least 2 SOURCE_QUOTE occurrences
    source_quote_count = research_output.count("SOURCE_QUOTE")
    if source_quote_count < 2:
        print(f"⚠ Guard 1 FAIL — Only {source_quote_count} SOURCE_QUOTE found. Minimum 2 required.")
        return False

    # Catch filler-only output — researcher summarizing instead of extracting
    filler_phrases = [
        "i now can give a great answer",
        "here is the answer",
        "here is my answer",
        "i'll now provide",
        "i will now provide",
        "let me provide",
    ]
    research_lower = research_output.lower()
    # Only flag if filler is in first 300 chars AND no real signals exist
    for phrase in filler_phrases:
        if phrase in research_lower[:300] and source_quote_count < 2:
            print(f"⚠ Guard 1 FAIL — Filler phrase at start with no real facts: '{phrase}'")
            return False

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

    # Minimum citation count — catches thin hallucinated documents
    cite_count = writer_output.count("[CITE:")
    if cite_count < 4:
        print(f"⚠ Guard 2 FAIL — Only {cite_count} citations found. Minimum 4 required.")
        return False

    # Catch filler phrases — writer producing preamble instead of document
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

    output_upper          = validation_output.upper()
    verified_no_count     = output_upper.count("VERIFIED: NO")
    cite_missing_count    = output_upper.count("CITE_TAG_PRESENT: NO")
    duplicate_count       = output_upper.count("DUPLICATE_EVIDENCE: YES")
    fabricated_count      = output_upper.count("QUOTE_IN_SOURCES: NO")
    semantic_fail_count   = output_upper.count("SEMANTIC_MATCH: NO")
    repetition_fail_count = output_upper.count("REPETITION_FAIL: YES")

    if stated_verdict == "PASS" and (
        verified_no_count     > 0 or
        cite_missing_count    > 0 or
        duplicate_count       > 0 or
        fabricated_count      > 0 or
        semantic_fail_count   > 0 or
        repetition_fail_count > 0
    ):
        print(f"\n⚠ Guard 3 — Verdict override: validator said PASS but found:")
        if verified_no_count > 0:
            print(f"   - {verified_no_count} unverified claim(s) (VERIFIED: NO)")
        if cite_missing_count > 0:
            print(f"   - {cite_missing_count} missing citation(s) (CITE_TAG_PRESENT: NO)")
        if duplicate_count > 0:
            print(f"   - {duplicate_count} duplicate evidence instance(s) (DUPLICATE_EVIDENCE: YES)")
        if fabricated_count > 0:
            print(f"   - {fabricated_count} fabricated quote(s) not in search results (QUOTE_IN_SOURCES: NO)")
        if semantic_fail_count > 0:
            print(f"   - {semantic_fail_count} semantic mismatch(es) — quote meaning contradicts claim (SEMANTIC_MATCH: NO)")
        if repetition_fail_count > 0:
            print(f"   - {repetition_fail_count} repetition failure(s) — Overview has near-identical sentences (REPETITION_FAIL: YES)")
        print(f"   Overriding stated PASS → FAIL.\n")
        return "FAIL"

    return stated_verdict


# ================================================================
# GUARD 4 — Validator output quality check
# ================================================================

def _is_valid_validator_output(validation_output: str) -> bool:
    """
    Catches silent validator failures.

    Fixes:
    - Validator returning empty output
    - Validator output truncated by token limit (no score lines written)
    - Validator producing filler instead of audit
    - Validator skipping the claim-by-claim audit entirely
    """
    if not validation_output:
        print("⚠ Guard 4 FAIL — Validator output is empty.")
        return False

    cleaned = validation_output.strip()

    # Too short to be a real audit
    if len(cleaned) < 100:
        print(f"⚠ Guard 4 FAIL — Validator output too short ({len(cleaned)} chars).")
        return False

    # Must have score lines — if missing, output was truncated by MAX_TOKENS
    if "Structure Score:" not in validation_output:
        print("⚠ Guard 4 FAIL — Missing 'Structure Score:' line. Output likely truncated (increase MAX_TOKENS).")
        return False

    if "Verdict:" not in validation_output:
        print("⚠ Guard 4 FAIL — Missing 'Verdict:' line.")
        return False

    # Must have at least 1 CLAIM audit entry
    has_audit = (
        "CLAIM:" in validation_output or
        "CITE_TAG_PRESENT:" in validation_output
    )
    if not has_audit:
        print("⚠ Guard 4 FAIL — No CLAIM audit entries found. Validator skipped audit entirely.")
        return False

    # Catch filler at start — validator producing preamble instead of audit
    filler_phrases = [
        "i now can give a great answer",
        "here is the answer",
        "here is my audit",
        "let me audit",
        "i'll audit",
        "i will audit",
        "thought:",
    ]
    validator_lower = validation_output.lower()
    for phrase in filler_phrases:
        if phrase in validator_lower[:300]:
            print(f"⚠ Guard 4 FAIL — Filler phrase at start of validator output: '{phrase}'")
            return False

    return True


# ================================================================
# INTERNAL GUARD RUNNER
# Runs all 4 guards, returns (validation_output, verdict).
# Returns ("", "FAIL") on any guard failure — lets caller decide retry.
# Does NOT call sys.exit — retry logic lives in run().
# ================================================================

def _validate_result(result, topic):
    """
    Runs all 4 quality guards on a crew result.

    Guard 1 — Research output: has real facts, not filler or garbage
    Guard 2 — Writer output: has sections, citations, no filler
    Guard 3 — Verdict override: catches validator self-contradiction
    Guard 4 — Validator output: has audit entries + score lines

    Returns (validation_output, verdict) where verdict is "PASS" or "FAIL".
    Never calls sys.exit — caller decides what to do with FAIL.
    """
    # Guard 1 — Research
    research_output = result.tasks_output[0].raw
    if not _is_valid_research_output(research_output):
        print("⚠ Guard 1 triggered — research output invalid.")
        return "", "FAIL"

    # Guard 2 — Writer
    writer_output = result.tasks_output[1].raw
    if not _is_valid_writer_output(writer_output):
        print("⚠ Guard 2 triggered — writer output invalid.")
        return "", "FAIL"

    # Guard 4 — Validator (check before Guard 3 since Guard 3 reads its content)
    validation_output = result.tasks_output[2].raw
    if not _is_valid_validator_output(validation_output):
        print("⚠ Guard 4 triggered — validator output invalid.")
        return validation_output, "FAIL"

    # Guard 3 — Verdict override (reads validated output)
    verdict = _get_true_verdict(validation_output)

    return validation_output, verdict


# ================================================================
# DEDUPLICATION — warn if topic already exists in history_log
# ================================================================

def _check_duplicate_topic(topic: str) -> bool:
    """
    Checks if topic already exists in history_log.json.
    Returns True if duplicate found, False if topic is new.
    Warns user and asks for confirmation before re-running.
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

    print("\n▶ Proceeding with re-run...\n")
    return False


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

    # Check for duplicate before doing anything else
    if _check_duplicate_topic(topic):
        sys.exit(0)

    # ------------------------------------------------------------------
    # 2. BUILD CREW
    # ------------------------------------------------------------------
    crew, source_count = build_crew(topic)

    print("\n🚀 Starting Crew Execution...\n")

    # ------------------------------------------------------------------
    # 3. START TIMER
    # ------------------------------------------------------------------
    start_time = time.time()

    # ------------------------------------------------------------------
    # 4. FIRST RUN
    # ------------------------------------------------------------------
    result = _kickoff_with_delays(crew)
    validation_output, verdict = _validate_result(result, topic)

    retry_used = False

    # ------------------------------------------------------------------
    # 5. RETRY LOGIC — one retry if first run failed
    # ------------------------------------------------------------------
    if verdict == "FAIL":
        print("\n⚠ First run failed. Retrying once...\n")
        retry_used = True

        retry_result = _kickoff_with_delays(crew)
        retry_validation_output, retry_verdict = _validate_result(retry_result, topic)

        if retry_verdict == "PASS":
            print("✅ Retry succeeded.\n")
            result            = retry_result
            validation_output = retry_validation_output
            verdict           = "PASS"
        else:
            # Both runs failed — save debug report and exit
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
    )

    save_metrics(metrics_data)
    save_report(topic, result)

    print(f"\n✅ Job complete! Finished in {metrics_data['run_duration_minutes']} mins\n")


# ================================================================
# CREW KICKOFF WITH RATE LIMIT DELAYS
# ================================================================

def _kickoff_with_delays(crew):
    """
    Runs crew with per-step delays between each agent call.
    Protects against free tier rate limits (Groq: 6K tokens/min,
    OpenRouter: varies per model).
    """
    def step_callback(step_output):
        print(f"\n💤 Waiting {AGENT_CALL_DELAY_SECONDS}s (rate limit protection)...\n")
        time.sleep(AGENT_CALL_DELAY_SECONDS)

    # Attach callback to all agents
    original_callbacks = []
    for agent in crew.agents:
        original_callbacks.append(getattr(agent, "step_callback", None))
        agent.step_callback = step_callback

    try:
        result = crew.kickoff()
    finally:
        # Always restore original callbacks even if kickoff raises
        for agent, cb in zip(crew.agents, original_callbacks):
            agent.step_callback = cb

    return result


if __name__ == "__main__":
    run()