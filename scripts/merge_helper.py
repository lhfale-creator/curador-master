#!/usr/bin/env python3
"""Curador - merge helper for de-bloat.

Shows two similar notes side by side, diffs them, and writes a merged draft.
Used after audit_kb.py flags POSSIBLE CONTENT DUPLICATES.

Usage:
    # Direct:
    python merge_helper.py --file1 <path> --file2 <path> [--output merged.md]

    # From audit JSON output (picks pair N, default 0 = most similar):
    python merge_helper.py --from-audit audit.json [--pair 0] [--root <vault-root>] [--output merged.md]

    # Produce audit JSON first:
    python audit_kb.py --path <folder> --json > audit.json
"""
import argparse
import difflib
import json
import os
import sys


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def propose_merge(text1, text2):
    """Base = longer note. Append unique non-empty lines from the shorter one."""
    if len(text2) > len(text1):
        text1, text2 = text2, text1
    base_lines = set(text1.splitlines())
    unique = [l for l in text2.splitlines() if l.strip() and l not in base_lines]
    if not unique:
        return text1
    return text1.rstrip() + "\n\n<!-- merged from duplicate — review before saving -->\n" + "\n".join(unique) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file1", help="first note")
    ap.add_argument("--file2", help="second note")
    ap.add_argument("--from-audit", metavar="JSON",
                    help="audit --json output file; picks from content_dupes list")
    ap.add_argument("--pair", type=int, default=0,
                    help="which content_dupe pair to pick (0 = most similar, default)")
    ap.add_argument("--root", default=".",
                    help="base folder for relative paths in the audit JSON")
    ap.add_argument("--output", metavar="FILE",
                    help="write merged draft to this file (does not overwrite either source)")
    args = ap.parse_args()

    if args.from_audit:
        if not os.path.exists(args.from_audit):
            print(f"ERROR: audit JSON not found: {args.from_audit}", file=sys.stderr)
            sys.exit(2)
        with open(args.from_audit, "r", encoding="utf-8") as f:
            raw = f.read()
        # Support both raw JSON and audit output with <<<JSON>>> marker
        if "<<<JSON>>>" in raw:
            raw = raw.split("<<<JSON>>>", 1)[1]
        data = json.loads(raw)
        dupes = data.get("content_dupes", [])
        if not dupes:
            print("No content_dupes in audit output. Run audit_kb.py and look for POSSIBLE CONTENT DUPLICATES.")
            sys.exit(0)
        if args.pair >= len(dupes):
            print(f"Only {len(dupes)} pairs; --pair must be < {len(dupes)}.")
            sys.exit(1)
        pair = dupes[args.pair]
        args.file1 = os.path.join(args.root, pair[0])
        args.file2 = os.path.join(args.root, pair[1])
        sim = pair[2] if len(pair) > 2 else "?"
        print(f"Pair {args.pair} (similarity {sim}):")
        print(f"  FILE 1: {args.file1}")
        print(f"  FILE 2: {args.file2}\n")

    if not (args.file1 and args.file2):
        print("ERROR: provide --file1/--file2 or --from-audit.", file=sys.stderr)
        sys.exit(2)

    for p in (args.file1, args.file2):
        if not os.path.exists(p):
            print(f"ERROR: file not found: {p}", file=sys.stderr)
            sys.exit(2)

    text1 = read(args.file1)
    text2 = read(args.file2)
    lines1 = text1.splitlines()
    lines2 = text2.splitlines()

    W = 100
    print("=" * W)
    print(f"FILE 1: {args.file1}  ({len(lines1)} lines, {len(text1):,} chars)")
    print(f"FILE 2: {args.file2}  ({len(lines2)} lines, {len(text2):,} chars)")
    print("=" * W)

    # Unified diff
    diff = list(difflib.unified_diff(
        lines1, lines2,
        fromfile=os.path.basename(args.file1),
        tofile=os.path.basename(args.file2),
        lineterm=""
    ))
    LIMIT = 60
    print(f"\n## DIFF ({len(diff)} changed lines)")
    for line in diff[:LIMIT]:
        print(line)
    if len(diff) > LIMIT:
        print(f"  ... +{len(diff) - LIMIT} more lines (use a text diff tool for full view)")

    # Unique content
    set1 = {l.strip() for l in lines1 if l.strip()}
    set2 = {l.strip() for l in lines2 if l.strip()}
    only1 = sorted(set1 - set2)
    only2 = sorted(set2 - set1)
    print(f"\n## UNIQUE TO FILE 1 ({len(only1)} lines)")
    for l in only1[:20]:
        print(f"  {l[:120]}")
    if len(only1) > 20:
        print(f"  ... +{len(only1) - 20} more")
    print(f"\n## UNIQUE TO FILE 2 ({len(only2)} lines)")
    for l in only2[:20]:
        print(f"  {l[:120]}")
    if len(only2) > 20:
        print(f"  ... +{len(only2) - 20} more")

    # Proposal
    merged = propose_merge(text1, text2)
    base_label = "FILE 1" if len(text1) >= len(text2) else "FILE 2"
    absorbed = len(only2) if len(text1) >= len(text2) else len(only1)
    print(f"\n## MERGE PROPOSAL")
    print(f"  Base: {base_label}  |  unique lines absorbed from the other: {absorbed}")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(merged)
        print(f"  Draft written to: {args.output}")
        print(f"\nNext steps:")
        print(f"  1. Review {args.output} — remove duplicate or stale content")
        print(f"  2. Overwrite the master note with the reviewed draft")
        print(f"  3. In the other note, replace content with: Moved to [[master]]")
        print(f"  4. Re-run audit_kb.py to confirm 0 broken links")
    else:
        print(f"  Add --output <path> to write the merged draft to a file.")


if __name__ == "__main__":
    main()
