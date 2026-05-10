#!/usr/bin/env bash
# RasaPi — lightweight health check.
#
# Returns 0 if /health is 200 AND the systemd service (if present) is
# active. Suitable for cron, uptime monitors, or wrapping in a one-shot
# alert. Does NOT print secrets, does NOT modify state.
#
# Usage:
#   bash deployment/raspberry-pi/health-check.sh
#   BASE_URL=http://127.0.0.1:8000 bash deployment/raspberry-pi/health-check.sh

set -euo pipefail

BASE_URL=${BASE_URL:-http://127.0.0.1:8000}

# /health is public and never requires auth.
code=$(curl -s -o /dev/null -w "%{http_code}" -m 5 "$BASE_URL/health" || echo "000")
if [ "$code" != "200" ]; then
  echo "FAIL: $BASE_URL/health returned HTTP $code" >&2
  exit 1
fi

if command -v systemctl >/dev/null 2>&1; then
  if ! systemctl is-active --quiet rasapi; then
    echo "FAIL: rasapi.service is not active" >&2
    exit 1
  fi
fi

echo "OK: rasapi is healthy on $BASE_URL"
