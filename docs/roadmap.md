# RasaPi — Build Roadmap

Each phase is independently deployable and demoable. Later phases extend earlier modules but never retroactively change their interfaces.

---

## ✅ Phase 1 — Secure Backend MVP (complete)

**Goal:** A working FastAPI server that enforces the security model from day one, with no LLM in the loop yet.

**Delivered:**

- [x] FastAPI app with `/health`, `/ask`, `/commands` endpoints
- [x] Pydantic-based config loaded from `.env`
- [x] Deterministic keyword-based intent router (9 intents + fallback)
- [x] Default-deny command allowlist with typed argument validation
- [x] `subprocess(shell=False)` command runner with 10 s timeout
- [x] Structured JSONL audit logger with daily rotation
- [x] Three-layer command safety model documented and enforced
- [x] pytest suite — **23 tests passing**

**Outcome:** A live server that can answer system-status questions with cryptographic-grade boundary enforcement, fully demonstrable on macOS or Pi without any model weights on disk.

---

## ✅ Phase 1.5 — Documentation & Polish (complete)

**Goal:** Make the project recruiter-ready before adding more code.

- [x] README rewritten with phase-aware status
- [x] `docs/architecture.md` updated with current request flow + safety layers
- [x] `docs/security-model.md` updated with three-layer model + audit details
- [x] `docs/roadmap.md` reflects Phase 1 completion and revised future phases
- [x] `docs/demo-checklist.md` lists screenshots to capture for the showcase

No new features in this phase — only documentation and minor polish.

---

## ✅ Phase 2 — Local LLM Fallback (complete)

**Goal:** Add a conversational fallback for queries that the deterministic router cannot match — fully local, fully opt-in, zero cloud calls.

**Delivered in this phase:**

- [x] New module `core/local_llm.py` — Ollama HTTP client (`/api/chat`)
- [x] `ENABLE_LOCAL_LLM` opt-in flag (default **off**)
- [x] Hard-coded system prompt; user query is the only dynamic input
- [x] Default model: `llama3.2:1b` (lightweight, Pi 5 friendly)
- [x] Configurable model + timeout via `.env`
- [x] LLM only invoked when router returns `fallback`
- [x] Graceful degradation on timeout / connection error / empty body
- [x] Structured `llm_call` audit events with outcome + duration
- [x] 9 new tests; **32/32 passing total**
- [x] Structural test prevents `core/local_llm.py` from importing executors

**Security invariant maintained:** The LLM is never an executor. `core/local_llm.py` does not import `command_runner`, `allowlist`, or `subprocess`. Output is opaque conversational text. See [docs/security-model.md](security-model.md#llm-cannot-execute-tools-phase-2).

**Still to do (optional polish before closing the phase):**

- [ ] Health endpoint reports Ollama reachability (`/health` field `local_llm: "up" | "down" | "disabled"`)
- [ ] Optional structured-output mode: LLM proposes a known intent name; router still dispatches (advances Phase 3 readiness)

**Models known to work:** `llama3.2:1b` (default), `llama3.2:3b`, `phi-3-mini`, `mistral:7b` (8 GB Pi only).

---

## ✅ Phase 3 — Local Memory, Notes, and Tasks (complete)

**Goal:** Give the assistant a memory across sessions — locally-stored memory items, free-form notes, and a tasks list.

**Delivered:**

- [x] SQLite database at `backend/data/rasapi.db` (gitignored)
- [x] Three tables: `memory_items`, `notes`, `tasks` (idempotent `CREATE TABLE IF NOT EXISTS`)
- [x] Service layer in `core/memory.py` and `core/tasks.py` (no LLM, no subprocess)
- [x] Conversational `/ask` intents: `save_memory`, `list_memory`, `save_note`, `list_notes`, `add_task`, `list_tasks`, `complete_task`
- [x] Direct REST endpoints: `POST/GET /memory`, `POST/GET /notes`, `POST/GET /tasks`, `PATCH /tasks/{id}/complete`
- [x] Sensitive-data detector (`security/sensitive_data.py`) blocks passwords, API keys, JWTs, SSNs, credit-card-shaped numbers, private keys
- [x] Audit log extended with 8 new `storage_event` types
- [x] Phase 1 `memory` intent renamed to `memory_usage` to free the keyword space
- [x] Per-test isolated SQLite via `conftest.py` autouse fixture
- [x] **77 tests passing**, including SQL injection regression and structural import checks

**Security invariants maintained:**

- Router still runs first; memory intents short-circuit before any LLM dispatch.
- LLM cannot create memory, notes, or tasks. Verified by `test_llm_response_does_not_create_memory`.
- Memory operations cannot invoke `command_runner.run_command`. Verified by mock-and-fail tests.
- Sensitive content is rejected with a static message; the matched pattern (not content) is audited.

**Still to do (optional polish):**

- [ ] `DELETE /memory/{id}`, `DELETE /notes/{id}` (Phase 3 spec called these out as "explicit endpoint with confirmation"; deferred until needed)
- [ ] Archiving endpoint (currently `archived` column exists but no UI to flip it)
- [ ] CLI tool to export or wipe local data

**Privacy invariant:** memory never leaves the device. Wipe is a single `rm -f backend/data/rasapi.db`.

---

## ✅ Phase 4 — Daily Intelligence Briefing (complete)

**Goal:** A free, local-first news + weather digest. No API keys. No cloud LLM. The deterministic intent router still runs first.

**Delivered:**

- [x] `backend/briefing/` package: `sources.py`, `rss_client.py`, `weather.py`, `generator.py`, `formatter.py`
- [x] Hardcoded source registry covering world, AI, tech, developer, weather, immigration
- [x] `feedparser==6.0.11` added to `requirements.txt`
- [x] Open-Meteo weather provider (no API key, free public-data service)
- [x] SQLite schema extended with `briefing_items` and `briefing_runs` tables + indexes
- [x] Seven new intents: `daily_briefing`, `world_briefing`, `ai_briefing`, `tech_briefing`, `developer_briefing`, `weather_briefing`, `immigration_briefing`
- [x] Five REST endpoints under `/briefing`
- [x] Auto-refresh on `/ask` cache miss (`BRIEFING_CACHE_MINUTES=60` default)
- [x] Per-source dedup (URL or category+title within 7 days)
- [x] Partial-success handling: one source failing doesn't kill the briefing
- [x] Hardcoded immigration disclaimer appended to all immigration responses
- [x] Optional opt-in-opt-in LLM summarization (`ENABLE_LOCAL_LLM` AND `ENABLE_LLM_BRIEFING_SUMMARY` both required, both default to off/false)
- [x] 10 new audit event types (`briefing_refresh_*`, `briefing_source_failed`, `briefing_item_stored`, `briefing_served`, `weather_fetch_*`, `llm_briefing_summary_*`)
- [x] **126 tests passing** (49 new, including a structural AST test that fails the build if `briefing/` ever imports memory/tasks/subprocess)

**Security invariants maintained:**

- Briefing path cannot read memory/notes/tasks (structural test).
- Briefing path cannot invoke `command_runner.run_command` (mock-and-fail test).
- Briefing intents short-circuit before any conversational LLM dispatch.
- LLM summary call only sees public source headlines, never personal data.
- All RSS/weather network egress is to hosts named in the hardcoded registry — runtime URL injection is impossible.

**Reserved for a future explicit security decision:**

- `personalized_action_items` category exists as a documented empty stub. Phase 4 deliberately does not feed it from local memory or tasks.

**Still to do (deferred):**

- [ ] Background scheduler (deferred to a later phase; Phase 4 is manual refresh only)
- [ ] Slack delivery (documented as future integration only)
- [ ] Auto-prune of old `briefing_items` rows
- [ ] Add OpenAI / Anthropic blog feeds when official RSS endpoints become available

---

## ✅ Phase 5 — Local Web Dashboard (complete)

**Goal:** Make the project recruiter-showcase ready with a clean, local-only web dashboard at `/dashboard`. Server-rendered HTML, no JavaScript framework, no CDN.

**Delivered:**

- [x] `backend/dashboard/service.py` — view-model aggregator
- [x] `backend/api/routes/dashboard.py` — 1 HTML + 3 JSON + 2 form-POST endpoints
- [x] `backend/templates/dashboard.html` — single Jinja2 template, autoescape on
- [x] `backend/static/dashboard.css` — local CSS, no remote fonts
- [x] `backend/security/audit_reader.py` — read-only JSONL parser, skips malformed lines
- [x] Two safe write actions: refresh briefing, complete task (both reuse existing services)
- [x] Path masking via `dashboard_mask_db_path=true` (default)
- [x] `Settings` projected to a hardcoded safe subset before reaching templates
- [x] 6 new audit event types via `log_dashboard_event`
- [x] `feedparser`/`jinja2` are the only two non-stdlib runtime deps so far
- [x] **154 tests passing** (28 new, 0 regressions)

**Security invariants maintained:**

- No authentication yet — local-only by design, README and template footer warn against public exposure.
- HTML autoescape on; user content truncated to 200 chars.
- No free-form input field; form actions whitelisted to `/briefing/refresh` and `/tasks/{id}/complete` (test enforces this).
- Audit reader is read-only and crash-resistant — malformed JSONL never breaks a page render.
- API keys, secrets, full DB paths, and audit log dir paths never appear in rendered HTML.
- Dashboard does not ping Ollama — configuration shown only.

**Reserved for later phases:**

- [ ] Authentication / sessions (Phase 8)
- [ ] HTTPS / TLS termination (Phase 8)
- [ ] CSRF tokens (Phase 8)
- [ ] Editing memory / notes from the dashboard (deferred — not security-justified yet)

---

## ✅ Phase 6 — Raspberry Pi Deployment (complete)

**Goal:** Deploy the existing backend + dashboard to a Raspberry Pi 5 as an always-on local-first service. No application code changes.

**Delivered:**

- [x] `deployment/raspberry-pi/install.sh` — idempotent, aborts if system packages missing, never runs `sudo apt`, never overwrites `.env`
- [x] `deployment/raspberry-pi/rasapi.service` — non-root systemd unit, default `127.0.0.1`, commented LAN-binding alternative, `Restart=on-failure`, modest sandboxing (`NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=full`)
- [x] `deployment/raspberry-pi/env.example.pi` — Pi-tuned defaults, LLM off, no real credentials
- [x] `deployment/raspberry-pi/smoke-test.sh` — 9-endpoint smoke check, `BASE_URL` configurable
- [x] `deployment/raspberry-pi/backup.sh` and `restore.sh` — DB + audit logs, never touches `.env`
- [x] `deployment/raspberry-pi/setup-pi.md` — 19-step copy-pasteable guide including optional Ollama and Tailscale appendices
- [x] `deployment/raspberry-pi/troubleshooting.md`
- [x] `docs/deployment.md` — top-level deployment overview + future phases
- [x] **31 new file/content/permission tests** in `tests/test_deployment_files.py`
- [x] **185 tests passing** (0 regressions)

**Security invariants maintained:**

- Default systemd binding is `127.0.0.1`; LAN binding is opt-in by editing a single line.
- Service runs as `<PI_USER>`, not root. Test rejects `User=root`.
- `install.sh` never modifies `/etc/`, never runs `sudo apt`, never overwrites `.env`.
- Backup and restore exclude `.env`. Tests enforce no copy of `.env` in either script.
- No authentication added; all warnings against public exposure are visible in README, setup guide, dashboard footer, and security model.

**Reserved for later phases:**

- [ ] Authentication / sessions (Phase 8)
- [ ] HTTPS / reverse proxy patterns (Phase 8)
- [ ] Tailscale / WireGuard install automation (Phase 8)
- [ ] Docker image (Phase 8+)
- [ ] OpenAI / Anthropic blog feeds when official RSS endpoints exist (any phase)

---

## 🟡 Phase 7 — Voice I/O (in progress)

**Goal:** Add a local push-to-talk voice interface. No wake word, no always-listening mode, no cloud speech, no audio leaving the device. Voice is a thin record/STT/TTS shell around the existing `/ask` orchestration.

**Delivered:**

- [x] `core/orchestration.py` — `process_query` extracted; `/ask` and voice both use it. Single source of truth for routing + LLM fallback.
- [x] `voice/recorder.py` — mock + arecord adapters
- [x] `voice/stt.py` — mock + whisper.cpp adapters
- [x] `voice/tts.py` — mock + espeak-ng + piper adapters
- [x] `voice/session.py` — push-to-talk orchestration. **No subprocess, no command_runner, no local_llm imports.**
- [x] `voice/cli.py` — `python -m voice.cli {status, record-test, stt-test, tts-test, once}`
- [x] `api/routes/voice.py` — `GET /voice/status`, `POST /voice/test-tts`, `POST /voice/session-once`
- [x] Dashboard "Voice" card with engine config + last-session status
- [x] `deployment/raspberry-pi/audio-setup.md` — full Pi audio setup, whisper.cpp build steps, Piper voice install, troubleshooting
- [x] 6 new audit event types via `log_voice_event`. Audio bytes never leave RAM.
- [x] Default engines are pure-Python mocks → no new pip dependencies, tests don't need a microphone
- [x] **32 new tests, 217 total passing, 0 regressions**

**Security invariants enforced in code AND tests:**

- Voice does not introduce a new exec path. All transcripts route through `orchestration.process_query`.
- `voice/session.py` and `voice/cli.py` cannot import `subprocess`, `core.command_runner`, or `core.local_llm`. Structural AST tests reject violations.
- Subprocess usage is whitelisted to engine adapters only (`recorder.py`, `stt.py`, `tts.py`).
- Voice REST endpoints return 403 when `ENABLE_VOICE=false`. Default is off.
- Audio temp files are deleted after STT unless `VOICE_SAVE_AUDIO=true`.
- Transcripts capped at `VOICE_MAX_TRANSCRIPT_CHARS` (default 1000).
- Audit log never contains audio bytes, file paths, or transcript content — only metadata.

**Reserved for later phases:**

- [ ] Wake word ("Hey RasaPi") — Phase 9 candidate
- [ ] Always-listening mode with VAD — needs explicit consent UX
- [ ] Browser microphone / WebRTC — would require Phase 8 auth first
- [ ] Background voice systemd worker
- [ ] Cloud speech fallback — out of charter

---

## 🔮 Phase 8 — Authentication and Remote-Access Hardening

**Goal:** Make remote access safe so the dashboard can be exposed beyond the Pi-local default.

**Planned (none of this exists yet):**

- [ ] Authentication: API key header for `/ask` and `/dashboard`; or session cookies for the dashboard
- [ ] HTTPS termination via a documented reverse proxy (Caddy or nginx)
- [ ] CSRF tokens on dashboard form-POST endpoints
- [ ] Tailscale/WireGuard install patterns documented and optionally automated
- [ ] Firewall sample (`ufw`) with explicit rules
- [ ] Log rotation via `logrotate` for audit JSONL files
- [ ] Optional Dockerfile (`linux/arm64`) for users who prefer containers
- [ ] `/metrics` endpoint (Prometheus format) for monitoring
- [ ] First-boot wizard that generates `API_SECRET_KEY` and substitutes `<PI_USER>` in the systemd unit automatically

---

## Permanent non-goals

These are decisions, not omissions. They will not change without an explicit project-charter update.

- ❌ No always-on cloud connectivity
- ❌ No sending queries to third-party LLM providers without per-request user consent
- ❌ No storing conversation history in any cloud
- ❌ No always-streaming audio to the network
- ❌ No telemetry beacons or usage analytics
- ❌ No unrestricted shell execution under any condition
