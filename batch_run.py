"""
batch_run.py — Run multiple research topics automatically.

Instead of manually entering one topic at a time,
this script runs a list of topics sequentially with
cooldown delays between runs to respect rate limits.

Usage:
    python batch_run.py

To customize topics, edit the TOPICS list below.
Results are saved to metrics/history_log.json automatically.
"""

import json
import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()

os.environ["OPENROUTER_API_KEY"] = os.getenv("OPENROUTER_API_KEY", "")
os.environ["OR_API_KEY"] = os.getenv("OPENROUTER_API_KEY", "")

from crew_runner import build_crew
from metrics import calculate_metrics, save_metrics
from utils.file_utils import save_report, save_failed_report
from config import AGENT_CALL_DELAY_SECONDS
from main import (
    _kickoff_with_delays,
    _validate_result,       # now takes only (result, topic) — no start_time/source_count
)

# ================================================================
# TOPICS TO RESEARCH
# Edit this list to run any topics you want
# ================================================================

TOPICS = [
    "Apache Kafka",           # distributed systems / data streaming
    "WebSockets",             # real-time communication protocol
    "Quantum Computing",      # completely different compute paradigm
    "Blockchain Technology",  # decentralized systems
    "Cyber Security",         # security domain — zero overlap with your list
]

# ================================================================
# COOLDOWN between runs (seconds)
# Prevents rate limit hits across consecutive runs
# ================================================================

COOLDOWN_BETWEEN_RUNS = 30


# ================================================================
# DEDUPLICATION — skip topics already in history_log
# Skips ALL existing topics regardless of verdict
# (prevents re-running topics that already passed OR failed)
# ================================================================

def _load_existing_topics() -> set:
    """
    Returns set of ALL topic names already in history_log.
    Skips both PASS and FAIL entries — no topic is re-run
    unless manually removed from history_log.
    """
    history_file = "metrics/history_log.json"
    if not os.path.exists(history_file):
        return set()
    with open(history_file, "r", encoding="utf-8") as f:
        history = json.load(f)
    # Include ALL verdicts — not just PASS
    return {r["topic"].lower().strip() for r in history}


# ================================================================
# SINGLE TOPIC RUN (mirrors main.py logic, no input prompt)
# ================================================================

def run_topic(topic: str) -> bool:
    """
    Runs the full pipeline for a single topic.
    Returns True if PASS, False if FAIL.
    Never raises — all exceptions caught and logged.
    """
    print(f"\n{'='*58}")
    print(f"🔬 RESEARCHING: {topic}")
    print(f"{'='*58}\n")

    try:
        crew, source_count = build_crew(topic)
        start_time = time.time()

        # ── First attempt ────────────────────────────────────
        result = _kickoff_with_delays(crew)
        validation_output, verdict = _validate_result(result, topic)

        retry_used = False

        # ── Retry if first attempt failed ────────────────────
        if verdict == "FAIL":
            print(f"\n⚠ First attempt failed. Retrying {topic}...\n")
            retry_used = True

            retry_result = _kickoff_with_delays(crew)
            retry_validation_output, retry_verdict = _validate_result(
                retry_result, topic
            )

            if retry_verdict == "PASS":
                print(f"✅ Retry succeeded for {topic}.\n")
                result            = retry_result
                validation_output = retry_validation_output
                verdict           = "PASS"
            else:
                # Both attempts failed — save debug report, continue batch
                elapsed_seconds = time.time() - start_time
                print(f"\n❌ Both attempts failed for {topic}. Moving to next topic.\n")
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
                return False

        # ── Success path ─────────────────────────────────────
        elapsed_seconds = time.time() - start_time
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
        print(f"\n✅ {topic} complete in {metrics_data['run_duration_minutes']} mins\n")
        return True

    except KeyboardInterrupt:
        # Re-raise so batch runner can catch it and print summary
        raise

    except Exception as e:
        # Any unexpected error — log and continue to next topic
        print(f"\n❌ Unexpected error on '{topic}': {type(e).__name__}: {e}\n")
        print(f"   Skipping topic and continuing batch.\n")
        return False


# ================================================================
# MAIN BATCH RUNNER
# ================================================================

def run_batch():
    if not TOPICS:
        print("\n⚠ TOPICS list is empty. Add topics to batch_run.py and retry.\n")
        return

    existing_topics = _load_existing_topics()

    # Filter out already completed topics
    pending = []
    skipped = []
    for topic in TOPICS:
        if topic.lower().strip() in existing_topics:
            skipped.append(topic)
        else:
            pending.append(topic)

    print(f"\n{'='*58}")
    print(f"🚀 BATCH RUN — {len(TOPICS)} topics requested")
    print(f"   ✅ Already in history (skipping): {len(skipped)}")
    print(f"   🔬 To run now:                    {len(pending)}")
    print(f"   ⏱  Cooldown between runs:         {COOLDOWN_BETWEEN_RUNS}s")
    print(f"{'='*58}")

    if skipped:
        print(f"\n⏭ Skipping already recorded topics:")
        for t in skipped:
            print(f"   - {t}")

    if not pending:
        print("\n✅ All topics already in history_log. Nothing to run.")
        return

    results = {"passed": [], "failed": []}

    try:
        for i, topic in enumerate(pending, 1):
            print(f"\n[{i}/{len(pending)}] Starting: {topic}")

            success = run_topic(topic)

            if success:
                results["passed"].append(topic)
            else:
                results["failed"].append(topic)

            # Cooldown between runs (skip after last topic)
            if i < len(pending):
                print(f"\n⏳ Cooldown: waiting {COOLDOWN_BETWEEN_RUNS}s before next topic...\n")
                time.sleep(COOLDOWN_BETWEEN_RUNS)

    except KeyboardInterrupt:
        # User pressed Ctrl+C — print partial summary and exit cleanly
        print(f"\n\n⚠ Batch interrupted by user (Ctrl+C).")
        print(f"   Topics completed before interrupt:")
        for t in results["passed"]:
            print(f"   ✅ {t}")
        for t in results["failed"]:
            print(f"   ❌ {t}")
        remaining = [t for t in pending if t not in results["passed"] and t not in results["failed"]]
        if remaining:
            print(f"\n   Topics NOT run:")
            for t in remaining:
                print(f"   ⏭ {t}")
        print(f"\n💡 Run 'python analyze_metrics.py' to see metrics for completed topics.\n")
        sys.exit(0)

    # ── Final summary ─────────────────────────────────────────
    print(f"\n{'='*58}")
    print(f"📊 BATCH RUN COMPLETE")
    print(f"{'='*58}")
    print(f"  Total run:  {len(pending)}")
    print(f"  Passed:     {len(results['passed'])}")
    print(f"  Failed:     {len(results['failed'])}")

    if results["passed"]:
        print(f"\n✅ Passed:")
        for t in results["passed"]:
            print(f"   - {t}")

    if results["failed"]:
        print(f"\n❌ Failed (check failed/ folder for debug reports):")
        for t in results["failed"]:
            print(f"   - {t}")

    print(f"\n💡 Run 'python analyze_metrics.py' to see updated aggregate report.\n")


if __name__ == "__main__":
    run_batch()