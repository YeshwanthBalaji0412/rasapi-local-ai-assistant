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
