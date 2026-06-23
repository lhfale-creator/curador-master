#!/usr/bin/env python3
"""Curador - safe fix applier.

Applies only what is mechanically unambiguous and reversible:
  1. Separator/case in internal wikilinks  -> [[feedback-x]] becomes [[feedback_x]]
  2. Repointing a renamed slug             -> --repoint old=new
  3. Removing duplicate lines in the index -> same .md file listed twice
  4. Align name: field to filename stem    -> --normalize-names
  5. Add missing tags/updated frontmatter  -> --normalize-frontmatter

Dry-run by default. Writes only with --write.
Prompts per file with --interactive (no --write needed; it asks as it goes).

Usage:
    python apply_safe_fixes.py --path "<folder>" [--config curador.json]
                               [--repoint old=new] [--normalize-names]
                               [--normalize-frontmatter] [--interactive]
                               [--write]
"""
import argparse
import datetime
import json
import os
import re
import sys

WIKILINK_RE = re.compile(r"\[\[([^\]\|#\^]+)((?:[#\^][^\]\|]*)?(?:\|[^\]]+)?)\]\]")
MDLINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+?\.md)(?:#[^)]*)?\)")
FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`]*`")


def load_config(config_path=None):
    if not config_path:
        for d in [os.path.dirname(os.path.abspath(__file__)), os.getcwd()]:
            c = os.path.join(d, "curador.json")
            if os.path.exists(c):
                config_path = c
                break
    if not config_path or not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def norm(s):
    s = s.strip().lower()
    if s.endswith(".md"):
        s = s[:-3]
    return re.sub(r"[\s_-]+", "-", s)


def is_external(t):
    t = t.strip()
    return ("/" in t) or (" " in t) or any(c.isupper() for c in t)


def in_code_spans(text):
    spans = []
    for m in list(FENCE_RE.finditer(text)) + list(INLINE_CODE_RE.finditer(text)):
        spans.append((m.start(), m.end()))
    return spans


def covered(pos, spans):
    return any(a <= pos < b for a, b in spans)


def collect_stems(root):
    stems = {}
    for dp, dn, fns in os.walk(root):
        dn[:] = [d for d in dn if d not in (".git", ".obsidian", ".trash", "node_modules")]
        for fn in fns:
            if fn.lower().endswith(".md"):
                stems.setdefault(norm(fn[:-3]), fn[:-3])
    return stems


def prompt_file(rel, local, fm_added, name_changed):
    """Interactive prompt for a single file. Returns True to write."""
    print(f"\n  FILE: {rel}")
    for a, b in local:
        print(f"    link:  {a}  ->  {b}")
    if name_changed:
        print(f"    name:  {name_changed[0]}  ->  {name_changed[1]}")
    if fm_added:
        print(f"    frontmatter: + {', '.join(fm_added)}")
    while True:
        ans = input("  Apply? [y]es / [n]o / [q]uit: ").strip().lower()
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        if ans in ("q", "quit"):
            print("Aborted.")
            sys.exit(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument("--index", default=None)
    ap.add_argument("--repoint", action="append", default=[], help="old=new (slugs)")
    ap.add_argument("--no-separator", action="store_true")
    ap.add_argument("--no-dedup", action="store_true")
    ap.add_argument("--normalize-names", action="store_true")
    ap.add_argument("--normalize-frontmatter", action="store_true")
    ap.add_argument("--interactive", action="store_true",
                    help="prompt per file instead of --write (implies write on 'y')")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if not args.path:
        args.path = os.path.expanduser(cfg.get("memory") or cfg.get("vault") or "")
    if not args.path:
        print("ERROR: --path required (or set paths in curador.json)", file=sys.stderr)
        sys.exit(2)

    root = os.path.abspath(args.path)
    stems = collect_stems(root)
    repoint = {}
    for r in args.repoint:
        if "=" in r:
            o, n = r.split("=", 1)
            repoint[norm(o)] = n.strip()

    index_name = args.index
    if not index_name:
        for c in ("MEMORY.md", "Home.md"):
            if os.path.exists(os.path.join(root, c)):
                index_name = c
                break
    index_path = os.path.join(root, index_name) if index_name else None

    do_write = args.write or args.interactive
    mode = "INTERACTIVE" if args.interactive else ("WRITING" if args.write else "DRY-RUN (nothing written)")

    NAME_RE = re.compile(r"^(name:\s*)(.+?)\s*$", re.MULTILINE)

    all_changes, name_fixes, fm_fixes = [], [], []

    for dp, dn, fns in os.walk(root):
        dn[:] = [d for d in dn if d not in (".git", ".obsidian", ".trash", "node_modules")]
        for fn in fns:
            if not fn.lower().endswith(".md"):
                continue
            full = os.path.join(dp, fn)
            with open(full, "r", encoding="utf-8") as f:
                text = f.read()
            spans = in_code_spans(text)
            orig = text
            local = []
            name_changed = None
            fm_added = []

            def repl(m):
                start = m.start()
                target, suffix = m.group(1), m.group(2)
                if covered(start, spans) or is_external(target):
                    return m.group(0)
                nt = norm(target)
                if nt in repoint:
                    new = repoint[nt]
                    if new != target:
                        local.append((f"[[{target}]]", f"[[{new}]]"))
                        return f"[[{new}{suffix}]]"
                    return m.group(0)
                if args.no_separator:
                    return m.group(0)
                if nt in stems and stems[nt] != target:
                    new = stems[nt]
                    local.append((f"[[{target}]]", f"[[{new}]]"))
                    return f"[[{new}{suffix}]]"
                return m.group(0)

            text = WIKILINK_RE.sub(repl, text)

            if args.normalize_names and text.startswith("---"):
                fm_end = text.find("\n---", 3)
                if fm_end != -1:
                    head, rest = text[:fm_end], text[fm_end:]
                    stem = fn[:-3]
                    m = NAME_RE.search(head)
                    if m and m.group(2).strip().strip('"').strip("'") != stem:
                        old_name = m.group(2).strip()
                        head = NAME_RE.sub(lambda mm: f"{mm.group(1)}{stem}", head, count=1)
                        text = head + rest
                        name_changed = (old_name, stem)
                        name_fixes.append((os.path.relpath(full, root), old_name, stem))

            if args.normalize_frontmatter and full != index_path:
                mdate = datetime.date.fromtimestamp(os.path.getmtime(full)).isoformat()
                clean = text.lstrip("﻿")
                if not clean.startswith("---"):
                    text = f"---\ntags: []\nupdated: {mdate}\n---\n\n" + clean
                    fm_added = ["tags", "updated"]
                else:
                    fm_end = clean.find("\n---", 3)
                    text = clean
                    if fm_end != -1:
                        head = text[3:fm_end]
                        insert = ""
                        if not re.search(r"^\s*tags\s*:", head, re.MULTILINE):
                            insert += "tags: []\n"; fm_added.append("tags")
                        if not re.search(r"^\s*updated\s*:", head, re.MULTILINE):
                            insert += f"updated: {mdate}\n"; fm_added.append("updated")
                        if insert:
                            text = "---" + head.rstrip("\n") + "\n" + insert.rstrip("\n") + text[fm_end:]
                if fm_added:
                    fm_fixes.append((os.path.relpath(full, root), fm_added))

            if repoint:
                def repl_md(m):
                    if covered(m.start(), spans):
                        return m.group(0)
                    tgt = os.path.basename(m.group(1))
                    nt = norm(tgt)
                    if nt in repoint:
                        new = repoint[nt] + ".md"
                        local.append((m.group(1), new))
                        return m.group(0).replace(m.group(1), new)
                    return m.group(0)
                text = MDLINK_RE.sub(repl_md, text)

            if text != orig:
                rel = os.path.relpath(full, root)
                all_changes.append((full, rel, text, local, name_changed, fm_added))

    # Dedup index
    dedup_report = []
    new_index_lines = None
    if index_path and not args.no_dedup and os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        seen, out = set(), []
        for ln in lines:
            stripped = ln.strip()
            mdt = MDLINK_RE.findall(ln)
            key = norm(os.path.basename(mdt[0])) if mdt else None
            if key and stripped.startswith("-") and key in seen:
                dedup_report.append(ln.rstrip())
                continue
            if key and stripped.startswith("-"):
                seen.add(key)
            out.append(ln)
        if dedup_report:
            new_index_lines = out

    # Report
    print(f"=== CURADOR apply_safe_fixes  [{mode}] ===")
    print(f"folder: {root}\n")
    print(f"## Links to rewrite ({len(all_changes)} files)")
    if not all_changes:
        print("  (none)")
    for _, rel, _, local, _, _ in all_changes:
        if local:
            print(f"  {rel}")
            for a, b in local:
                print(f"      {a}  ->  {b}")
    print(f"\n## name: fields to align ({len(name_fixes)})")
    for rel, old, new in name_fixes:
        print(f"  {rel}:  {old}  ->  {new}")
    print(f"\n## Frontmatter to normalize ({len(fm_fixes)} files)")
    for rel, added in fm_fixes:
        print(f"  {rel}:  + {', '.join(added)}")
    print(f"\n## Index duplicate lines to remove ({len(dedup_report)})")
    for ln in dedup_report:
        print(f"  - {ln}")

    # Apply
    if args.interactive:
        print("\n--- INTERACTIVE MODE (y/n/q per file) ---")
        for full, rel, text, local, name_changed, fm_added in all_changes:
            if not (local or name_changed or fm_added):
                continue
            if prompt_file(rel, local, fm_added, name_changed):
                with open(full, "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"    written.")
        if new_index_lines and dedup_report:
            ans = input(f"  Remove {len(dedup_report)} duplicate line(s) from index? [y/n]: ").strip().lower()
            if ans in ("y", "yes"):
                with open(index_path, "w", encoding="utf-8") as f:
                    f.writelines(new_index_lines)
    elif args.write:
        for full, rel, text, _, _, _ in all_changes:
            with open(full, "w", encoding="utf-8") as f:
                f.write(text)
        if new_index_lines and dedup_report:
            with open(index_path, "w", encoding="utf-8") as f:
                f.writelines(new_index_lines)
    else:
        print("\n>>> DRY-RUN. Add --write to apply all, or --interactive to choose per file.")


if __name__ == "__main__":
    main()
