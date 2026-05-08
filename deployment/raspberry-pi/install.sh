#!/usr/bin/env bash
# RasaPi — Raspberry Pi installer (Phase 6).
#
# Idempotent. Safe to re-run. Does NOT install system packages, modify the
# firewall, or touch /etc/. It prepares the project venv, installs Python
# requirements, creates the data + logs directories, and seeds .env from
# env.example.pi if no .env exists.
#
# Usage (from the repo root on the Pi):
#   bash deployment/raspberry-pi/install.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
DATA_DIR="$BACKEND_DIR/data"
LOGS_DIR="$REPO_ROOT/logs"
ENV_FILE="$REPO_ROOT/.env"
ENV_EXAMPLE="$REPO_ROOT/deployment/raspberry-pi/env.example.pi"

# The exact apt command the user should run if dependencies are missing.
# Kept as a string so the script never executes it itself.
APT_HINT="sudo apt install -y python3 python3-venv python3-pip git"

abort() {
  echo ""
  echo "ERROR: $*" >&2
  echo ""
  exit 1
}

step() {
  echo ""
  echo "── $* ────────────────────────────────────────────────────────────────"
}

# ── 1. Required system tools ─────────────────────────────────────────────────
step "Checking system prerequisites"

missing=()
command -v git >/dev/null 2>&1 || missing+=("git")
command -v python3 >/dev/null 2>&1 || missing+=("python3")
python3 -c "import venv" >/dev/null 2>&1 || missing+=("python3-venv")
python3 -c "import ensurepip" >/dev/null 2>&1 || missing+=("python3-pip")

if [ ${#missing[@]} -gt 0 ]; then
  echo "Missing required packages: ${missing[*]}"
  echo ""
  echo "Please run this command, then re-run install.sh:"
  echo "    $APT_HINT"
  abort "system prerequisites missing"
fi

PY_MAJOR_MINOR=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "  python3 = $PY_MAJOR_MINOR"

case "$PY_MAJOR_MINOR" in
  3.10|3.11|3.12|3.13|3.14)
    ;;
  *)
    abort "python 3.10+ required (found $PY_MAJOR_MINOR)"
    ;;
esac

# ── 2. Project virtualenv ────────────────────────────────────────────────────
step "Creating Python virtual environment"
if [ -d "$BACKEND_DIR/.venv" ]; then
  echo "  .venv already exists at $BACKEND_DIR/.venv (skipping)"
else
  python3 -m venv "$BACKEND_DIR/.venv"
  echo "  created $BACKEND_DIR/.venv"
fi

# ── 3. Python dependencies ───────────────────────────────────────────────────
step "Installing Python requirements"
# shellcheck disable=SC1091
source "$BACKEND_DIR/.venv/bin/activate"
pip install --upgrade pip >/dev/null
pip install -r "$BACKEND_DIR/requirements.txt"
deactivate

# ── 4. Local data + logs directories ─────────────────────────────────────────
step "Creating data and log directories"
mkdir -p "$DATA_DIR"
mkdir -p "$LOGS_DIR"
chmod 700 "$DATA_DIR" 2>/dev/null || true
chmod 700 "$LOGS_DIR" 2>/dev/null || true
echo "  $DATA_DIR (mode 700)"
echo "  $LOGS_DIR (mode 700)"

# ── 5. .env seeding (never overwrite) ────────────────────────────────────────
step "Configuring environment file"
if [ -f "$ENV_FILE" ]; then
  echo "  $ENV_FILE already exists — leaving it untouched."
else
  if [ -f "$ENV_EXAMPLE" ]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    echo "  copied env.example.pi → .env"
  else
    abort "expected $ENV_EXAMPLE but it is missing"
  fi
fi

# ── 6. Done ──────────────────────────────────────────────────────────────────
step "Install complete"
cat <<EOF

Next steps:

  1. Lock down the env file:
       chmod 600 "$ENV_FILE"

  2. Edit values to taste:
       nano "$ENV_FILE"

  3. Try a manual run first:
       cd "$BACKEND_DIR"
       source .venv/bin/activate
       uvicorn main:app --host 127.0.0.1 --port 8000

  4. From a second shell on the Pi, sanity-check:
       curl http://127.0.0.1:8000/health
       bash deployment/raspberry-pi/smoke-test.sh

  5. Install as a systemd service (see setup-pi.md).

  Notes:
   - Default binding is 127.0.0.1 (Pi-local only). If you want to reach
     the dashboard from your MacBook over the LAN, switch to 0.0.0.0
     deliberately. Do NOT port-forward this to the public internet.
   - Local LLM (Ollama) is OFF by default. Verify the dashboard works
     first, then enable it later if your Pi can handle the model.

EOF
