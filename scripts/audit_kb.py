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
import datetime
import json
import os
import re
import sys

# Windows consoles/redirects often default to cp1252 (or another legacy codepage), which
# crashes on NFD-decomposed accents (e.g. a lone combining acute from a Mac-authored
# filename) even though every file is read/written as UTF-8. Force UTF-8 out so a vault
# note or filename with any Unicode content never takes the whole audit down.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

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

# The `Memory/` folder inside the vault is the MIRROR that sync-cerebro owns and
# regenerates. Per the shared contract (SKILL.md > "The contract"), the curador must
# NOT audit it for de-bloat/orphans: every mirrored note legitimately restates the
# vault note it came from, which produced a flood of false "duplicates".
MIRROR_PREFIX = "memory/"

# A note whose `updated`/`atualizado` is this old is suspect when it describes CURRENT
# state (architecture, status, integrations). Stale state-docs are more dangerous than
# duplicates: they actively mislead whoever reads them next.
DEFAULT_STALE_DAYS = 120
DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")

# CODE DRIFT. Date-staleness is a weak proxy: a note 24 days old can already describe a
# module that was deleted last week. The hard signal is a note naming a source file that
# no longer exists on disk. This is the check that would have caught the architecture notes
# still documenting `engine/pix.mjs` + `engine/mercadopago.mjs` months after they were
# removed — the exact stale doc that led an audit to report a bug in dead code.
CODE_PATH_RE = re.compile(
    r"(?<![\w/-])((?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.(?:mjs|jsx?|tsx?|py|sql))(?![\w/])"
)

# A line that says a file WAS DELETED, or WILL BE CREATED, is not drift — it is the note
# doing its job. Without this, a correct tombstone ("engine/pix.mjs foi deletado") gets
# flagged as a lie, and the check trains people to ignore it.
NOT_DRIFT_RE = re.compile(
    r"delet|remov|exclu|apagad|extint|substitu|legad|descontinuad|"
    r"n[aã]o existe|j[aá] n[aã]o|no longer|deprecat|"
    r"~~|"                                     # strikethrough
    r"\bcriar\b|\bnovo\b|\bnova\b|\bpropost|a construir",
    re.I,
)

# SPLIT CANDIDATES. The mirror image of the de-bloat/merge check above: instead of two
# notes that should become one, this looks for one note that should become several.
#   - GRAB-BAG: total absence of headers on a large note (e.g. a 76 KB FAQ mixing product
#     genetics, herbicide compatibility and pasture management as one wall of text).
#   - GROWING LOG: headers are mostly dated entries stacked over time (a changelog that
#     never gets archived) — not a topic mix, so the fix is periodic archiving, not a split.
# Everything else is a generic SIZE WARNING, not a confident GRAB-BAG claim. An earlier cut
# tried to detect "unrelated headers glued together" via low word-overlap between headers
# (Jaccard on header tokens) — checked against a real project (Professor Pastagem) where a
# prior recon had already read every note by hand: notes independently confirmed COHERENT
# (single topic, just many descriptive subheadings) scored LOWER diversity (0.011-0.089)
# than the one genuine grab-bag in that same recon (0.018). Portuguese prose subheadings on
# ONE topic rarely repeat exact words, so low header-overlap doesn't distinguish "many facets
# of one thing" from "unrelated things glued together" — it flagged most of a project's
# well-organized long notes as grab-bags. Removed rather than shipped mislabeled; no-headers
# and dated-headers are both confirmed-reliable signals, so those stay.
HEADER_RE = re.compile(r"^#{2,3}\s+(.+)$", re.MULTILINE)
# (?<!\d) / (?!\d) so a 3+ digit run isn't torn into a fake match: "47/180" (a freq
# ratio) would otherwise match "47/18" (the \d{1,2} caps just stop early inside "180").
# Real bug this caused: "freq: 47/180 = 26%" section headers in a reference note got
# read as 26% dated, flipping it into a false GROWING LOG.
DATE_TOKEN_RE = re.compile(r"(?<!\d)\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?(?!\d)")
SPLIT_SIZE_KB = 12  # same threshold the size-warning check already used


def has_duplicate_frontmatter(text):
    """Two stacked '---' blocks (a copy/paste artifact) — the 2nd block silently shadows
    or gets ignored, and a reader/parser only sees the first. Real bug this caught: a note
    with frontmatter on lines 1-4 and a second orphaned block on lines 7-10."""
    if not text.startswith("---"):
        return False
    first_end = text.find("\n---", 3)
    if first_end == -1:
        return False
    rest = text[first_end + 4:].lstrip("\n \t")
    if not rest.startswith("---"):
        return False
    return rest.find("\n---", 3) != -1


# MEMORY SIZE RULES. Already-documented conventions (feedback_memoria_notas_enxutas):
# project_* notes max 15 lines, reference_* notes max 5 lines + pointer. Nobody checked
# this mechanically before; a project note grew to 89 KB of session logs before anyone
# noticed. Body line count excludes frontmatter and blank lines.
MEMORY_SIZE_LIMITS = {"project": 15, "reference": 5}

# DESORGANIZATION RADAR (vault only). 'Entregáveis' is the one folder name that is
# SUPPOSED to repeat at every depth (feedback_estrutura_vault: every deliverable subfolder
# gets its own Entregáveis/) — excluded, or every project would false-positive on it.
ENTREGAVEIS_NAMES = {"entregáveis", "entregaveis"}
NON_PROJECT_DIRS = {".obsidian", ".git", ".trash", "memory", "node_modules"}


def scan_projects(root):
    """Top-level project folders directly under `root`, each with its full file/dir
    listing (all extensions, not just .md — misplacement and cross-project contamination
    care about PDFs/scripts/assets too, not only notes)."""
    projects = {}
    try:
        entries = os.listdir(root)
    except OSError:
        return projects
    for entry in entries:
        full = os.path.join(root, entry)
        # "_"-prefixed top folders (_Arquivo) are archives/meta, not projects — the
        # root-level-file and duplicate-folder expectations don't apply to an archive.
        if not os.path.isdir(full) or entry.lower() in NON_PROJECT_DIRS or entry.startswith("_"):
            continue
        files, dirs = [], []
        for dirpath, dirnames, filenames in os.walk(full):
            dirnames[:] = [d for d in dirnames if d not in (".git", ".obsidian", ".trash", "node_modules")]
            rel_dir = os.path.relpath(dirpath, full)
            for d in dirnames:
                dirs.append(d if rel_dir == "." else os.path.normpath(os.path.join(rel_dir, d)))
            for fn in filenames:
                files.append(fn if rel_dir == "." else os.path.normpath(os.path.join(rel_dir, fn)))
        projects[entry] = {"files": files, "dirs": dirs}
    return projects


def find_misplacement(projects):
    """Three mechanical desorganization signals, radar only (Claude decides the move):
    1. same subfolder name at DIFFERENT depths inside one project (a topic living in
       two homes). Same-depth repeats are NOT flagged: checked against every duplicate
       group this vault actually had, all 7 same-depth groups were parallel BY DESIGN —
       the Conhecimento/X + Entregaveis/X topic mirror (the documented convention) and
       per-entity folders repeating the same substructure (Personagens/<Nome>/cenas).
       The one real bug (Produto-MVP at project root AND under Conhecimento/) was the
       only group whose occurrences sat at different depths.
    2. loose files at a project root when the project otherwise organizes into subfolders
       (excludes the project's own hub note, e.g. 'Milagro.md' at the root of Milagro/).
    3. a file whose path mentions ANOTHER top-level project's name (cross-contamination)."""
    dup_folder, root_orphan, cross_project = [], [], []
    names = list(projects.keys())
    for pname, info in projects.items():
        by_base = {}
        for d in info["dirs"]:
            base = os.path.basename(d).strip().lower()
            if base in ENTREGAVEIS_NAMES:
                continue
            by_base.setdefault(base, []).append(d)
        for base, paths in by_base.items():
            depths = {p.replace("\\", "/").count("/") for p in paths}
            if len(paths) >= 2 and len(depths) >= 2:
                dup_folder.append((pname, base, paths))

        if info["dirs"]:
            hub = pname.strip().lower()
            for f in info["files"]:
                if os.path.dirname(f) not in ("", "."):
                    continue
                stem = os.path.splitext(os.path.basename(f))[0].strip().lower()
                if stem == hub:
                    continue
                root_orphan.append((pname, f))

        norm_pname = re.sub(r"[\s_&-]+", " ", pname).strip().lower()
        for other in names:
            if other == pname:
                continue
            norm_other = re.sub(r"[\s_&-]+", " ", other).strip().lower()
            if len(norm_other) < 5:
                continue
            # Project-name containment is not contamination: every file inside
            # "Marca Pessoal Nathalya" trivially mentions the project "Marca Pessoal".
            if norm_other in norm_pname or norm_pname in norm_other:
                continue
            pat = re.compile(r"\b" + re.escape(norm_other) + r"\b", re.I)
            seen_dirs = set()
            for f in info["files"]:
                norm_f = re.sub(r"[\s_&.-]+", " ", f).lower()
                if not pat.search(norm_f):
                    continue
                # When the match comes from a DIRECTORY segment, report that folder
                # once — not one finding per file inside it. A subfolder named after
                # another project (e.g. Nathalya's "Content Hub/", where that project
                # was born) is ONE decision to make, not sixteen.
                parts = re.split(r"[\\/]", f)
                dir_hit = None
                for i, seg in enumerate(parts[:-1]):
                    if pat.search(re.sub(r"[\s_&.-]+", " ", seg).lower()):
                        dir_hit = "\\".join(parts[:i + 1])
                        break
                if dir_hit:
                    if dir_hit not in seen_dirs:
                        seen_dirs.add(dir_hit)
                        cross_project.append((pname, dir_hit + "\\*", other))
                else:
                    cross_project.append((pname, f, other))
    return dup_folder, root_orphan, cross_project


def extract_code_refs(raw):
    """Source-file paths named by a note.

    Skips URLs. Skips refs whose surrounding context frames the file as deleted (a
    tombstone) or as yet-to-be-created (a proposal) — otherwise a note correctly saying
    "engine/pix.mjs foi deletado" is reported as a lie, and people learn to ignore the check.

    The context is a ±1-line window, not the line itself: prose wraps ("...meses depois de
    eles serem\\ndeletados") and lists put the marker on the line above ("Removidos:\\n- x.mjs").
    """
    refs = set()
    lines = raw.splitlines()
    for i, line in enumerate(lines):
        window = " ".join(lines[max(0, i - 1):i + 2])
        if NOT_DRIFT_RE.search(window):
            continue
        for m in CODE_PATH_RE.finditer(line):
            start = max(0, m.start() - 10)
            if "://" in line[start:m.start()]:
                continue
            refs.add(m.group(1))
    return refs


def in_mirror(rel):
    return rel.replace("\\", "/").lower().startswith(MIRROR_PREFIX)


# A note that DECLARES itself historical is allowed to describe the past — that is what an
# archive is for. Drift only matters in notes that claim to describe the CURRENT system.
HISTORICAL_RE = re.compile(r"hist[oó]ric|arquivad|archived|obsolet|deprecat|superad|legad", re.I)


def is_historical(fields):
    blob = " ".join(str(fields.get(k) or "") for k in ("status", "tags", "type"))
    return bool(HISTORICAL_RE.search(blob))


def parse_date(fields):
    """Reads `updated` or the pt-BR `atualizado`. Returns date or None."""
    for key in ("updated", "atualizado"):
        m = DATE_RE.search(str(fields.get(key) or ""))
        if m:
            try:
                return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass
    return None


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
        stripped = line.strip()
        # YAML dash-list item under the current top-level key. Without this, a note
        # using the block form (tags:\n  - projeto\n  - agro) reads as tags == None
        # and gets flagged "missing tags" — a real false positive this base hit
        # (AGROHAP.md, tags present in dash-list form, reported missing for weeks).
        dm = re.match(r"^-\s+(.+)$", stripped)
        if dm and parent:
            item = dm.group(1).strip().strip('"').strip("'")
            fields[parent] = f"{fields[parent]}, {item}" if fields.get(parent) else item
            continue
        m = re.match(r"^([\w.-]+)\s*:\s*(.*)$", stripped)
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


def extract_aliases(text):
    """Frontmatter `aliases:` values — inline list ([a, b]) or YAML dash-list.

    Obsidian OFFICIALLY resolves [[wikilinks]] by filename OR by an `aliases:` entry
    (help.obsidian.md > Properties, Aliases) — it is the documented safety net when a
    note is renamed (`conventions.md` prescribes exactly that). parse_frontmatter()
    above only captures `key: value` scalars, so alias lists were invisible to the
    audit and every legitimate alias link was reported as BROKEN."""
    if not text.startswith("---"):
        return []
    end = text.find("\n---", 3)
    if end == -1:
        return []
    aliases = []
    in_alias_block = False
    for line in text[3:end].splitlines():
        stripped = line.strip()
        m = re.match(r"^alias(?:es)?\s*:\s*(.*)$", stripped)
        if m:
            val = m.group(1).strip()
            if val.startswith("[") and val.endswith("]"):
                aliases += [a.strip().strip('"').strip("'") for a in val[1:-1].split(",")]
            in_alias_block = (val == "")
            continue
        if in_alias_block:
            dm = re.match(r"^-\s+(.+)$", stripped)
            if dm:
                aliases.append(dm.group(1).strip().strip('"').strip("'"))
            elif stripped and not stripped.startswith("-"):
                in_alias_block = False
    return [a for a in aliases if a]


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
            # Body WITHOUT frontmatter — the real content signature for de-bloat.
            prose = body
            if has_fm:
                end = prose.find("\n---", 3)
                if end != -1:
                    prose = prose[end + 4:]
            notes[full] = {
                "path": full, "stem": stem, "rel": os.path.relpath(full, root),
                "frontmatter": fm, "has_frontmatter": has_fm,
                "name": fm.get("name"), "title": h1.group(1).strip() if h1 else None,
                "wikilinks": wl, "mdlinks": ml,
                "body_tokens": tokenize(prose[:6000]),
                "updated": parse_date(fm),
                # from RAW text: strip_code() would have eaten the backticked paths
                "code_refs": extract_code_refs(text),
                "headers": HEADER_RE.findall(prose),
                "body_line_count": len([l for l in prose.strip().splitlines() if l.strip()]),
                "dup_frontmatter": has_duplicate_frontmatter(text),
                "aliases": extract_aliases(text),
            }
    return notes


def build_index(notes):
    # stem first, then name:, then aliases — a file's own stem always wins a
    # collision with another file's alias (setdefault keeps the first claim).
    idx = {}
    for path, n in notes.items():
        idx.setdefault(norm(n["stem"]), path)
    for path, n in notes.items():
        for ident in filter(None, [n["name"], *n["aliases"]]):
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
    ap.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS,
                    help=f"flag notes not updated in N days (default {DEFAULT_STALE_DAYS})")
    ap.add_argument("--code-root", default=None,
                    help="comma-separated repo roots: flags notes naming source files that "
                         "no longer exist (code drift). Strongest staleness signal there is.")
    ap.add_argument("--code-scope", default=None,
                    help="only check notes whose path contains this substring "
                         "(e.g. 'Professor Pastagem'). Pair with --code-root.")
    ap.add_argument("--project-scope", default=None,
                    help="alias for --code-scope, for readability in project wrap-up runs: "
                         "filters stale/split-candidate/size-rule/misplacement findings down "
                         "to notes/files whose path contains this substring. Same variable as "
                         "--code-scope (also gates code-drift checking); the two are OR'd.")
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

    def norm_scope(s):
        # Vault paths use spaces/hyphens ("Professor Pastagem", "Produto-MVP"); Claude
        # memory filenames use underscores ("project_professor_pastagem.md"). Without
        # collapsing all three to one separator, "--project-scope 'Professor Pastagem'"
        # never matches its own project's memory notes — caught by re-running this
        # exact case after the first cut only normalized case/slashes, not separators.
        return re.sub(r"[\s_-]+", " ", s.replace("\\", "/").strip().lower())

    global_scope = norm_scope(args.project_scope or args.code_scope or "")

    def scoped(items, keyfn):
        if not global_scope:
            return items
        return [it for it in items if global_scope in norm_scope(keyfn(it))]

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
                    # A link that resolves via an alias is CORRECT Obsidian behavior
                    # (the documented rename safety net), not a separator mismatch —
                    # flagging it would make the fixer rewrite a deliberate alias.
                    is_alias = norm(base) in {norm(a) for a in notes[dest]["aliases"]}
                    if base != notes[dest]["stem"] and not is_alias:
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
        # The Memory/ mirror is regenerated by sync-cerebro and hangs off its own
        # category hubs. Auditing it here double-reports what sync already owns.
        if profile == "vault" and in_mirror(n["rel"]):
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

    fm_issues, name_mismatch, vault_hygiene, size_rule_violations = [], [], [], []
    key_freq = {}
    for path, n in notes.items():
        if path == index_path:
            continue
        for k in n["frontmatter"]:
            key_freq[k] = key_freq.get(k, 0) + 1
        if n["dup_frontmatter"]:
            msg = "duplicate frontmatter block (two stacked '---' blocks)"
            (fm_issues if profile == "memory" else vault_hygiene).append((n["rel"], msg))
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
            slug = MEMORY_SLUG_RE.match(n["stem"])
            if slug:
                kind = slug.group(1).lower()
                limit = MEMORY_SIZE_LIMITS.get(kind)
                if limit and n["body_line_count"] > limit:
                    size_rule_violations.append((n["rel"], kind, n["body_line_count"], limit))
        else:
            fm = n["frontmatter"]
            if not n["has_frontmatter"]:
                vault_hygiene.append((n["rel"], "no frontmatter"))
            else:
                if not fm.get("updated"):
                    vault_hygiene.append((n["rel"], "missing updated"))
                if not fm.get("tags"):
                    vault_hygiene.append((n["rel"], "missing tags"))
    size_rule_violations = scoped(size_rule_violations, lambda x: x[0])

    n_notes = len([p for p in notes if p != index_path]) or 1
    inconsistent_keys = [(k, c) for k, c in key_freq.items() if 0 < c < n_notes and "." in k]

    # De-bloat detection. Title similarity ALONE is not evidence of duplication: a pair of
    # complementary notes ("Arquitetura de Contexto" / "Arquitetura do Projeto") shares most
    # of its title words and none of its content. A real duplicate is similar in BOTH the
    # title and the prose, AND the two notes do not already reference each other (a human who
    # linked A->B has already decided they are distinct). We also skip the Memory/ mirror.
    sigs, bodies = {}, {}
    for path, n in notes.items():
        if path == index_path:
            continue
        if profile == "vault" and in_mirror(n["rel"]):
            continue
        if profile == "memory":
            src = (n["frontmatter"].get("description") or "") + " " + n["stem"].replace("_", " ")
        else:
            src = (n["title"] or n["stem"]) + " " + n["stem"].replace("-", " ")
        sigs[path] = tokenize(src)
        bodies[path] = n["body_tokens"]

    def related(a, b):
        return a in incoming.get(b, set()) or b in incoming.get(a, set())

    content_dupes = []
    paths = list(sigs)
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            pa, pb = paths[i], paths[j]
            t_sim = jaccard(sigs[pa], sigs[pb])
            if t_sim < 0.6:
                continue
            if related(pa, pb):
                continue  # deliberate pair, not an accident
            b_sim = jaccard(bodies[pa], bodies[pb])
            if b_sim < 0.45:
                continue  # same words in the title, different content
            content_dupes.append((notes[pa]["rel"], notes[pb]["rel"],
                                  round(t_sim, 2), round(b_sim, 2)))
    content_dupes.sort(key=lambda x: -(x[2] + x[3]))

    # STALENESS — the failure that duplicates get blamed for. A note that describes current
    # state (architecture, integrations, status) and has not been touched in months will
    # confidently describe modules that were deleted. This has already caused a real bad
    # diagnosis in this base. Reported oldest first.
    today = datetime.date.today()
    stale = []
    for path, n in notes.items():
        if path == index_path:
            continue
        if profile == "vault" and in_mirror(n["rel"]):
            continue
        d = n["updated"]
        if d is None:
            continue
        age = (today - d).days
        if age > args.stale_days:
            stale.append((n["rel"], d.isoformat(), age))
    stale = scoped(stale, lambda x: x[0])
    stale.sort(key=lambda x: -x[2])

    # A ref counts as alive if it exists under ANY of the given roots.
    #
    # Two scoping rules, or this becomes a false-positive machine (a note about Remotion
    # naming `src/Root.tsx` is not "drift" just because we pointed at the pasture repo):
    #  1. --code-scope limits WHICH notes are checked (substring of the note's rel path).
    #  2. A ref is only checked when its top-level directory actually exists in some root.
    #     `engine/` exists in the repo, so `engine/pix.mjs` is checkable and its absence is
    #     real drift. `examples/` does not, so those refs belong to someone else's tree.
    code_roots = [os.path.abspath(os.path.expanduser(r.strip()))
                  for r in (args.code_root or "").split(",") if r.strip()]
    code_drift = []
    if code_roots:
        for path, n in notes.items():
            if path == index_path:
                continue
            if global_scope and global_scope not in norm_scope(n["rel"]):
                continue
            if is_historical(n["frontmatter"]):
                continue  # an archive is supposed to describe the past
            for ref in sorted(n["code_refs"]):
                top = ref.split("/")[0]
                if top in (".", ".."):
                    continue  # relative to the doc's own file, not to the repo root
                owned = [r for r in code_roots if os.path.isdir(os.path.join(r, top))]
                if not owned:
                    continue  # ref belongs to a tree we were not given
                if not any(os.path.exists(os.path.join(r, *ref.split("/"))) for r in owned):
                    code_drift.append((n["rel"], ref))

    size_warn, split_grabbag, split_growinglog = [], [], []
    if index_path:
        ilines = sum(1 for _ in open(index_path, encoding="utf-8"))
        if ilines > 120:
            size_warn.append((os.path.basename(index_path), f"index has {ilines} lines (consider grouping/archiving)"))
    for path, n in notes.items():
        if path == index_path:
            continue
        if profile == "vault" and in_mirror(n["rel"]):
            continue
        # An ARCHIVE is supposed to be a big dated log — that's its job, same reason
        # is_historical() already exempts staleness and code drift. Without this, the
        # very archive note the growing-log fix tells you to create gets flagged as a
        # growing log the next day (happened to Blueprint do Motor - Changelog).
        if is_historical(n["frontmatter"]):
            continue
        try:
            kb = os.path.getsize(path) / 1024
        except OSError:
            continue
        if kb <= SPLIT_SIZE_KB:
            continue
        headers = n["headers"]
        date_ratio = (sum(1 for h in headers if DATE_TOKEN_RE.search(h)) / len(headers)) if headers else 0.0
        if not headers:
            split_grabbag.append((n["rel"], f"{kb:.0f} KB, no headers at all — likely several facts glued together"))
        elif len(headers) >= 3 and date_ratio >= 0.3:
            split_growinglog.append((n["rel"],
                f"{kb:.0f} KB, {len(headers)} headers, {date_ratio:.0%} look dated — "
                "chronological log; consider archiving by period rather than splitting by topic"))
        else:
            size_warn.append((n["rel"], f"{kb:.0f} KB, {len(headers)} headers (large note; read before deciding — "
                                         "may be one coherent topic, evaluate structure not just size)"))
    split_grabbag = scoped(split_grabbag, lambda x: x[0])
    split_growinglog = scoped(split_growinglog, lambda x: x[0])
    size_warn = scoped(size_warn, lambda x: x[0])

    # DESORGANIZATION RADAR (vault only, judgement fixes — Claude moves files, never a script).
    dup_folder, root_orphan, cross_project = [], [], []
    if profile == "vault":
        projects = scan_projects(root)
        dup_folder, root_orphan, cross_project = find_misplacement(projects)
        dup_folder = scoped(dup_folder, lambda x: x[0])
        root_orphan = scoped(root_orphan, lambda x: x[0])
        cross_project = scoped(cross_project, lambda x: x[0])

    # size_rule_violations is real and worth fixing, but deliberately NOT folded into
    # `total`/CRITICAL: that count's whole value is being a clean "0 = orphans/broken
    # fixed" bar. On this base it started at 90/136 memory notes over the line limit —
    # mixing that volume into CRITICAL would drown the graph-hygiene signal. Tracked
    # separately (its own section, its own snapshot field) instead.
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
        section("POSSIBLE CONTENT DUPLICATES (de-bloat: title AND body match, unlinked)",
                content_dupes, lambda x: f"{x[0]}  ~  {x[1]}  (title {x[2]} / body {x[3]})")
        section(f"STALE NOTES (not updated in >{args.stale_days}d — verify before trusting)",
                stale, lambda x: f"{x[0]}  ->  {x[1]}  ({x[2]}d old)")
        if code_roots:
            section("CODE DRIFT (note names a source file that no longer exists)",
                    code_drift, lambda x: f"{x[0]}  ->  {x[1]}")
        if profile == "memory":
            section("SIZE RULE VIOLATION (over the documented line limit for its type)",
                    size_rule_violations, lambda x: f"{x[0]}  ({x[1]}_*: {x[2]} lines, limit {x[3]})")
        section("SPLIT CANDIDATES - GRAB-BAG (unrelated facts glued into one note)",
                split_grabbag, lambda x: f"{x[0]}  ->  {x[1]}")
        section("SPLIT CANDIDATES - GROWING LOG (unbounded chronological accretion)",
                split_growinglog, lambda x: f"{x[0]}  ->  {x[1]}")
        section("SIZE WARNINGS (large but single-topic; evaluate anyway)", size_warn,
                lambda x: f"{x[0]}  ->  {x[1]}")
        if profile == "vault":
            section("DUPLICATE FOLDER NAME (same subfolder name at 2+ depths in one project)",
                    dup_folder, lambda x: f"{x[0]}: '{x[1]}'  at  {', '.join(x[2])}")
            section("ROOT-LEVEL FILE (project uses subfolders elsewhere; this file has none)",
                    root_orphan, lambda x: f"{x[0]}/{x[1]}")
            section("CROSS-PROJECT FILE (name references a different top-level project)",
                    cross_project, lambda x: f"{x[0]}/{x[1]}  (mentions '{x[2]}')")
            section("VAULT HYGIENE (non-critical)",
                    vault_hygiene, lambda x: f"{x[0]}  ->  {x[1]}")

    split_total = len(split_grabbag) + len(split_growinglog)
    misplaced_total = len(dup_folder) + len(root_orphan) + len(cross_project)

    print("\n" + "=" * 60)
    print(f"CRITICAL: {total}   |   {extra}{len(weak)} weak")
    drift_txt = f" | {len(code_drift)} code drift" if code_roots else ""
    size_rule_txt = f" | {len(size_rule_violations)} size-rule" if profile == "memory" else ""
    print(f"graph: {n_notes} notes | density {density} links/note | {len(content_dupes)} dupe pairs | "
          f"{len(stale)} stale{drift_txt} | {split_total} split candidates | {misplaced_total} misplaced{size_rule_txt}")
    print("=" * 60)

    if args.snapshot:
        row = {
            "date": today.isoformat(), "profile": profile,
            "notes": n_notes, "orphans": len(orphans), "weak": len(weak),
            "broken": len(broken), "separator": len(near), "dupes": len(content_dupes),
            "stale": len(stale), "code_drift": len(code_drift),
            "split_candidates": split_total, "misplaced": misplaced_total,
            "size_rule_violations": len(size_rule_violations),
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
            "stale_notes": stale, "stale_days_threshold": args.stale_days,
            "code_drift": code_drift, "code_roots": code_roots,
            "size_rule_violations": size_rule_violations,
            "split_candidates_grabbag": split_grabbag,
            "split_candidates_growinglog": split_growinglog,
            "duplicate_folder_name": dup_folder, "root_level_files": root_orphan,
            "cross_project_files": cross_project,
            "project_scope": global_scope or None,
            "size_warnings": size_warn, "graph_density": density, "total_critical": total,
        }
        print("<<<JSON>>>")
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
