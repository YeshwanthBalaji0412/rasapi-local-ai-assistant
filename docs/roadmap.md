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

## 🟡 Phase 1.5 — Documentation & Polish (current)

**Goal:** Make the project recruiter-ready before adding more code.

- [x] README rewritten with phase-aware status
- [x] `docs/architecture.md` updated with current request flow + safety layers
- [x] `docs/security-model.md` updated with three-layer model + audit details
- [x] `docs/roadmap.md` reflects Phase 1 completion and revised future phases
- [x] `docs/demo-checklist.md` lists screenshots to capture for the showcase

No new features in this phase — only documentation and minor polish.

---

## 🔜 Phase 2 — Ollama Local LLM Integration

**Goal:** Move from deterministic keyword matching to real natural-language understanding, all on-device.

**Planned:**

- [ ] Connect `core/llm.py` to live Ollama HTTP API (`/api/generate`)
- [ ] Default model: `llama3.2:3b` (fits in 4 GB RAM, fast on Pi 5 CPU)
- [ ] Structured output: LLM returns `{intent, args, reasoning}` JSON, never raw shell
- [ ] Router uses LLM-proposed intent only if it maps to a known intent name
- [ ] Fallback to Phase 1 keyword router if Ollama is unavailable
- [ ] Per-request audit log includes `model`, `prompt_tokens`, `completion_tokens`
- [ ] Integration tests with mocked Ollama responses
- [ ] Health endpoint reports Ollama reachability

**Security invariant maintained:** the LLM proposes intents; the *router* and *allowlist* still own dispatch. The model can never execute a command directly.

**Models considered:** `llama3.2:3b` (default), `mistral:7b` (optional, 8 GB Pi only), `phi-3-mini` (experimental).

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
