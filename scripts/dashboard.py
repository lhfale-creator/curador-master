#!/usr/bin/env python3
"""Curador - growth dashboard.

Reads a growth_log.jsonl (produced by audit_kb.py --snapshot) and shows
a trend table with change indicators. Alerts if any metric worsened.

Usage:
    python dashboard.py --log <path/to/growth_log.jsonl> [--profile memory|vault|all] [--last N]
"""
import argparse
import json
import os
import sys

METRICS = ["notes", "orphans", "broken", "separator", "weak", "dupes", "stale",
           "split_candidates", "misplaced", "size_rule_violations", "density", "critical"]
UP_IS_BAD  = {"orphans", "broken", "separator", "weak", "critical",
              "stale", "split_candidates", "misplaced", "size_rule_violations"}
UP_IS_GOOD = {"notes", "density"}


def indicator(key, prev_val, curr_val):
    if prev_val is None or prev_val == curr_val:
        return " "
    if key in UP_IS_BAD:
        return "-" if curr_val < prev_val else "!"
    if key in UP_IS_GOOD:
        return "+" if curr_val > prev_val else "."
    return " "


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True, help="path to growth_log.jsonl")
    ap.add_argument("--profile", default="all", help="filter: memory | vault | all")
    ap.add_argument("--last", type=int, default=10, help="show last N runs per profile (default 10)")
    args = ap.parse_args()

    if not os.path.exists(args.log):
        print(f"ERROR: log not found: {args.log}", file=sys.stderr)
        sys.exit(2)

    rows = []
    with open(args.log, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if not rows:
        print("Log is empty.")
        return

    by_profile = {}
    for r in rows:
        p = r.get("profile", "unknown")
        by_profile.setdefault(p, []).append(r)

    profiles = [p for p in by_profile if args.profile == "all" or p == args.profile]
    if not profiles:
        print(f"No entries for profile '{args.profile}'.")
        return

    all_alerts = []

    for profile in profiles:
        entries = by_profile[profile][-args.last:]
        print(f"\n{'=' * 72}")
        print(f"CURADOR DASHBOARD  |  profile: {profile}  |  {len(entries)} run(s)")
        print(f"{'=' * 72}")
        col = 9
        header = f"{'date':<12}" + "".join(f"{m[:col]:>{col+1}}" for m in METRICS)
        print(header)
        print("-" * len(header))

        prev = None
        for r in entries:
            line = f"{r.get('date', '?'):<12}"
            for m in METRICS:
                val = r.get(m, "-")
                ind = indicator(m, prev.get(m) if prev else None, val)
                cell = f"{ind}{val}" if ind != " " else f" {val}"
                line += f"{str(cell):>{col+1}}"
                if prev and m in UP_IS_BAD and isinstance(val, (int, float)) and val > (prev.get(m) or 0):
                    all_alerts.append(f"  [{profile}] {r.get('date')}: {m} {prev[m]} -> {val}")
            print(line)
            prev = r

    print(f"\n{'=' * 72}")
    print("LEGEND: + improved  ! worsened  - fixed  . dropped")
    if all_alerts:
        print(f"\n## REGRESSIONS ({len(all_alerts)})")
        for a in all_alerts:
            print(a)
    else:
        print("\n  OK - no regressions detected.")
    print()

    # Latest per profile
    print(f"{'=' * 72}")
    print("CURRENT STATE PER PROFILE")
    for profile in profiles:
        r = by_profile[profile][-1]
        print(f"  {profile:<10}  {r.get('date','?')}  "
              f"critical={r.get('critical','?')}  "
              f"orphans={r.get('orphans','?')}  "
              f"density={r.get('density','?')}  "
              f"notes={r.get('notes','?')}")


if __name__ == "__main__":
    main()
