# Curador — Claude Code Knowledge Base Skill

> Keeps your **Obsidian vault** + **Claude Code memory** clean, connected, and cloud-durable.

A Claude Code skill that treats your knowledge base as a **library, not a landfill**. It detects and fixes the entropy that generates **loose memory** (orphan notes, broken links, separator mismatches, bloated index, inconsistent frontmatter) across the two systems Claude Code users typically maintain:

1. **Claude memory** — `.md` files in your Claude Code project memory folder (`~/.claude/projects/<id>/memory/`)
2. **Obsidian vault** — your Obsidian vault, ideally synced via OneDrive, iCloud Drive, or Dropbox

## What it does

| Dimension | Details |
|---|---|
| **Hygiene** | Orphans, broken links, kebab-vs-underscore mismatch, `name` ≠ filename, frontmatter issues, index duplicates |
| **Graph health** | Link density metric, weakly-connected notes, cross-system references |
| **De-bloat** | Content-similarity detection (Jaccard ≥ 0.6) flags candidate notes to merge |
| **Growth tracking** | `--snapshot` appends one JSON line per audit — track cleanliness trends over time |
| **Cloud durability** | Verifies vault is under your cloud sync root, sync process is running, no knowledge files stranded outside the vault |

## Three scripts

```bash
# Windows: set UTF-8 first
# $env:PYTHONUTF8=1; $env:PYTHONIOENCODING="utf-8"

# 1. Audit — always first, never fix blind
python scripts/audit_kb.py --path "<your-folder>" [--snapshot growth_log.jsonl] [--json]

# 2. Fix safe issues (dry-run by default; add --write to apply)
python scripts/apply_safe_fixes.py --path "<your-folder>" \
    [--repoint old_slug=new_slug] [--normalize-names] [--normalize-frontmatter] [--write]

# 3. Cloud durability check
python scripts/check_cloud_health.py --vault "<path/to/your/vault>"
```

## The golden rule

> **filename stem == `name:` field == `[[wikilink]]` == index entry — all in underscore.**

Obsidian resolves `[[X]]` by the file `X.md` (or by `aliases:`), never by the `name:` field. A kebab wikilink won't connect in the graph. That mismatch is the #1 cause of loose memory — every detection and fix in this skill traces back to it.

## Install

```bash
# macOS / Linux
git clone https://github.com/lhfale-creator/curador.git ~/.claude/skills/curador

# Windows (PowerShell)
git clone https://github.com/lhfale-creator/curador.git "$env:USERPROFILE\.claude\skills\curador"
```

Then trigger via natural language in Claude Code:
- *"run the curator"* / *"roda o curador"*
- *"audit my memory"* / *"audita a memoria"*
- *"clean loose memory"* / *"limpa memoria solta"*
- *"check cloud durability"* / *"checa se ta na nuvem"*
- *"wrap up the day"* / *"encerra o dia"*

## Cadence

| When | What |
|---|---|
| **End of day** | audit both folders — nothing born disconnected |
| **Weekly** | audit + snapshot + cloud health check |
| **Before migrating machines** | full cleanup + cloud check + backup |

## Requirements

- Python 3.9+ (zero external dependencies — stdlib only)
- [Claude Code CLI](https://claude.ai/code)
- Works on **Windows, macOS, Linux**

## Findings the auditor detects

| Finding | Critical? | Fix |
|---|---|---|
| Orphan (no incoming links) | Yes | Connect to a hub or peer |
| Broken wikilink | Yes | Repoint or create target |
| Separator mismatch (`kebab` vs `underscore`) | Yes | `apply_safe_fixes.py` (auto) |
| `name:` field ≠ filename | Yes | `--normalize-names` (auto) |
| Index duplicate | Yes | fixer keeps first line (auto) |
| Frontmatter missing `tags`/`updated` | Hygiene | `--normalize-frontmatter` (auto) |
| Content-similar notes (de-bloat) | Judgement | Merge manually |
| Large note / bloated index | Hygiene | Split or archive |
| File outside vault (cloud check) | Hygiene | Copy master to vault |
| Parallel vault (iCloud vs OneDrive) | Warning | Pick one source of truth |

## Inspired by

- [Dewey memory librarian](https://github.com/cillianconlong/dewey) — de-bloat and memory dating
- [obsidian-agent-memory-skills](https://github.com/calclavia/obsidian-agent-memory-skills) — orient-at-start, write-back, bidirectional links
- Andrej Karpathy's LLM Wiki pattern — compile and interlink, don't accumulate

## License

MIT
