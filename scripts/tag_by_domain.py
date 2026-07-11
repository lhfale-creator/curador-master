#!/usr/bin/env python3
"""
tag_by_domain.py — Stamp a real domain tag + `updated` on every vault note that
lacks them, derived from its top-level folder. Gives the graph/Dataview useful
tags (one per project) instead of empty `tags: []`. Never overrides existing tags.

Skips Memory/ (owned by sync-cerebro), .obsidian, _Arquivo. Idempotent, dry-run
by default.

Usage:  python tag_by_domain.py --vault "<vault>" [--write]
"""
import argparse
import os
import re
import unicodedata

SKIP = {".obsidian", "_Arquivo", "Memory", ".trash"}


def slug(name):
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    n = n.lower().replace("&", " ").replace("+", " ")
    n = re.sub(r"[^a-z0-9]+", "-", n).strip("-")
    return n


def stat_date(path):
    import datetime
    return datetime.date.fromtimestamp(os.path.getmtime(path)).isoformat()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=r"C:\Users\alexa\OneDrive\Documentos\Obsidian Vault")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    plan = []
    for entry in os.listdir(args.vault):
        root = os.path.join(args.vault, entry)
        if not os.path.isdir(root) or entry in SKIP:
            continue
        tag = slug(entry)
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP]
            for f in files:
                if not f.endswith(".md"):
                    continue
                p = os.path.join(dirpath, f)
                text = open(p, encoding="utf-8").read()
                added = []
                if text.startswith("---"):
                    end = text.find("\n---", 3)
                    fm = text[:end] if end != -1 else ""
                    rest_start = end + 4 if end != -1 else 0
                    new_fm = fm
                    if not re.search(r"^\s*tags\s*:", fm, re.MULTILINE):
                        new_fm += f"\ntags: [{tag}]"; added.append("tags")
                    if not re.search(r"^\s*updated\s*:", fm, re.MULTILINE):
                        new_fm += f"\nupdated: {stat_date(p)}"; added.append("updated")
                    new = new_fm + text[end:] if end != -1 else text
                else:
                    new = f"---\ntags: [{tag}]\nupdated: {stat_date(p)}\n---\n\n" + text
                    added = ["tags", "updated"]
                if added:
                    plan.append((os.path.relpath(p, args.vault), tag, added))
                    if args.write:
                        open(p, "w", encoding="utf-8").write(new)

    print(f"== tag_by_domain {'WROTE' if args.write else 'DRY-RUN'} — {len(plan)} notes ==")
    by_tag = {}
    for rel, tag, added in plan:
        by_tag[tag] = by_tag.get(tag, 0) + 1
    for tag, n in sorted(by_tag.items()):
        print(f"  #{tag:24} {n} notes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
