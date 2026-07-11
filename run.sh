#!/usr/bin/env bash
# Curador — full run: audit memory + vault + storage + cloud check
# Usage: ./run.sh [--summary] [--write] [--project "Nome"]
set -euo pipefail
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG="$DIR/curador.json"

if [ ! -f "$CFG" ]; then
  echo "curador.json not found."
  echo "Copy curador.example.json to curador.json and fill in your paths."
  exit 1
fi

# Parse paths from JSON using Python (no jq required)
_py() { python3 -c "import json,os; d=json.load(open('$CFG')); v=d.get('$1',''); print(os.path.expanduser(v) if v else '')"; }
MEMORY=$(_py memory)
VAULT=$(_py vault)
SNAPSHOT=$(_py snapshot)

# --project is consumed here (not forwarded blindly): audit_kb.py wants
# --project-scope (a filter), storage_audit.py wants --project (scopes the walk).
PROJECT=""
PASSTHROUGH=()
while [ $# -gt 0 ]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    *) PASSTHROUGH+=("$1"); shift ;;
  esac
done

# NOTE: previously took "$@" INSIDE this function too, on top of the "$path" already
# passed as $1 — that silently re-appended the path as a stray positional argument,
# which argparse (no positional args defined) would reject as "unrecognized arguments".
RUN_AUDIT() {
  local path="$1"; shift
  local snap_args=()
  [ -n "$SNAPSHOT" ] && snap_args=(--snapshot "$SNAPSHOT")
  local scope_args=()
  [ -n "$PROJECT" ] && scope_args=(--project-scope "$PROJECT")
  python3 "$DIR/scripts/audit_kb.py" --path "$path" "${snap_args[@]}" "${scope_args[@]}" "$@"
}

[ -n "$MEMORY" ] && { echo "=== memory ==="; RUN_AUDIT "$MEMORY" "${PASSTHROUGH[@]}"; echo; }
[ -n "$VAULT" ]  && { echo "=== vault ===";  RUN_AUDIT "$VAULT"  "${PASSTHROUGH[@]}"; echo; }
if [ -n "$VAULT" ]; then
  echo "=== storage ==="
  storage_args=()
  [ -n "$SNAPSHOT" ] && storage_args+=(--snapshot "$SNAPSHOT")
  [ -n "$PROJECT" ] && storage_args+=(--project "$PROJECT")
  for a in "${PASSTHROUGH[@]}"; do [ "$a" = "--summary" ] && storage_args+=(--summary); done
  python3 "$DIR/scripts/storage_audit.py" --vault "$VAULT" "${storage_args[@]}"
  echo
  echo "=== cloud ==="
  python3 "$DIR/scripts/check_cloud_health.py" --vault "$VAULT"
fi
