# RasaPi — Local-First Secure AI Assistant on Raspberry Pi 5

[![Phase](https://img.shields.io/badge/phase-1%20MVP-green)]() [![Tests](https://img.shields.io/badge/tests-23%2F23-brightgreen)]() [![License](https://img.shields.io/badge/license-MIT-blue)]()

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

## Phase 1 — what works today

The Phase 1 MVP is a fully working text-based assistant with three-layer command safety. **No LLM yet** — Phase 1 uses a deterministic keyword router so the security model can be validated in isolation.

**Capabilities:**

- `POST /ask` — submit a natural-language query, get a routed response
- `GET /commands` — list every supported intent (great for live demos)
- `GET /health` — liveness, version, assistant name
- Deterministic keyword-based intent router (no model required)
- Safe command execution gated by an allowlist with typed argument validation
- Structured JSONL audit trail for every request and command
- `.env`-based configuration via `pydantic-settings`
- Full test suite — **23/23 passing** (`pytest`)

**Supported intents (Phase 1):**

| Intent | Triggers | Action |
|---|---|---|
| `greeting` | "hello", "hi", "hey" | Built-in static response |
| `help` | "help", "what can you do" | Lists available intents |
| `time` | "time", "date", "what day" | Runs `date` |
| `uptime` | "uptime", "how long" | Runs `uptime` |
| `cpu_temp` | "temperature", "how hot" | Runs `vcgencmd measure_temp` (Pi only) |
| `disk` | "disk", "storage", "space" | Runs `df -h` |
| `memory` | "memory", "ram" | Runs `free -h` |
| `hostname` | "hostname", "device name" | Runs `hostname` |
| `system` | "kernel", "os version" | Runs `uname -a` |
| `fallback` | _anything else_ | Returns "not supported in Phase 1" |

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

That's it. No model download required for Phase 1.

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

## API endpoints

| Method | Path | Purpose | Body |
|---|---|---|---|
| GET | `/health` | Liveness probe | — |
| GET | `/commands` | List supported intents | — |
| POST | `/ask` | Submit a query | `{"query": "string"}` |

### Response schema for `/ask`

```json
{
  "request_id": "uuid",
  "intent": "time | greeting | fallback | …",
  "response": "string — output of command or built-in handler",
  "source": "local",
  "duration_ms": 3
}
```

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
```

### Run the test suite

```bash
cd backend && source .venv/bin/activate
cd .. && python -m pytest tests/ -v
```

Expected: `23 passed`.

---

## Security model summary

Every command goes through **three independent layers** before any process is spawned. Each layer alone would be sufficient for most attackers; together they make Phase 1 the security foundation the rest of the project builds on.

```
Query → [1] Intent Router → [2] Allowlist Validator → [3] Subprocess (shell=False)
         keyword-matched      typed args, default-deny    no shell expansion, list args
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
│   │   ├── intent_router.py       # Keyword → intent → command
│   │   ├── command_runner.py      # subprocess(shell=False) + audit
│   │   └── llm.py                 # Phase 2 stub
│   └── security/
│       ├── allowlist.py           # Default-deny command whitelist
│       └── audit_log.py           # JSONL audit logger
├── docs/
│   ├── architecture.md            # System design, request flow
│   ├── security-model.md          # Threat model, safety layers
│   ├── roadmap.md                 # Phased build plan
│   └── demo-checklist.md          # Screenshot checklist
├── scripts/setup.sh               # Pi bootstrap helper
└── tests/                         # 23 pytest tests
```

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

- **Phase 2** — Ollama local LLM integration
- **Phase 3** — Persistent memory and reminder storage
- **Phase 4** — Voice input/output (Whisper + Piper, all local)
- **Phase 5** — Raspberry Pi deployment hardening

---

## License

MIT
