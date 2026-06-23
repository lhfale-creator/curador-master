#!/usr/bin/env bash
# Curador — full run: audit memory + vault + cloud check
# Usage: ./run.sh [--summary] [--write] [--snapshot]
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

RUN_AUDIT() {
  local path="$1"
  local snap_args=()
  [ -n "$SNAPSHOT" ] && snap_args=(--snapshot "$SNAPSHOT")
  python3 "$DIR/scripts/audit_kb.py" --path "$path" "${snap_args[@]}" "$@"
}

[ -n "$MEMORY" ] && { echo "=== memory ==="; RUN_AUDIT "$MEMORY" "${@}"; echo; }
[ -n "$VAULT" ]  && { echo "=== vault ===";  RUN_AUDIT "$VAULT"  "${@}"; echo; }
[ -n "$VAULT" ]  && { echo "=== cloud ===";  python3 "$DIR/scripts/check_cloud_health.py" --vault "$VAULT"; }
