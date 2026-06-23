#!/usr/bin/env python3
"""Curador - cloud durability checker.

Ensures the knowledge base is actually in the cloud and nothing important
lives only locally. Core rule: EVERYTHING in the vault (OneDrive/iCloud/Dropbox),
nothing outside.

Checks:
  1. Is the vault under the synced cloud root? (path + environment variable)
  2. Is the cloud sync process running? (Windows) -> if not, nothing is uploading.
  3. Knowledge files stranded outside the vault (tmp, Desktop, Downloads,
     Documents root) that should have a master copy in the vault.
     (.md/.pdf/.docx/.pptx)
  4. Parallel vault in iCloud (divergent source) - divergence alert.
  5. Online-only notes (dehydrated placeholder): ARE in the cloud (durability ok),
     informative only - they download on open.
  6. Recency of the last local backup (tmp/curador-backup-*).

Deterministic, zero external dependencies. Works on Windows (NTFS attrs via ctypes)
and macOS (iCloud/OneDrive paths). Output: report + durability verdict.

Usage:
    python check_cloud_health.py --vault "<vault folder>" [--extra-dir "<dir>"] [--json]
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

# NTFS attributes relevant for OneDrive Files On-Demand (Windows)
FILE_ATTRIBUTE_OFFLINE = 0x00001000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x00040000          # placeholder (online-only)
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000   # dehydrated (cloud only)
FILE_ATTRIBUTE_PINNED = 0x00080000                  # "always keep on this device"
FILE_ATTRIBUTE_UNPINNED = 0x00100000                # eligible for "free up space"
INVALID = 0xFFFFFFFF

# knowledge deliverables (not transient data: .csv/.xlsx are dumps, ignored)
KNOWLEDGE_EXT = re.compile(r"\.(md|pdf|docx?|pptx?)$", re.I)
# scratch/disposable folders where permanent knowledge should NOT be born
SCRATCH_HINTS = ["tmp", "temp", "desktop", "downloads", "documents", "documentos"]


def win_attrs(path):
    """NTFS attributes via ctypes (Windows). None outside Windows or on error."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        fn = ctypes.windll.kernel32.GetFileAttributesW
        fn.argtypes = [wintypes.LPCWSTR]
        fn.restype = wintypes.DWORD
        a = fn(str(path))
        return None if a == INVALID else a
    except Exception:
        return None


def is_online_only(attrs):
    if attrs is None:
        return False
    return bool(attrs & (FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
                         | FILE_ATTRIBUTE_RECALL_ON_OPEN
                         | FILE_ATTRIBUTE_OFFLINE))


def onedrive_roots():
    """Synced roots known by the OS (environment variables)."""
    roots = []
    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        v = os.environ.get(var)
        if v and os.path.isdir(v):
            roots.append(os.path.normcase(os.path.abspath(v)))
    # macOS: typical CloudStorage path
    home = os.path.expanduser("~")
    mac_od = os.path.join(home, "Library", "CloudStorage")
    if os.path.isdir(mac_od):
        for d in os.listdir(mac_od):
            if d.lower().startswith("onedrive"):
                roots.append(os.path.normcase(os.path.join(mac_od, d)))
    return sorted(set(roots))


def under(path, roots):
    p = os.path.normcase(os.path.abspath(path))
    return any(p == r or p.startswith(r + os.sep) for r in roots)


def onedrive_running():
    """True/False/None(unknown). Only tries on Windows."""
    if os.name != "nt":
        return None
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq OneDrive.exe"],
                             capture_output=True, text=True, timeout=15)
        return "OneDrive.exe" in out.stdout
    except Exception:
        return None


def icloud_vault_candidates():
    """Look for a parallel vault in iCloud (divergent source)."""
    home = os.path.expanduser("~")
    cands = []
    guesses = [
        os.path.join(home, "Library", "Mobile Documents", "iCloud~md~obsidian"),
        os.path.join(home, "iCloudDrive"),
        os.path.join(home, "Library", "Mobile Documents", "com~apple~CloudDocs"),
    ]
    for g in guesses:
        if os.path.isdir(g):
            cands.append(g)
    return cands


# markers that a folder is a code project/tool, NOT loose knowledge
PROJECT_MARKERS = {".git", "package.json", "SKILL.md", "requirements.txt",
                   "pyproject.toml", "node_modules", "Cargo.toml", "go.mod", ".venv"}


def scan_loose(vault_root, extra_dirs):
    """Find knowledge files (deliverables/notes) stranded in scratch folders
    that should have a master copy in the vault. Stays shallow and SKIPS
    folders that are code projects (cloned repos, skills, etc.) — they live
    in a repo, not as loose knowledge."""
    vault_nc = os.path.normcase(os.path.abspath(vault_root))
    home = os.path.expanduser("~")
    roots = [
        os.path.join("C:\\", "tmp") if os.name == "nt" else "/tmp",
        os.path.join(home, "Desktop"),
        os.path.join(home, "Downloads"),
    ] + list(extra_dirs or [])
    vault_basenames = set()
    for dp, dn, fns in os.walk(vault_root):
        dn[:] = [d for d in dn if d not in (".git", ".obsidian", ".trash", "node_modules")]
        for fn in fns:
            if KNOWLEDGE_EXT.search(fn):
                vault_basenames.add(fn.lower())
    loose = []
    seen = set()
    for r in roots:
        if not os.path.isdir(r):
            continue
        for dp, dn, fns in os.walk(r):
            if os.path.normcase(os.path.abspath(dp)).startswith(vault_nc):
                dn[:] = []
                continue
            if PROJECT_MARKERS & set(fns + dn):
                dn[:] = []
                continue
            dn[:] = [d for d in dn if not d.startswith(".")
                     and d not in ("node_modules", "__pycache__", "AppData", "Library")]
            depth = os.path.relpath(dp, r).count(os.sep)
            if depth >= 1:
                dn[:] = []
            for fn in fns:
                if not KNOWLEDGE_EXT.search(fn):
                    continue
                if fn.lower() in ("readme.md", "license.md", "changelog.md",
                                  "contributing.md", "third_party_notices.md"):
                    continue
                full = os.path.abspath(os.path.join(dp, fn))
                if full in seen:
                    continue
                seen.add(full)
                loose.append({"path": full, "mirrored_in_vault": fn.lower() in vault_basenames})
    return loose


def last_backup():
    base = "C:\\tmp" if os.name == "nt" else "/tmp"
    if not os.path.isdir(base):
        return None
    newest = None
    for d in os.listdir(base):
        if d.startswith("curador-backup-"):
            full = os.path.join(base, d)
            if os.path.isdir(full):
                m = os.path.getmtime(full)
                if newest is None or m > newest[1]:
                    newest = (full, m)
    if not newest:
        return None
    return {"path": newest[0],
            "date": datetime.date.fromtimestamp(newest[1]).isoformat()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True, help="Obsidian vault root folder")
    ap.add_argument("--extra-dir", action="append", default=[],
                    help="extra scratch folder to scan for loose files")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    vault = os.path.abspath(args.vault)
    if not os.path.isdir(vault):
        print(f"ERROR: vault not found: {vault}", file=sys.stderr)
        sys.exit(2)

    roots = onedrive_roots()
    in_cloud = under(vault, roots)
    running = onedrive_running()
    icloud = icloud_vault_candidates()
    loose = scan_loose(vault, args.extra_dir)
    bk = last_backup()

    online_only = []
    total_md = 0
    for dp, dn, fns in os.walk(vault):
        dn[:] = [d for d in dn if d not in (".git", ".obsidian", ".trash", "node_modules")]
        for fn in fns:
            if fn.lower().endswith(".md"):
                total_md += 1
                a = win_attrs(os.path.join(dp, fn))
                if is_online_only(a):
                    online_only.append(os.path.relpath(os.path.join(dp, fn), vault))

    risks = []
    if not in_cloud:
        risks.append("CRITICAL: vault is NOT under the synced OneDrive root - "
                     "changes may not upload to the cloud.")
    if running is False:
        risks.append("ALERT: OneDrive process is not running - nothing is syncing right now.")
    not_mirrored = [x for x in loose if not x["mirrored_in_vault"]]
    if not_mirrored:
        risks.append(f"WARNING: {len(not_mirrored)} knowledge file(s) outside the vault "
                     "with no copy in vault (rule: nothing outside).")
    if len(icloud) > 0:
        risks.append(f"NOTE: {len(icloud)} possible parallel vault(s) in iCloud - "
                     "confirm single source of truth is OneDrive.")
    if bk is None:
        risks.append("NOTE: no local curador-backup-* found.")

    print("=" * 60)
    print("CURADOR - CLOUD DURABILITY CHECK")
    print(f"vault: {vault}")
    print("=" * 60)
    print(f"\nOneDrive roots detected: {roots or '(none via env vars)'}")
    print(f"Vault under synced OneDrive: {'YES' if in_cloud else 'NO'}")
    running_txt = "YES" if running else ("NO" if running is False else "(unknown)")
    print(f"OneDrive process running: {running_txt}")
    print(f"Notes (.md) in vault: {total_md}  |  online-only (cloud only right now): {len(online_only)}")
    print(f"Last local backup: {bk['date'] + '  ' + bk['path'] if bk else '(none)'}")

    print(f"\n## KNOWLEDGE FILES OUTSIDE THE VAULT ({len(loose)})")
    if not loose:
        print("  ok - nothing loose found in scratch folders")
    for x in loose:
        flag = "" if x["mirrored_in_vault"] else "  <-- NO copy in vault"
        print(f"  - {x['path']}{flag}")

    if icloud:
        print(f"\n## POSSIBLE PARALLEL VAULT (iCloud) ({len(icloud)})")
        for c in icloud:
            print(f"  - {c}")

    if online_only:
        print(f"\n## ONLINE-ONLY NOTES (in cloud, download on open) ({len(online_only)})")
        for r in online_only[:30]:
            print(f"  - {r}")
        if len(online_only) > 30:
            print(f"  ... +{len(online_only) - 30}")

    print("\n" + "=" * 60)
    print("DURABILITY VERDICT")
    if not risks:
        print("  OK - base in cloud, syncing, no loose knowledge files.")
    else:
        for r in risks:
            print(f"  - {r}")
    print("=" * 60)

    if args.json:
        print("<<<JSON>>>")
        print(json.dumps({
            "vault": vault, "onedrive_roots": roots, "vault_under_onedrive": in_cloud,
            "onedrive_running": running, "total_md": total_md,
            "online_only": online_only, "loose_files": loose,
            "icloud_candidates": icloud, "last_backup": bk, "risks": risks,
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
