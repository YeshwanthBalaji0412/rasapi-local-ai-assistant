# RasaPi — Local-First Secure AI Assistant on Raspberry Pi 5

[![Phase](https://img.shields.io/badge/phase-6%20in%20progress-yellow)]() [![Tests](https://img.shields.io/badge/tests-185%2F185-brightgreen)]() [![License](https://img.shields.io/badge/license-MIT-blue)]()

A privacy-preserving AI assistant that runs entirely on a Raspberry Pi 5. No cloud dependency. Secure command execution by default. Built iteratively, phase by phase, so every increment is testable on its own.

---

## Why this project exists

Most "AI assistants" on the market send your voice and text to a vendor cloud the moment you press a button. RasaPi takes the opposite stance: **the Pi is the assistant**. Inference, command execution, and audit logs all stay on the device.

This repo is also a recruiter-facing showcase of how to build a **secure** AI system from the ground up — defense in depth, explicit threat modelling, and zero unrestricted shell execution.

---

## Project philosophy

| Principle | What it means here |
|---|---|
| **Local-first** | All processing on-device by default |
| **Secure by default** | Three-layer command safety; default-deny everything |
| **Low cost** | Runs on ~$80 hardware; no API subscription |
| **Modular** | Each capability lives in its own module with an explicit interface |
| **Recruiter-showcase ready** | Clean docs, traceable design decisions, every phase demoable |
| **Cloud fallback is opt-in only** | Reserved for a later phase, behind explicit user consent |

---

## What works today

| Phase | Status | What it adds |
|---|---|---|
| 1 | ✅ complete | Secure FastAPI backend, three-layer command safety, structured audit log |
| 1.5 | ✅ complete | Documentation polish, demo checklist |
| 2 | ✅ complete | Optional Ollama LLM fallback for free-form queries (off by default) |
| 3 | ✅ complete | Local SQLite memory, notes, and tasks with sensitive-data blocking |
| 4 | ✅ complete | Daily intelligence briefing — RSS + Open-Meteo, all local, no API keys |
| 5 | ✅ complete | Local web dashboard — server-rendered HTML, no JS framework, no CDN |
| 6 | 🟡 in progress | Raspberry Pi deployment — systemd service, install / smoke / backup / restore scripts |

The deterministic intent router is still the only thing that decides what code path runs. The LLM is text-only. Memory writes go through the router or direct REST endpoints — never the LLM.

**Capabilities:**

- `POST /ask` — submit a natural-language query, get a routed response
- `GET /commands` — list every supported intent (great for live demos)
- `GET /health` — liveness, version, assistant name
- Deterministic keyword-based intent router (no model required)
- Safe command execution gated by an allowlist with typed argument validation
- Structured JSONL audit trail for every request, command, LLM call, and memory event
- `.env`-based configuration via `pydantic-settings`
- Full test suite — **185/185 passing** (`pytest`)

**Phase 2 additions (opt-in via `ENABLE_LOCAL_LLM=true`):**

- Local Ollama integration via HTTP (`/api/chat`) — no cloud calls
- Falls back to LLM **only** when no safe intent matches
- Hard-coded system prompt; user query is the only dynamic content sent
- LLM response treated as plain conversational text — never parsed, never executed
- Graceful degradation on timeout, connection error, or empty response
- Every LLM call audited with model name, outcome, duration, and (on error) reason

> **The LLM never reaches the command runner.** `core/local_llm.py` does not import `command_runner`, `allowlist`, or `subprocess`. A dedicated structural test enforces this invariant in CI.

**Supported intents:**

| Intent | Triggers | Action | Phase |
|---|---|---|---|
| `greeting` | "hello", "hi", "hey" | Built-in static response | 1 |
| `help` | "help", "what can you do" | Lists available intents | 1 |
| `time` | "time", "date", "what day" | Runs `date` | 1 |
| `uptime` | "uptime", "how long" | Runs `uptime` | 1 |
| `cpu_temp` | "temperature", "how hot" | Runs `vcgencmd measure_temp` (Pi only) | 1 |
| `disk` | "disk", "storage", "space" | Runs `df -h` | 1 |
| `memory_usage` | "ram", "free memory", "memory usage" | Runs `free -h` | 1 |
| `hostname` | "hostname", "device name" | Runs `hostname` | 1 |
| `system` | "kernel", "os version" | Runs `uname -a` | 1 |
| `save_memory` | "remember that …", "remember …" | Saves to local SQLite | 3 |
| `list_memory` | "what do you remember", "show memory" | Lists saved memory items | 3 |
| `save_note` | "save note …", "add note …" | Saves a note to SQLite | 3 |
| `list_notes` | "show notes", "my notes" | Lists notes | 3 |
| `add_task` | "add task …", "new task …" | Creates a task | 3 |
| `list_tasks` | "show tasks", "my tasks" | Lists open tasks | 3 |
| `complete_task` | "mark task N as done", "complete task N" | Marks task N done | 3 |
| `daily_briefing` | "daily briefing", "what's happening today" | Full briefing across categories | 4 |
| `world_briefing` | "world news" | World headlines (BBC, NPR) | 4 |
| `ai_briefing` | "AI news" | AI updates (Hugging Face, Google AI) | 4 |
| `tech_briefing` | "tech news" | Tech headlines (Ars, The Verge) | 4 |
| `developer_briefing` | "hacker news", "developer news" | Hacker News front page | 4 |
| `weather_briefing` | "Boston weather" | Open-Meteo current + daily | 4 |
| `immigration_briefing` | "F1 OPT", "immigration updates" | USCIS news + legal disclaimer | 4 |
| `llm_fallback` | unknown, with `ENABLE_LOCAL_LLM=true` | Routed to Ollama | 2 |
| `fallback` | unknown, no LLM | Static "not supported" message | 1 |

---

## Installation

**Requirements:** Python 3.10+ on macOS, Linux, or Raspberry Pi OS (Bookworm).

```bash
# Clone
git clone https://github.com/<your-handle>/rasapi-local-ai-assistant
cd rasapi-local-ai-assistant

# Set up the backend virtualenv
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure
cp ../.env.example ../.env
# (optional) edit ../.env to change the port, log level, etc.
```

That's it. **No model download required for Phase 1.**

### Optional — enable local LLM fallback (Phase 2)

If you want unrecognised queries to be answered by a local model:

```bash
# 1. Install Ollama (https://ollama.com)
curl -fsSL https://ollama.com/install.sh | sh    # Linux / Pi
# or `brew install ollama` on macOS

# 2. Pull a small model
ollama pull llama3.2:1b

# 3. Start the Ollama daemon (usually runs automatically)
ollama serve &

# 4. In your .env, opt in:
#    ENABLE_LOCAL_LLM=true
```

Phase 2 is **off by default**. Set `ENABLE_LOCAL_LLM=true` in `.env` only when you intentionally want Ollama enabled.

---

## Running the server

```bash
# from inside backend/, with the venv activated
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

You should see:

```
INFO  Starting RasaPi on 0.0.0.0:8000
INFO  Uvicorn running on http://0.0.0.0:8000
```

Audit log streams to `logs/audit-YYYY-MM-DD.jsonl` (created automatically).

---

## Local memory, notes, and tasks (Phase 3)

Phase 3 adds a local SQLite store at `backend/data/rasapi.db` (gitignored). The same service layer is reachable via two surfaces:

- **Conversational** — through the router on `POST /ask`
- **REST** — direct endpoints for clean backend integration

### Examples

```bash
# Conversational
curl -s -X POST http://localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"query":"remember that my portfolio domain is yeshwanthbalaji.com"}'

curl -s -X POST http://localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"query":"what do you remember"}'

curl -s -X POST http://localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"query":"add task ship Phase 3"}'

curl -s -X POST http://localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"query":"mark task 1 as done"}'

# REST
curl -s -X POST http://localhost:8000/memory -H 'Content-Type: application/json' \
  -d '{"value":"my hobby is rock climbing","key":"hobby"}'

curl -s http://localhost:8000/tasks
```

### Privacy & sensitive-data protection

- Memory and notes live **only** on disk in the SQLite file.
- Memory is **never** sent to Ollama or any cloud service.
- Before saving, every value is checked by `security/sensitive_data.py`. Inputs containing passwords, API keys, tokens, private keys, SSNs, or credit-card-shaped numbers are **rejected with a safe message**, and the rejection is audited.
- The detector is a **practical** safety layer, not a perfect DLP system. Don't rely on it as the only barrier — don't intentionally tell RasaPi your secrets.

### What the LLM cannot do (still true in Phase 3)

The LLM cannot create, read, or modify memory, notes, or tasks. The service modules are not imported by `core/local_llm.py`. The only path to a memory write is through the deterministic router or a direct REST call.

---

## Daily briefing (Phase 4)

A free, local-first news + weather digest. No API keys required. Sources are hardcoded RSS feeds (BBC, NPR, Hugging Face, Google AI Blog, Ars Technica, The Verge, Hacker News, USCIS) plus Open-Meteo for weather.

### Examples

```bash
# Conversational
curl -s -X POST http://localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"query":"what'\''s happening today"}' | python3 -m json.tool

curl -s -X POST http://localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"query":"give me AI news"}' | python3 -m json.tool

curl -s -X POST http://localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"query":"Boston weather"}' | python3 -m json.tool

curl -s -X POST http://localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"query":"F1 OPT updates"}' | python3 -m json.tool

# REST
curl -s http://localhost:8000/briefing/sources | python3 -m json.tool
curl -s -X POST http://localhost:8000/briefing/refresh | python3 -m json.tool
curl -s http://localhost:8000/briefing/daily | python3 -m json.tool
curl -s http://localhost:8000/briefing/category/ai_news | python3 -m json.tool
```

### How it works

1. **`POST /briefing/refresh`** fetches every configured source over HTTPS, parses RSS via `feedparser`, queries Open-Meteo for weather, and stores items in `briefing_items` (deduped by URL within a 7-day window).
2. **`GET /briefing/daily`** reads recent items grouped by category and renders a plain-text digest.
3. **`/ask` daily briefing** auto-refreshes if the cache (`BRIEFING_CACHE_MINUTES=60`) has expired, then renders the same digest.

### Immigration disclaimer

Any briefing that includes USCIS items is appended with:

> *"These are official-source updates only, not legal advice. Verify with USCIS, your school OGS, or a qualified immigration advisor."*

### Privacy properties

- **No API keys.** Open-Meteo is free and unauthenticated.
- **No personal data sent anywhere.** Briefing fetchers are isolated in `backend/briefing/`. They don't import `core/memory.py`, `core/tasks.py`, `core/command_runner.py`, or `subprocess`. A structural test enforces this.
- **LLM summary is opt-in-opt-in.** Both `ENABLE_LOCAL_LLM=true` AND `ENABLE_LLM_BRIEFING_SUMMARY=true` must be set before any LLM call happens on the briefing path. When enabled, only public source headlines are sent — never memory/notes/tasks/audit-log content.
- **Reserved category.** `personalized_action_items` is a documented empty stub. Phase 4 deliberately does not feed it from your local memory or tasks; that requires a future security decision.

---

## API endpoints

| Method | Path | Purpose | Body | Phase |
|---|---|---|---|---|
| GET | `/health` | Liveness probe | — | 1 |
| GET | `/commands` | List supported intents | — | 1 |
| POST | `/ask` | Submit a query | `{"query": "string"}` | 1 |
| POST | `/memory` | Save a memory item | `{"value": "...", "key"?, "category"?}` | 3 |
| GET | `/memory` | List memory items | — | 3 |
| POST | `/notes` | Save a note | `{"content": "...", "tags"?}` | 3 |
| GET | `/notes` | List notes | — | 3 |
| POST | `/tasks` | Create a task | `{"title": "...", "priority"?, "due_date"?}` | 3 |
| GET | `/tasks?include_done=false` | List tasks | — | 3 |
| PATCH | `/tasks/{id}/complete` | Mark a task done | — | 3 |
| GET | `/briefing` / `/briefing/daily` | Render the daily briefing | — | 4 |
| GET | `/briefing/category/{category}` | Items in one category | — | 4 |
| POST | `/briefing/refresh` | Fetch every source now | — | 4 |
| GET | `/briefing/sources` | List configured sources + categories | — | 4 |
| GET | `/dashboard` | Server-rendered HTML dashboard | — | 5 |
| GET | `/dashboard/health` | JSON health snapshot | — | 5 |
| GET | `/dashboard/audit/recent` | JSON list of latest audit events | `?limit=25` | 5 |
| GET | `/dashboard/security-events` | JSON list of security-relevant events | — | 5 |
| POST | `/dashboard/briefing/refresh` | Trigger refresh, redirect to `/dashboard` | — | 5 |
| POST | `/dashboard/tasks/{id}/complete` | Mark task done, redirect | — | 5 |

## Dashboard (Phase 5)

A clean, local-only web dashboard at `http://localhost:8000/dashboard`. Server-rendered HTML, no JavaScript framework, no CDN, no remote fonts.

```bash
# Open in your browser
open http://localhost:8000/dashboard       # macOS
xdg-open http://localhost:8000/dashboard   # Linux
```

### Sections

1. **Overview** — name, version, phase, key flags
2. **System Health** — UTC time, Python version, platform, disk usage, load average
3. **Assistant Commands** — every intent grouped by phase
4. **Memory / Notes / Tasks** — last 5 of each (truncated, escaped); inline "Complete" buttons on tasks
5. **Daily Briefing** — counts per category, last refresh status, "Refresh now" button
6. **Local LLM** — configuration only (no live ping)
7. **Recent Audit Events** — newest 25 entries
8. **Security Events** — filtered: blocked memory, command rejections, LLM unavailable, briefing source failures

### Privacy properties

- **Local-only by design.** ⚠️ The dashboard is intended for local development. Do not expose it to the public internet — there is no authentication in Phase 5. Phase 6 deployment will add bind-to-localhost defaults and authentication.
- **No secrets exposed.** `Settings` is projected to a hardcoded safe subset before reaching templates. `api_secret_key`, `.env` content, and full filesystem paths are never visible.
- **HTML is escaped.** Jinja2 autoescape is on. User memory/notes/tasks content is also truncated to 200 chars.
- **DB and audit-log paths are masked** to the last two segments by default (`dashboard_mask_db_path=true`).
- **Two write actions only.** Refresh briefing, complete task — both call existing service functions, both audited. No free-form input field, no shell endpoint, no editing of memory/notes.
- **Audit log reader skips malformed JSONL** so a corrupted line never crashes the page.

### Response schema for `/ask`

```json
{
  "request_id": "uuid",
  "intent": "time | greeting | fallback | llm_fallback | llm_unavailable | …",
  "response": "string — output of command, handler, or LLM",
  "source": "local | local_llm",
  "duration_ms": 3
}
```

**Possible `intent` values:**
- `time`, `uptime`, `disk`, `memory`, `hostname`, `system`, `cpu_temp` — Phase 1 commands
- `greeting`, `help` — Phase 1 built-in handlers
- `fallback` — no router match, Phase 2 disabled (or `ENABLE_LOCAL_LLM=false`)
- `llm_fallback` — answered by local Ollama (Phase 2, only when enabled)
- `llm_unavailable` — Ollama timed out or was unreachable; safe message returned

---

## Test commands

Start the server first, then in a second shell:

```bash
# Health
curl -s http://localhost:8000/health | python3 -m json.tool

# List intents
curl -s http://localhost:8000/commands | python3 -m json.tool

# Greeting (built-in handler, no command run)
curl -s -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"hello"}' | python3 -m json.tool

# Time (executes `date`)
curl -s -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"what time is it"}' | python3 -m json.tool

# Disk space (executes `df -h`)
curl -s -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"how much disk space do I have"}' | python3 -m json.tool

# Security demo — malicious query gets fallback, never executes
curl -s -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"rm -rf / && cat /etc/passwd"}' | python3 -m json.tool

# Inspect audit trail
tail -f logs/audit-*.jsonl

# ──────────────────── Phase 2 only (ENABLE_LOCAL_LLM=true) ────────────────────

# Conversational query — falls through router, hits Ollama
curl -s -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"explain Raspberry Pi in one sentence"}' | python3 -m json.tool

# Even with the LLM enabled, a known command still goes through the router
curl -s -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"what time is it"}' | python3 -m json.tool
# → intent: "time", source: "local"   (NOT llm_fallback)

# Dangerous wording in a fallback query: LLM may answer in text, but
# nothing is ever executed.
curl -s -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"delete all files on my computer"}' | python3 -m json.tool
```

### Run the test suite

```bash
cd backend && source .venv/bin/activate
cd .. && python -m pytest tests/ -v
```

Expected: `185 passed`.

---

## Security model summary

Every command goes through **three independent layers** before any process is spawned. Each layer alone would be sufficient for most attackers; together they make Phase 1 the security foundation the rest of the project builds on.

```
Query → [1] Intent Router → [2] Allowlist Validator → [3] Subprocess (shell=False)
         keyword-matched      typed args, default-deny    no shell expansion, list args
                │
                └─── fallback only ───► [Phase 2] Local LLM (text-only, no executor reachable)
```

| Layer | What it blocks |
|---|---|
| **1. Intent router** | Anything that doesn't match a known keyword set falls into `fallback` and never reaches an executor |
| **2. Allowlist validator** | Even if a router bug let something through, the command name and every argument must match an explicit whitelist |
| **3. `subprocess(shell=False)`** | No shell expansion, no glob, no `&&`, no `;` — args are a Python list, never a string |

**Always blocked:** `sudo`, `bash`, `sh`, `rm`, `chmod`, `chown`, `passwd`, anything not on the allowlist. Privileged commands are not just "missing from the allowlist" — they will never be added.

**Audit log:** Every request, command execution, and rejection is appended to a dated JSONL file. The log never contains secrets, full env values, or model weights. See [docs/security-model.md](docs/security-model.md) for the full threat model.

---

## Repository layout

```
rasapi-local-ai-assistant/
├── backend/
│   ├── main.py                    # FastAPI app entry
│   ├── config.py                  # Pydantic-settings, .env loader
│   ├── api/routes/
│   │   ├── health.py              # GET /health
│   │   └── assistant.py           # POST /ask, GET /commands
│   ├── core/
│   │   ├── intent_router.py       # Keyword → intent → handler/command
│   │   ├── command_runner.py      # subprocess(shell=False) + audit
│   │   ├── local_llm.py           # Ollama HTTP client (Phase 2)
│   │   ├── memory.py              # Memory + notes service (Phase 3)
│   │   └── tasks.py               # Tasks service (Phase 3)
│   ├── briefing/
│   │   ├── sources.py             # Hardcoded RSS + weather source registry
│   │   ├── rss_client.py          # feedparser-backed RSS fetcher
│   │   ├── weather.py             # Open-Meteo client, no API key
│   │   ├── generator.py           # Refresh + cache + dispatch
│   │   └── formatter.py           # Daily/category text rendering
│   ├── storage/
│   │   ├── database.py            # SQLite session helper, init_db()
│   │   └── schema.py              # CREATE TABLE statements
│   ├── data/                      # SQLite DB lives here (gitignored)
│   ├── dashboard/
│   │   └── service.py             # View-model aggregator (Phase 5)
│   ├── templates/
│   │   └── dashboard.html         # Single Jinja2 template
│   ├── static/
│   │   └── dashboard.css          # Local CSS, no remote fonts
│   └── security/
│       ├── allowlist.py           # Default-deny command whitelist
│       ├── audit_log.py           # JSONL audit logger
│       ├── audit_reader.py        # Read-only audit log parser (Phase 5)
│       └── sensitive_data.py      # Sensitive-data detector (Phase 3)
├── docs/
│   ├── architecture.md            # System design, request flow
│   ├── security-model.md          # Threat model, safety layers
│   ├── roadmap.md                 # Phased build plan
│   └── demo-checklist.md          # Screenshot checklist
├── scripts/setup.sh               # Pi bootstrap helper
└── tests/                         # 23 pytest tests
```

---

## Deploying to a Raspberry Pi 5 (Phase 6)

Phase 6 ships a turn-key deployment to a Raspberry Pi. The same backend that runs on your MacBook in development runs unchanged on the Pi as a non-root systemd service. No application code changes are needed.

```bash
# On the Pi (after SSH-ing in):
git clone https://github.com/YeshwanthBalaji0412/rasapi-local-ai-assistant.git
cd rasapi-local-ai-assistant
bash deployment/raspberry-pi/install.sh    # creates venv, installs deps, seeds .env
chmod 600 .env

# Try a manual run first
cd backend && source .venv/bin/activate
uvicorn main:app --host 127.0.0.1 --port 8000

# Then the smoke test
bash deployment/raspberry-pi/smoke-test.sh

# Install as a systemd service
sed "s|<PI_USER>|$USER|g" deployment/raspberry-pi/rasapi.service \
  | sudo tee /etc/systemd/system/rasapi.service > /dev/null
sudo systemctl daemon-reload && sudo systemctl enable --now rasapi
sudo systemctl status rasapi
```

> ⚠️ **No public exposure.** Phase 6 has no authentication. The shipped systemd unit binds to `127.0.0.1` (Pi-local only). To reach the dashboard from your MacBook over the home LAN, switch one line to `--host 0.0.0.0` and only do this on a trusted network. Never port-forward to the public internet.

Full guide, troubleshooting, backup/restore, and the optional Ollama appendix: [`deployment/raspberry-pi/setup-pi.md`](deployment/raspberry-pi/setup-pi.md). Cross-environment overview: [`docs/deployment.md`](docs/deployment.md).

---

## Hardware target

- Raspberry Pi 5 (8 GB recommended for Phase 2 LLM)
- 64-bit Raspberry Pi OS (Bookworm)
- USB 3 SSD recommended for model storage
- No GPU required

The Phase 1 MVP also runs cleanly on macOS and Linux for development.

---

## Next phases

See [docs/roadmap.md](docs/roadmap.md) for the full plan.

- **Phase 2** ✅ Local LLM fallback via Ollama (opt-in)
- **Phase 3** ✅ Local memory, notes, and tasks
- **Phase 4** ✅ Daily intelligence briefing
- **Phase 5** ✅ Local web dashboard
- **Phase 6** 🟡 Raspberry Pi deployment (in progress) — see [docs/deployment.md](docs/deployment.md)
- **Phase 7** — Voice input/output (Whisper + Piper, all local)
- **Phase 8** — Authentication and remote-access hardening

---

## License

MIT
