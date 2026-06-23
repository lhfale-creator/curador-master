#!/usr/bin/env python3
"""Curador - safe fix applier.

Applies only what is mechanically unambiguous and reversible:
  1. Separator/case in internal wikilinks  -> [[feedback-x]] becomes [[feedback_x]]
  2. Repointing a renamed slug             -> --repoint old=new
  3. Removing duplicate lines in the index -> same .md file listed twice
  4. Align name: field to filename stem    -> --normalize-names
  5. Add missing tags/updated frontmatter  -> --normalize-frontmatter

Does NOT touch: orphans, weak connections, vault refs, content merge, file
rename, or any other judgment call. Those require human/Claude decision.

Dry-run by default. Writes only with --write.

Usage:
    python apply_safe_fixes.py --path "<folder>" [--index MEMORY.md]
                               [--repoint project_old=project_new]
                               [--no-separator] [--no-dedup]
                               [--normalize-names] [--normalize-frontmatter]
                               [--write]
"""
import argparse
import datetime
import os
import re
import sys

WIKILINK_RE = re.compile(r"\[\[([^\]\|#\^]+)((?:[#\^][^\]\|]*)?(?:\|[^\]]+)?)\]\]")
MDLINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+?\.md)(?:#[^)]*)?\)")
FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`]*`")


def norm(s):
    s = s.strip().lower()
    if s.endswith(".md"):
        s = s[:-3]
    return re.sub(r"[\s_-]+", "-", s)


def is_external(t):
    t = t.strip()
    return ("/" in t) or (" " in t) or any(c.isupper() for c in t)


def in_code_spans(text):
    """List of (start, end) intervals covered by code, so we skip those."""
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", required=True)
    ap.add_argument("--index", default=None)
    ap.add_argument("--repoint", action="append", default=[], help="old=new (slugs)")
    ap.add_argument("--no-separator", action="store_true")
    ap.add_argument("--no-dedup", action="store_true")
    ap.add_argument("--normalize-names", action="store_true",
                    help="align name: field to filename stem (kebab -> underscore)")
    ap.add_argument("--normalize-frontmatter", action="store_true",
                    help="vault: add missing tags:/updated: (updated comes from file mtime)")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

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

    changes = []
    name_fixes = []
    fm_fixes = []
    mode = "WRITING" if args.write else "DRY-RUN (nothing written)"

    NAME_RE = re.compile(r"^(name:\s*)(.+?)\s*$", re.MULTILINE)

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

            def repl(m):
                start = m.start()
                target, suffix = m.group(1), m.group(2)
                if covered(start, spans):
                    return m.group(0)
                if is_external(target):
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
                        name_fixes.append((os.path.relpath(full, root), old_name, stem))

            if args.normalize_frontmatter and full != index_path:
                mdate = datetime.date.fromtimestamp(os.path.getmtime(full)).isoformat()
                added = []
                clean = text.lstrip("﻿")  # strip UTF-8 BOM before checking frontmatter
                if not clean.startswith("---"):
                    text = f"---\ntags: []\nupdated: {mdate}\n---\n\n" + clean
                    added = ["tags", "updated"]
                else:
                    fm_end = clean.find("\n---", 3)
                    text = clean  # ensure no BOM
                    if fm_end != -1:
                        head = text[3:fm_end]
                        insert = ""
                        if not re.search(r"^\s*tags\s*:", head, re.MULTILINE):
                            insert += "tags: []\n"
                            added.append("tags")
                        if not re.search(r"^\s*updated\s*:", head, re.MULTILINE):
                            insert += f"updated: {mdate}\n"
                            added.append("updated")
                        if insert:
                            text = "---" + head.rstrip("\n") + "\n" + insert.rstrip("\n") + text[fm_end:]
                if added:
                    fm_fixes.append((os.path.relpath(full, root), added))

            if repoint:
                def repl_md(m):
                    if covered(m.start(), spans):
                        return m.group(0)
                    tgt = os.path.basename(m.group(1))
                    nt = norm(tgt)
                    if nt in repoint:
                        new = repoint[nt] + ".md"
                        whole = m.group(0).replace(m.group(1), new)
                        local.append((m.group(1), new))
                        return whole
                    return m.group(0)
                text = MDLINK_RE.sub(repl_md, text)

            if text != orig:
                changes.append((os.path.relpath(full, root), local))
                if args.write:
                    with open(full, "w", encoding="utf-8") as f:
                        f.write(text)

    dedup_report = []
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
        if dedup_report and args.write:
            with open(index_path, "w", encoding="utf-8") as f:
                f.writelines(out)

    print(f"=== CURADOR apply_safe_fixes  [{mode}] ===")
    print(f"folder: {root}\n")
    print(f"## Links rewritten ({len(changes)} files)")
    if not changes:
        print("  (none)")
    for rel, local in changes:
        print(f"  {rel}")
        for a, b in local:
            print(f"      {a}  ->  {b}")
    print(f"\n## name: fields aligned to filename ({len(name_fixes)})")
    for rel, old, new in name_fixes:
        print(f"  {rel}:  name: {old}  ->  {new}")
    print(f"\n## Frontmatter normalized ({len(fm_fixes)} files)")
    for rel, added in fm_fixes:
        print(f"  {rel}:  + {', '.join(added)}")
    print(f"\n## Duplicate index lines removed ({len(dedup_report)})")
    for ln in dedup_report:
        print(f"  - {ln}")
    if not args.write:
        print("\n>>> DRY-RUN. Review above and re-run with --write to apply.")


if __name__ == "__main__":
    main()
