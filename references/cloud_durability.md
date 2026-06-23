# Cloud durability (rule: nothing outside the vault)

Knowledge is only durable if it lives in the cloud. Core rule:
**EVERYTHING inside the vault (Obsidian/cloud sync). Nothing outside.**
Scratch folders (`/tmp`, Desktop, Downloads) are disposable: anything produced
there must get a master copy in the vault before ending the task.

## Why it matters

- The vault sits inside your cloud sync root (OneDrive/iCloud/Dropbox). Every edit
  automatically goes to the cloud (if the sync process is running). That's the live backup.
- A file outside that root doesn't sync. If the machine dies, it's gone. That's
  why the curator hunts for loose knowledge files and asks you to bring them to the vault.
- **Machine migration**: if the single source of truth is OneDrive, signing into
  OneDrive on the new machine is all it takes. A parallel vault on iCloud breaks
  the single source.

## How to run

```bash
# Windows: force UTF-8 first
# $env:PYTHONUTF8=1; $env:PYTHONIOENCODING="utf-8"

python scripts/check_cloud_health.py --vault "<path/to/your/vault>" \
    [--extra-dir "<extra-scratch-dir>"] [--json]
```

## What the check verifies

| Check | Meaning | Action if it fails |
|---|---|---|
| Vault under cloud root | vault path is inside the synced root (`%OneDrive%`, iCloud, etc.) | CRITICAL: move vault inside the cloud sync folder |
| Sync process running | `OneDrive.exe` (Windows) / equivalent active | ALERT: open the sync app; nothing is syncing while it's stopped |
| Loose files | `.md/.pdf/.docx/.pptx` in scratch without a copy in vault | bring master copy to vault, then discard the scratch version |
| Parallel vault (iCloud) | evidence of a second vault source (`~/iCloudDrive`, `Mobile Documents`) | confirm single source of truth; don't edit in both |
| Online-only notes | dehydrated placeholder (content only in cloud right now) | informative: IS in the cloud (durability ok), downloads on open |
| Local backup | most recent `curador-backup-*` in scratch | run a backup before any `--write` |

### How online-only is detected (Windows)

Via NTFS attributes from OneDrive Files On-Demand (ctypes `GetFileAttributesW`):
`FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS` (0x400000) and
`FILE_ATTRIBUTE_RECALL_ON_OPEN` (0x40000) = dehydrated placeholder (content only
in cloud). `PINNED` (0x80000) = "always keep on this device". `UNPINNED`
(0x100000) = eligible for "free up space". Online-only is NOT a durability risk:
the file can only be dehydrated because it already uploaded. The real risk is a
file outside the cloud sync root.

## The loose-file scan (high signal, low noise)

- Scans only scratch areas (`/tmp` or `C:\tmp`, Desktop, Downloads + `--extra-dir`),
  shallow (root + 1 level).
- SKIPS folders that are code projects (contain `.git`, `package.json`, `SKILL.md`,
  `requirements.txt`, `node_modules` etc.): a cloned repo is not "loose knowledge".
- Ignores `README/LICENSE/CHANGELOG` and transient data files.
- Marks each file as "has copy in vault" or "NO copy" (by filename).

## macOS

The script detects OneDrive at `~/Library/CloudStorage/OneDrive-*` and iCloud at
`~/Library/Mobile Documents`. The rule doesn't change: single source in your
chosen cloud provider. When migrating to a new Mac, running the check confirms
that the vault fully synced before relying on it.
