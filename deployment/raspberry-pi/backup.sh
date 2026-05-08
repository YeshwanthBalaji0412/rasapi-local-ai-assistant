#!/usr/bin/env bash
# RasaPi — local backup.
#
# Copies the SQLite database and audit log files into a timestamped folder
# under ~/rasapi-backups/. Never includes the .env file. Safe to run while
# the service is up — SQLite reads are non-destructive — but for a fully
# consistent snapshot, stop the service first:
#     sudo systemctl stop rasapi
#
# Usage:
#   bash deployment/raspberry-pi/backup.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATA_FILE="$REPO_ROOT/backend/data/rasapi.db"
LOGS_DIR="$REPO_ROOT/logs"
BACKUP_ROOT="${BACKUP_ROOT:-$HOME/rasapi-backups}"

stamp=$(date -u +%Y-%m-%dT%H-%M-%SZ)
dest="$BACKUP_ROOT/$stamp"
mkdir -p "$dest"

copied_anything=0

if [ -f "$DATA_FILE" ]; then
  cp "$DATA_FILE" "$dest/rasapi.db"
  echo "  copied SQLite DB → $dest/rasapi.db"
  copied_anything=1
else
  echo "  (skipped: $DATA_FILE does not exist)"
fi

if [ -d "$LOGS_DIR" ]; then
  shopt -s nullglob
  jsonl_files=("$LOGS_DIR"/audit-*.jsonl)
  shopt -u nullglob
  if [ ${#jsonl_files[@]} -gt 0 ]; then
    cp "${jsonl_files[@]}" "$dest/"
    echo "  copied ${#jsonl_files[@]} audit log file(s) → $dest/"
    copied_anything=1
  else
    echo "  (skipped: no audit-*.jsonl files in $LOGS_DIR)"
  fi
else
  echo "  (skipped: $LOGS_DIR does not exist)"
fi

# Explicitly NOT included in any backup:
#   - $REPO_ROOT/.env  (may contain secrets)
#   - any os env vars
#   - source code (already in git)

if [ "$copied_anything" -eq 0 ]; then
  echo ""
  echo "Nothing to back up. Removing empty backup directory."
  rmdir "$dest" || true
  exit 1
fi

echo ""
echo "Backup written to: $dest"
echo "(.env is intentionally not backed up.)"
