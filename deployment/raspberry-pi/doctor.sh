#!/usr/bin/env bash
# RasaPi — diagnostic report ("what's wrong with my install").
#
# Prints a single readable report covering filesystem, venv, .env, port,
# systemd, and recent journald errors. Does NOT print secrets, does NOT
# modify state. Useful when something feels off and check-readiness.sh
# doesn't catch it.
#
# Usage:
#   bash deployment/raspberry-pi/doctor.sh

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE_URL=${BASE_URL:-http://127.0.0.1:8000}

section() {
  echo ""
  echo "── $* ────────────────────────────────────────────────────────────────"
}

# ── 1. host info ────────────────────────────────────────────────────────────
section "Host"
echo "  hostname    : $(hostname 2>/dev/null || echo 'unknown')"
echo "  user        : ${USER:-$(whoami 2>/dev/null || echo 'unknown')}"
echo "  os          : $(uname -s) $(uname -m) ($(uname -r))"
echo "  python3     : $(python3 --version 2>/dev/null || echo 'not found')"
echo "  curl        : $(curl --version 2>/dev/null | head -n 1 || echo 'not found')"

# ── 2. repo layout ──────────────────────────────────────────────────────────
section "Repo layout"
echo "  root        : $REPO_ROOT"
[ -d "$REPO_ROOT/backend" ]              && echo "  backend/    : OK"          || echo "  backend/    : MISSING"
[ -d "$REPO_ROOT/backend/.venv" ]        && echo "  backend/.venv: OK"          || echo "  backend/.venv: MISSING (run install.sh)"
[ -d "$REPO_ROOT/backend/data" ]         && echo "  backend/data: OK"          || echo "  backend/data: MISSING"
[ -d "$REPO_ROOT/logs" ]                 && echo "  logs/       : OK"          || echo "  logs/       : MISSING"
if [ -d "$REPO_ROOT/backend/backend" ]; then
  echo "  WARNING: backend/backend exists — likely an .env path bug; check DATABASE_PATH and VOICE_AUDIO_TEMP_DIR"
fi

# ── 3. .env (presence + perms only, NEVER contents) ─────────────────────────
# The service reads backend/.env — checked first. If a repo-root .env exists
# too, flag it: it's ignored by the service and almost always a source of
# confusion.
section ".env"
BACKEND_ENV="$REPO_ROOT/backend/.env"
LEGACY_ENV="$REPO_ROOT/.env"

if [ -f "$BACKEND_ENV" ]; then
  mode=$(stat -c '%a' "$BACKEND_ENV" 2>/dev/null || stat -f '%Lp' "$BACKEND_ENV" 2>/dev/null || echo "?")
  size=$(stat -c '%s' "$BACKEND_ENV" 2>/dev/null || stat -f '%z' "$BACKEND_ENV" 2>/dev/null || echo "?")
  count=$(grep -c '^[A-Z_][A-Z0-9_]*=' "$BACKEND_ENV" 2>/dev/null || echo "0")
  echo "  backend/.env: yes  mode=$mode  size=${size}b  keys=$count"
  # Flag placeholder-only API_SECRET_KEY without printing it.
  key_line=$(grep '^API_SECRET_KEY=' "$BACKEND_ENV" | head -n 1)
  case "$key_line" in
    "API_SECRET_KEY="|\
    "API_SECRET_KEY=change-me-before-use"|\
    "API_SECRET_KEY=replace-with-output-of-generate-secret-sh"|\
    "API_SECRET_KEY=replace-with-output-of-openssl-rand-hex-32")
      echo "  API_SECRET_KEY: PLACEHOLDER — rotate with: bash deployment/raspberry-pi/generate-secret.sh"
      ;;
    "")
      echo "  API_SECRET_KEY: NOT SET"
      ;;
    *)
      # length only (never the value)
      val_len=$(( ${#key_line} - 15 ))  # 15 = len('API_SECRET_KEY=')
      echo "  API_SECRET_KEY: configured (length=$val_len)"
      ;;
  esac
else
  echo "  backend/.env: NO — copy from deployment/raspberry-pi/env.example.pi"
fi

if [ -f "$LEGACY_ENV" ]; then
  echo "  WARNING: repo-root .env exists at $LEGACY_ENV"
  echo "           The service reads backend/.env, NOT this file."
  echo "           If you configured this file expecting it to work, move it:"
  echo "             mv \"$LEGACY_ENV\" \"$BACKEND_ENV\""
fi

# ── 4. port 8000 ────────────────────────────────────────────────────────────
section "Port 8000"
if command -v ss >/dev/null 2>&1; then
  ss -tlnp 2>/dev/null | grep -E ':8000\b' | sed 's/^/  /' || echo "  nothing listening on :8000"
elif command -v lsof >/dev/null 2>&1; then
  lsof -iTCP:8000 -sTCP:LISTEN 2>/dev/null | tail -n +2 | sed 's/^/  /' || echo "  nothing listening on :8000"
else
  echo "  (no ss/lsof available)"
fi

# ── 5. HTTP probes (no auth required) ───────────────────────────────────────
section "HTTP probes"
for path in /health /version /readiness /dashboard/health /voice/status; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -m 3 "$BASE_URL$path" 2>/dev/null || echo "000")
  printf "  %-20s %s\n" "$path" "$code"
done

# ── 6. systemd (optional) ───────────────────────────────────────────────────
if command -v systemctl >/dev/null 2>&1; then
  section "systemd"
  if systemctl list-unit-files rasapi.service >/dev/null 2>&1; then
    state=$(systemctl is-active rasapi 2>/dev/null || echo "unknown")
    enabled=$(systemctl is-enabled rasapi 2>/dev/null || echo "unknown")
    echo "  state       : $state"
    echo "  enabled     : $enabled"
    echo ""
    echo "  last 10 journal lines:"
    journalctl -u rasapi -n 10 --no-pager 2>/dev/null | sed 's/^/    /' || echo "    (journalctl unavailable)"
  else
    echo "  rasapi.service is not installed"
  fi
fi

# ── 7. recent audit-log sample (event types only, no content) ───────────────
section "Recent audit-log activity"
if ls "$REPO_ROOT"/logs/audit-*.jsonl >/dev/null 2>&1; then
  tail -n 50 "$REPO_ROOT"/logs/audit-*.jsonl 2>/dev/null \
    | python3 -c "
import json, sys
counts = {}
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        continue
    et = obj.get('event_type', '?')
    counts[et] = counts.get(et, 0) + 1
for et, c in sorted(counts.items(), key=lambda x: -x[1]):
    print(f'  {et:40s}  {c}')
" 2>/dev/null || echo "  (could not parse audit logs)"
else
  echo "  no audit logs yet"
fi

# ── 8. disk ─────────────────────────────────────────────────────────────────
section "Disk"
df -h "$REPO_ROOT" 2>/dev/null | sed 's/^/  /' || echo "  (df unavailable)"

echo ""
echo "Done. Tip: bash deployment/raspberry-pi/check-readiness.sh"
