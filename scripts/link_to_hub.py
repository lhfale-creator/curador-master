#!/usr/bin/env python3
"""
link_to_hub.py — Connect weakly/orphaned notes to their project hub.

For every note inside a project folder that does NOT already link to its
nearest hub, insert a `→ [[Hub]]` backlink right after the frontmatter.
This is the mechanical fix for "weakly connected" / orphan sub-notes the
audit flags: it guarantees every note is reachable from its project hub,
which is reachable from Home/MEMORY.

"Nearest hub": walk up from the note's folder to the project root; the hub
is the first ancestor folder F that contains F.md (e.g. a Caltim/ note links
[[Caltim]], a Conhecimento/Dev/ note links the project hub). Falls back to
the project-root hub, with an exceptions map for odd hub filenames.

Idempotent + dry-run by default. Never touches Memory/ (the auto mirror),
.obsidian, _Arquivo, or the hub notes themselves.

Usage:
  python link_to_hub.py --vault "<vault>" [--write]
"""
import argparse
import os
import re

SKIP_DIRS = {".obsidian", "_Arquivo", "Memory", ".trash"}
# folders whose hub note isn't "<Folder>.md"
HUB_EXCEPTIONS = {"EUA 2027": "EUA-2027-Portfolio"}


def has_link_to(text, hub_stem):
    pat = r'\[\[([^\]]*/)?' + re.escape(hub_stem) + r'(\s*\|[^\]]*)?\]\]'
    return re.search(pat, text) is not None


def insert_backlink(text, hub_stem):
    line = f"\n→ [[{hub_stem}]]\n"
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            nl = text.find("\n", end + 1)
            nl = nl if nl != -1 else len(text)
            return text[:nl + 1] + line + text[nl + 1:]
    return line.lstrip("\n") + "\n" + text


def project_hubs(vault):
    """Map each project folder -> hub_stem, ONLY for folders with a resolvable
    hub note (<Folder>.md or an exception). Folders without a hub are skipped
    so we never link to a non-existent hub (e.g. a transient inbox folder)."""
    hubs, skipped = {}, []
    for entry in os.listdir(vault):
        p = os.path.join(vault, entry)
        if not os.path.isdir(p) or entry in SKIP_DIRS:
            continue
        stem = HUB_EXCEPTIONS.get(entry, entry)
        if os.path.exists(os.path.join(p, stem + ".md")):
            hubs[p] = stem
        else:
            skipped.append(entry)
    if skipped:
        print(f"  (skipped folders with no hub note: {', '.join(skipped)})")
    return hubs


def nearest_hub(note_path, project_root, project_hub_stem):
    d = os.path.dirname(note_path)
    while True:
        folder = os.path.basename(d)
        if os.path.exists(os.path.join(d, folder + ".md")):
            return folder
        if os.path.normpath(d) == os.path.normpath(project_root):
            return project_hub_stem
        parent = os.path.dirname(d)
        if parent == d:
            return project_hub_stem
        d = parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=r"C:\Users\alexa\OneDrive\Documentos\Obsidian Vault")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    plan = []
    for project_root, hub_stem in project_hubs(args.vault).items():
        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if not f.endswith(".md"):
                    continue
                note = os.path.join(root, f)
                hub = nearest_hub(note, project_root, hub_stem)
                if f[:-3] == hub:           # the hub note itself
                    continue
                with open(note, encoding="utf-8") as fh:
                    text = fh.read()
                if has_link_to(text, hub):
                    continue
                rel = os.path.relpath(note, args.vault)
                plan.append((rel, hub))
                if args.write:
                    with open(note, "w", encoding="utf-8") as fh:
                        fh.write(insert_backlink(text, hub))

    verb = "WROTE" if args.write else "PLAN (dry-run)"
    print(f"== link_to_hub {verb} — {len(plan)} notes ==")
    for rel, hub in plan:
        print(f"  {rel}  ->  [[{hub}]]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
