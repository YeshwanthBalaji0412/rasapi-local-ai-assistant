#!/usr/bin/env bash
# RasaPi — generate a fresh API_SECRET_KEY.
#
# Prints one URL-safe 32-byte token (~43 characters, ~256 bits of entropy).
# Does NOT write to .env. Operator pastes the value into .env themselves.
#
# Usage:
#   bash deployment/raspberry-pi/generate-secret.sh
#
# Recommended workflow:
#   bash deployment/raspberry-pi/generate-secret.sh
#   nano .env   # paste as the value of API_SECRET_KEY
#   chmod 600 .env

set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found on PATH." >&2
  echo "Install with: sudo apt install python3" >&2
  exit 1
fi

python3 -c "import secrets; print(secrets.token_urlsafe(32))"
