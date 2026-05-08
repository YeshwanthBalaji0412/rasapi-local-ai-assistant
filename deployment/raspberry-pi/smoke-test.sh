#!/usr/bin/env bash
# RasaPi — smoke test.
#
# Hits a small set of endpoints and prints PASS/FAIL per row. Safe to run
# repeatedly. Does not modify state beyond what the endpoints themselves do
# (one memory insert + one sensitive-block test).
#
# Usage:
#   bash deployment/raspberry-pi/smoke-test.sh
#   BASE_URL=http://192.168.1.50:8000 bash deployment/raspberry-pi/smoke-test.sh

BASE_URL=${BASE_URL:-http://127.0.0.1:8000}

# Don't use -e — we want every check to run even if one fails.
fail_count=0

ok()   { printf "  PASS  %s\n" "$1"; }
fail() { printf "  FAIL  %s — %s\n" "$1" "$2"; fail_count=$((fail_count + 1)); }

check_status() {
  local label="$1" url="$2" expected="$3"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" "$url" || echo "000")
  if [ "$code" = "$expected" ]; then
    ok "$label  →  HTTP $code"
  else
    fail "$label" "got HTTP $code, expected $expected"
  fi
}

check_post_intent() {
  local label="$1" query="$2" expected_intent="$3"
  local body
  body=$(curl -s -X POST "$BASE_URL/ask" \
    -H 'Content-Type: application/json' \
    -d "{\"query\":\"$query\"}")
  if printf '%s' "$body" | grep -q "\"intent\":\"$expected_intent\""; then
    ok "$label  →  intent=$expected_intent"
  else
    fail "$label" "expected intent=$expected_intent in response, got: ${body:0:200}"
  fi
}

echo ""
echo "Smoke testing $BASE_URL"
echo ""

check_status        "GET /health"                  "$BASE_URL/health"             200
check_status        "GET /commands"                "$BASE_URL/commands"           200
check_status        "GET /dashboard"               "$BASE_URL/dashboard"          200
check_status        "GET /dashboard/health"        "$BASE_URL/dashboard/health"   200
check_status        "GET /briefing/sources"        "$BASE_URL/briefing/sources"   200

check_post_intent   "POST /ask  (greeting)"        "hello"                              "greeting"
check_post_intent   "POST /ask  (time)"            "what time is it"                    "time"
check_post_intent   "POST /ask  (save_memory)"     "remember that my project is RasaPi" "save_memory"
check_post_intent   "POST /ask  (sensitive block)" "remember that my password is secret" "save_memory"

echo ""
if [ "$fail_count" -eq 0 ]; then
  echo "All smoke tests PASSED."
  exit 0
else
  echo "$fail_count smoke test(s) FAILED."
  exit 1
fi
