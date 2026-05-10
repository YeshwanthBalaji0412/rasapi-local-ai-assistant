# RasaPi — Use Cases

Concrete daily-use scenarios. Each one shows what RasaPi can do for an
individual operator on a Raspberry Pi 5.

> Assumes the deployment from [Phase 6](deployment.md) is in place and,
> for some scenarios, [Phase 8 auth](../README.md#authentication--remote-access-phase-8)
> is enabled.

---

## 1. Morning briefing

**Goal:** Wake up, get a quick read on world news, AI news, tech news, and the weather.

```bash
# From your MacBook over the LAN (or via Tailscale):
open http://<pi-ip>:8000/dashboard
```

Scroll to the **Daily Briefing** card. Click **Refresh briefing**. Or in a terminal:

```bash
curl -X POST http://<pi-ip>:8000/briefing/refresh \
  -H "X-RasaPi-Key: $YOUR_KEY"

curl -s http://<pi-ip>:8000/briefing/daily \
  -H "X-RasaPi-Key: $YOUR_KEY" | python3 -m json.tool
```

If you have a Slack workspace and Phase 9 Slack is configured:

```bash
curl -s -X POST http://<pi-ip>:8000/ask \
  -H "X-RasaPi-Key: $YOUR_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"query":"send today'\''s briefing to Slack"}' | python3 -m json.tool
```

---

## 2. Quick system status

**Goal:** Check your home assistant Pi is healthy without opening the dashboard.

```bash
curl -s http://<pi-ip>:8000/health | python3 -m json.tool
curl -s http://<pi-ip>:8000/readiness | python3 -m json.tool

# Or via /ask:
curl -s -X POST http://<pi-ip>:8000/ask \
  -H "X-RasaPi-Key: $YOUR_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"query":"what time is it"}' | python3 -m json.tool
```

---

## 3. Voice command for time / status

**Goal:** Ask out loud, hear the answer.

On the Pi, with `ENABLE_VOICE=true` and the audio stack set up
(see [audio-setup.md](../deployment/raspberry-pi/audio-setup.md)):

```bash
cd ~/rasapi-local-ai-assistant/backend
source .venv/bin/activate
python -m voice.cli once
```

Speak: *"What time is it?"*

You should hear the answer come back through your speaker. The transcript
goes through the same `/ask` router as a text query, so the same intents
work.

---

## 4. Save a memory

**Goal:** "Remember this fact so I can ask for it later."

```bash
# Conversational:
curl -s -X POST http://<pi-ip>:8000/ask \
  -H "X-RasaPi-Key: $YOUR_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"query":"remember that my project name is RasaPi"}'

# Later:
curl -s -X POST http://<pi-ip>:8000/ask \
  -H "X-RasaPi-Key: $YOUR_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"query":"what do you remember"}'
```

Or REST:

```bash
curl -s -X POST http://<pi-ip>:8000/memory \
  -H "X-RasaPi-Key: $YOUR_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"value":"my project name is RasaPi","key":"project_name"}'
```

If you accidentally include something that looks like a secret (e.g.
*"remember that my password is hunter2"*), the sensitive-data detector
blocks the write and logs `sensitive_memory_blocked`. The detector is
not perfect — don't deliberately store secrets.

---

## 5. Add and complete tasks

```bash
# Add:
curl -s -X POST http://<pi-ip>:8000/ask \
  -H "X-RasaPi-Key: $YOUR_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"query":"add task review pull requests"}'

# List:
curl -s -X POST http://<pi-ip>:8000/ask \
  -H "X-RasaPi-Key: $YOUR_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"query":"show tasks"}'

# Complete:
curl -s -X POST http://<pi-ip>:8000/ask \
  -H "X-RasaPi-Key: $YOUR_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"query":"mark task 1 as done"}'
```

The dashboard shows the same tasks with inline **Complete** buttons.

---

## 6. View the dashboard from your MacBook

**Goal:** See everything at a glance.

```bash
open http://<pi-ip>:8000/dashboard
```

Sections you'll see (auth-gated when enabled):

- Overview — version, phase, key flags
- System Health — UTC time, Python, platform, disk, load average
- Assistant Commands — every intent grouped by phase
- Memory / Notes / Tasks — recent items with inline actions
- Daily Briefing — counts per category + refresh button
- Local LLM — config only (no live ping)
- Security — auth posture, secret-configured indicator
- Voice — engine config + last session status
- Integrations — Slack / HA / Alexa-stub with action buttons
- Recent Audit Events — newest 25
- Security Events — filtered to blocks/failures only

---

## 7. Check security events

**Goal:** "Did anything weird happen?"

```bash
curl -s http://<pi-ip>:8000/dashboard/security-events \
  -H "X-RasaPi-Key: $YOUR_KEY" | python3 -m json.tool

# Or just open the dashboard and read the Security Events card.
```

Events surfaced here include: blocked sensitive memory writes, rejected
commands, LLM unavailable, briefing source failures, blocked Home
Assistant entities, CSRF validation failures.

For a quick event-type histogram:

```bash
bash deployment/raspberry-pi/doctor.sh | tail -n 20
```

---

## 8. Send the AI briefing to Slack

**Prerequisite:** Phase 9 Slack configured. See
[integrations.md](../deployment/raspberry-pi/integrations.md).

```bash
curl -s -X POST http://<pi-ip>:8000/ask \
  -H "X-RasaPi-Key: $YOUR_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"query":"send AI briefing to Slack"}' | python3 -m json.tool
```

The deterministic router parses the category ("AI") and posts the
formatted briefing for `ai_news`.

---

## 9. Control a safe Home Assistant device

**Prerequisite:** Phase 9 Home Assistant configured with the entity in
`HOME_ASSISTANT_ALLOWED_ENTITIES`.

```bash
# Conversational:
curl -s -X POST http://<pi-ip>:8000/ask \
  -H "X-RasaPi-Key: $YOUR_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"query":"turn on desk light"}'

# Or REST:
curl -s -X POST http://<pi-ip>:8000/integrations/home-assistant/entities/light.desk_light/turn-on \
  -H "X-RasaPi-Key: $YOUR_KEY"
```

If you ask for a hard-blocked entity (`lock.front_door`), the response
is a refusal. Always.

---

## 10. Run a backup

**Goal:** Snapshot the SQLite database and audit logs before an update.

```bash
bash deployment/raspberry-pi/backup.sh
# → ~/rasapi-backups/<utc-timestamp>/
```

`.env` is intentionally not included. Restore with:

```bash
sudo systemctl stop rasapi
bash deployment/raspberry-pi/restore.sh ~/rasapi-backups/<utc-timestamp>
sudo systemctl start rasapi
```

See [maintenance.md](maintenance.md) for full details.

---

## 11. Update RasaPi

```bash
cd ~/rasapi-local-ai-assistant
bash deployment/raspberry-pi/update-rasapi.sh
```

The script refuses to run with uncommitted changes, then:
- `git pull --ff-only`
- `pip install -r backend/requirements.txt` into the existing venv
- `systemctl restart rasapi`
- Probes `/health`

After the update:

```bash
bash deployment/raspberry-pi/check-readiness.sh
```

---

## 12. Triage when something is off

```bash
bash deployment/raspberry-pi/doctor.sh
```

This prints a single readable report — host info, repo layout, `.env`
presence and permissions (never the contents), port 8000 listeners,
HTTP probes against the local server, systemd state and last 10 journal
lines, recent audit-log event types, and disk usage. It never prints
secrets.

If you need help opening an issue, attach the `doctor.sh` output. It's
safe to share.
