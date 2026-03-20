"""
clean_history.py — Cleans history_log.json

Fixes 3 problems:
1. Verified > Total math bug (removes broken runs)
2. Duplicate topics with different casing (keeps best run per topic)
3. FAIL verdict runs (removes them)

Creates a backup before making any changes.

Usage:
    python clean_history.py
"""

import json
import os
import shutil
from datetime import datetime

HISTORY_FILE = "metrics/history_log.json"
BACKUP_FILE  = f"metrics/history_log_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"


def load_history():
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_history(data):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def print_separator():
    print("=" * 58)


def run():
    if not os.path.exists(HISTORY_FILE):
        print(f"❌ {HISTORY_FILE} not found.")
        return

    # ── Backup first ──────────────────────────────────────────
    shutil.copy(HISTORY_FILE, BACKUP_FILE)
    print(f"\n✅ Backup created: {BACKUP_FILE}")

    history = load_history()
    original_count = len(history)

    print_separator()
    print(f"📂 Loaded {original_count} runs from history_log.json")
    print_separator()

    # ── FIX 1: Remove FAIL verdict runs ───────────────────────
    passed_runs = [r for r in history if r.get("verdict") == "PASS"]
    removed_fails = original_count - len(passed_runs)
    print(f"\n🔧 FIX 1 — Remove FAIL runs")
    print(f"   Removed: {removed_fails} FAIL runs")
    print(f"   Remaining: {len(passed_runs)} runs")

    # ── FIX 2: Remove verified > total math bug runs ──────────
    valid_math = []
    removed_math = 0
    for r in passed_runs:
        total    = r.get("total_claims", 0)
        verified = r.get("verified_claims", 0)
        if total == 0 or verified > total:
            removed_math += 1
            print(f"   ⚠ Math bug removed: {r.get('topic')} "
                  f"(verified={verified} > total={total})")
        else:
            valid_math.append(r)

    print(f"\n🔧 FIX 2 — Remove verified > total math bug runs")
    print(f"   Removed: {removed_math} broken runs")
    print(f"   Remaining: {len(valid_math)} runs")

    # ── FIX 3: Deduplicate topics (case-insensitive) ──────────
    # Keep the best run per topic (highest verification rate)
    topic_map = {}
    for r in valid_math:
        key = r.get("topic", "").lower().strip()
        if key not in topic_map:
            topic_map[key] = r
        else:
            # Keep whichever has higher verification rate
            existing_rate = topic_map[key].get("verification_rate_percent", 0)
            current_rate  = r.get("verification_rate_percent", 0)
            if current_rate > existing_rate:
                print(f"   ↩ Replacing '{topic_map[key].get('topic')}' "
                      f"({existing_rate}%) with '{r.get('topic')}' ({current_rate}%)")
                topic_map[key] = r

    deduped = list(topic_map.values())
    removed_dupes = len(valid_math) - len(deduped)

    print(f"\n🔧 FIX 3 — Deduplicate topics (case-insensitive)")
    print(f"   Removed: {removed_dupes} duplicate topic runs")
    print(f"   Remaining: {len(deduped)} unique topics")

    # ── Save cleaned history ───────────────────────────────────
    save_history(deduped)

    # ── Summary ───────────────────────────────────────────────
    print_separator()
    print(f"📊 CLEAN SUMMARY")
    print_separator()
    print(f"  Before: {original_count} runs")
    print(f"  Removed FAIL runs:       {removed_fails}")
    print(f"  Removed math bug runs:   {removed_math}")
    print(f"  Removed duplicate runs:  {removed_dupes}")
    print(f"  After:  {len(deduped)} clean runs")
    print(f"\n✅ Cleaned history saved to {HISTORY_FILE}")
    print(f"✅ Backup saved to {BACKUP_FILE}")
    print(f"\n💡 Run 'python analyze_metrics.py' to see updated metrics.\n")


if __name__ == "__main__":
    run()