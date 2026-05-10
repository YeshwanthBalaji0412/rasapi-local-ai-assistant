# RasaPi — Final Architecture (Phases 1–10)

This document is the canonical architecture reference. The shorter
[`architecture.md`](architecture.md) is an operator-facing summary that
links here for the deep dive.

> Phase 10 makes no application-logic changes. The architecture below
> describes phases 1 through 9 as they exist in code today, plus the
> three Phase 10 endpoints (`/version`, `/readiness`, `/config/status`).

---

## 1. High-level deployment topology

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
   │   /etc/systemd/system/rasapi.service                    │
   │     User=<PI_USER>  (NOT root)                          │
   │     ExecStart=uvicorn main:app  (Pi-local OR LAN)       │
   │                                                         │
   │   ~/rasapi-local-ai-assistant/                          │
   │     ├── backend/.venv               (Python venv)       │
   │     ├── backend/data/rasapi.db      (SQLite)            │
   │     ├── backend/data/audio_tmp/     (deleted after STT) │
   │     ├── logs/audit-*.jsonl          (append-only)       │
   │     └── .env                        (chmod 600)         │
   │                                                         │
   │   Optional local services:                              │
   │     ├── ollama daemon  (Phase 2, opt-in, localhost only)│
   │     └── whisper.cpp + espeak-ng / piper  (Phase 7)      │
   └────────────────────────┬────────────────────────────────┘
                            │ http  (LAN-only with auth,
                            │        or Tailscale, no public exposure)
                            ▼
                       MacBook browser
                       http://<pi-ip>:8000/dashboard
```

**Trust boundary:** RasaPi never accepts traffic from the public
internet. Phase 8 added optional auth so LAN/Tailscale access is safer;
Phase 9 added gated integrations; Phase 10 is read-only polish.

---

## 2. Request flow — `POST /ask`

```
   client (curl / browser / voice CLI)
      │  Authorization or X-RasaPi-Key (Phase 8, optional)
      ▼
   api/routes/assistant.py  (auth dependency on protected flags)
      │  audit log_request(query)
      ▼
   core/orchestration.process_query(query, request_id)
      │
      │  step 1: deterministic intent router (Phase 1)
      ▼
   core/intent_router.route()
      │  match keywords against the closed INTENTS tuple
      │
      ├── matched intent ─►  handler(query, request_id)
      │                       OR command_runner.run_command(cmd, args)
      │                            ├── allowlist validate
      │                            └── subprocess.run(shell=False)
      │
      └── intent == "fallback" AND enable_local_llm
                                   ▼
                          core/local_llm.generate_chat_response(query)
                          (Phase 2 — Ollama, opt-in, never executes)
```

**Key invariant:** the LLM has no path to `command_runner`, to
`memory.save_memory`, to `tasks.add_task`, to `integrations.slack`, or
to `integrations.home_assistant`. The intent router is the only
dispatcher. Structural AST tests (Phase 2, 3, 4, 7, 9) enforce this.

---

## 3. Voice flow (Phase 7)

```
   microphone (USB / Bluetooth HSP)
        │
        ▼
   voice/recorder.py (arecord adapter)
        │  writes <uuid>.wav to backend/data/audio_tmp/
        ▼
   voice/stt.py (whisper.cpp adapter)
        │  transcribes locally, truncates to VOICE_MAX_TRANSCRIPT_CHARS
        ▼
   voice/session.py
        │  audit voice_session_started, _recording_completed, _transcription_completed
        │
        ▼
   core/orchestration.process_query(transcript)  ◄── SAME function /ask uses
        │
        ▼
   voice/tts.py (espeak / piper adapter)
        │  speaks the response
        │
        ▼
   speaker (3.5mm / HDMI / Bluetooth A2DP)
   audit voice_tts_completed, voice_session_completed
   delete <uuid>.wav unless VOICE_SAVE_AUDIO=true
```

**Key invariant:** voice does not introduce a new dispatch path. The
deterministic router runs first regardless of input modality. Voice
modules never import `subprocess`, `core.command_runner`, or
`core.local_llm` (the engine adapters are the only exception, restricted
to `recorder.py`, `stt.py`, `tts.py`).

---

## 4. Auth flow (Phase 8)

```
   BROWSER FLOW                          API CLIENT FLOW
   ────────────                          ───────────────

   GET /dashboard                        POST /ask  (or /memory/*, /voice/*, etc.)
        │                                     │  X-RasaPi-Key: <secret>
        ▼                                     │  OR Authorization: Bearer <secret>
   redirect → /login                          ▼
        │                                require_auth_for_<flag>
   GET /login (form)                          │
        │                                hmac.compare_digest(...)
        ▼                                     │
   POST /login (form: api_key)                ├── ok    → audit protected_route_accessed, continue
        │                                     └── bad   → 401 + audit auth_invalid_key
   hmac.compare_digest(...)
        │
        ├── ok   → Set-Cookie rasapi_session=<signed>
        │         redirect → /dashboard
        │         audit auth_login_success
        │
        └── bad  → redirect → /login?error=1
                   audit auth_login_failed  (reason="bad_key", NO key value)
```

Session cookies are **stateless and signed** (HMAC-SHA256 over JSON
payload with `exp`). No server-side session store. Rotating
`API_SECRET_KEY` invalidates every existing cookie immediately.

CSRF on dashboard form posts uses the **double-submit cookie pattern**
(`rasapi_csrf`). The new `verify_csrf_for_api` helper (Phase 9) skips
CSRF when the caller authenticated via header (API client) and enforces
it when the caller authenticated via cookie (browser).

---

## 5. Dashboard flow (Phase 5)

```
   Browser
      │  GET /dashboard
      ▼
   api/routes/dashboard.py
      │  if AUTH_PROTECT_DASHBOARD and not authenticated → 303 → /login
      ▼
   dashboard/service.build_view_model()
      │
      │  Project a SAFE subset of settings (no secrets):
      │    - overview, system health, intents grouped by phase
      │    - memory/notes/tasks (truncated to 200 chars, HTML-escaped)
      │    - briefing counts + last run
      │    - LLM config (host-only URL, no full path)
      │    - voice config (no audio paths)
      │    - integrations registry (no webhook URL, no HA token)
      │    - auth flags (never the secret)
      │    - recent audit events (truncated to 120 chars per field)
      │    - security events (filtered subset)
      │
      ▼
   Jinja2 (autoescape on) → dashboard.html
      │  every form includes hidden _csrf input
      ▼
   Browser
```

Sentinel tests plant canary values for every secret (`api_secret_key`,
`slack_webhook_url`, `home_assistant_token`) and assert absence in the
rendered HTML.

---

## 6. Briefing flow (Phase 4)

```
   POST /ask "what's happening today"
            OR /briefing/daily
            OR POST /briefing/refresh
      │
      ▼
   briefing/generator.get_or_refresh_daily_briefing
      │  cache check (BRIEFING_CACHE_MINUTES)
      │
      ├── cache HIT  → read from briefing_items
      └── cache MISS → for each Source in briefing/sources.py:
                         │
                         ├── kind=rss   → rss_client.fetch_rss_items (httpx + feedparser)
                         ├── kind=weather → weather.fetch_weather (Open-Meteo, no API key)
                         └── kind=placeholder → []  (personalized_action_items stub)
                         │
                         dedup by URL (or category+title) within 7 days
                         INSERT into briefing_items
                         audit briefing_item_stored
      │
      ▼
   briefing/formatter.format_daily_briefing
      │  immigration_updates items → append disclaimer
      │
      │  if both ENABLE_LOCAL_LLM and ENABLE_LLM_BRIEFING_SUMMARY:
      │     headlines (titles + source names ONLY) → local_llm.generate_briefing_summary
      │
      ▼
   response text
```

**Key invariant:** briefing modules do not import `core/memory` or
`core/tasks` — briefing cannot reach personal data. Structural test
enforces this.

Outbound network goes to: the hardcoded RSS hosts (BBC, NPR, Hugging
Face, Google AI, Ars Technica, The Verge, Hacker News mirror, USCIS)
plus `api.open-meteo.com`. No other hosts.

---

## 7. Integrations flow (Phase 9)

```
   /ask intent           OR        REST endpoint
   (slack_send_test,                 (POST /integrations/slack/test,
    slack_send_briefing,              POST /integrations/home-assistant/.../turn-on,
    ha_status,                        etc.)
    ha_turn_on,
    ha_turn_off)
        │                                  │  X-RasaPi-Key OR session cookie
        │                                  │  + _csrf token (browser flow)
        ▼                                  ▼
   integrations/slack.py             integrations/home_assistant.py
        │                                  │
        │  send_test() — fixed string      │  is_entity_allowed(entity_id):
        │  send_briefing(category) —       │     1. domain in ALLOWED_DOMAINS
        │    uses briefing.formatter       │        AND not in HARD_BLOCK_DOMAINS
        │    output, never raw LLM         │     2. entity_id in ALLOWED_ENTITIES
        │                                  │        (when list is non-empty)
        ▼                                  │     3. method check (turn_on/off → light/switch only)
   httpx.post(SLACK_WEBHOOK_URL, ...)      │
   (URL never logged, never echoed)        ▼
                                      httpx GET/POST with Authorization: Bearer <HA_TOKEN>
                                      (token never logged, never echoed)
        │                                  │
        ▼                                  ▼
   audit log_integration_event       audit log_integration_event
   (target="daily" or               (target=entity_id, reason=action)
    "category:<name>")
```

**Key invariants:**
- Slack only sends the fixed test string or the briefing formatter's output. There is no API surface for free-form messages.
- Home Assistant only invokes `turn_on`/`turn_off` (on `light`/`switch`) or state reads. There is no API surface for arbitrary service names.
- The hard-block list (`lock`, `alarm_control_panel`, `cover`, `camera`, `device_tracker`, `person`) is enforced inside the HA module. Operator cannot override via `.env`.
- Webhook URL and HA token live in `.env` only. Sentinel tests assert absence in audit logs, API responses, and dashboard HTML.

---

## 8. Storage and audit flow

```
   ┌──────────────────────────────────────────────────────────────┐
   │                  storage/database.py                         │
   │   db_session() context manager — sqlite3, parameterized SQL  │
   │   init_db() runs CREATE TABLE IF NOT EXISTS on startup       │
   └─────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
   ┌──────────────────────────────────────────────────────────────┐
   │              backend/data/rasapi.db (SQLite)                 │
   │                                                              │
   │   memory_items  (Phase 3 — sensitive_data check on write)   │
   │   notes         (Phase 3)                                   │
   │   tasks         (Phase 3)                                   │
   │   briefing_items, briefing_runs   (Phase 4)                 │
   └──────────────────────────────────────────────────────────────┘

   ┌──────────────────────────────────────────────────────────────┐
   │                 logs/audit-YYYY-MM-DD.jsonl                  │
   │   (append-only, rotated daily, never overwritten)            │
   │                                                              │
   │   Event types (cumulative across all phases):                │
   │     request, command_exec, llm_call                          │
   │     memory_*, note_*, task_*, sensitive_memory_blocked       │
   │     briefing_*, weather_fetch_*, llm_briefing_summary_*      │
   │     dashboard_*, dashboard_briefing_refresh_requested, …     │
   │     voice_session_*, voice_recording_*, voice_*              │
   │     auth_login_*, auth_required_missing, csrf_validation_… │
   │     integration_*, slack_*, home_assistant_*                 │
   │                                                              │
   │   Never logged: secrets, audio bytes, full path traces.      │
   └──────────────────────────────────────────────────────────────┘
```

The audit reader (`security/audit_reader.py`) parses the JSONL files
read-only and is crash-resistant (skips malformed lines). The dashboard
and `doctor.sh` both use it.

---

## 9. Security boundaries

| Boundary | Enforced by |
|---|---|
| **LLM ↔ executor** | `core/local_llm.py` does not import `command_runner`, `allowlist`, or `subprocess`. Structural AST test. |
| **LLM ↔ memory/tasks** | `core/local_llm.py` does not import `core/memory` or `core/tasks`. Tests confirm LLM "telling RasaPi to save" does not create a row. |
| **Briefing ↔ personal data** | `backend/briefing/` does not import `core/memory` or `core/tasks`. Structural test. |
| **Voice ↔ executor** | `voice/session.py` and `voice/cli.py` do not import `subprocess`, `command_runner`, or `local_llm`. Structural test. Subprocess use restricted to engine adapters. |
| **Voice ↔ /ask safety** | Voice flows through `orchestration.process_query` — the same function `/ask` uses. No new dispatch path. |
| **Auth ↔ secrets** | API key compared with `hmac.compare_digest`. Stateless session cookies signed with the secret. No equality (`==`) comparisons against the secret anywhere in `auth.py`. |
| **Dashboard ↔ secrets** | Settings projected to a hardcoded safe subset before reaching templates. Sentinel test plants `api_secret_key="SENTINEL-…"` and asserts absence in `/dashboard`. |
| **Integrations ↔ secrets** | Slack webhook URL and HA token live in `.env` only. Method signatures (`send_test(request_id)`, `turn_on(request_id, entity_id)`) do not accept tokens. Audit logs never contain them. |
| **Integrations ↔ LLM** | Integration handlers reached only via the deterministic router. LLM cannot synthesize Slack messages or HA service calls. |
| **HA ↔ dangerous domains** | Hard-block list inside `home_assistant.py` always rejects `lock`, `alarm_control_panel`, `cover`, `camera`, `device_tracker`, `person`. Cannot be overridden by env. |
| **Network ↔ public internet** | Phase 6 default binds to `127.0.0.1`. Phase 8 strongly recommends Tailscale over port-forwarding. No code path accepts a public-internet origin as trusted. |

---

## 10. What stays on the Pi vs. what leaves it

| Data | Stays on Pi? | Leaves only if… |
|---|---|---|
| Memory items, notes, tasks | yes | (never) |
| Audit logs | yes | (never) |
| Voice audio | yes (deleted after STT by default) | `VOICE_SAVE_AUDIO=true` (still on Pi, never uploaded) |
| Voice transcripts | yes (recorded in audit at the operator's choice) | (never) |
| API_SECRET_KEY | yes | (never) |
| Briefing items (cached) | yes | (never) |
| Slack messages | leaves to Slack | `ENABLE_SLACK=true` and the operator triggers a send |
| HA actions | leaves to HA host | `ENABLE_HOME_ASSISTANT=true` and the operator triggers an action |
| Outbound RSS / weather requests | leaves to public hosts | `ENABLE_BRIEFING=true` (default) |
| Outbound LLM headlines | yes (Ollama is local) | (never; Phase 14 may add cloud LLM with redaction) |

**No data ever leaves the Pi to a cloud LLM, a third-party analytics
service, or an integration provider unless the operator has explicitly
turned on that integration.**

---

## 11. Phase 10 additions

Three new endpoints (no application-logic changes):

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /version` | public | name + version |
| `GET /readiness` | public | k8s-style readiness probe over JSON |
| `GET /config/status` | session or API key when auth on | safe feature-flag summary, no secrets |

Four new scripts:

| Script | Purpose |
|---|---|
| `check-readiness.sh` | PASS/FAIL audit of service + endpoints + filesystem |
| `health-check.sh` | One-liner for cron monitors |
| `update-rasapi.sh` | Safe git pull + pip + restart |
| `doctor.sh` | "What's wrong" diagnostic — never prints secrets |

Ten new docs consolidate operator knowledge (this one, plus
[`operator-guide.md`](operator-guide.md),
[`configuration.md`](configuration.md),
[`maintenance.md`](maintenance.md),
[`troubleshooting.md`](troubleshooting.md),
[`security-hardening-checklist.md`](security-hardening-checklist.md),
[`use-cases.md`](use-cases.md),
[`command-reference.md`](command-reference.md),
[`readiness-checklist.md`](readiness-checklist.md),
[`phase-11-roadmap.md`](phase-11-roadmap.md)).

---

## 12. Future direction (Phase 11+)

See [`phase-11-roadmap.md`](phase-11-roadmap.md). RasaPi's charter
through Phase 10:

- ✅ Local-first
- ✅ Secure by default
- ✅ Optional auth
- ✅ Allowlisted integrations
- ❌ No public exposure
- ❌ No cloud APIs
- ❌ No always-listening voice
- ❌ No multi-user

Phase 11+ may relax some of these **with operator consent**, never by
default. The hard-block list (HA), the no-LLM-executor invariant, the
no-secrets-in-logs invariant, and the no-public-exposure default are
permanent.
