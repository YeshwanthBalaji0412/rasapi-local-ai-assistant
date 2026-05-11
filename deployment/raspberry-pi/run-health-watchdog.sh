#!/usr/bin/env bash
# RasaPi — health watchdog.
#
# Checks four signals and exits non-zero if any of them fail:
#   1. systemd unit `rasapi` is active (when systemd is present)
#   2. GET /health returns 200 (public, no key)
#   3. GET /readiness reports ready=true (public)
#   4. Disk usage on the data partition is below WATCHDOG_DISK_THRESHOLD_PCT
#
# Optional: if SLACK_WEBHOOK_URL is set in the environment AND any check
# fails, post a short alert. Message body never includes the webhook URL,
# API key, hostname FQDN, or any audit content.
#
# Safety:
#   - Never reboots, never deletes data, never restarts services.
#   - Never prints the API key or webhook URL.
#   - Read-only against the running system.
#
# Usage:
#   bash deployment/raspberry-pi/run-health-watchdog.sh
#   BASE_URL=http://127.0.0.1:8000 WATCHDOG_DISK_THRESHOLD_PCT=90 \
#     bash deployment/raspberry-pi/run-health-watchdog.sh
#
# Cron example (every 15 minutes):
#   */15 * * * * /usr/bin/bash /home/yesh/rasapi-local-ai-assistant/deployment/raspberry-pi/run-health-watchdog.sh

set -euo pipefail

BASE_URL=${BASE_URL:-http://127.0.0.1:8000}
WATCHDOG_DISK_THRESHOLD_PCT=${WATCHDOG_DISK_THRESHOLD_PCT:-90}
DATA_PARTITION=${DATA_PARTITION:-/}

failures=()

# ── 1. systemd ───────────────────────────────────────────────────────────────
if command -v systemctl >/dev/null 2>&1; then
  if ! systemctl is-active --quiet rasapi; then
    failures+=("systemd: rasapi.service is not active")
  fi
fi

# ── 2. /health ───────────────────────────────────────────────────────────────
health_code=$(curl -s -o /dev/null -w "%{http_code}" -m 5 "$BASE_URL/health" || echo "000")
if [ "$health_code" != "200" ]; then
  failures+=("health: $BASE_URL/health returned HTTP $health_code")
fi

# ── 3. /readiness ────────────────────────────────────────────────────────────
ready_body=$(curl -s -m 5 "$BASE_URL/readiness" || echo "")
case "$ready_body" in
  *'"ready":true'*|*'"ready": true'*)
    : # ok
    ;;
  *)
    failures+=("readiness: $BASE_URL/readiness did not report ready=true")
    ;;
esac

# ── 4. disk ──────────────────────────────────────────────────────────────────
# df output: Filesystem 1K-blocks Used Available Use% Mounted-on
# We extract the "Use%" column and strip the % sign.
disk_pct=$(df -P "$DATA_PARTITION" 2>/dev/null | awk 'NR==2 {gsub(/%/,"",$5); print $5}')
if [ -z "$disk_pct" ]; then
  failures+=("disk: could not read usage for $DATA_PARTITION")
elif [ "$disk_pct" -ge "$WATCHDOG_DISK_THRESHOLD_PCT" ]; then
  failures+=("disk: $DATA_PARTITION at ${disk_pct}% (threshold ${WATCHDOG_DISK_THRESHOLD_PCT}%)")
fi

# ── report ───────────────────────────────────────────────────────────────────
if [ "${#failures[@]}" -eq 0 ]; then
  echo "OK: rasapi watchdog clean"
  exit 0
fi

# Short, fixed-template alert. No secrets.
hostname_short=$(hostname -s 2>/dev/null || echo "unknown")
timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)

{
  echo "RasaPi watchdog alert"
  echo "host: $hostname_short"
  echo "time: $timestamp"
  for f in "${failures[@]}"; do
    echo "- $f"
  done
} >&2

# Optional Slack post. We rely on the operator setting SLACK_WEBHOOK_URL
# in the environment OR the script reading it from /etc/rasapi/slack-webhook
# (chmod 600). The URL is never echoed.
webhook_url=""
if [ -n "${SLACK_WEBHOOK_URL:-}" ]; then
  webhook_url="$SLACK_WEBHOOK_URL"
elif [ -r /etc/rasapi/slack-webhook ]; then
  webhook_url="$(cat /etc/rasapi/slack-webhook)"
fi

if [ -n "$webhook_url" ]; then
  # Build the JSON body without echoing the webhook.
  body_lines="RasaPi watchdog alert\\nhost: $hostname_short\\ntime: $timestamp"
  for f in "${failures[@]}"; do
    # Strip any double quotes from the failure line to keep JSON valid.
    safe_f=${f//\"/}
    body_lines="${body_lines}\\n- ${safe_f}"
  done
  json_body=$(printf '{"text":"%s"}' "$body_lines")
  curl -fsS -o /dev/null -m 10 \
    -H 'Content-Type: application/json' \
    -d "$json_body" \
    "$webhook_url" || echo "WARN: Slack post failed" >&2
  unset webhook_url
fi

exit 1
