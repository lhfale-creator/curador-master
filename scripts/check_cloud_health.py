#!/usr/bin/env python3
"""Curador - cloud durability checker.

Ensures the knowledge base is actually in the cloud and nothing important
lives only locally. Core rule: EVERYTHING in the vault (cloud-synced), nothing outside.

Supports: OneDrive, Dropbox, Google Drive (Windows + macOS).

Usage:
    python check_cloud_health.py --vault "<vault folder>" [--extra-dir "<dir>"] [--json]
    python check_cloud_health.py --config curador.json
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

FILE_ATTRIBUTE_OFFLINE = 0x00001000
FILE_ATTRIBUTE_RECALL_ON_OPEN = 0x00040000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000
FILE_ATTRIBUTE_PINNED = 0x00080000
FILE_ATTRIBUTE_UNPINNED = 0x00100000
INVALID = 0xFFFFFFFF

KNOWLEDGE_EXT = re.compile(r"\.(md|pdf|docx?|pptx?)$", re.I)
PROJECT_MARKERS = {".git", "package.json", "SKILL.md", "requirements.txt",
                   "pyproject.toml", "node_modules", "Cargo.toml", "go.mod", ".venv"}


def load_config(config_path=None):
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


def win_attrs(path):
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


def cloud_roots():
    """All known cloud sync roots: OneDrive, Dropbox, Google Drive (Windows + macOS)."""
    roots = []
    home = os.path.expanduser("~")

    # ---- OneDrive ----
    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        v = os.environ.get(var)
        if v and os.path.isdir(v):
            roots.append(v)
    mac_cs = os.path.join(home, "Library", "CloudStorage")
    if os.path.isdir(mac_cs):
        for d in os.listdir(mac_cs):
            if d.lower().startswith("onedrive"):
                roots.append(os.path.join(mac_cs, d))

    # ---- Dropbox ----
    for candidate in [
        os.environ.get("DROPBOX", ""),
        os.path.join(home, "Dropbox"),
        os.path.join(home, "Dropbox (Personal)"),
        os.path.join(home, "Dropbox (Business)"),
    ]:
        if candidate and os.path.isdir(candidate):
            roots.append(candidate)
    # Dropbox info file (cross-platform)
    for info_path in [
        os.path.join(os.environ.get("APPDATA", ""), "Dropbox", "info.json"),
        os.path.join(home, ".dropbox", "info.json"),
        os.path.join(home, "Library", "Preferences", "Dropbox", "info.json"),
    ]:
        if os.path.exists(info_path):
            try:
                with open(info_path, "r", encoding="utf-8") as f:
                    info = json.load(f)
                for acct in info.values():
                    p = acct.get("path", "")
                    if p and os.path.isdir(p):
                        roots.append(p)
            except Exception:
                pass

    # ---- Google Drive ----
    for candidate in [
        os.path.join(home, "Google Drive"),
        os.path.join(home, "GoogleDrive"),
        os.path.join(home, "My Drive"),
    ]:
        if os.path.isdir(candidate):
            roots.append(candidate)
    if os.path.isdir(mac_cs):
        for d in os.listdir(mac_cs):
            if "google" in d.lower() or "mydrive" in d.lower():
                roots.append(os.path.join(mac_cs, d))
    # Google Drive for Desktop (Windows)
    for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
        gdrive = f"{letter}:\\My Drive"
        if os.path.isdir(gdrive):
            roots.append(gdrive)

    return sorted({os.path.normcase(os.path.abspath(r)) for r in roots if r})


def under(path, roots):
    p = os.path.normcase(os.path.abspath(path))
    return any(p == r or p.startswith(r + os.sep) for r in roots)


def sync_running():
    """Check if any sync client is running (Windows only). Returns list of running clients."""
    if os.name != "nt":
        return None
    running = []
    clients = {
        "OneDrive.exe": "OneDrive",
        "Dropbox.exe": "Dropbox",
        "googledrivesync.exe": "Google Drive (old)",
        "GoogleDriveFS.exe": "Google Drive",
    }
    try:
        out = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=15)
        for exe, name in clients.items():
            if exe.lower() in out.stdout.lower():
                running.append(name)
    except Exception:
        return None
    return running


def icloud_vault_candidates():
    home = os.path.expanduser("~")
    cands = []
    for g in [
        os.path.join(home, "Library", "Mobile Documents", "iCloud~md~obsidian"),
        os.path.join(home, "iCloudDrive"),
        os.path.join(home, "Library", "Mobile Documents", "com~apple~CloudDocs"),
    ]:
        if os.path.isdir(g):
            cands.append(g)
    return cands


def scan_loose(vault_root, extra_dirs):
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
    loose, seen = [], set()
    for r in roots:
        if not os.path.isdir(r):
            continue
        for dp, dn, fns in os.walk(r):
            if os.path.normcase(os.path.abspath(dp)).startswith(vault_nc):
                dn[:] = []; continue
            if PROJECT_MARKERS & set(fns + dn):
                dn[:] = []; continue
            dn[:] = [d for d in dn if not d.startswith(".")
                     and d not in ("node_modules", "__pycache__", "AppData", "Library")]
            if os.path.relpath(dp, r).count(os.sep) >= 1:
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
    return {"path": newest[0], "date": datetime.date.fromtimestamp(newest[1]).isoformat()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument("--extra-dir", action="append", default=[])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if not args.vault and cfg.get("vault"):
        args.vault = os.path.expanduser(cfg["vault"])
    extra_dirs = args.extra_dir + [os.path.expanduser(d) for d in (cfg.get("extra_dirs") or [])]

    if not args.vault:
        print("ERROR: --vault required (or set 'vault' in curador.json)", file=sys.stderr)
        sys.exit(2)

    vault = os.path.abspath(args.vault)
    if not os.path.isdir(vault):
        print(f"ERROR: vault not found: {vault}", file=sys.stderr)
        sys.exit(2)

    roots = cloud_roots()
    in_cloud = under(vault, roots)
    running = sync_running()
    icloud = icloud_vault_candidates()
    loose = scan_loose(vault, extra_dirs)
    bk = last_backup()

    online_only, total_md = [], 0
    for dp, dn, fns in os.walk(vault):
        dn[:] = [d for d in dn if d not in (".git", ".obsidian", ".trash", "node_modules")]
        for fn in fns:
            if fn.lower().endswith(".md"):
                total_md += 1
                if is_online_only(win_attrs(os.path.join(dp, fn))):
                    online_only.append(os.path.relpath(os.path.join(dp, fn), vault))

    risks = []
    if not in_cloud:
        risks.append("CRITICAL: vault is NOT under any cloud sync root (OneDrive/Dropbox/Google Drive).")
    if running is not None and not running:
        risks.append("ALERT: no sync client running — nothing is uploading right now.")
    not_mirrored = [x for x in loose if not x["mirrored_in_vault"]]
    if not_mirrored:
        risks.append(f"WARNING: {len(not_mirrored)} knowledge file(s) outside the vault with no copy in vault.")
    if icloud:
        risks.append(f"NOTE: {len(icloud)} possible parallel vault(s) in iCloud — confirm single source of truth.")
    if bk is None:
        risks.append("NOTE: no local curador-backup-* found.")

    print("=" * 60)
    print("CURADOR — CLOUD DURABILITY CHECK")
    print(f"vault: {vault}")
    print("=" * 60)
    print(f"\nCloud roots detected ({len(roots)}):")
    for r in roots:
        print(f"  {r}")
    if not roots:
        print("  (none — OneDrive/Dropbox/Google Drive not detected)")
    print(f"Vault under cloud root: {'YES' if in_cloud else 'NO'}")
    if running is None:
        print("Sync client running: (unknown — non-Windows)")
    elif running:
        print(f"Sync client running: YES ({', '.join(running)})")
    else:
        print("Sync client running: NO")
    print(f"Notes (.md) in vault: {total_md}  |  online-only: {len(online_only)}")
    print(f"Last local backup: {bk['date'] + '  ' + bk['path'] if bk else '(none)'}")

    print(f"\n## KNOWLEDGE FILES OUTSIDE VAULT ({len(loose)})")
    if not loose:
        print("  ok — nothing loose found")
    for x in loose:
        flag = "" if x["mirrored_in_vault"] else "  <-- NO copy in vault"
        print(f"  - {x['path']}{flag}")

    if icloud:
        print(f"\n## POSSIBLE PARALLEL VAULT (iCloud) ({len(icloud)})")
        for c in icloud:
            print(f"  - {c}")

    if online_only:
        print(f"\n## ONLINE-ONLY NOTES ({len(online_only)}) — in cloud, download on open")
        for r in online_only[:30]:
            print(f"  - {r}")
        if len(online_only) > 30:
            print(f"  ... +{len(online_only) - 30}")

    print("\n" + "=" * 60)
    print("DURABILITY VERDICT")
    if not risks:
        print("  OK — vault in cloud, sync running, no loose files.")
    else:
        for r in risks:
            print(f"  - {r}")
    print("=" * 60)

    if args.json:
        print("<<<JSON>>>")
        print(json.dumps({
            "vault": vault, "cloud_roots": roots, "vault_under_cloud": in_cloud,
            "sync_running": running, "total_md": total_md, "online_only": online_only,
            "loose_files": loose, "icloud_candidates": icloud, "last_backup": bk, "risks": risks,
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
