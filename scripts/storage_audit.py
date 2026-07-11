#!/usr/bin/env python3
"""Curador - storage/binary audit.

audit_kb.py only ever reads .md files. But in a real vault the .md notes are a sliver of
the weight — this base is 557 MB across 326 notes, and every one of those megabytes is a
PDF, image or video that the note-level audit never looks at. This script is the binary
counterpart: exact duplicates, near-duplicate versions left over from re-exports, malformed
filenames, files that broke the Entregaveis/ convention, and assets nobody catalogued.

Radar only, same as audit_kb.py's de-bloat/split findings: it NEVER deletes, renames or
moves a file. The vault has no git history — OneDrive is the only safety net — so any
destructive action is a judgement call for Claude to make with the user, never a script.

Deterministic, zero external dependencies. Cross-platform (Windows/macOS/Linux).

Usage:
    python storage_audit.py --vault "<vault folder>" [--project "Nome"]
                             [--min-size-mb N] [--snapshot growth_log.jsonl] [--json]
    python storage_audit.py --config curador.json --project "Nome"
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import unicodedata

BINARY_EXT = re.compile(
    r"\.(pdf|docx?|pptx?|xlsx?|docm|pptm|xlsm|png|jpe?g|gif|svg|webp|bmp|mp4|mov|webm|"
    r"mp3|wav|zip|rar|7z|eps|psd)$", re.I)

# Files above this size are still counted and pattern-checked, but not hashed (a 200 MB+
# teaser video hashing on every run is wasted I/O for a check whose real targets are the
# handful-of-MB PDFs/pptx that actually appear twice in this base).
HASH_CAP_MB = 100
CHUNK = 1024 * 1024

ENTREGAVEIS_NAMES = {"entregáveis", "entregaveis"}
NON_SCAN_DIRS = {".git", ".obsidian", ".trash", "node_modules", "memory"}

# Strips the trailing marker a re-export/re-download leaves behind, to compare the
# "real" name: "report (1).pdf" / "report-1.pdf" / "Copia de report.pdf" all normalize
# to the same key as "report.pdf".
COPY_SUFFIX_RE = re.compile(r"\s*(\(\d+\)|-\d+)$")
COPY_PREFIX_RE = re.compile(r"^(c[oó]pia de |copy of )", re.I)

# "G4 Arquitetura de Receita.pdf.pdf" — same extension twice, a copy/rename artifact.
DOUBLE_EXT_RE = re.compile(r"\.([A-Za-z0-9]{2,5})\.\1$", re.I)


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


def sha256_of(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(CHUNK)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def normalize_stem(stem):
    s = COPY_SUFFIX_RE.sub("", stem.strip())
    s = COPY_PREFIX_RE.sub("", s)
    return s.strip().lower()


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def word_tokens(s):
    return set(re.findall(r"[a-z0-9]{3,}", strip_accents(s.lower())))


def collect_binaries(root):
    """Binaries + a per-folder index of .md text (uncatalogued-asset check) + a
    per-folder list of subdirectory names (convention check)."""
    binaries = []
    md_text_by_dir = {}
    subdirs_by_dir = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d.lower() not in NON_SCAN_DIRS]
        subdirs_by_dir[dirpath] = list(dirnames)
        md_blob = []
        for fn in filenames:
            if fn.lower().endswith(".md"):
                try:
                    with open(os.path.join(dirpath, fn), "r", encoding="utf-8") as f:
                        md_blob.append(f.read().lower())
                except (OSError, UnicodeDecodeError):
                    pass
        if md_blob:
            md_text_by_dir[dirpath] = " ".join(md_blob)
        for fn in filenames:
            if not BINARY_EXT.search(fn):
                continue
            full = os.path.join(dirpath, fn)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            binaries.append({
                "path": full, "dir": dirpath, "name": fn,
                "rel": os.path.relpath(full, root), "size": size,
            })
    return binaries, md_text_by_dir, subdirs_by_dir


def catalog_dirs_for(binary_dir, root):
    """Which directories should be searched for a companion .md.

    The vault convention deliberately SEPARATES .md and PDF into different folders
    ('.md na raiz da subpasta; PDFs em Entregaveis/ dentro da mesma subpasta') — so a
    binary inside an Entregaveis/ folder will NEVER find a sibling .md in its own
    directory, only in the topic folder one or more levels up (the first ancestor
    that is not itself an Entregaveis/ segment). For a binary NOT inside Entregaveis/,
    its own directory is the right place to look."""
    rel = os.path.relpath(binary_dir, root)
    if rel == ".":
        return [binary_dir]
    parts = rel.split(os.sep)
    for i, p in enumerate(parts):
        if p.strip().lower() in ENTREGAVEIS_NAMES:
            ancestor = os.path.join(root, *parts[:i]) if parts[:i] else root
            return [binary_dir, ancestor]
    return [binary_dir]


def find_exact_duplicates(binaries):
    by_hash = {}
    for b in binaries:
        if b["size"] > HASH_CAP_MB * 1024 * 1024:
            continue
        if b["size"] == 0:
            continue
        digest = sha256_of(b["path"])
        if digest:
            by_hash.setdefault(digest, []).append(b["rel"])
    return [(h, paths) for h, paths in by_hash.items() if len(paths) >= 2]


def find_near_duplicates(binaries):
    groups = {}
    for b in binaries:
        stem, ext = os.path.splitext(b["name"])
        key = (b["dir"], normalize_stem(stem), ext.lower())
        groups.setdefault(key, []).append(b["rel"])
    return [(k[1] + k[2], paths) for k, paths in groups.items() if len(paths) >= 2]


def find_malformed(binaries):
    return [b["rel"] for b in binaries if DOUBLE_EXT_RE.search(b["name"])]


def find_convention_violations(binaries, subdirs_by_dir):
    """NOT 'is this binary outside Entregaveis somewhere' — that fires on every
    reference PDF ever downloaded into a Conhecimento/Pesquisas folder, which was
    never claimed to need Entregaveis (that convention is for OUR OWN deliverables,
    not source material). The real, narrow bug this catches: a file sitting loose
    directly at the ROOT of an Entregaveis/ folder that ALSO has real subfolders —
    e.g. Milagro/Entregaveis/*.pptx sitting beside Documentos Legais/, Exportacao/,
    Marketing/, Scripts/ instead of being filed into one of them."""
    out = []
    for b in binaries:
        base = os.path.basename(b["dir"]).strip().lower()
        if base in ENTREGAVEIS_NAMES and subdirs_by_dir.get(b["dir"]):
            out.append(b["rel"])
    return out


def find_uncatalogued(binaries, md_text_by_dir, root):
    """A deliverable with no companion .md describing it anywhere nearby. 'Nearby' =
    its own folder, or (for anything inside Entregaveis/) the topic folder one level
    up too — see catalog_dirs_for. Reference material (a Pesquisas/ folder of
    downloaded papers with zero .md files anywhere close) legitimately has no catalog
    and is correctly not held to this — the check only fires when a catalog dir has
    SOME .md content that doesn't seem to describe this specific file.

    Word-overlap, NOT exact filename match: a real cataloged example in this base
    (Gestao de Terras Piaui/.../Alta Mira.md) lists 'Carta de anuencia' as prose, never
    spelling out the literal filename 'CARTA DE ANUENCIA ALTA MIRA.pdf'. Matching only
    exact substrings flagged 244/336 files as uncatalogued, including this one — a
    textbook-correct catalog entry. Majority of the filename's own words appearing
    somewhere in the blob is what actually distinguishes a described asset."""
    out = []
    for b in binaries:
        dirs = catalog_dirs_for(b["dir"], root)
        blob = " ".join(md_text_by_dir.get(d, "") for d in dirs)
        if not blob:
            continue  # no .md anywhere nearby at all — not this project's convention
        stem_tokens = word_tokens(os.path.splitext(b["name"])[0])
        if not stem_tokens:
            continue
        blob_tokens = word_tokens(blob)
        overlap = len(stem_tokens & blob_tokens) / len(stem_tokens)
        if overlap < 0.5:
            out.append(b["rel"])
    return out


def size_summary(binaries):
    by_ext = {}
    total = 0
    for b in binaries:
        ext = os.path.splitext(b["name"])[1].lower().lstrip(".")
        d = by_ext.setdefault(ext, {"count": 0, "mb": 0.0})
        d["count"] += 1
        d["mb"] += b["size"] / (1024 * 1024)
        total += b["size"]
    for d in by_ext.values():
        d["mb"] = round(d["mb"], 1)
    return total / (1024 * 1024), by_ext


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=None)
    ap.add_argument("--config", default=None, help="path to curador.json (auto-detected if omitted)")
    ap.add_argument("--project", default=None,
                    help="scope to <vault>/<project> instead of the whole vault")
    ap.add_argument("--min-size-mb", type=float, default=0,
                    help="only list files >= this size in the size summary detail (default: all)")
    ap.add_argument("--snapshot", default=None,
                    help=".jsonl file: appends one storage-metrics line per run (same log audit_kb.py uses)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--summary", action="store_true", help="print only the final summary line")
    args = ap.parse_args()

    cfg = load_config(args.config)
    vault = args.vault or os.path.expanduser(cfg.get("vault") or "")
    if not vault:
        print("ERROR: --vault required (or set 'vault' in curador.json)", file=sys.stderr)
        sys.exit(2)
    if not args.snapshot and cfg.get("snapshot"):
        args.snapshot = os.path.expanduser(cfg["snapshot"])

    root = os.path.abspath(os.path.expanduser(vault))
    if args.project:
        root = os.path.join(root, args.project)
    if not os.path.isdir(root):
        print(f"ERROR: folder not found: {root}", file=sys.stderr)
        sys.exit(2)

    binaries, md_text_by_dir, subdirs_by_dir = collect_binaries(root)
    exact = find_exact_duplicates(binaries)
    near = find_near_duplicates(binaries)
    malformed = find_malformed(binaries)
    convention = find_convention_violations(binaries, subdirs_by_dir)
    uncatalogued = find_uncatalogued(binaries, md_text_by_dir, root)
    total_mb, by_ext = size_summary(binaries)

    if not args.summary:
        def section(title, items, render):
            print(f"\n## {title}  ({len(items)})")
            if not items:
                print("  ok - nothing found")
                return
            for it in items:
                print("  - " + render(it))

        print("=" * 60)
        print("STORAGE AUDIT")
        print(f"folder: {root}")
        print(f"binaries: {len(binaries)}  |  total: {total_mb:.1f} MB")
        print("=" * 60)

        print(f"\n## SIZE BY EXTENSION")
        for ext, d in sorted(by_ext.items(), key=lambda kv: -kv[1]["mb"]):
            if d["mb"] < args.min_size_mb:
                continue
            print(f"  - .{ext}: {d['count']} files, {d['mb']} MB")

        section("EXACT DUPLICATE (identical content, byte-for-byte)", exact,
                 lambda x: f"{x[0][:10]}...  ->  " + "  ==  ".join(x[1]))
        section("NEAR-DUPLICATE NAME (same folder, name differs only by a copy/version marker)",
                near, lambda x: f"{x[0]}  ->  " + "  ~  ".join(x[1]))
        section("MALFORMED FILENAME (doubled extension)", malformed, lambda x: x)
        section("CONVENTION VIOLATION (loose at the root of an Entregaveis/ that has subfolders)",
                 convention, lambda x: x)
        section("UNCATALOGUED ASSET (no .md nearby mentions this file)", uncatalogued, lambda x: x)

    total_findings = len(exact) + len(near) + len(malformed) + len(convention) + len(uncatalogued)
    print("\n" + "=" * 60)
    print(f"STORAGE FINDINGS: {total_findings}   |   {len(binaries)} binaries   |   {total_mb:.1f} MB total")
    print("=" * 60)

    if args.snapshot:
        row = {
            "date": datetime.date.today().isoformat(), "profile": "storage",
            "scope": args.project or "(whole vault)",
            "binaries": len(binaries), "total_mb": round(total_mb, 1),
            "exact_dupes": len(exact), "near_dupes": len(near),
            "malformed": len(malformed), "convention_violations": len(convention),
            "uncatalogued": len(uncatalogued),
        }
        try:
            with open(args.snapshot, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"snapshot appended to {args.snapshot}")
        except OSError as e:
            print(f"[warning] could not write snapshot: {e}", file=sys.stderr)

    if args.json:
        payload = {
            "root": root, "binary_count": len(binaries), "total_mb": round(total_mb, 1),
            "size_by_extension": by_ext,
            "exact_duplicates": exact, "near_duplicates": near,
            "malformed_filenames": malformed, "convention_violations": convention,
            "uncatalogued_assets": uncatalogued, "total_findings": total_findings,
        }
        print("<<<JSON>>>")
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
