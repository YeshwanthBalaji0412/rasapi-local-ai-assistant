#!/usr/bin/env bash
# RasaPi — restore from a backup directory.
#
# Restores rasapi.db and audit log files from the given backup directory.
# Never overwrites .env. Stop the service first for a clean restore:
#     sudo systemctl stop rasapi
#     bash deployment/raspberry-pi/restore.sh ~/rasapi-backups/<timestamp>
#     sudo systemctl start rasapi
#
# Usage:
#   bash deployment/raspberry-pi/restore.sh <backup-directory>

set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <backup-directory>" >&2
  echo "Example: $0 ~/rasapi-backups/2026-05-08T15-30-00Z" >&2
  exit 1
fi

SOURCE="$1"
if [ ! -d "$SOURCE" ]; then
  echo "Error: backup directory not found: $SOURCE" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATA_FILE="$REPO_ROOT/backend/data/rasapi.db"
LOGS_DIR="$REPO_ROOT/logs"

# Pre-flight reminder.
if systemctl is-active --quiet rasapi 2>/dev/null; then
  echo "WARNING: rasapi service appears to be running."
  echo "Stop it before restoring to avoid corruption:"
  echo "    sudo systemctl stop rasapi"
  echo ""
fi

mkdir -p "$(dirname "$DATA_FILE")"
mkdir -p "$LOGS_DIR"

if [ -f "$SOURCE/rasapi.db" ]; then
  cp "$SOURCE/rasapi.db" "$DATA_FILE"
  echo "  restored DB → $DATA_FILE"
fi

shopt -s nullglob
jsonl_files=("$SOURCE"/audit-*.jsonl)
shopt -u nullglob
if [ ${#jsonl_files[@]} -gt 0 ]; then
  cp "${jsonl_files[@]}" "$LOGS_DIR/"
  echo "  restored ${#jsonl_files[@]} audit log file(s) → $LOGS_DIR/"
fi

# Explicitly NOT touched by restore:
#   - $REPO_ROOT/.env  (must be configured manually)
#   - source code

echo ""
echo "Restore complete."
echo "Next: sudo systemctl start rasapi"
