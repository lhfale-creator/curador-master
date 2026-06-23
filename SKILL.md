---
name: curador
description: "Knowledge base librarian/curator and Obsidian specialist. Keeps hygiene, consistency and CLOUD DURABILITY of the TWO systems (Claude Code memory at ~/.claude/projects/<id>/memory and the Obsidian vault synced via OneDrive/iCloud). Prevents loose memory: orphan nodes, duplicates, broken links, kebab-vs-underscore separator, bad frontmatter, name != filename. Handles de-bloat/consolidation, tracks growth via snapshots, normalizes frontmatter/tags/aliases, and verifies everything is cloud-synced with nothing stranded outside the vault. Use when asked to run the curator, audit/organize memory, clean loose memory, fix the vault, check broken links, verify cloud sync, or at end of day to ensure nothing was born disconnected or left outside the cloud. Also the teachable standard (single source) so other projects don't generate loose memory."
---

# Curador (Knowledge Base Librarian)

## Purpose

Treat the knowledge base as a library, not a landfill, and ensure it
**grows without getting lost**. Three fronts:
1. **Hygiene/connection**: prevent loose memory (orphans, duplicates, broken links,
   separator mismatch, bad frontmatter, name != filename) in both systems.
2. **Sustainable growth**: de-bloat (merge redundant notes), size warnings, and
   growth snapshots to track trends over time.
3. **Cloud durability**: confirm everything is in the synced vault (OneDrive/iCloud)
   and nothing of value lives stranded outside it (rule: nothing outside the vault).

Inspired by (patterns incorporated, not copied): Dewey memory librarian (de-bloat
and dating), obsidian-agent-memory-skills (orient-at-start + write-back + bidirectional
links), Karpathy LLM Wiki pattern (compile and interlink, don't accumulate).

## Tools (scripts/)

| Script | Does |
|---|---|
| `audit_kb.py` | scans and reports findings; `--snapshot` records growth metrics; detects de-bloat and size issues |
| `apply_safe_fixes.py` | fixes only the mechanical (dry-run by default); `--normalize-frontmatter` fills tags/updated |
| `check_cloud_health.py` | verifies durability: vault in cloud, sync running, loose files outside vault, parallel iCloud vault |

References (load as needed): `references/conventions.md` (the law of both systems),
`references/fixes.md` (recipe per finding type), `references/cloud_durability.md`
(cloud rule + the check), `references/growth_and_debloat.md`
(metrics, snapshots, merge criteria, archive policy).

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

## When to use

- Explicit request: "run the curator", "audit memory", "clean loose memory".
- At end of day / "wrap up" (together with the save-to-both-systems rule).
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
inconsistent keys, content duplicates (de-bloat), size warnings.

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

## Cadence

- **End of day** ("wrap up"): save to both systems + quick audit of both folders.
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

## Safety

- Dry-run always before `--write`. Backup before writing to the real base.
- The fixer only touches what is mechanically unambiguous. Content merge and file
  rename are human/Claude decisions, never the script's.
- Report findings faithfully (real numbers, never inflate or hide).
