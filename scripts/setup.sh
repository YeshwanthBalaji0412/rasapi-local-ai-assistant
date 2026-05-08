#!/usr/bin/env bash
# RasaPi — Raspberry Pi 5 bootstrap script
# Phase 1 stub: documents the manual setup steps.
# Phase 2 will automate these.

set -euo pipefail

echo "=== RasaPi Setup ==="
echo "Target: Raspberry Pi 5, 64-bit Raspberry Pi OS (Bookworm)"
echo ""

# ── Step 1: System packages ───────────────────────────────────────────────────
# sudo apt update && sudo apt upgrade -y
# sudo apt install -y python3 python3-pip python3-venv git curl

# ── Step 2: Install Ollama ────────────────────────────────────────────────────
# curl -fsSL https://ollama.com/install.sh | sh
# ollama pull llama3.2:3b

# ── Step 3: Clone repo and set up virtualenv ──────────────────────────────────
# git clone https://github.com/<your-handle>/rasapi-local-ai-assistant
# cd rasapi-local-ai-assistant/backend
# python3 -m venv .venv && source .venv/bin/activate
# pip install -r requirements.txt

# ── Step 4: Configure environment ────────────────────────────────────────────
# cp .env.example .env
# nano .env    # set API_SECRET_KEY to output of: openssl rand -hex 32

# ── Step 5: Run the server ────────────────────────────────────────────────────
# uvicorn main:app --host 0.0.0.0 --port 8000

echo "See docs/roadmap.md for the full build plan."
echo "Automation of this script is planned for Phase 2."
