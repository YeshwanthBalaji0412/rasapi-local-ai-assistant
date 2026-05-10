# RasaPi — Phase 11+ Roadmap

What might come after Phase 10. Each phase below is **scoped and
realistic** — none of them is a rewrite, none of them assumes a team,
none of them breaks the security invariants codified through Phase 10.

The order is suggestive, not strict. You may skip a phase, do them out
of order, or never do some of them at all.

---

## Phase 11 — Reliability + Scheduler

**Goal:** RasaPi runs unattended for weeks. Background work that today
requires the operator to manually trigger (briefing refresh, backups,
log rotation) should be automatic and observable.

**Likely scope:**
- Local scheduler module (`backend/scheduler/`) — APScheduler or a
  hand-rolled async loop. No new heavy deps if avoidable.
- Scheduled daily briefing refresh (e.g. every morning at 06:30 local)
- Scheduled backups (e.g. nightly to `~/rasapi-backups/`)
- Log rotation: prune `audit-*.jsonl` older than N days
- Health watchdog: emit `health_warning` audit event when disk > 90%,
  when `rasapi.service` has restarted recently, when briefing fetches
  fail consistently
- Optional Slack notification on watchdog events (reuses Phase 9 Slack)
- Schedule config in `.env`:
  - `SCHEDULER_ENABLED=false`
  - `SCHEDULED_BRIEFING_CRON=`
  - `SCHEDULED_BACKUP_CRON=`
  - `AUDIT_LOG_RETENTION_DAYS=30`

**Security invariants preserved:**
- All scheduled actions go through the same orchestration + audit path
  as manual ones
- No new external dependencies on a third-party cron service
- Scheduler can be disabled with one env flag

**Out of scope for Phase 11:**
- ❌ Public-facing webhooks (would require Phase 16 work)
- ❌ Multi-host coordination

---

## Phase 12 — Wake Word Mode (opt-in)

**Goal:** Hands-free voice without losing local-first privacy.

**Likely scope:**
- [openWakeWord](https://github.com/dscripka/openWakeWord) integration —
  local model, low CPU, no cloud
- New module `voice/wake.py` with `start_listener()`, `stop_listener()`
- Wake-word listener is a separate systemd unit, opt-in via
  `ENABLE_WAKE_WORD=false` (default off)
- On wake, run the existing `voice/session.run_session_once()` flow
- Privacy banner on the dashboard whenever wake mode is enabled
- Audit event `wake_word_triggered` per detection (no audio bytes)

**Security invariants preserved:**
- Wake-word listener runs locally, no cloud transcription
- Once triggered, the existing Phase 7 push-to-talk flow handles the
  rest (record → STT → process_query → TTS)
- Disable knob in `.env` immediately stops listening on next restart
- Dashboard shows clear "listening" indicator

**Out of scope for Phase 12:**
- ❌ Custom wake words requiring training
- ❌ Always-streaming audio to cloud STT

---

## Phase 13 — Home Assistant Polish

**Goal:** Make the existing HA integration nicer to use day to day,
without expanding its security surface.

**Likely scope:**
- Entity aliases: `light.kitchen_main_aaa_b1234567` → "kitchen light"
  via a simple `HA_ENTITY_ALIASES=` map in `.env`
- Confirmation flow for medium-risk actions (e.g. "turn off everything")
- Room / device grouping ("turn on all lights in the living room")
- `ha_state` intent for natural-language sensor reads (deferred from
  Phase 9 — needs careful entity matching)
- Dashboard tab listing live entity state

**Security invariants preserved:**
- Two-layer allowlist (domain + entity_id) unchanged
- Hard-block list still applies — no new dangerous domains
- LLM still cannot synthesize HA calls

**Out of scope for Phase 13:**
- ❌ Lock / camera / alarm domains
- ❌ HA configuration mutation

---

## Phase 14 — Cloud LLM Fallback with Redaction (opt-in-opt-in-opt-in)

**Goal:** When Ollama can't answer well enough and the operator
explicitly opts in, send the query to a cloud LLM **after redaction**.

**Likely scope:**
- `core/cloud_llm.py` with adapters for Claude and OpenAI (operator
  picks one, can disable both)
- Hard requirement: a redaction pass runs **before** the query leaves
  the Pi. Strips memory contents, names, addresses, phone numbers,
  emails, IPs, file paths. The Phase 3 sensitive-data detector is the
  starting point.
- Per-request confirmation: the operator must approve sending the query
  to the cloud OR pre-authorize an "always send" category
- Cost tracking: dashboard shows tokens sent + estimated cost per day
- Audit event `cloud_llm_call` with model name, redaction count, token
  count — **never** the redacted query content
- `.env`:
  - `ENABLE_CLOUD_LLM=false` (triple-locked)
  - `CLOUD_LLM_PROVIDER=` (`anthropic` | `openai`)
  - `CLOUD_LLM_KEY=` (in `.env` only)
  - `CLOUD_LLM_DAILY_TOKEN_BUDGET=10000`

**Security invariants preserved:**
- Cloud LLM never sees `memory_items`, `notes`, `tasks`, audit logs, or
  config secrets
- Redaction errs on the side of over-redaction
- Token budget enforced at the Pi
- Cloud LLM has no path to integrations (Slack, HA) — still text-only

**Out of scope for Phase 14:**
- ❌ Fine-tuning a cloud model on your data
- ❌ Sending audio to cloud STT (still local whisper.cpp)
- ❌ Long-context conversation history sent to cloud

---

## Phase 15 — Global Risk Intelligence Layer

**Goal:** A second briefing category that tracks risks rather than news:
geopolitical conflict, internet outages, sanctions, severe weather,
natural disasters relevant to the operator's location.

**Likely scope:**
- New briefing category `global_risk`
- Sources: public APIs and RSS only
  - [USGS earthquakes](https://earthquake.usgs.gov/earthquakes/feed/)
  - [NOAA weather alerts](https://www.weather.gov/documentation/services-web-api)
  - GDELT, ACLED (public datasets)
  - OFAC sanctions list updates
  - NIST CVE feed
- Risk scoring per item (low/medium/high)
- Dashboard "Risk briefing" card alongside the existing briefing card
- Optional Slack alert for `risk=high` items
- Operator-configurable allowed sources (defaults conservative)

**Security invariants preserved:**
- Public-source RSS / APIs only — no scraping
- No data leaves the Pi unless Slack alert is configured
- LLM cannot reach the risk module directly

**Out of scope for Phase 15:**
- ❌ Predictive scoring / machine learning
- ❌ Paid threat-intel feeds
- ❌ Per-user risk profiles

---

## Phase 16 — Alexa Skill or Voice Assistant Bridge

**Goal:** Reach RasaPi from Alexa, Google Assistant, or Apple Shortcuts.

**Likely scope (after HTTPS + reverse-proxy work, which is a sub-phase
of Phase 10's "deferred" list):**
- Reverse proxy with TLS (Caddy or Tailscale Serve / Funnel)
- Per-skill API key with limited scope
- Alexa Skill (or Google Action) that POSTs to `/ask` over HTTPS
- Per-request confirmation if the skill triggers an HA action

**Important framing:** the safer path through Phase 16 is

```
   Alexa / Google → Home Assistant → (Alexa Smart Home integration) → physical devices
```

…rather than Alexa → RasaPi → HA. RasaPi's role becomes "the brain"
rather than "the speech endpoint". This keeps Amazon/Google out of
RasaPi's data flow.

**Security invariants preserved:**
- No data leaves the Pi unless the operator explicitly enables the skill
- API key scoped to the skill (revocable independently of the operator's
  main key)
- Alexa never sees memory / notes / tasks / audit content

**Out of scope for Phase 16:**
- ❌ Multi-account skills (single-operator only)
- ❌ Cloud-hosted RasaPi backend (still runs on the Pi)

---

## What is permanently out of scope

Independent of any future phase, RasaPi will not:

- ❌ Ship telemetry to anyone
- ❌ Auto-update itself
- ❌ Run as root
- ❌ Allow LLM output to execute commands
- ❌ Allow LLM output to write to memory/tasks directly
- ❌ Allow arbitrary URLs from user input
- ❌ Allow arbitrary HA service names from user input
- ❌ Bind to a public port by default
- ❌ Store secrets in the database
- ❌ Send audio bytes to cloud STT

These are the project's **permanent non-goals**, codified in
[`docs/roadmap.md`](roadmap.md).
