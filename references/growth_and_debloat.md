# Sustainable growth and de-bloat

The curator's goal is not just to fix links: it's to make the base **grow without
getting lost**. A healthy base = information finds whoever needs it, doesn't bloat,
doesn't duplicate, and you can see the trend over time.
Karpathy LLM Wiki pattern: compile and interlink, don't accumulate.
Dewey pattern: de-bloat and dating.

## Graph health metrics (what `audit_kb.py` reports)

- **density** = total incoming links / number of notes. Low (< ~2) = sparse graph,
  many isolated notes. High and stable = well-interlinked base.
- **orphans** = notes with no incoming links. Target: always 0.
- **weak** = only the index points to it. Tolerate a few; ideally decreases over time.
- **similar pairs** = merge candidates (de-bloat). Human decision.

## Growth snapshot (track trends)

Running the audit with `--snapshot` appends ONE JSON line per execution to a log
that **lives in the vault** (rule: nothing outside):

```bash
python scripts/audit_kb.py --path "<memory-folder>" \
    --snapshot "<your-vault>/growth_log.jsonl"

python scripts/audit_kb.py --path "<vault-folder>" \
    --snapshot "<your-vault>/growth_log.jsonl"
```

Each line: `date, profile, notes, orphans, weak, broken, separator, dupes,
density, critical`. Reading the log in order shows whether the base is getting
cleaner or messier as it grows. If `orphans` or `broken` rise between snapshots,
the teachable pattern wasn't followed during note creation.

## De-bloat: when to merge two notes

`audit_kb.py` flags "POSSIBLE CONTENT DUPLICATES" by token overlap (Jaccard ≥ 0.6
between descriptions/titles). It's just a radar; the merge is human.

Decision criteria:
- **Cover the same fact** → merge into the master note (most complete/recent),
  move unique content, turn the other into a redirect (`Moved to [[master]].`) or
  delete and remove from index; repoint links that went to the dead note.
- **One is a subset of the other** → absorb the smaller into the larger.
- **Distinct facets of the same topic** (e.g. a hub and its sub-note) → do NOT merge;
  just cross-link with `[[ ]]`. Hub↔child pairs appear as "similar" and are
  expected false positives.

## Size warnings (bloat)

Very large notes (the report flags > 12 KB) tend to become landfills. Evaluate:
- Does the note mix several facts? → split into smaller notes linked to a hub.
- Is it history that's already passed? → archive (see archive policy below).
A long index (`MEMORY.md` > ~120 lines) signals it's time to group pointers by topic
or archive dead memories.

## When to split a note (desmembramento — the mirror of merge)

De-bloat above asks "should these 2 notes become 1?" This is the opposite question:
"should this 1 note become several?" `audit_kb.py` reports two distinct shapes, both
radar only — Claude reads the note and decides, the same way merge candidates work:

- **GRAB-BAG**: no headers at all (a large note needs *some* structure to not default
  to grab-bag), or 4+ headers with little word overlap between them. Real example:
  `FAQ Dunamis (interno).md`, 76 KB, zero headers, mixing product genetics, seed specs,
  herbicide compatibility and pasture management in one wall of text. Fix: one note per
  fact/topic, cross-linked to a hub — not one note trying to answer everything.
- **GROWING LOG**: 3+ headers, 30%+ of them dated (`DD/MM`, `(DD/MM/AAAA)`). This is NOT
  a topic mix — it's a changelog that never gets archived. Fix: archive by period (one
  note per month/quarter), don't split by topic — the topic (e.g. "engineering
  changelog") is genuinely one thing, it just needs its tail cut off periodically.

Distinguishing these two matters: splitting a growing log by topic produces N notes that
are each still growing logs; the actual fix is archiving old entries out, not
topic-decomposition.

**Claude memory has a mechanical (non-radar) version**: `project_*` notes over 15 lines
and `reference_*` notes over 5 lines are a documented hard limit
([[feedback_memoria_notas_enxutas]]), not a heuristic — `SIZE RULE VIOLATION` in the
report. Fix: move the excess into a dated vault note, leave only the pointer in memory.
This is exactly the failure the rule was written to prevent (a project note grew to 89 KB
of session logs before anyone noticed) — and on this base, checking it mechanically for
the first time found 90 of 136 memory notes already over the limit.

## Archive policy (don't delete carelessly)

- `reminder_*` whose deadline passed or whose action is done: resolve and remove, or
  mark as completed. An eternal reminder pollutes.
- `project_*` for a closed project: don't delete; update status to "closed" and
  keep as linked historical reference.
- Before deleting any note: check who points to it (`audit_kb.py` shows incoming
  links) and repoint or remove those links first, to avoid creating new broken links.

## Recommended cadence

- **End of day** ("wrap up"): save to both systems + quick audit of both folders to
  ensure nothing was born disconnected that day.
- **Weekly**: audit + snapshot on both folders + cloud durability check.
- **Before migrating machines**: full cleanup + cloud check + backup.
