#!/usr/bin/env bash
# RasaPi — scheduled backup with rotation.
#
# Wraps the existing backup.sh and then prunes backup directories under
# $BACKUP_ROOT older than BACKUP_RETENTION_DAYS. Safe for cron / systemd
# timers. Never deletes anything outside $BACKUP_ROOT.
#
# Usage:
#   bash deployment/raspberry-pi/run-backup.sh
#   BACKUP_RETENTION_DAYS=14 bash deployment/raspberry-pi/run-backup.sh
#
# Cron example (every day at 03:15):
#   15 3 * * * /usr/bin/bash /home/yesh/rasapi-local-ai-assistant/deployment/raspberry-pi/run-backup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_ROOT=${BACKUP_ROOT:-$HOME/rasapi-backups}
BACKUP_RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-14}
DRY_RUN=0

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done

# 1. Take a fresh backup using the existing audited script.
if [ "$DRY_RUN" -eq 1 ]; then
  echo "DRY-RUN: would invoke backup.sh"
else
  BACKUP_ROOT="$BACKUP_ROOT" bash "$SCRIPT_DIR/backup.sh"
fi

# 2. Rotate. Only directories directly under $BACKUP_ROOT are eligible.
if [ ! -d "$BACKUP_ROOT" ]; then
  echo "No backup root at $BACKUP_ROOT — nothing to rotate."
  exit 0
fi

# Guard against accidental empty values that would expand to "/".
if [ -z "$BACKUP_ROOT" ] || [ "$BACKUP_ROOT" = "/" ]; then
  echo "Refusing to rotate: BACKUP_ROOT is empty or root." >&2
  exit 2
fi

# Use -mindepth/-maxdepth so we only touch top-level backup folders.
while IFS= read -r -d '' dir; do
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "DRY-RUN: would remove $dir"
  else
    rm -rf -- "$dir"
    echo "Removed old backup: $dir"
  fi
done < <(find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d \
           -mtime "+$BACKUP_RETENTION_DAYS" -print0)

echo "OK: backup rotation complete (retention=${BACKUP_RETENTION_DAYS}d)"
