#!/usr/bin/env bash
# RasaPi — safe update from GitHub.
#
# Pulls the latest main, reinstalls Python requirements into the existing
# venv, and (if systemd is in use) restarts rasapi.service. Refuses to
# run with uncommitted local changes — operator must commit or stash first.
#
# Does NOT modify .env. Does NOT run sudo apt install. Does NOT touch the
# database or audit logs.
#
# Usage:
#   bash deployment/raspberry-pi/update-rasapi.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

step() {
  echo ""
  echo "── $* ────────────────────────────────────────────────────────────────"
}

abort() {
  echo ""
  echo "ERROR: $*" >&2
  echo ""
  exit 1
}

# ── 1. safety: no uncommitted local changes ────────────────────────────────
step "Checking for uncommitted changes"
if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
  abort "Uncommitted changes detected. Commit or stash before updating."
fi

# Permit existing untracked .env / data — that's expected.
untracked=$(git ls-files --others --exclude-standard | grep -vE '^(\.env$|backend/data/|logs/)' || true)
if [ -n "$untracked" ]; then
  echo ""
  echo "Untracked files (not blocking, just informational):"
  echo "$untracked" | sed 's/^/    /'
fi

# ── 2. git pull ────────────────────────────────────────────────────────────
step "Pulling latest from origin (fast-forward only)"
git fetch origin
git pull --ff-only

# ── 3. pip install ─────────────────────────────────────────────────────────
step "Updating Python requirements"
if [ ! -d backend/.venv ]; then
  abort "backend/.venv does not exist — run install.sh first"
fi
# shellcheck disable=SC1091
source backend/.venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r backend/requirements.txt
deactivate

# ── 4. systemctl restart (optional) ────────────────────────────────────────
if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files rasapi.service >/dev/null 2>&1; then
  step "Restarting rasapi.service"
  sudo systemctl restart rasapi
  sleep 1
  if systemctl is-active --quiet rasapi; then
    echo "  rasapi.service is active"
  else
    abort "rasapi.service did not come back up — check: journalctl -u rasapi -n 50"
  fi
else
  echo ""
  echo "(no systemd unit found — restart your uvicorn process manually if running)"
fi

# ── 5. health probe ────────────────────────────────────────────────────────
step "Probing /health"
code=$(curl -s -o /dev/null -w "%{http_code}" -m 5 http://127.0.0.1:8000/health || echo "000")
if [ "$code" = "200" ]; then
  echo "  /health returned 200"
else
  abort "/health returned $code"
fi

echo ""
echo "Update complete."
echo "Next: bash deployment/raspberry-pi/check-readiness.sh"
