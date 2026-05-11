#!/usr/bin/env bash
# RasaPi — log and audio cleanup with safe defaults.
#
# Prunes:
#   - audit JSONL files older than LOG_RETENTION_DAYS (default 30)
#   - temp audio files older than AUDIO_TMP_RETENTION_HOURS (default 24)
#
# Paths are hardcoded relative to the repo root. The script never reads
# a path from an environment variable, so an attacker who can set env
# vars cannot point it at /etc or /home.
#
# Pass --dry-run to print what would be deleted without deleting anything.
#
# Usage:
#   bash deployment/raspberry-pi/run-log-cleanup.sh
#   bash deployment/raspberry-pi/run-log-cleanup.sh --dry-run
#   LOG_RETENTION_DAYS=7 bash deployment/raspberry-pi/run-log-cleanup.sh
#
# Cron example (daily at 04:00):
#   0 4 * * * /usr/bin/bash /home/yesh/rasapi-local-ai-assistant/deployment/raspberry-pi/run-log-cleanup.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOGS_DIR="$REPO_ROOT/logs"
AUDIO_DIR="$REPO_ROOT/backend/data/audio_tmp"

LOG_RETENTION_DAYS=${LOG_RETENTION_DAYS:-30}
AUDIO_TMP_RETENTION_HOURS=${AUDIO_TMP_RETENTION_HOURS:-24}
DRY_RUN=0

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done

prune_logs() {
  if [ ! -d "$LOGS_DIR" ]; then
    return 0
  fi
  while IFS= read -r -d '' f; do
    if [ "$DRY_RUN" -eq 1 ]; then
      echo "DRY-RUN: would remove $f"
    else
      rm -f -- "$f"
      echo "Removed log: $f"
    fi
  done < <(find "$LOGS_DIR" -mindepth 1 -maxdepth 1 -type f \
             -name 'audit-*.jsonl' -mtime "+$LOG_RETENTION_DAYS" -print0)
}

prune_audio() {
  if [ ! -d "$AUDIO_DIR" ]; then
    return 0
  fi
  # mmin is in minutes — convert hours.
  local mins=$(( AUDIO_TMP_RETENTION_HOURS * 60 ))
  while IFS= read -r -d '' f; do
    if [ "$DRY_RUN" -eq 1 ]; then
      echo "DRY-RUN: would remove $f"
    else
      rm -f -- "$f"
      echo "Removed audio: $f"
    fi
  done < <(find "$AUDIO_DIR" -mindepth 1 -maxdepth 1 -type f \
             \( -name '*.wav' -o -name '*.raw' -o -name '*.flac' -o -name '*.ogg' \) \
             -mmin "+$mins" -print0)
}

prune_logs
prune_audio

echo "OK: cleanup complete (logs>${LOG_RETENTION_DAYS}d, audio>${AUDIO_TMP_RETENTION_HOURS}h)"
