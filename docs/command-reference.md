# RasaPi — Command Reference

Every command in one place. Copy-paste-ready.

> Replace `$YOUR_KEY` with your `API_SECRET_KEY` value. Replace `<pi-ip>`
> with the Pi's LAN IP (or `127.0.0.1` if you're on the Pi itself).

---

## HTTP — public endpoints (no auth needed)

```bash
# Health and version (always public)
curl -s http://<pi-ip>:8000/health    | python3 -m json.tool
curl -s http://<pi-ip>:8000/version   | python3 -m json.tool
curl -s http://<pi-ip>:8000/readiness | python3 -m json.tool

# Dashboard health snapshot (always public)
curl -s http://<pi-ip>:8000/dashboard/health | python3 -m json.tool

# Voice config snapshot (always public)
curl -s http://<pi-ip>:8000/voice/status | python3 -m json.tool

# List supported intents (always public)
curl -s http://<pi-ip>:8000/commands | python3 -m json.tool
```

## HTTP — auth-protected endpoints

```bash
# Config status (auth-gated when ENABLE_AUTH=true)
curl -s http://<pi-ip>:8000/config/status \
  -H "X-RasaPi-Key: $YOUR_KEY" | python3 -m json.tool

# /ask — natural-language interface
curl -s -X POST http://<pi-ip>:8000/ask \
  -H "X-RasaPi-Key: $YOUR_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"query":"what time is it"}' | python3 -m json.tool

# Memory
curl -s -X POST http://<pi-ip>:8000/memory \
  -H "X-RasaPi-Key: $YOUR_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"value":"my domain is rasapi.dev","key":"domain"}'

curl -s http://<pi-ip>:8000/memory -H "X-RasaPi-Key: $YOUR_KEY"

# Notes
curl -s -X POST http://<pi-ip>:8000/notes \
  -H "X-RasaPi-Key: $YOUR_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"content":"buy a USB mic"}'

curl -s http://<pi-ip>:8000/notes -H "X-RasaPi-Key: $YOUR_KEY"

# Tasks
curl -s -X POST http://<pi-ip>:8000/tasks \
  -H "X-RasaPi-Key: $YOUR_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"title":"ship phase 11","priority":"high"}'

curl -s http://<pi-ip>:8000/tasks -H "X-RasaPi-Key: $YOUR_KEY"

curl -s -X PATCH http://<pi-ip>:8000/tasks/1/complete \
  -H "X-RasaPi-Key: $YOUR_KEY"
```

## HTTP — briefing

```bash
curl -s http://<pi-ip>:8000/briefing/sources | python3 -m json.tool

curl -s -X POST http://<pi-ip>:8000/briefing/refresh \
  -H "X-RasaPi-Key: $YOUR_KEY" | python3 -m json.tool

curl -s http://<pi-ip>:8000/briefing/daily \
  -H "X-RasaPi-Key: $YOUR_KEY" | python3 -m json.tool

curl -s http://<pi-ip>:8000/briefing/category/ai_news \
  -H "X-RasaPi-Key: $YOUR_KEY" | python3 -m json.tool
```

## HTTP — voice

```bash
# Test TTS (auth required when enabled)
curl -s -X POST http://<pi-ip>:8000/voice/test-tts \
  -H "X-RasaPi-Key: $YOUR_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello, I am RasaPi"}'

# One push-to-talk cycle (auth required when enabled)
curl -s -X POST http://<pi-ip>:8000/voice/session-once \
  -H "X-RasaPi-Key: $YOUR_KEY"
```

## HTTP — integrations

```bash
curl -s http://<pi-ip>:8000/integrations \
  -H "X-RasaPi-Key: $YOUR_KEY" | python3 -m json.tool

# Slack
curl -s -X POST http://<pi-ip>:8000/integrations/slack/test \
  -H "X-RasaPi-Key: $YOUR_KEY"

curl -s -X POST http://<pi-ip>:8000/integrations/slack/send-briefing \
  -H "X-RasaPi-Key: $YOUR_KEY"

# Home Assistant
curl -s http://<pi-ip>:8000/integrations/home-assistant/status \
  -H "X-RasaPi-Key: $YOUR_KEY"

curl -s http://<pi-ip>:8000/integrations/home-assistant/entities \
  -H "X-RasaPi-Key: $YOUR_KEY"

curl -s http://<pi-ip>:8000/integrations/home-assistant/entities/light.desk_light/state \
  -H "X-RasaPi-Key: $YOUR_KEY"

curl -s -X POST http://<pi-ip>:8000/integrations/home-assistant/entities/light.desk_light/turn-on \
  -H "X-RasaPi-Key: $YOUR_KEY"

curl -s -X POST http://<pi-ip>:8000/integrations/home-assistant/entities/light.desk_light/turn-off \
  -H "X-RasaPi-Key: $YOUR_KEY"
```

## HTTP — login / logout (browser)

```bash
# Login form (HTML)
curl -s http://<pi-ip>:8000/login

# POST login (sets cookie, redirects to /dashboard)
curl -s -X POST http://<pi-ip>:8000/login \
  -d "api_key=$YOUR_KEY&next=/dashboard" -i

# Logout (clears cookie)
curl -s -X POST http://<pi-ip>:8000/logout -i
```

---

## Voice CLI

All run from the Pi inside the backend venv:

```bash
cd ~/rasapi-local-ai-assistant/backend
source .venv/bin/activate

python -m voice.cli status                       # config snapshot
python -m voice.cli record-test                  # 5s record into temp dir
python -m voice.cli stt-test --audio /tmp/x.wav  # transcribe one file
python -m voice.cli tts-test "Hello, I am RasaPi"
python -m voice.cli once                         # full record → STT → /ask → TTS
```

---

## systemd

```bash
sudo systemctl status   rasapi
sudo systemctl start    rasapi
sudo systemctl restart  rasapi
sudo systemctl stop     rasapi
sudo systemctl enable   rasapi      # auto-start on boot
sudo systemctl disable  rasapi
sudo journalctl -u rasapi -f         # live tail
sudo journalctl -u rasapi -n 100 --no-pager
```

---

## Deployment scripts

```bash
# One-time install:
bash deployment/raspberry-pi/install.sh

# Generate a new API_SECRET_KEY (prints, does not write .env):
bash deployment/raspberry-pi/generate-secret.sh

# Quick endpoint sanity check:
bash deployment/raspberry-pi/smoke-test.sh
BASE_URL=http://10.0.0.118:8000 bash deployment/raspberry-pi/smoke-test.sh

# Health probe (cron-friendly):
bash deployment/raspberry-pi/health-check.sh

# Big readiness audit:
bash deployment/raspberry-pi/check-readiness.sh
RASA_API_KEY=... bash deployment/raspberry-pi/check-readiness.sh

# Diagnostic report:
bash deployment/raspberry-pi/doctor.sh

# Safe update from GitHub:
bash deployment/raspberry-pi/update-rasapi.sh
```

---

## Backup / restore

```bash
# Backup → ~/rasapi-backups/<utc-timestamp>/
bash deployment/raspberry-pi/backup.sh

# Restore from a backup dir (stop service first for consistency):
sudo systemctl stop rasapi
bash deployment/raspberry-pi/restore.sh ~/rasapi-backups/<timestamp>
sudo systemctl start rasapi
```

`.env` is **never** part of a backup or restore.

---

## Integration test snippets

```bash
# Confirm /ask refuses memory writes for secrets:
curl -s -X POST http://<pi-ip>:8000/ask \
  -H "X-RasaPi-Key: $YOUR_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"query":"remember that my password is hunter2"}'
# → response contains "I can't save sensitive information"

# Confirm /voice/session-once is auth-gated:
curl -i -X POST http://<pi-ip>:8000/voice/session-once
# → HTTP 401 (when ENABLE_AUTH=true)

# Confirm HA hard-block list rejects locks:
curl -i -X POST http://<pi-ip>:8000/integrations/home-assistant/entities/lock.front_door/turn-on \
  -H "X-RasaPi-Key: $YOUR_KEY"
# → HTTP 400, "entity blocked: hard_blocked_domain:lock"
```

---

## Dashboard URLs

| URL | What |
|---|---|
| `http://<pi-ip>:8000/dashboard` | Full dashboard |
| `http://<pi-ip>:8000/dashboard/health` | JSON health snapshot |
| `http://<pi-ip>:8000/dashboard/audit/recent` | JSON, last N audit events |
| `http://<pi-ip>:8000/dashboard/security-events` | JSON, filtered to blocks/failures |
| `http://<pi-ip>:8000/login` | Login form |
| `http://<pi-ip>:8000/docs` | FastAPI Swagger UI (only when `DEBUG=true`) |

---

## Troubleshooting commands

```bash
# Is the service alive?
bash deployment/raspberry-pi/health-check.sh

# What's wrong with my install?
bash deployment/raspberry-pi/doctor.sh

# Big audit with optional API key:
RASA_API_KEY=... bash deployment/raspberry-pi/check-readiness.sh

# Live systemd journal:
sudo journalctl -u rasapi -f

# Today's audit log:
tail -n 100 ~/rasapi-local-ai-assistant/logs/audit-$(date -u +%Y-%m-%d).jsonl

# Port 8000 status:
ss -tlnp | grep 8000        # Linux
lsof -iTCP:8000 -sTCP:LISTEN  # macOS / Linux
```

---

## Never include real values

In any command above, **never** paste:
- the literal `API_SECRET_KEY`
- a Slack webhook URL
- a Home Assistant token
- a `.env` file's contents

…into a screenshot, a public chat, a commit, or an issue body. Use the
placeholders shown here (`$YOUR_KEY`, `<pi-ip>`).
