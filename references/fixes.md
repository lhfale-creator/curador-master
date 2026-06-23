# Fix guide by finding type

For each category in the `audit_kb.py` report: what it is, whether it is SAFE (script)
or REQUIRES JUDGEMENT (Claude), and how to fix it.

## SAFE (apply_safe_fixes.py — always dry-run before --write)

### Separator/case mismatch
- **What**: wikilink pointing to an existing note but in the wrong format
  (e.g. `[[feedback-my-rule]]` when the file is `feedback_my_rule.md`). In Obsidian's
  graph this doesn't connect.
- **Fix**: `apply_safe_fixes.py --path <folder>`. Rewrites to the file's stem.

### Broken links from rename (old slug)
- **What**: links to a note that was renamed (e.g. `project_old_name`
  became `project_new_name`). The target no longer exists.
- **Fix**: `--repoint project_old_name=project_new_name`. Confirm first that the
  new destination actually exists.

### Index duplicate
- **What**: the same `.md` file listed twice in `MEMORY.md` / `Home.md`.
- **Fix**: the fixer keeps the first line and removes subsequent ones. If the 2nd
  line has a better description, merge the text into the 1st manually BEFORE running dedup.

### Name != filename
- **What**: `name:` field in a different format from the filename (kebab vs underscore).
- **Fix**: `--normalize-names` aligns the `name:` to the file's stem.

### Missing frontmatter (vault: tags/updated)
- **What**: vault note without `tags:` and/or `updated:` (hygiene, non-critical).
- **Fix**: `--normalize-frontmatter` adds the missing fields (`updated` comes from
  the file's mtime; `tags` is initialised as `[]`).

## REQUIRES JUDGEMENT (Claude does these; script doesn't touch)

### Orphans (no incoming links)
- **What**: note that nothing references, not even the index. True loose memory.
- **Fix**: read the note → decide which topic/hub it belongs to → add line to
  index → add `[[link]]` to and from at least one peer note. If the note has no
  more value, delete it and remove from index (conscious decision).

### Weakly connected (only the index points to it)
- **What**: indexed, but no peer links. Isolated in the graph.
- **Fix**: add reciprocal wikilinks to notes on the same topic.

### Cross-system references
- **What**: memory cites a note by title that lives in the Obsidian vault, not in
  memory. Expected, not an error.
- **Fix**: confirm in the vault that the note exists. If it doesn't, either create
  the note in the vault, or replace with a reference that exists. Don't "fix" as an
  internal link.

### Two notes about the same fact (de-bloat / consolidation)
- **What**: doesn't appear directly in the report; detect by reading similar
  descriptions in the index (e.g. two files about "product roadmap Q3").
- **Merge criteria**: if they cover the same fact, merge. If one is a subset of the
  other, absorb. If they are distinct facets, keep both but cross-link with `[[ ]]`.
- **How**: choose the master note (most complete/recent) → move unique content from
  the other into it → in the other, leave only `Moved to [[master]].` OR delete and
  remove from index → repoint links that pointed to the dead note.

## Recommended execution order

1. Backup the folder.
2. Dry-run the fixer; review.
3. `--write` for safe fixes (separator, repoint, names, dedup, frontmatter).
4. Re-audit.
5. Resolve orphans and weak connections (judgement).
6. Evaluate de-bloat (judgement).
7. Re-audit and record conscious pending items.
