# RasaPi — Operator Guide

Day-to-day usage of a deployed RasaPi. This is the doc to read **after**
the install is working — see [`deployment/raspberry-pi/setup-pi.md`](../deployment/raspberry-pi/setup-pi.md)
for first-time setup.

> ⚠️ RasaPi is a local-first assistant. Do not expose it to the public
> internet. See [security-hardening-checklist.md](security-hardening-checklist.md).

---

## What RasaPi does

| Capability | How |
|---|---|
| Answer "what time is it", "free memory", … | `POST /ask`, dashboard, or voice |
| Save memory / notes / tasks | `POST /ask` ("remember that …", "add task …") |
| Read a daily briefing (RSS + weather) | `/briefing/daily` or "what's happening today" |
| Talk via push-to-talk voice | `python -m voice.cli once` |
| View live status | `http://<pi-ip>:8000/dashboard` |
| Send briefing to Slack | "send today's briefing to Slack" (if configured) |
| Turn on a light via Home Assistant | "turn on desk light" (if allowlisted) |

All on-device. No cloud APIs.

---

## Accessing the dashboard

```
http://<pi-ip>:8000/dashboard
```

If `ENABLE_AUTH=true` (recommended for LAN access), you'll be redirected
to `/login`. Paste the `API_SECRET_KEY` from `.env`.

To sign out, click **Sign out** in the top bar.

---

## Chatting from the browser (Phase 11)

```
http://<pi-ip>:8000/assistant
```

A simple chat box that POSTs to `orchestration.process_query` — the same
entry point `/ask` uses. The page also has a **Start one voice session
on the Pi** button that triggers a single push-to-talk session on the
Raspberry Pi's microphone (your browser does not stream audio).

The last 10 exchanges are kept in memory only and clear on sign-out.
They are not written to SQLite and are not part of `/memory`.

---

## Using `/ask` from the command line

```bash
# When auth is off (local-only):
curl -s -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"what time is it"}' | python3 -m json.tool

# When auth is on:
curl -s -X POST http://<pi-ip>:8000/ask \
  -H "X-RasaPi-Key: $YOUR_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"query":"what time is it"}' | python3 -m json.tool
```

For the full intent list, see [command-reference.md](command-reference.md).

---

## Using voice

```bash
ssh <PI_USER>@<pi-ip>
cd ~/rasapi-local-ai-assistant/backend
source .venv/bin/activate

python -m voice.cli status      # show config
python -m voice.cli once         # full record → STT → /ask → TTS cycle
```

Voice is **push-to-talk only**. No wake word, no always-listening. See
[`deployment/raspberry-pi/audio-setup.md`](../deployment/raspberry-pi/audio-setup.md)
for engine setup.

### Voice setup on a Pi (Phase 10 polish)

Once `whisper.cpp` and Piper are installed, three `.env` keys make the
voice stack work cleanly — no symlinks, no wrapper scripts:

```env
VOICE_WHISPER_MODEL_PATH=/home/<PI_USER>/whisper.cpp/models/ggml-tiny.en.bin
VOICE_PIPER_MODEL_PATH=/home/<PI_USER>/piper-voices/en_US-amy-low.onnx
VOICE_TTS_PLAYBACK_COMMAND=auto   # prefers paplay (PipeWire/Bluetooth safe)
```

Piper is recommended over espeak-ng for clearer voice. `espeak-ng`
remains the reliable fallback if Piper has trouble installing.

---

## Memory, notes, tasks

| Conversational | REST |
|---|---|
| "remember that my domain is rasapi.dev" | `POST /memory` |
| "what do you remember" | `GET /memory` |
| "save note buy a USB mic" | `POST /notes` |
| "add task ship phase 10" | `POST /tasks` |
| "show tasks" | `GET /tasks` |
| "mark task 1 as done" | `PATCH /tasks/1/complete` |

Sensitive content (passwords, API keys, JWTs, SSNs, credit-card-shaped
numbers) is blocked **before** writing to SQLite. See
[security-model.md](security-model.md).

---

## Daily briefing

```bash
# Force a refresh (fetches all configured sources):
curl -X POST http://<pi-ip>:8000/briefing/refresh \
  -H "X-RasaPi-Key: $YOUR_KEY"

# Read the latest:
curl -s http://<pi-ip>:8000/briefing/daily \
  -H "X-RasaPi-Key: $YOUR_KEY" | python3 -m json.tool

# Or via /ask:
# "what's happening today"
# "give me AI news"
# "Boston weather"
# "F1 OPT updates"   (USCIS — disclaimer auto-appended)
```

---

## Logs

```bash
# systemd journal:
sudo journalctl -u rasapi -f                 # live tail
sudo journalctl -u rasapi -n 100 --no-pager  # last 100 lines

# Audit log (JSONL, one event per line):
tail -n 50 ~/rasapi-local-ai-assistant/logs/audit-$(date -u +%Y-%m-%d).jsonl

# Quick event-type histogram:
bash deployment/raspberry-pi/doctor.sh
```

---

## Service control

```bash
sudo systemctl status  rasapi
sudo systemctl restart rasapi
sudo systemctl stop    rasapi
sudo systemctl start   rasapi
```

---

## Updating from GitHub

The safest path:

```bash
cd ~/rasapi-local-ai-assistant
bash deployment/raspberry-pi/update-rasapi.sh
```

The script:
- Refuses to run if you have uncommitted local changes
- `git pull --ff-only`
- Reinstalls Python requirements into the existing venv
- Restarts `rasapi.service`
- Probes `/health`

If something breaks, see [troubleshooting.md](troubleshooting.md).

---

## Enabling / disabling features

Every feature lives behind an `ENABLE_*` flag in `.env`. Edit, then
restart:

```bash
sudo nano ~/rasapi-local-ai-assistant/.env
chmod 600 ~/rasapi-local-ai-assistant/.env
sudo systemctl restart rasapi
```

| To turn on… | Flag |
|---|---|
| API + dashboard auth | `ENABLE_AUTH=true` (plus a real `API_SECRET_KEY`) |
| Local LLM fallback (Ollama) | `ENABLE_LOCAL_LLM=true` |
| Daily briefing | `ENABLE_BRIEFING=true` |
| Voice | `ENABLE_VOICE=true` |
| Slack | `ENABLE_SLACK=true` + `SLACK_WEBHOOK_URL` |
| Home Assistant | `ENABLE_HOME_ASSISTANT=true` + `HOME_ASSISTANT_URL` + `HOME_ASSISTANT_TOKEN` + allowlist |

Full reference: [configuration.md](configuration.md).

---

## Shut down / reboot the Pi safely

RasaPi has nothing fragile about it — SQLite handles its own crash
recovery, the audit log is append-only, and systemd brings the service
back on boot. Still:

```bash
# Optional: snapshot before a reboot:
bash deployment/raspberry-pi/backup.sh

# Stop the service cleanly before unplugging:
sudo systemctl stop rasapi
sudo shutdown -h now      # power off
# or
sudo reboot
```

After a reboot, `rasapi.service` should come back automatically. Verify:

```bash
sudo systemctl status rasapi
bash deployment/raspberry-pi/check-readiness.sh
```

---

## Going further

- [`configuration.md`](configuration.md) — every `.env` setting
- [`maintenance.md`](maintenance.md) — backup / restore / rotate secret
- [`troubleshooting.md`](troubleshooting.md) — when something breaks
- [`security-hardening-checklist.md`](security-hardening-checklist.md) — before LAN/Tailscale access
- [`use-cases.md`](use-cases.md) — concrete daily scenarios
- [`command-reference.md`](command-reference.md) — every HTTP endpoint, CLI, script
