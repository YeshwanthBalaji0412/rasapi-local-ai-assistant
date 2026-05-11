#!/usr/bin/env bash
# RasaPi — scheduled daily briefing refresh.
#
# Calls POST /briefing/refresh on the local backend. Designed for cron or
# a systemd .timer. Never starts the backend itself — if rasapi is not
# running, the script exits non-zero and logs to stderr.
#
# Auth handling:
#   /briefing/refresh is currently unauthenticated (it's a read-only
#   aggregation of public sources). If the operator has set
#   AUTH_PROTECT_MUTATIONS=true and added a Depends-guard to that route
#   in the future, set RASA_API_KEY or RASA_API_KEY_FILE to authenticate.
#   The key value is never printed and is never embedded in the URL.
#
# Usage:
#   bash deployment/raspberry-pi/run-daily-briefing.sh
#   BASE_URL=http://127.0.0.1:8000 bash deployment/raspberry-pi/run-daily-briefing.sh
#
# Cron example (every day at 06:30 local):
#   30 6 * * * /usr/bin/bash /home/yesh/rasapi-local-ai-assistant/deployment/raspberry-pi/run-daily-briefing.sh

set -euo pipefail

BASE_URL=${BASE_URL:-http://127.0.0.1:8000}
KEY_FILE=${RASA_API_KEY_FILE:-/etc/rasapi/key}

api_key=""
if [ -n "${RASA_API_KEY:-}" ]; then
  api_key="$RASA_API_KEY"
elif [ -r "$KEY_FILE" ]; then
  api_key="$(cat "$KEY_FILE")"
fi

curl_args=(-fsS -o /dev/null -w "%{http_code}" -m 60 -X POST)
if [ -n "$api_key" ]; then
  curl_args+=(-H "X-RasaPi-Key: $api_key")
fi

http_code=$("${curl_args[@]}" "$BASE_URL/briefing/refresh" || true)
unset api_key

case "$http_code" in
  200)
    echo "OK: briefing refresh succeeded"
    exit 0
    ;;
  *)
    echo "FAIL: $BASE_URL/briefing/refresh returned HTTP $http_code" >&2
    exit 1
    ;;
esac
