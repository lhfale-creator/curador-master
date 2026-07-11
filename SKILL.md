---
name: curador
description: "Knowledge base librarian/curator and Obsidian specialist. Keeps hygiene, consistency and CLOUD DURABILITY of the TWO systems (Claude Code memory at ~/.claude/projects/<id>/memory and the Obsidian vault synced via OneDrive/iCloud). Prevents loose memory: orphan nodes, duplicates, broken links, kebab-vs-underscore separator, bad frontmatter, name != filename. Handles de-bloat/consolidation (merge), split candidates/desmembramento (grab-bag notes, growing logs, oversized memory notes), desorganization (misplaced files, duplicate folder names, cross-project contamination), storage optimization of binaries (duplicate/near-duplicate PDFs, malformed filenames, uncatalogued assets), tracks growth via snapshots, normalizes frontmatter/tags/aliases, and verifies everything is cloud-synced with nothing stranded outside the vault. Use when asked to run the curator, audit/organize memory or projects, clean loose memory, split/desmembrar an oversized note, optimize storage, fix the vault, check broken links, verify cloud sync, or at the end of a work session (overall or per-project) to ensure nothing was born disconnected, oversized, misplaced, or left outside the cloud. Also the teachable standard (single source) so other projects don't generate loose memory."
---

# Curador (Knowledge Base Librarian)

## Purpose

Treat the knowledge base as a library, not a landfill, and ensure it
**grows without getting lost**. Four fronts:
1. **Hygiene/connection**: prevent loose memory (orphans, duplicates, broken links,
   separator mismatch, bad frontmatter, name != filename) in both systems.
2. **Sustainable growth**: de-bloat (merge redundant notes) AND its mirror, split
   candidates/desmembramento (grab-bag notes, growing logs, oversized memory notes),
   plus size warnings and growth snapshots to track trends over time.
3. **Organization**: desorganization radar (misplaced files, duplicate folder names,
   cross-project contamination) and storage optimization of binaries (duplicate/
   near-duplicate PDFs, malformed filenames, uncatalogued assets) — see *Project
   wrap-up* below for the end-of-session-per-project flow that runs all of this.
4. **Cloud durability**: confirm everything is in the synced vault (OneDrive/iCloud)
   and nothing of value lives stranded outside it (rule: nothing outside the vault).

Inspired by (patterns incorporated, not copied): Dewey memory librarian (de-bloat
and dating), obsidian-agent-memory-skills (orient-at-start + write-back + bidirectional
links), Karpathy LLM Wiki pattern (compile and interlink, don't accumulate).

## Tools (scripts/)

| Script | Does |
|---|---|
| `audit_kb.py` | scans and reports findings; `--snapshot` records growth metrics; detects de-bloat and size issues |
| `audit_kb.py` (staleness) | `--stale-days N` · `--code-root P` · `--code-scope/--project-scope S` — see *Staleness and code drift* below |
| `audit_kb.py` (split + desorganization) | grab-bag/growing-log/size-rule/misplacement radar — see *Split candidates* and *Desorganization radar* below |
| `storage_audit.py` | binary/storage radar: exact + near-duplicate files, malformed filenames, Entregaveis convention, uncatalogued assets — see *Storage optimization* below |
| `apply_safe_fixes.py` | fixes only the mechanical (dry-run by default); `--normalize-frontmatter` fills tags/updated |
| `check_cloud_health.py` | verifies durability: vault in cloud, sync running, loose files outside vault, parallel iCloud vault |

References (load as needed): `references/conventions.md` (the law of both systems),
`references/fixes.md` (recipe per finding type), `references/cloud_durability.md`
(cloud rule + the check), `references/growth_and_debloat.md`
(metrics, snapshots, merge criteria, archive policy, split criteria).

## The two systems

1. **Claude memory** — `~/.claude/projects/<project-id>/memory/`
   - One fact per `.md` file with frontmatter `name` / `description` / `metadata.type`.
   - Index: `MEMORY.md` (one line per note, markdown link `(file.md)`).
   - Links between notes: wikilink `[[stem]]`.
2. **Obsidian vault** — `<path/to/your/vault>` (synced via OneDrive, iCloud, Dropbox…)
   - Purpose→Topic model, frontmatter `tags` / `updated`, wikilinks `[[...]]`.
   - Hub: `Home.md`. Deliverables (PDFs) in `Entregaveis/`.

Full conventions in `references/conventions.md`. **Golden rule: underscore is canonical
in everything (filename == `name:` field == wikilink == index entry).** Only then do
Claude and Obsidian agree and the graph connects.

## Staleness and code drift (the dangerous findings)

A stale note is worse than a duplicate: a duplicate wastes space, a stale note **actively
misleads whoever reads it next**. This base has already paid for it — a bug audit read an
architecture note that still documented `engine/mercadopago.mjs` months after that module
was deleted, and reported a "critical bug" in code that no longer existed.

```
--stale-days N     flag notes whose updated/atualizado is older than N days (default 120)
--code-root  P     comma-separated repo roots
--code-scope S     only check notes whose path contains S (e.g. "Professor Pastagem")
```

`--code-root` is the strongest signal: it flags any note naming a **source file that no
longer exists**. Date-staleness is only a proxy (a note 3 weeks old can already be wrong);
code drift is proof.

```
python scripts/audit_kb.py --path "<vault>" \
    --code-root "<repo>" --code-scope "Professor Pastagem"
```

Always pair `--code-root` with `--code-scope`, or notes about other repos get checked
against the wrong tree.

Four rules keep it from crying wolf (a check people learn to ignore is worse than no check):
1. A ref is only checked when its top-level dir exists in some root (`engine/` does,
   `examples/` does not), and `./relative` refs are skipped.
2. **Tombstones and proposals are not drift.** A ±1-line window around the ref is scanned
   for markers (`deletado`, `removido`, `não existe`, `~~`, `criar`, `novo`, `proposto`).
   A note correctly saying "`engine/pix.mjs` foi deletado" is doing its job. The window is
   ±1 line, not the line itself, because prose wraps and lists put the marker one line up.
3. **Notes that declare themselves historical are skipped** — `status:` or `tags:` matching
   `histórico|arquivado|obsoleto|superado|legado`. An archive is supposed to describe the past.
   This is the clean way to retire an old doc: mark it historical instead of deleting it.
4. Only paths containing a `/` are detected, so a bare `` `pix.mjs` `` is not caught.

Sanity-check after changing this: a *live* note naming a deleted module must still be flagged.

## De-bloat is title AND body, never title alone

Similar titles are not evidence of duplication. `Arquitetura de Contexto` (the why) and
`Arquitetura do Projeto` (the what/how) are a deliberate complementary pair that share 3 of
4 title words. A real duplicate matches in title **and** prose, **and** the two notes do not
already link each other (a human who wrote `A → B` already decided they are distinct).
The `Memory/` mirror is excluded from de-bloat and orphans, per *The contract* below — it is
sync's output, and every mirrored note legitimately restates the vault note it came from.

## Split candidates (desmembramento) — the mirror of de-bloat

De-bloat asks "should these 2 notes become 1?". This asks the opposite: "should this 1
note become several?" A note that mixes N unrelated facts is worse than a duplicate — it
makes retrieval return the wrong 90% of a file along with the 10% that was needed. Real
example found in this base: `FAQ Dunamis (interno).md`, 76 KB, zero headers, mixing
product genetics, seed specs, herbicide compatibility and pasture management in one wall
of text.

`audit_kb.py` reports notes above the existing 12 KB bloat threshold in one of three
buckets, radar only — Claude reads the content and decides, exactly like de-bloat merges:

- **SPLIT CANDIDATE - GRAB-BAG**: no headers at all (a large note needs *some* structure
  to not be a grab-bag by default), or 4+ headers with little word overlap between them
  (headers talking about unrelated things). Fix: break into one note per fact/topic,
  cross-linked to a hub, per the "one fact per file" rule.
- **SPLIT CANDIDATE - GROWING LOG**: 3+ headers, 30%+ of them look dated (`DD/MM`,
  `(DD/MM/AAAA)`). Not a topic mix — a changelog that never gets archived. Fix: archive by
  period (e.g. one note per month) instead of splitting by topic.
- **SIZE WARNING**: large but neither of the above — one coherent topic that's just long
  (e.g. a 700-line brand manual). Evaluate anyway, but splitting isn't automatically right.

For **Claude memory** specifically, there's a mechanical (not radar) version of this:
`project_*` notes over 15 lines and `reference_*` notes over 5 lines are a documented hard
rule ([[feedback_memoria_notas_enxutas]]) — `SIZE RULE VIOLATION` in the report. Fix: move
the excess into a dated vault note, leave only the pointer in memory. Deliberately NOT part
of `CRITICAL` (see comment in `audit_kb.py` — this base started at 90/136 memory notes over
the limit; folding that volume into the "must be 0" bar would drown the graph-hygiene signal).

## Desorganization radar (vault only)

Three mechanical, path-only checks — real bugs each one caught in this base:

- **DUPLICATE FOLDER NAME**: the same subfolder name at 2+ depths inside one project (e.g.
  `Professor Pastagem/Produto-MVP/` AND `Professor Pastagem/Conhecimento/Produto-MVP/` —
  same topic, two homes). `Entregáveis`/`Entregaveis` is excluded — it's SUPPOSED to repeat
  at every depth, that's the convention.
- **ROOT-LEVEL FILE**: a file sitting loose at a project's root when the project otherwise
  organizes into subfolders (excludes the project's own hub note, e.g. `Milagro.md` at the
  root of `Milagro/`). Real example: 3 `.docx`/`.pdf` files loose at `Operations Center/`
  root while everything else lives under `Conhecimento/<subfolder>/`.
- **CROSS-PROJECT FILE**: a filename/path mentioning a DIFFERENT top-level project's name.
  Real example: `kb_milagro_403_conversas.json` sitting inside the `Professor Pastagem`
  project folder.

All three are radar — Claude decides whether and where to move the file, never the script.

## Storage optimization (binaries — `storage_audit.py`)

`audit_kb.py` only ever reads `.md`. In a real vault the notes are a sliver of the weight —
this base is 557 MB across 326 notes; the rest is PDFs/images/video the note audit never
looks at. Same radar-only rule: never deletes, renames or moves — the vault has no git
history, OneDrive is the only safety net, so any destructive call is Claude's, with the
user present.

```
python scripts/storage_audit.py --vault "<vault>" [--project "Nome"] [--min-size-mb N]
```

- **EXACT DUPLICATE** — sha256 match, byte-for-byte identical (files > 100 MB aren't hashed;
  pattern checks still run on them).
- **NEAR-DUPLICATE NAME** — same folder, name differs only by a copy/version marker
  (` (1)`, `-1`, `Cópia de `). Real example: 3 near-duplicate PDFs in Gestão de Terras Piauí,
  `milagro-relatorio-terras-2026-07-06.pdf` / ` (1).pdf` / ` (2).pdf`, different sizes, no
  versioning note — could be 3 copies or 3 genuinely different revisions; judgement, not auto-delete.
- **MALFORMED FILENAME** — doubled extension (`G4 Arquitetura de Receita.pdf.pdf`).
- **CONVENTION VIOLATION** — narrow and specific on purpose: a file sitting loose at the ROOT
  of an `Entregáveis/` folder that ALSO has real subfolders (real bug: 3 files loose in
  `Milagro/Entregáveis/` while `Documentos Legais/`, `Exportação/`, `Marketing/`, `Scripts/`
  hold everything else). NOT "any binary outside Entregáveis" — that fires on every
  legitimately-placed reference PDF in a `Conhecimento/Pesquisas/` folder (source material
  was never claimed to need the deliverable convention); the first cut of this check did
  exactly that and had to be narrowed.
- **UNCATALOGUED ASSET** — a binary with no `.md` nearby describing it, by WORD OVERLAP not
  exact filename match. A real cataloged example in this base (`Alta Mira.md`) lists "Carta
  de anuência" as prose, never the literal filename `CARTA DE ANUENCIA ALTA MIRA.pdf` —
  exact-substring matching flagged it anyway (244/336 false-positive rate) until switched to
  majority-of-filename-words-appear-somewhere-nearby.

## When to use

- Explicit request: "run the curator", "audit memory", "clean loose memory".
- At end of day / "wrap up" (together with the save-to-both-systems rule).
- **At the end of a work session on a specific project** ("curador e sync no projeto X") —
  see *Project wrap-up* below.
- To check if the base is in the cloud / if something was left outside the vault.
- Before migrating to a new machine (clean base + confirm sync before moving).
- After a session that created many new notes (check they were born connected).

## Workflow

### 1. Audit (always first, never fix blind)

```
python scripts/audit_kb.py --path "<folder>" [--index MEMORY.md] [--json]
```
- Claude memory and vault are audited separately.
- Profile and index are auto-detected (`.obsidian` dir → vault; `MEMORY.md` → memory).
- `--json` to consume output programmatically (after the `<<<JSON>>>` marker).
- On Windows, force UTF-8 first: `$env:PYTHONUTF8=1; $env:PYTHONIOENCODING="utf-8"`.

Report groups findings as: orphans, weakly connected, broken links, separator mismatch,
cross-system references, index duplicates, name≠filename, frontmatter issues,
inconsistent keys, content duplicates (de-bloat), stale notes, code drift, size-rule
violations (memory), split candidates — grab-bag/growing-log, size warnings, and
(vault only) duplicate folder name / root-level file / cross-project file.

### 2. Triage

Classify each finding as **safe** (mechanical, reversible) or **requires judgement**.
Detailed breakdown by type in `references/fixes.md`. Summary:

| Type | Action |
|---|---|
| Separator/case mismatch | SAFE — fixer |
| Renamed slug (broken links from rename) | SAFE — fixer with `--repoint old=new` |
| Index duplicate | SAFE — fixer (keeps first line) |
| Name != filename | SAFE — fixer `--normalize-names` |
| Orphans / weakly connected | JUDGEMENT — decide where to link |
| Cross-system references | JUDGEMENT — confirm note exists in the other system |
| Two notes about the same fact | JUDGEMENT — manual merge + redirect |

### 3. Apply safe fixes (dry-run first, ALWAYS)

```
python scripts/apply_safe_fixes.py --path "<folder>" [--index MEMORY.md] \
    [--repoint old_slug=new_slug] [--normalize-names] [--no-separator] [--no-dedup]
```
- No `--write` = dry-run: prints everything it would do and writes nothing. **Review first.**
- Add `--write` only after reviewing the dry-run.
- Before `--write` on real data, **make a backup** (copy the folder to a scratch
  location or commit if it's a git repo).

### 4. Judgement fixes (Claude does these, not the script)

- **Orphan**: read the note, decide which hub/topic it belongs to, add an entry
  to the index (`MEMORY.md` / `Home.md`) and at least one `[[link]]` to and from a peer.
- **Weakly connected**: add reciprocal wikilinks to notes on the same topic.
- **Two notes about the same fact (de-bloat)**: merge into the more complete one,
  move unique content, turn the other into a short redirect (`Moved to [[x]].`) or
  delete and remove from index. Criteria in `references/fixes.md`.
- **Bidirectional write-back**: when linking A→B, ensure B→A when the relation is mutual.

### 5. Re-audit (with snapshot)

Run `audit_kb.py` again and confirm critical findings are zero (or that remaining
ones are conscious deferred decisions). Record what is pending.
Use `--snapshot` pointing to a log inside the vault to record the day's metric:
```
python scripts/audit_kb.py --path "<folder>" \
    --snapshot "<your-vault>/growth_log.jsonl"
```
If `orphans`/`broken` increased since the last snapshot, the teachable pattern
was not followed during note creation — fix and reinforce the rule.

### 6. Verify cloud durability

```
python scripts/check_cloud_health.py --vault "<vault>" [--extra-dir "<scratch-dir>"]
```
Confirms vault is under the synced OneDrive root, OneDrive is running, and lists
knowledge files stranded outside the vault (rule: nothing outside). Details in
`references/cloud_durability.md`.

## Project wrap-up (end of a work session on one project)

When Alexandre says something like "curador e sync no projeto X" / "encerrar sessão de Y",
this is the chain — sync makes the structure correct first, then curador audits it,
scoped to that one project with `--project-scope`/`--code-scope` (same flag, filters
stale/split/size-rule/misplacement findings down to paths containing the project name;
`--project` on `storage_audit.py` scopes the walk itself to `<vault>/<project>`):

1. **Mirror**: `python ../sync-cerebro/scripts/sync_memory_mirror.py --memory "<memory>" --vault "<vault>" --write`
   (global, idempotent — memory→vault stays current before auditing).
2. **Scoped audit**:
   ```
   python scripts/audit_kb.py --path "<memory>" --project-scope "<Projeto>"
   python scripts/audit_kb.py --path "<vault>"  --project-scope "<Projeto>"
   python scripts/storage_audit.py --vault "<vault>" --project "<Projeto>"
   ```
3. **Read, don't just parse the report.** For every split/misplacement/storage finding,
   open the actual note/file — the report is a radar, not a verdict. Decide: split, merge,
   move, archive, dedupe, or leave it (a coherent-but-long note is not a bug).
4. **Execute.** Text edits (new split notes, merged notes, updated links/index) via
   Edit/Write. File moves/renames/deletes via Bash/PowerShell — NEVER a script's job (see
   *Storage optimization* above: no git history on the vault, OneDrive is the only net).
5. **Re-audit** the same 3 commands + `--snapshot` on all of them to record the after-state.
6. **One report to Alexandre**: what changed, what's deferred and why.

## Cadence

- **End of day** ("wrap up"): save to both systems + quick audit of both folders.
- **End of a work session on one project**: the Project wrap-up chain above.
- **Weekly**: audit + snapshot of both folders + `check_cloud_health.py`.
- **Before switching machines**: full cleanup + cloud check + backup.

## Teachable pattern (so other projects don't generate loose memory)

The root cause of loose memory is a note born without connections. Apply to EVERY
new note (memory or vault), in any project:

1. **Canonical name**: filename, `name:` field and wikilinks in the SAME underscore format.
2. **Never create a note without indexing it**: every new note goes into `MEMORY.md` / `Home.md` immediately.
3. **Never create a note without at least 1 link**: connect to a hub or sibling note at creation time.
4. **Before creating, check if it already exists**: update the existing note instead of duplicating.
5. **Wikilink only with the file stem** (not with title or kebab slug).

This block is the operational summary; full conventions live in
`references/conventions.md` — it is the single source cited by all other projects.

## Never trust a filename — compare content

`check_cloud_health.py` indexes the vault by **sha256 of the file**, not by filename, and the
audit's de-bloat compares body text, not titles. This is not a detail; it is the difference
between a curator and a shredder.

Real case (10/07/2026): the check reported 9 loose files "with no copy in vault" and they
looked like junk (`download.pdf`, `Untitled.pdf`, `TRT.pdf`, `Comprovante.pdf`). They were
**not** junk, and they were **not** missing:

| Loose file | What it actually was | Already in vault as |
|---|---|---|
| `download.pdf` | SIGEF certified parcel, Serrinha | `Planta Certificada Serrinha.pdf` |
| `download (1).pdf` | SIGEF descriptive memorial | `Memorial Descritivo Serrinha.pdf` |
| `Comprovante.pdf` | R$195,93 Pix paid to INCRA | `Comprovante Pagamento INCRA.pdf` |
| `TRT.pdf` | Technical Responsibility Term, Alta Mira | `TRT - Termo Responsabilidade Tecnica.pdf` |
| `Untitled.pdf` | The Professor Pastagem sample report | `Laudo Exemplo - Nathalya Neme.pdf` |
| `Roadmap_Caltim (1).pdf` | **A NEWER revision of a client deliverable** | (vault held the OLDER one) |

Archiving a file under a better name is the CORRECT behaviour — and a name-only index then
reports it as missing, pressuring you to delete a document that is already safe. Worse, one
of the "(1)" duplicates was a **revised client deliverable**, newer than the vault's copy.

**Rules that follow, in order:**
1. **Read the file before deleting it.** Extract its text. A generic name (`download.pdf`,
   `Untitled.pdf`) is evidence of nothing.
2. **Match by content hash.** Same name + different bytes = possibly a NEWER revision. Report
   it as `mesmo NOME, conteudo DIFERENTE` and compare dates/length before touching it.
3. **Delete only with a proven twin.** Hash the candidate against the vault at the moment of
   deletion; no twin, no delete. Copy to the backup first regardless.

## Safety

- Dry-run always before `--write`. Backup before writing to the real base.
- The fixer only touches what is mechanically unambiguous. Content merge and file
  rename are human/Claude decisions, never the script's.
- Report findings faithfully (real numbers, never inflate or hide).
