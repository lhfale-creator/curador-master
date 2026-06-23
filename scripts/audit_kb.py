#!/usr/bin/env python3
"""Curador - knowledge base audit engine.

Scans a folder of .md notes (Claude memory OR Obsidian vault) and detects
what causes loose memory: orphans, duplicates, broken links, separator
mismatch, inconsistent frontmatter, name diverging from filename, and
cross-system references (vault <-> memory).

Deterministic, zero external dependencies. Cross-platform (Windows/macOS/Linux).

Usage:
    python audit_kb.py --path "<folder>" [--profile memory|vault|auto]
                       [--snapshot <file.jsonl>] [--summary] [--json]

    # With config file (paths stored in curador.json):
    python audit_kb.py --config curador.json [--summary]
"""
import argparse
import json
import os
import re
import sys

WIKILINK_RE = re.compile(r"\[\[([^\]\|#\^]+)(?:[#\^][^\]\|]*)?(?:\|[^\]]+)?\]\]")
MDLINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+?\.md)(?:#[^)]*)?\)")
H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`]*`")
ASSET_RE = re.compile(r"\.(png|jpe?g|svg|gif|webp|bmp|pdf|mp4|mov|webm|mp3|wav|zip|xlsx?|docx?|pptx?|csv)$", re.I)
MEMORY_SLUG_RE = re.compile(r"^(project|feedback|reference|reminder|user)[_-]", re.I)

STOPWORDS = set("""a o os as de da do das dos e em no na nos nas um uma para por com que
do da pra pro como sao e ou ser ja nao sem ate uns umas the of and to in for project
feedback reference reminder user memoria projeto referencia""".split())


def load_config(config_path=None):
    """Load curador.json. Auto-detects in script dir or cwd when path is omitted."""
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


def tokenize(s):
    if not s:
        return set()
    words = re.findall(r"\w{4,}", s.lower(), re.UNICODE)
    return {w for w in words if w not in STOPWORDS}


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def strip_code(text):
    text = FENCE_RE.sub(" ", text)
    text = INLINE_CODE_RE.sub(" ", text)
    return text


def norm(s):
    s = s.strip().lower()
    if s.endswith(".md"):
        s = s[:-3]
    return re.sub(r"[\s_-]+", "-", s)


def link_basename(t):
    t = t.strip().rstrip("\\").strip()
    return re.split(r"[\\/]", t)[-1].strip()


def is_external(target):
    t = target.strip()
    return ("/" in t) or (" " in t) or any(c.isupper() for c in t)


def parse_frontmatter(text):
    fields = {}
    if not text.startswith("---"):
        return fields, False
    end = text.find("\n---", 3)
    if end == -1:
        return fields, False
    block = text[3:end]
    parent = None
    for line in block.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        m = re.match(r"^([\w.-]+)\s*:\s*(.*)$", line.strip())
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip().strip('"').strip("'")
        if indent == 0:
            parent = key if val == "" else None
            if val != "":
                fields[key] = val
        elif parent:
            fields[f"{parent}.{key}"] = val
    return fields, True


def collect_notes(root):
    notes = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", ".obsidian", ".trash", "node_modules")]
        for fn in filenames:
            if not fn.lower().endswith(".md"):
                continue
            full = os.path.join(dirpath, fn)
            try:
                with open(full, "r", encoding="utf-8") as f:
                    text = f.read()
            except (OSError, UnicodeDecodeError) as e:
                print(f"  [warning] could not read {full}: {e}", file=sys.stderr)
                continue
            stem = fn[:-3]
            fm, has_fm = parse_frontmatter(text)
            body = strip_code(text)
            h1 = H1_RE.search(body)
            wl = [w.strip() for w in WIKILINK_RE.findall(body)]
            ml = [os.path.basename(m).strip() for m in MDLINK_RE.findall(body)]
            notes[full] = {
                "path": full, "stem": stem, "rel": os.path.relpath(full, root),
                "frontmatter": fm, "has_frontmatter": has_fm,
                "name": fm.get("name"), "title": h1.group(1).strip() if h1 else None,
                "wikilinks": wl, "mdlinks": ml,
            }
    return notes


def build_index(notes):
    idx = {}
    for path, n in notes.items():
        for ident in filter(None, [n["stem"], n["name"]]):
            idx.setdefault(norm(ident), path)
    full = {}
    for path, n in notes.items():
        full[norm(n["rel"][:-3].replace("\\", "/"))] = path
    return idx, full


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=None)
    ap.add_argument("--config", default=None, help="path to curador.json (auto-detected if omitted)")
    ap.add_argument("--index", default=None)
    ap.add_argument("--profile", default="auto", choices=["memory", "vault", "auto"])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--summary", action="store_true",
                    help="print only the final summary line (no section details)")
    ap.add_argument("--snapshot", default=None,
                    help=".jsonl file: appends one metrics line per run for growth tracking")
    args = ap.parse_args()

    # Config file fills missing args
    cfg = load_config(args.config)
    if not args.path:
        args.path = os.path.expanduser(cfg.get("memory") or cfg.get("vault") or "")
    if not args.snapshot and cfg.get("snapshot"):
        args.snapshot = os.path.expanduser(cfg["snapshot"])

    if not args.path:
        print("ERROR: --path required (or set 'memory'/'vault' in curador.json)", file=sys.stderr)
        sys.exit(2)

    root = os.path.abspath(args.path)
    if not os.path.isdir(root):
        print(f"ERROR: folder not found: {root}", file=sys.stderr)
        sys.exit(2)

    profile = args.profile
    if profile == "auto":
        if os.path.isdir(os.path.join(root, ".obsidian")):
            profile = "vault"
        elif os.path.exists(os.path.join(root, "MEMORY.md")):
            profile = "memory"
        else:
            profile = "vault"

    index_name = args.index
    if not index_name:
        prefer = ("Home.md", "MEMORY.md") if profile == "vault" else ("MEMORY.md", "Home.md")
        for cand in prefer:
            if os.path.exists(os.path.join(root, cand)):
                index_name = cand
                break
    index_path = os.path.join(root, index_name) if index_name and os.path.exists(os.path.join(root, index_name)) else None

    notes = collect_notes(root)
    idx, full_idx = build_index(notes)

    incoming = {p: set() for p in notes}
    broken, near, external, asset_refs = [], [], [], []

    for path, n in notes.items():
        for t in n["wikilinks"]:
            base = link_basename(t)
            full_key = norm(t.strip().rstrip("\\").replace("\\", "/"))
            dest = full_idx.get(full_key) or idx.get(norm(base))
            if dest is not None:
                if dest != path:
                    incoming[dest].add(path)
                    if base != notes[dest]["stem"]:
                        near.append((n["rel"], base, notes[dest]["rel"]))
            elif ASSET_RE.search(base):
                asset_refs.append((n["rel"], t))
            elif profile == "memory" and is_external(t):
                external.append((n["rel"], t))
            elif profile == "vault" and MEMORY_SLUG_RE.match(base):
                external.append((n["rel"], t))
            else:
                broken.append((n["rel"], t))
        for t in n["mdlinks"]:
            nt = norm(link_basename(t))
            if nt in idx:
                dest = idx[nt]
                if dest != path:
                    incoming[dest].add(path)
            else:
                broken.append((n["rel"], t))

    orphans, weak = [], []
    for path, n in notes.items():
        if path == index_path:
            continue
        inc = incoming[path]
        out = len(n["wikilinks"]) + len(n["mdlinks"])
        inc_non_index = {p for p in inc if p != index_path}
        if not inc:
            orphans.append(n["rel"])
        elif not inc_non_index and out == 0:
            weak.append(n["rel"])

    index_dups = []
    if index_path and profile == "memory":
        with open(index_path, "r", encoding="utf-8") as f:
            itext = strip_code(f.read())
        refs = [link_basename(x) for x in MDLINK_RE.findall(itext)]
        refs += [link_basename(w) for w in WIKILINK_RE.findall(itext)
                 if profile == "vault" or not is_external(w)]
        counts = {}
        for r in refs:
            counts[norm(r)] = counts.get(norm(r), 0) + 1
        index_dups = [(k, c) for k, c in counts.items() if c > 1]

    fm_issues, name_mismatch, vault_hygiene = [], [], []
    key_freq = {}
    for path, n in notes.items():
        if path == index_path:
            continue
        for k in n["frontmatter"]:
            key_freq[k] = key_freq.get(k, 0) + 1
        if profile == "memory":
            fm = n["frontmatter"]
            if not n["has_frontmatter"]:
                fm_issues.append((n["rel"], "no frontmatter"))
                continue
            if not fm.get("name"):
                fm_issues.append((n["rel"], "missing name"))
            if not fm.get("description"):
                fm_issues.append((n["rel"], "missing description"))
            if not (fm.get("metadata.type") or fm.get("type")):
                fm_issues.append((n["rel"], "missing metadata.type"))
            if fm.get("name") and fm["name"] != n["stem"]:
                name_mismatch.append((n["rel"], fm["name"], n["stem"]))
        else:
            fm = n["frontmatter"]
            if not n["has_frontmatter"]:
                vault_hygiene.append((n["rel"], "no frontmatter"))
            else:
                if not fm.get("updated"):
                    vault_hygiene.append((n["rel"], "missing updated"))
                if not fm.get("tags"):
                    vault_hygiene.append((n["rel"], "missing tags"))

    n_notes = len([p for p in notes if p != index_path]) or 1
    inconsistent_keys = [(k, c) for k, c in key_freq.items() if 0 < c < n_notes and "." in k]

    sigs = {}
    for path, n in notes.items():
        if path == index_path:
            continue
        if profile == "memory":
            src = (n["frontmatter"].get("description") or "") + " " + n["stem"].replace("_", " ")
        else:
            src = (n["title"] or n["stem"]) + " " + n["stem"].replace("-", " ")
        sigs[path] = tokenize(src)
    content_dupes = []
    paths = list(sigs)
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            sim = jaccard(sigs[paths[i]], sigs[paths[j]])
            if sim >= 0.6:
                content_dupes.append((notes[paths[i]]["rel"], notes[paths[j]]["rel"], round(sim, 2)))
    content_dupes.sort(key=lambda x: -x[2])

    size_warn = []
    if index_path:
        ilines = sum(1 for _ in open(index_path, encoding="utf-8"))
        if ilines > 120:
            size_warn.append((os.path.basename(index_path), f"index has {ilines} lines (consider grouping/archiving)"))
    for path, n in notes.items():
        if path == index_path:
            continue
        try:
            kb = os.path.getsize(path) / 1024
        except OSError:
            continue
        if kb > 12:
            size_warn.append((n["rel"], f"{kb:.0f} KB (large note; consider splitting)"))

    total = (len(orphans) + len(broken) + len(near) + len(index_dups)
             + len(name_mismatch) + len(fm_issues))
    total_links = sum(len(v) for v in incoming.values())
    density = round(total_links / n_notes, 2)
    extra = f"{len(external)} vault refs   |   " if profile == "memory" else f"{len(vault_hygiene)} hygiene   |   "

    if not args.summary:
        def section(title, items, render):
            print(f"\n## {title}  ({len(items)})")
            if not items:
                print("  ok - nothing found")
                return
            for it in items:
                print("  - " + render(it))

        print("=" * 60)
        print(f"CURADOR AUDIT  |  profile: {profile}")
        print(f"folder: {root}")
        print(f"index: {os.path.basename(index_path) if index_path else '(none)'}")
        print(f"notes (.md): {len(notes)}")
        print("=" * 60)

        section("ORPHANS (no incoming links)", orphans, lambda x: x)
        section("WEAKLY CONNECTED (only index points here)", weak, lambda x: x)
        section("BROKEN LINKS", broken, lambda x: f"{x[0]}  ->  {x[1]}")
        section("SEPARATOR/CASE MISMATCH (auto-fixable)", near,
                lambda x: f"{x[0]}  ->  [[{x[1]}]]  should be  {x[2]}")
        section("CROSS-SYSTEM REFERENCES", external, lambda x: f"{x[0]}  ->  [[{x[1]}]]")
        section("ASSET EMBEDS", asset_refs, lambda x: f"{x[0]}  ->  {x[1]}")
        section("INDEX DUPLICATES", index_dups, lambda x: f"{x[0]}  appears {x[1]}x")
        section("NAME != FILENAME", name_mismatch, lambda x: f"{x[0]}  (name: {x[1]})")
        section("FRONTMATTER ISSUES", fm_issues, lambda x: f"{x[0]}  ->  {x[1]}")
        section("INCONSISTENT KEYS", inconsistent_keys, lambda x: f"{x[0]}  in {x[1]}/{n_notes} notes")
        section("POSSIBLE CONTENT DUPLICATES (de-bloat)",
                content_dupes, lambda x: f"{x[0]}  ~  {x[1]}  (sim {x[2]})")
        section("SIZE WARNINGS", size_warn, lambda x: f"{x[0]}  ->  {x[1]}")
        if profile == "vault":
            section("VAULT HYGIENE (non-critical)",
                    vault_hygiene, lambda x: f"{x[0]}  ->  {x[1]}")

    print("\n" + "=" * 60)
    print(f"CRITICAL: {total}   |   {extra}{len(weak)} weak")
    print(f"graph: {n_notes} notes | density {density} links/note | {len(content_dupes)} similar pairs")
    print("=" * 60)

    if args.snapshot:
        import datetime
        row = {
            "date": datetime.date.today().isoformat(), "profile": profile,
            "notes": n_notes, "orphans": len(orphans), "weak": len(weak),
            "broken": len(broken), "separator": len(near), "dupes": len(content_dupes),
            "density": density, "critical": total,
        }
        try:
            with open(args.snapshot, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"snapshot appended to {args.snapshot}")
        except OSError as e:
            print(f"[warning] could not write snapshot: {e}", file=sys.stderr)

    if args.json:
        payload = {
            "profile": profile, "root": root, "note_count": len(notes),
            "orphans": orphans, "weak": weak, "broken_links": broken,
            "separator_mismatch": near, "vault_refs": external, "asset_refs": asset_refs,
            "index_duplicates": index_dups, "name_mismatch": name_mismatch,
            "frontmatter_issues": fm_issues, "inconsistent_keys": inconsistent_keys,
            "vault_hygiene": vault_hygiene, "content_dupes": content_dupes,
            "size_warnings": size_warn, "graph_density": density, "total_critical": total,
        }
        print("<<<JSON>>>")
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
