#!/usr/bin/env bash
# RasaPi — readiness audit (Phase 10).
#
# Big PASS/FAIL audit of a running RasaPi install. Safe to run repeatedly.
# Does not modify state. Does not print secrets. Exits non-zero if any
# check fails.
#
# Usage:
#   bash deployment/raspberry-pi/check-readiness.sh
#   RASA_API_KEY=... bash deployment/raspberry-pi/check-readiness.sh
#   BASE_URL=http://10.0.0.118:8000 bash deployment/raspberry-pi/check-readiness.sh

BASE_URL=${BASE_URL:-http://127.0.0.1:8000}
RASA_API_KEY=${RASA_API_KEY:-}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

fail_count=0

ok()   { printf "  PASS  %s\n" "$1"; }
fail() { printf "  FAIL  %s — %s\n" "$1" "$2"; fail_count=$((fail_count + 1)); }
info() { printf "  ----  %s\n" "$1"; }

_http() {
  curl -s -o /dev/null -w "%{http_code}" -m 5 "$@" || echo "000"
}

_curl_with_key() {
  if [ -n "$RASA_API_KEY" ]; then
    _http -H "X-RasaPi-Key: $RASA_API_KEY" "$@"
  else
    _http "$@"
  fi
}

echo ""
echo "RasaPi readiness check against $BASE_URL"
echo "(set RASA_API_KEY=… to exercise auth-protected paths)"
echo ""

# ── filesystem layout ───────────────────────────────────────────────────────
# The service reads backend/.env (see backend/config.py). A repo-root .env
# is a common install artifact but the running service ignores it — flag it.
BACKEND_ENV="$REPO_ROOT/backend/.env"
LEGACY_ENV="$REPO_ROOT/.env"

echo "Filesystem"
[ -f "$BACKEND_ENV" ]                   && ok "backend/.env present"     || fail "backend/.env present"    "no .env at $BACKEND_ENV"
[ -d "$REPO_ROOT/backend/.venv" ]       && ok "backend/.venv present"    || fail "backend/.venv present"   "did you run install.sh?"
[ -d "$REPO_ROOT/backend/data" ]        && ok "backend/data dir"         || fail "backend/data dir"        "missing"
[ -d "$REPO_ROOT/logs" ]                && ok "logs/ dir"                || fail "logs/ dir"               "missing"

# Detect the pre-v0.11.2 backend/backend/ nesting artifact. When the systemd
# service ran with CWD=backend/, relative default paths that already started
# with "backend/" doubled up. v0.11.2 anchors those paths to the repo root
# so the nesting can't happen for new writes — but old writes may still be
# sitting on disk. Run `bash deployment/raspberry-pi/doctor.sh` for the
# migration steps.
if [ -d "$REPO_ROOT/backend/backend" ]; then
  fail "no legacy backend/backend/ nesting" "found $REPO_ROOT/backend/backend — legacy data from pre-v0.11.2; run doctor.sh for migration steps"
else
  ok "no legacy backend/backend/ nesting"
fi

# Legacy repo-root .env — silently ignored by the service, flag it.
if [ -f "$LEGACY_ENV" ]; then
  fail "no legacy repo-root .env" "found $LEGACY_ENV — the service reads backend/.env; move or delete this file"
else
  ok "no legacy repo-root .env"
fi

# backend/.env should not be world-readable.
if [ -f "$BACKEND_ENV" ]; then
  mode=$(stat -c '%a' "$BACKEND_ENV" 2>/dev/null || stat -f '%Lp' "$BACKEND_ENV" 2>/dev/null || echo "")
  if [ "$mode" = "600" ]; then
    ok "backend/.env mode is 600"
  else
    fail "backend/.env mode is 600" "current mode: ${mode:-unknown}"
  fi
fi

# ── HTTP endpoints ──────────────────────────────────────────────────────────
echo ""
echo "HTTP endpoints"

code=$(_http "$BASE_URL/health")
[ "$code" = "200" ] && ok "GET /health = 200"             || fail "GET /health"             "got $code"

code=$(_http "$BASE_URL/version")
[ "$code" = "200" ] && ok "GET /version = 200"            || fail "GET /version"            "got $code"

code=$(_http "$BASE_URL/readiness")
[ "$code" = "200" ] && ok "GET /readiness = 200"          || fail "GET /readiness"          "got $code"

code=$(_curl_with_key "$BASE_URL/config/status")
if [ "$code" = "200" ]; then
  ok "GET /config/status = 200"
elif [ "$code" = "401" ] && [ -z "$RASA_API_KEY" ]; then
  info "GET /config/status = 401 (auth on, no key provided — expected)"
else
  fail "GET /config/status" "got $code"
fi

code=$(_curl_with_key "$BASE_URL/commands")
[ "$code" = "200" ] && ok "GET /commands = 200"           || fail "GET /commands"           "got $code"

code=$(_http "$BASE_URL/dashboard/health")
[ "$code" = "200" ] && ok "GET /dashboard/health = 200"   || fail "GET /dashboard/health"   "got $code"

code=$(_http "$BASE_URL/voice/status")
[ "$code" = "200" ] && ok "GET /voice/status = 200"       || fail "GET /voice/status"       "got $code"

code=$(_curl_with_key "$BASE_URL/integrations")
if [ "$code" = "200" ] || ([ "$code" = "401" ] && [ -z "$RASA_API_KEY" ]); then
  ok "GET /integrations reachable"
else
  fail "GET /integrations" "got $code"
fi

# ── readiness JSON ──────────────────────────────────────────────────────────
echo ""
echo "Readiness JSON"
ready_body=$(curl -s -m 5 "$BASE_URL/readiness" || echo '{"ready":false}')
if echo "$ready_body" | grep -q '"ready":true'; then
  ok "readiness JSON reports ready=true"
else
  fail "readiness JSON ready=true" "body: ${ready_body:0:200}"
fi

# ── systemd (optional, only checks if systemctl exists) ─────────────────────
if command -v systemctl >/dev/null 2>&1; then
  echo ""
  echo "systemd"
  if systemctl is-active --quiet rasapi 2>/dev/null; then
    ok "rasapi.service active"
  else
    info "rasapi.service not active (skip if you run uvicorn manually)"
  fi
fi

# ── disk ────────────────────────────────────────────────────────────────────
echo ""
echo "Disk"
if command -v df >/dev/null 2>&1; then
  df -h "$REPO_ROOT" 2>/dev/null | tail -n 1 | awk '{printf "  ----  filesystem %s  size %s  used %s  free %s  use %s\n", $1,$2,$3,$4,$5}'
fi

# ── final ───────────────────────────────────────────────────────────────────
echo ""
if [ "$fail_count" -eq 0 ]; then
  echo "All readiness checks PASSED."
  exit 0
else
  echo "$fail_count check(s) FAILED."
  exit 1
fi
