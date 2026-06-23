# Knowledge base conventions (single source of truth)

This document defines how Claude memory and the Obsidian vault should be structured.
Other projects cite THIS file instead of reinventing rules.

## Golden rule: canonical name in underscore

The graph only connects when the link matches the FILE NAME. Obsidian resolves
`[[X]]` by the file `X.md` (or by `aliases:`), never by the `name:` field. Therefore:

> **filename (stem) == `name:` field == wikilink `[[...]]` == index entry**, all
> lowercase with **underscore** as separator.

Why underscore and not kebab: Claude Code memory files already use underscore and
`MEMORY.md` links by `(filename.md)`. Standardising the rest to underscore requires
only adjusting the `name:` field and wikilinks, without renaming any file (safer).

## System 1 — Claude memory

Folder: `~/.claude/projects/<project-id>/memory/`

### Fact file (one note = one fact)
```markdown
---
name: <file_stem_in_underscore>
description: <one line; used when retrieving the memory>
metadata:
  type: user | feedback | project | reference
---

<the fact. For feedback/project, follow with **Why:** and **How to apply:** lines>
Link related notes with [[stem_of_other_note]].
```
- `type`: `user` (who the user is), `feedback` (how to work, with the why),
  `project` (ongoing work, relative dates become absolute),
  `reference` (pointer to external resource).

### Index `MEMORY.md`
- One line per note: `- [Title](filename.md) — short hook`.
- Loaded at every session start. Never put fact content here, only the pointer.
- Each file appears ONCE. Duplicate = bug to remove.

## System 2 — Obsidian vault

Canonical folder: `<path/to/your/vault>` (use the one synced to OneDrive/iCloud/Dropbox;
avoid keeping parallel vaults in two cloud providers). Hub: `Home.md`.

### Purpose → Topic model
- Each project has a **root folder** with the project name.
- Inside: subfolders by topic/category; additional subfolders when it makes sense.
- PDFs in `Entregaveis/` inside each subfolder; `.md` at the subfolder root.
- Every deliverable (PDF) has a companion `.md` that catalogs it.
- Heavy binary assets may live outside the vault, but must be cataloged in a `.md` inside.

### Vault note frontmatter
```markdown
---
tags: [project, topic]
updated: YYYY-MM-DD
---
```
- Update `updated:` on every edit.
- Wikilinks `[[...]]` to and from related notes (both incoming AND outgoing).
- Obsidian callouts when helpful: `> [!note]`, `> [!warning]`, `> [!danger]`.

## Linking (applies to both systems)

1. **Every new note goes into the index immediately** (`MEMORY.md` or `Home.md`).
2. **Every new note gets at least 1 link** (to a hub or sibling note) at creation.
3. **Bidirectional write-back**: when linking A→B, create B→A when the relation is mutual.
4. **Wikilink only with the stem** (underscore). Don't link by title or kebab slug.
5. **Cross-system reference**: memory may cite a vault note by title
   (`[[My Vault Note]]`); this is NOT an error and won't resolve inside memory.
   To become a real link, the note must exist in the vault.
6. **Rename uses alias, never breaks links** (vault): when renaming a note that others
   already link to, add the old name to `aliases:` in frontmatter. Obsidian resolves
   `[[old name]]` via alias and the graph stays intact. Repointing links is ideal,
   but the alias is the safety net.
   ```yaml
   aliases: [old name, previous title]
   ```

## Tags (vault)

- Tag = search facet, not a folder. The folder already says the topic; the tag crosses topics.
- Keep a small, reused vocabulary. Before creating a new tag, check if an equivalent
  already exists (avoid `marketing` and `mkt` coexisting).
- Minimum frontmatter for every vault note: `tags` + `updated`. The
  `apply_safe_fixes.py --normalize-frontmatter` fills in what's missing (`updated`
  comes from the file's mtime).

## Antidote against loose memory (root cause)

Loose memory is born when a note is created without connections. Before creating ANY note:
- Check if a note on the topic already exists → if yes, **update**, don't duplicate.
- If creating: index + link in the same action, never later.
- If the topic is too small: don't create a note; append to an existing one.

## Cloud durability (nothing outside the vault)

Knowledge is only durable if it lives in the cloud. Core rule: **EVERYTHING inside
the vault (cloud-synced), nothing outside.** Scratch work in `/tmp`, Desktop, Downloads
gets a master copy in the vault before ending the task. Details and the verifier
in `cloud_durability.md`.

## Propagation (this file is the single source)

Other projects do NOT reinvent organisation rules: they cite THIS file. When a project
needs a specific convention, it becomes an addendum here, not a parallel rule.
That way the law is one and the curator audits all projects with the same criteria.
