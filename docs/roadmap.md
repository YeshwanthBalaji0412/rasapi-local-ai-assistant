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

## 🟡 Phase 2 — Local LLM Fallback (in progress)

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

## 🔮 Phase 3 — Memory & Persistent Storage

**Goal:** Give the assistant a memory across sessions — reminders, preferences, conversation history.

**Planned:**

- [ ] SQLite database (`data/rasapi.db`) — local only
- [ ] Schema: `reminders`, `preferences`, `conversation_log`
- [ ] New endpoints: `POST /reminders`, `GET /reminders`, `DELETE /reminders/{id}`
- [ ] Conversation context: last N turns passed to the LLM as memory
- [ ] User-scoped data (single-user Phase 3, multi-user Phase 5+)
- [ ] Encryption-at-rest option using `SQLCipher` (off by default, `.env` flag)
- [ ] CLI tool to export/wipe local data

**Privacy invariant:** memory never leaves the device. Wipe is a single `rm -f data/rasapi.db`.

---

## 🔮 Phase 4 — Voice I/O

**Goal:** Hands-free operation on Pi 5, fully local.

**Planned:**

- [ ] Wake-word detection (openWakeWord, local model)
- [ ] Speech-to-text via `whisper.cpp` (local, CPU)
- [ ] Text-to-speech via Piper TTS (local, fast on Pi 5)
- [ ] Voice session manager: start, listen, transcribe, route, respond, timeout
- [ ] Audio hardware abstraction layer (USB mic, 3.5mm or HDMI audio out)
- [ ] Voice activity detection to avoid streaming silence
- [ ] Audit log records voice sessions with `event_type="voice_session"` (no audio stored)

**Privacy invariant:** audio is processed in-memory and discarded; only transcripts are logged, and only at the user's configured log level.

---

## 🔮 Phase 5 — Raspberry Pi Deployment

**Goal:** Production-grade deployment on Pi 5 with sensible defaults.

**Planned:**

- [ ] Hardened `scripts/setup.sh` that automates the full bootstrap
- [ ] systemd service unit (`rasapi.service`) with auto-restart
- [ ] Bind to localhost by default; explicit `.env` flag to expose on LAN
- [ ] Firewall rules (`ufw`) sample config
- [ ] Log rotation via `logrotate` (audit JSONL files)
- [ ] Optional: nginx reverse proxy with HTTPS via mDNS / Tailscale
- [ ] Dockerfile (`linux/arm64`) for users who prefer containers
- [ ] Health monitoring: `/metrics` endpoint (Prometheus format)
- [ ] First-boot wizard for `.env` generation and model selection

**Out of scope for Phase 5:** any cloud component. If cloud fallback is ever added, it will be a deliberate Phase 6+ design decision behind explicit user consent.

---

## Permanent non-goals

These are decisions, not omissions. They will not change without an explicit project-charter update.

- ❌ No always-on cloud connectivity
- ❌ No sending queries to third-party LLM providers without per-request user consent
- ❌ No storing conversation history in any cloud
- ❌ No always-streaming audio to the network
- ❌ No telemetry beacons or usage analytics
- ❌ No unrestricted shell execution under any condition
