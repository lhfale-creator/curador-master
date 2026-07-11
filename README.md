# Curador — Claude Code Knowledge Base Skill

> Keeps your **Obsidian vault** + **Claude Code memory** clean, connected, and cloud-durable.

A Claude Code skill that treats your knowledge base as a **library, not a landfill**. It detects and fixes the entropy that generates **loose memory** (orphan notes, broken links, separator mismatches, bloated index, inconsistent frontmatter) across the two systems Claude Code users typically maintain:

1. **Claude memory** — `.md` files in `~/.claude/projects/<id>/memory/`
2. **Obsidian vault** — synced via OneDrive, iCloud Drive, Dropbox, or Google Drive

## Real-world results

Metrics from an actual vault + memory pair after one full curator session:

| Metric | Before | After |
|---|---|---|
| Vault notes | 141 | 141 |
| Critical findings | 59 | **0** |
| Notes missing frontmatter | 55 | **0** |
| Weakly connected notes | 2 | **0** |
| Broken links | 2 | **0** |
| Graph density | 3.12 | **3.55** links/note |

The 55 missing-frontmatter notes were fixed in one `--normalize-frontmatter` pass. The 2 broken links became stub notes. The 2 weakly connected notes got a `## Related` section added manually.

## What it does

| Dimension | Details |
|---|---|
| **Hygiene** | Orphans, broken links, kebab-vs-underscore mismatch, `name` ≠ filename, frontmatter (incl. duplicate `---` blocks), index duplicates |
| **Graph health** | Link density, weakly-connected notes, cross-system references |
| **De-bloat (merge)** | Jaccard ≥ 0.6 similarity flags merge candidates; `merge_helper.py` produces the draft |
| **Split (desmembramento)** | The mirror of de-bloat: grab-bag notes, growing logs, and (memory) hard line-limit violations |
| **Desorganization** | Duplicate folder names, root-level orphan files, cross-project file contamination (vault) |
| **Storage optimization** | `storage_audit.py`: exact/near-duplicate binaries, malformed filenames, Entregaveis convention, uncatalogued assets |
| **Growth tracking** | `--snapshot` appends one JSON line per run; `dashboard.py` shows the trend |
| **Cloud durability** | OneDrive + Dropbox + Google Drive detection; loose-file scan; sync-process check |

## Scripts

| Script | Purpose |
|---|---|
| `audit_kb.py` | Full audit. `--summary` for quick daily check. `--json` for machine output. `--project-scope` filters to one project. |
| `storage_audit.py` | Binary/storage audit (not just `.md`): duplicates, malformed names, convention, uncatalogued assets. `--project` scopes the walk. |
| `apply_safe_fixes.py` | Mechanical fixes. `--interactive` prompts per file. Dry-run by default. |
| `check_cloud_health.py` | Cloud durability. Covers OneDrive, Dropbox, Google Drive. |
| `dashboard.py` | Trend view from `growth_log.jsonl`. Shows regressions. |
| `merge_helper.py` | Side-by-side diff + merged draft for de-bloat candidate pairs. |

## Install

```bash
# macOS / Linux
git clone https://github.com/lhfale-creator/curador-master.git ~/.claude/skills/curador

# Windows (PowerShell)
git clone https://github.com/lhfale-creator/curador-master.git "$env:USERPROFILE\.claude\skills\curador"
```

## Quick start

```bash
# 1. Copy config template and fill in your paths
cp curador.example.json curador.json

# 2. Run everything (audit + cloud check)
./run.sh            # macOS/Linux
.\run.ps1           # Windows

# Or run scripts directly:
python scripts/audit_kb.py --path "<folder>" --summary
python scripts/check_cloud_health.py --vault "<vault>"
```

## Typical workflows

```bash
# End of day — quick check
python scripts/audit_kb.py --path "<memory>" --summary
python scripts/audit_kb.py --path "<vault>"  --summary

# End of a work session on ONE project — same idea as run.ps1 -Project/run.sh --project
python scripts/audit_kb.py --path "<memory>" --project-scope "Nome do Projeto"
python scripts/audit_kb.py --path "<vault>"  --project-scope "Nome do Projeto"
python scripts/storage_audit.py --vault "<vault>" --project "Nome do Projeto"

# Weekly — full audit + snapshot + cloud
python scripts/audit_kb.py --path "<memory>" --snapshot "<vault>/growth_log.jsonl"
python scripts/audit_kb.py --path "<vault>"  --snapshot "<vault>/growth_log.jsonl"
python scripts/storage_audit.py --vault "<vault>" --snapshot "<vault>/growth_log.jsonl"
python scripts/check_cloud_health.py --vault "<vault>"
python scripts/dashboard.py --log "<vault>/growth_log.jsonl"

# Fix safe issues (dry-run first, then write)
python scripts/apply_safe_fixes.py --path "<folder>" --normalize-frontmatter
python scripts/apply_safe_fixes.py --path "<folder>" --normalize-frontmatter --write

# Interactive fix — approve per file
python scripts/apply_safe_fixes.py --path "<folder>" --normalize-names --interactive

# De-bloat — two similar notes flagged by audit
python scripts/audit_kb.py --path "<folder>" --json > audit.json
python scripts/merge_helper.py --from-audit audit.json --root "<folder>" --output merged.md
```

Split candidates, desorganization, and storage findings are all radar, never auto-fixed —
Claude reads the flagged note/file and decides (split/merge/move/dedupe), the same
judgement-call model the merge workflow above already uses. See `SKILL.md` → *Split
candidates*, *Desorganization radar*, *Storage optimization*, and *Project wrap-up*.

## The golden rule

> **filename stem == `name:` field == `[[wikilink]]` == index entry — all in underscore.**

Obsidian resolves `[[X]]` by the file `X.md` (or `aliases:`), never by the `name:` field. A kebab wikilink won't connect in the graph. That mismatch is the #1 cause of loose memory.

## Requirements

- Python 3.9+ (zero external dependencies — stdlib only)
- [Claude Code CLI](https://claude.ai/code)
- Windows, macOS, Linux

## Trigger via natural language in Claude Code

- *"run the curator"* / *"roda o curador"*
- *"audit my memory"* / *"quick check"* / *"--summary"*
- *"fix loose memory"* / *"apply safe fixes"*
- *"check cloud"* / *"is everything in the vault?"*
- *"show growth trend"* / *"dashboard"*
- *"help me merge these two notes"* / *"de-bloat"*
- *"split this note"* / *"desmembrar essa nota"* / *"optimize storage"*
- *"wrap up the day"* / *"curador e sync no projeto X"* (end of a per-project session)

## Cadence

| When | What |
|---|---|
| **End of day** | `--summary` on both folders |
| **End of a work session on one project** | sync mirror → scoped audit + storage audit → judgement fixes → re-audit (`SKILL.md` → *Project wrap-up*) |
| **Weekly** | Full audit + snapshot + cloud check + dashboard |
| **Before migrating machines** | Full cleanup + cloud check + backup |

## Inspired by

- [Dewey memory librarian](https://github.com/cillianconlong/dewey) — de-bloat and memory dating
- [obsidian-agent-memory-skills](https://github.com/calclavia/obsidian-agent-memory-skills) — orient-at-start, write-back, bidirectional links
- Andrej Karpathy's LLM Wiki pattern — compile and interlink, don't accumulate

## License

MIT
