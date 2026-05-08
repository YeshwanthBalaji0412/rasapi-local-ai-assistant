# Phase 1 Demo Checklist

Screenshots to capture before sharing this repo with recruiters or hiring managers. Each one tells a piece of the story: that the system works, that it is secure by design, and that the design is observable.

Save screenshots to `docs/images/` (create the folder when you do). Suggested filenames are listed against each item.

> **Setup before capturing:** start the server with `uvicorn main:app --host 0.0.0.0 --port 8000`. Have a second terminal ready for `curl` and a third tailing the audit log.

---

## ✅ The seven required screenshots

### 1. Health endpoint response
**File:** `docs/images/01-health.png`
**Why it matters:** Proves the service is live and self-identifies cleanly.

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```

**Expected output:**
```json
{
    "status": "ok",
    "version": "0.1.0",
    "assistant": "RasaPi"
}
```

---

### 2. `/commands` endpoint response
**File:** `docs/images/02-commands.png`
**Why it matters:** Demonstrates self-documenting capabilities — the system tells you exactly what it can do.

```bash
curl -s http://localhost:8000/commands | python3 -m json.tool
```

**Expected output:** JSON array of intents (`time`, `uptime`, `cpu_temp`, `disk`, `memory`, `hostname`, `system`, `greeting`, `help`) with descriptions and keywords.

---

### 3. Greeting response
**File:** `docs/images/03-greeting.png`
**Why it matters:** Shows the built-in handler path — a response that doesn't run any subprocess at all. Demonstrates the router can also dispatch to in-process logic.

```bash
curl -s -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"hello"}' | python3 -m json.tool
```

**Expected output:**
```json
{
    "request_id": "<uuid>",
    "intent": "greeting",
    "response": "Hello. I'm RasaPi, your local AI assistant. ...",
    "source": "local",
    "duration_ms": 0
}
```

---

### 4. Disk space command response
**File:** `docs/images/04-disk-command.png`
**Why it matters:** Shows a real allowlisted command (`df -h`) executing safely and returning structured output. This is the happy path through all three safety layers.

```bash
curl -s -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"how much disk space do I have"}' | python3 -m json.tool
```

**Expected output:** `intent: "disk"`, `response` containing `df -h` output, `duration_ms` in single-digit milliseconds.

---

### 5. Malicious command blocked
**File:** `docs/images/05-malicious-blocked.png`
**Why it matters:** **The most important screenshot.** Shows that an attacker query is caught at Layer 1 (intent router) and never reaches an executor. Pair with the audit-log screenshot below to show the rejection is recorded.

```bash
curl -s -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"rm -rf / && cat /etc/passwd"}' | python3 -m json.tool
```

**Expected output:**
```json
{
    "request_id": "<uuid>",
    "intent": "fallback",
    "response": "I don't understand that yet. Phase 1 only supports a fixed set of intents...",
    "source": "local",
    "duration_ms": 0
}
```

**Caption to add:** "Query never matched any intent → routed to fallback → no subprocess invoked. Layer 1 of the three-layer model in action."

---

### 6. Test suite passing
**File:** `docs/images/06-tests-passing.png`
**Why it matters:** 23/23 green tests is the strongest single proof that the security model is enforced, not just documented.

```bash
cd backend && source .venv/bin/activate
cd .. && python -m pytest tests/ -v
```

**Expected output:** Final line `======= 23 passed in <time> =======` with all `tests/test_allowlist.py`, `tests/test_health.py`, and `tests/test_intent_router.py` items marked `PASSED`.

---

### 7. Audit log entry
**File:** `docs/images/07-audit-log.png`
**Why it matters:** Shows that every request and command is recorded in an append-only structured log — the foundation for any future compliance or forensic story.

```bash
tail -n 5 logs/audit-*.jsonl | python3 -m json.tool --json-lines
# or
tail -n 5 logs/audit-*.jsonl
```

**Expected output:** A handful of JSONL lines each containing `timestamp`, `event_type` (one of `request`, `command_exec`), `request_id`, and command-specific fields.

**Bonus framing:** capture a sequence showing one `request` event followed by one `command_exec` event with the same `request_id` — that proves end-to-end traceability.

---

## Phase 2 — Ollama LLM fallback screenshots

These show the LLM in action. Capture them with `ENABLE_LOCAL_LLM=true` in `.env` and `ollama serve` running with `llama3.2:1b` pulled.

### P2-1. LLM answers a free-form question
**File:** `docs/images/p2-01-llm-fallback.png`
**Why it matters:** Demonstrates Phase 2's added capability — the assistant can discuss things outside its hard-coded intent set, all locally.

```bash
curl -s -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"explain Raspberry Pi in one sentence"}' | python3 -m json.tool
```

**Expected output:** `intent: "llm_fallback"`, `source: "local_llm"`, `response` containing a coherent answer about the Pi.

### P2-2. Known command still bypasses the LLM
**File:** `docs/images/p2-02-router-still-first.png`
**Why it matters:** Proves the security invariant — even with the LLM enabled, known intents go through the deterministic path. No LLM call, no model latency.

```bash
curl -s -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"what time is it"}' | python3 -m json.tool
```

**Expected output:** `intent: "time"`, `source: "local"` (NOT `llm_fallback`), `duration_ms` in single digits (no model inference cost).

### P2-3. Dangerous query — LLM can talk about it but never runs it
**File:** `docs/images/p2-03-dangerous-text-only.png`
**Why it matters:** The most defensible Phase 2 screenshot. Shows the LLM may discuss destructive commands as text, but `source: "local_llm"` confirms it went through the conversational path — no command was executed.

```bash
curl -s -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"delete all files on my computer"}' | python3 -m json.tool
```

**Caption:** "The LLM may produce text about destructive operations, but it has no path to an executor. The audit log shows zero `command_exec` events for this request."

### P2-4. Ollama unavailable — graceful degradation
**File:** `docs/images/p2-04-ollama-down.png`
**Why it matters:** Service stays up even when the model crashes or the daemon is offline.

```bash
# Stop Ollama first:  pkill ollama
curl -s -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"tell me a joke"}' | python3 -m json.tool
```

**Expected output:** `intent: "llm_unavailable"`, response containing "unavailable", and a hint to use `help`.

### P2-5. Audit log entry for an LLM call
**File:** `docs/images/p2-05-llm-audit-entry.png`
**Why it matters:** Every LLM call is auditable just like every command was in Phase 1. Same trail, same tooling.

```bash
tail -n 3 logs/audit-*.jsonl | grep llm_call
```

**Expected output:** A JSONL line with `event_type: "llm_call"`, `outcome: "success"` or `"error"`, `model`, `duration_ms`.

### P2-6. Updated test suite (32/32)
**File:** `docs/images/p2-06-tests-32.png`
**Why it matters:** Phase 2 added 9 tests including the structural import-check that mathematically prevents the LLM from reaching the executor.

```bash
cd backend && source .venv/bin/activate && cd ..
python -m pytest tests/ -v
```

**Expected output:** Final line `======= 32 passed in <time> =======`.

---

## Phase 3 — local memory, notes, tasks screenshots

These show RasaPi remembering things across requests, with sensitive-data protection. Capture them with the Phase 3 build running and a clean DB.

### P3-1. Save a memory
**File:** `docs/images/p3-01-save-memory.png`
**Why it matters:** Demonstrates persistent local memory.

```bash
curl -s -X POST http://localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"query":"remember that my portfolio domain is yeshwanthbalaji.com"}' | python3 -m json.tool
```

**Expected:** `intent: "save_memory"`, response contains "Saved to local memory."

### P3-2. List memory
**File:** `docs/images/p3-02-list-memory.png`
**Why it matters:** Confirms the data is persisted between requests.

```bash
curl -s -X POST http://localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"query":"what do you remember"}' | python3 -m json.tool
```

**Expected:** `intent: "list_memory"`, response includes "yeshwanthbalaji.com".

### P3-3. Sensitive-data block
**File:** `docs/images/p3-03-sensitive-blocked.png`
**Why it matters:** **The Phase 3 linchpin screenshot.** Shows that obvious secrets are refused before they touch the disk.

```bash
curl -s -X POST http://localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"query":"remember that my password is hunter2"}' | python3 -m json.tool
```

**Expected:** response contains *"I can't save sensitive information…"*. A `tail -n 1 logs/audit-*.jsonl` should show `event_type: "sensitive_memory_blocked"`, `reason: "password"`. Capture both side by side.

### P3-4. Add a task
**File:** `docs/images/p3-04-add-task.png`
**Why it matters:** End-to-end task creation through the conversational path.

```bash
curl -s -X POST http://localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"query":"add task ship Phase 3"}' | python3 -m json.tool
```

### P3-5. Complete a task
**File:** `docs/images/p3-05-complete-task.png`

```bash
curl -s -X POST http://localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"query":"mark task 1 as done"}' | python3 -m json.tool

curl -s http://localhost:8000/tasks | python3 -m json.tool   # shows it gone from open list
curl -s "http://localhost:8000/tasks?include_done=true" | python3 -m json.tool   # shows it with status=done
```

### P3-6. List notes
**File:** `docs/images/p3-06-list-notes.png`

```bash
curl -s -X POST http://localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"query":"save note buy a USB microphone for the Pi"}' | python3 -m json.tool

curl -s -X POST http://localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"query":"show notes"}' | python3 -m json.tool
```

### P3-7. Audit log shows a memory event
**File:** `docs/images/p3-07-audit-memory.png`
**Why it matters:** Every storage operation is recorded in the same JSONL trail as Phase 1/2 events.

```bash
tail -n 5 logs/audit-*.jsonl
```

**Expected:** lines with `event_type` values like `memory_created`, `task_completed`, and (if you ran P3-3) `sensitive_memory_blocked`.

### P3-8. Updated test suite (77/77)
**File:** `docs/images/p3-08-tests-77.png`

```bash
cd backend && source .venv/bin/activate && cd ..
python -m pytest tests/ -v
```

**Expected:** Final line `======= 77 passed in <time> =======`.

---

## Phase 4 — daily briefing screenshots

These show the briefing layer in action. Capture with the Phase 4 build running and a clean DB. Each curl below is self-contained.

### P4-1. Configured sources
**File:** `docs/images/p4-01-sources.png`
**Why it matters:** Demonstrates the registry — every source is public, named, and version-controlled. No secrets exposed.

```bash
curl -s http://localhost:8000/briefing/sources | python3 -m json.tool | head -40
```

**Expected:** JSON listing each source with `name`, `category`, `kind`, `url`. Categories include `world_news`, `ai_news`, `tech_news`, `developer_news`, `boston_weather`, `immigration_updates`, `personalized_action_items`.

### P4-2. Refresh run
**File:** `docs/images/p4-02-refresh.png`
**Why it matters:** Shows the manual refresh path with run metadata.

```bash
curl -s -X POST http://localhost:8000/briefing/refresh | python3 -m json.tool
```

**Expected:** `run_id`, `item_count`, `status` (`success` or `partial`), and an `errors` array (empty if every source returned). Bonus: capture the audit log right after with `tail -n 20 logs/audit-*.jsonl | grep briefing`.

### P4-3. Daily briefing (REST)
**File:** `docs/images/p4-03-daily-rest.png`

```bash
curl -s http://localhost:8000/briefing/daily | python3 -m json.tool | head -60
```

**Expected:** `text` field with category headers and headlines, and `items_by_category` for programmatic use.

### P4-4. Daily briefing (conversational)
**File:** `docs/images/p4-04-daily-ask.png`
**Why it matters:** Same data, conversational interface, auto-refresh on cache miss.

```bash
curl -s -X POST http://localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"query":"what'\''s happening today"}' | python3 -m json.tool
```

**Expected:** `intent: "daily_briefing"`, `response` containing multiple category sections.

### P4-5. AI news
**File:** `docs/images/p4-05-ai-news.png`

```bash
curl -s -X POST http://localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"query":"give me AI news"}' | python3 -m json.tool
```

**Expected:** `intent: "ai_briefing"`, headlines from Hugging Face / Google AI Blog.

### P4-6. Boston weather
**File:** `docs/images/p4-06-weather.png`

```bash
curl -s -X POST http://localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"query":"Boston weather"}' | python3 -m json.tool
```

**Expected:** `intent: "weather_briefing"`, response with location, current temp, and high/low.

### P4-7. Immigration briefing with disclaimer
**File:** `docs/images/p4-07-immigration-disclaimer.png`
**Why it matters:** **The Phase 4 linchpin screenshot.** Proves the legal disclaimer is appended.

```bash
curl -s -X POST http://localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"query":"F1 OPT updates"}' | python3 -m json.tool
```

**Expected:** Response text ends with *"These are official-source updates only, not legal advice…"*

### P4-8. Audit log entries for a briefing run
**File:** `docs/images/p4-08-briefing-audit.png`

```bash
tail -n 20 logs/audit-*.jsonl | grep -E "briefing|weather_fetch"
```

**Expected:** A sequence of `briefing_refresh_started`, multiple `briefing_item_stored`, `weather_fetch_completed` (or `_failed`), `briefing_refresh_completed`, `briefing_served`.

### P4-9. Tests passing (126/126)
**File:** `docs/images/p4-09-tests-126.png`

```bash
cd backend && source .venv/bin/activate && cd ..
python -m pytest tests/ -v
```

**Expected:** Final line `======= 126 passed in <time> =======`.

---

## Phase 5 — dashboard screenshots

These are the recruiter-facing screenshots. Capture them in a clean state with the Phase 5 build running and Ollama optionally enabled.

### P5-1. Dashboard overview (full page)
**File:** `docs/images/p5-01-overview.png`
**Why it matters:** This is the headline screenshot. Shows the project as a polished local product, not just a CLI.

```bash
open http://localhost:8000/dashboard
```

Capture the full-page view with all 8 sections visible (you may need to scroll-stitch).

### P5-2. System Health card
**File:** `docs/images/p5-02-health.png`
**Why it matters:** Shows the dashboard reads real system state without exposing absolute paths or environment values.

Crop to just the **System Health** card. Optional: also capture the JSON endpoint:
```bash
curl -s http://localhost:8000/dashboard/health | python3 -m json.tool
```

### P5-3. Local LLM section
**File:** `docs/images/p5-03-llm-config.png`
**Why it matters:** Demonstrates the LLM is **opt-in** and that the dashboard shows configuration only — no live ping, no model load triggered.

Crop to the **Local LLM** card.

### P5-4. Memory / Notes / Tasks
**File:** `docs/images/p5-04-memory-tasks.png`
**Why it matters:** End-to-end Phase 3 surface visible at a glance; shows the inline "Complete" buttons.

Pre-populate via `/ask` then crop the section:
```bash
curl -s -X POST http://localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"query":"remember that my domain is yeshwanthbalaji.com"}'
curl -s -X POST http://localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"query":"add task ship phase 5"}'
curl -s -X POST http://localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"query":"add task write demo screenshots"}'
```

### P5-5. Daily Briefing section with refresh button
**File:** `docs/images/p5-05-briefing.png`
**Why it matters:** Shows category counts and the "Refresh briefing" button. Click it once before screenshotting so the "Last refresh" panel has data.

### P5-6. Recent Audit Events
**File:** `docs/images/p5-06-audit.png`
**Why it matters:** Demonstrates the audit trail is observable and human-readable, not just a JSONL file on disk.

Crop to the **Recent Audit Events** card.

### P5-7. Security Events
**File:** `docs/images/p5-07-security.png`
**Why it matters:** **The Phase 5 linchpin screenshot.** Shows that blocked memory attempts, source failures, and rejected commands surface at the top level.

Trigger one before screenshotting:
```bash
curl -s -X POST http://localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"query":"remember that my password is hunter2"}'
```

Then refresh `/dashboard` and crop the **Security Events** card. The new entry should be `sensitive_memory_blocked`.

### P5-8. Tests passing (154/154)
**File:** `docs/images/p5-08-tests-154.png`

```bash
cd backend && source .venv/bin/activate && cd ..
python -m pytest tests/ -v
```

**Expected:** Final line `======= 154 passed in <time> =======`.

---

## Phase 6 — Raspberry Pi deployment screenshots

These prove the project runs end-to-end on real hardware.

### P6-1. SSH session into the Pi
**File:** `docs/images/p6-01-ssh.png`

```bash
ssh <PI_USER>@<pi-host-or-ip>
hostname && uname -a
```

Capture the prompt + the model line so it's clear this is the Pi, not your Mac.

### P6-2. Install + smoke test
**File:** `docs/images/p6-02-install.png`

```bash
cd ~/rasapi-local-ai-assistant
git pull --ff-only
bash deployment/raspberry-pi/install.sh
bash deployment/raspberry-pi/smoke-test.sh
```

**Expected:** Install steps each show a `──` heading, then 9 PASS lines from the smoke test.

### P6-3. systemctl status
**File:** `docs/images/p6-03-systemctl.png`

```bash
sudo systemctl status rasapi
```

**Expected:** `Active: active (running)`, `Main PID:`, `Memory:`, `CPU:`, and a few recent log lines from journald.

### P6-4. Dashboard from MacBook
**File:** `docs/images/p6-04-dashboard-from-mac.png`
**Why it matters:** Proves LAN access works — the headline screenshot for "RasaPi running on real hardware".

In your MacBook browser:
```
http://<PI_LAN_IP>:8000/dashboard
```

Capture the full dashboard. (This requires step 11 in setup-pi.md — switching the systemd unit to `--host 0.0.0.0`.)

### P6-5. Reboot + auto-start
**File:** `docs/images/p6-05-reboot-autostart.png`

```bash
sudo reboot
# wait ~30 seconds, SSH back in:
sudo systemctl status rasapi
```

**Expected:** Service is `active (running)` with `Started` timestamp matching the post-reboot uptime. Optionally include `uptime` output in the same screenshot.

### P6-6. Audit log on the Pi
**File:** `docs/images/p6-06-pi-audit.png`

```bash
ls -la ~/rasapi-local-ai-assistant/logs/
tail -n 5 ~/rasapi-local-ai-assistant/logs/audit-*.jsonl
```

**Expected:** Files exist with mode `-rw-------`, owned by `<PI_USER>`. Recent JSONL entries visible.

### P6-7. Backup script output
**File:** `docs/images/p6-07-backup.png`

```bash
bash deployment/raspberry-pi/backup.sh
ls -la ~/rasapi-backups/
ls -la ~/rasapi-backups/<latest>/
```

**Expected:** Timestamped folder containing `rasapi.db` and `audit-*.jsonl`. Confirm `.env` is **not** present in the backup.

### P6-8. Tests passing (185/185)
**File:** `docs/images/p6-08-tests-185.png`

```bash
cd backend && source .venv/bin/activate && cd ..
python -m pytest tests/ -v
```

**Expected:** Final line `======= 185 passed in <time> =======`.

---

## Optional bonus screenshots

These aren't required but strengthen the story:

| Screenshot | Why |
|---|---|
| `docs/images/08-architecture-diagram.png` | Render the ASCII diagram from `docs/architecture.md` as an image |
| `docs/images/09-fastapi-docs.png` | Set `DEBUG=true` in `.env`, restart, screenshot `http://localhost:8000/docs` |
| `docs/images/10-pi-deployment.png` | (Phase 5) Photo of the actual Pi 5 running RasaPi |

---

## Before-you-publish checklist

- [ ] No `.env` values visible in any screenshot
- [ ] No personal hostnames, IP addresses, or usernames left in terminal prompts (replace with `pi@rasapi:~$` or similar)
- [ ] Audit log screenshot shows non-PII queries only
- [ ] All 23 tests are green
- [ ] README, architecture, security-model, roadmap docs are up to date with current code
- [ ] The repo has a sensible top-level commit message and a clean `git log`

When all of the above are checked, the project is ready to drop into a portfolio, a GitHub README, or a recruiter conversation.
