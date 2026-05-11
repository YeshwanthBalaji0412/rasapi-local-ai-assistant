# RasaPi — Configuration Reference

Every `.env` setting organized by phase. Mark which ones are secrets and
which are safe to share.

> Always `chmod 600 .env`. Never commit `.env`. Never paste secrets into
> screenshots, audit logs, or chat.

---

## Server (Phase 1)

| Variable | Default | Required | Secret | Notes |
|---|---|---|---|---|
| `HOST` | `0.0.0.0` | yes | no | Use `127.0.0.1` for Pi-local only. Phase 6 default unit binds to `127.0.0.1`. |
| `PORT` | `8000` | yes | no | Change here AND in the systemd unit if you move it. |
| `DEBUG` | `false` | no | no | Enables `/docs` (FastAPI Swagger). Leave off in production. |
| `LOG_LEVEL` | `INFO` | no | no | One of `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `ASSISTANT_NAME` | `RasaPi` | no | no | Cosmetic — appears in `/health` and the dashboard header. |

---

## Local LLM (Phase 2)

| Variable | Default | Required | Secret | Notes |
|---|---|---|---|---|
| `ENABLE_LOCAL_LLM` | `false` | no | no | Set `true` to enable Ollama fallback for unknown queries. |
| `LOCAL_LLM_PROVIDER` | `ollama` | no | no | Currently only `ollama` is implemented. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | no | no | URL of the local Ollama daemon. |
| `LOCAL_LLM_MODEL` | `llama3.2:1b` | no | no | Must be pulled with `ollama pull <model>` first. |
| `LOCAL_LLM_TIMEOUT_SECONDS` | `20` | no | no | Hard cap on a single inference call. |

---

## Local Storage (Phase 3)

| Variable | Default | Required | Secret | Notes |
|---|---|---|---|---|
| `DATABASE_PATH` | `backend/data/rasapi.db` | yes | no | SQLite file path. Relative paths resolve from the project root. |
| `AUDIT_LOG_DIR` | `logs` | yes | no | Directory of `audit-YYYY-MM-DD.jsonl` files. |

---

## Daily Briefing (Phase 4)

| Variable | Default | Required | Secret | Notes |
|---|---|---|---|---|
| `ENABLE_BRIEFING` | `true` | no | no | The briefing fetcher and intents only run if this is `true`. |
| `ENABLE_LLM_BRIEFING_SUMMARY` | `false` | no | no | Both this **and** `ENABLE_LOCAL_LLM` must be true for any LLM call on the briefing path. |
| `BRIEFING_MAX_ITEMS_PER_CATEGORY` | `5` | no | no | Top N per category in the formatted briefing. |
| `BRIEFING_DEFAULT_LOCATION` | `Boston, MA` | no | no | Display label only. |
| `BRIEFING_WEATHER_LAT` | `42.3601` | no | no | Open-Meteo latitude. |
| `BRIEFING_WEATHER_LON` | `-71.0589` | no | no | Open-Meteo longitude. |
| `BRIEFING_FETCH_TIMEOUT_SECONDS` | `10` | no | no | Per-source timeout. |
| `BRIEFING_CACHE_MINUTES` | `60` | no | no | `/ask "daily briefing"` auto-refreshes only after this window. |

---

## Dashboard (Phase 5)

| Variable | Default | Required | Secret | Notes |
|---|---|---|---|---|
| `DASHBOARD_MASK_DB_PATH` | `true` | no | no | When `true`, only the last two segments of `DATABASE_PATH` and `AUDIT_LOG_DIR` appear in the UI. |

---

## Voice (Phase 7)

| Variable | Default | Required | Secret | Notes |
|---|---|---|---|---|
| `ENABLE_VOICE` | `false` | no | no | Voice CLI and `/voice/session-once` are off until enabled. |
| `VOICE_RECORDER_ENGINE` | `mock` | no | no | `mock` \| `arecord`. |
| `VOICE_STT_ENGINE` | `mock` | no | no | `mock` \| `whisper`. |
| `VOICE_TTS_ENGINE` | `mock` | no | no | `mock` \| `espeak` \| `piper`. |
| `VOICE_RECORD_SECONDS` | `5` | no | no | Length of each push-to-talk capture. |
| `VOICE_AUDIO_TEMP_DIR` | `backend/data/audio_tmp` | no | no | Temp wav files live here briefly. |
| `VOICE_SAVE_AUDIO` | `false` | no | no | `true` keeps the wav after STT (debug only). |
| `VOICE_LOG_TRANSCRIPTS` | `true` | no | no | When `true`, voice transcripts go through the existing `request` audit event. |
| `VOICE_MAX_TRANSCRIPT_CHARS` | `1000` | no | no | Truncates before `process_query`. |
| `VOICE_REQUIRE_PUSH_TO_TALK` | `true` | no | no | Phase 7 has no wake word — leave this on. |
| `VOICE_DEVICE_INPUT` | _empty_ | no | no | ALSA device hint. Use `pulse` on Pi with PipeWire / Bluetooth. |
| `VOICE_DEVICE_OUTPUT` | _empty_ | no | no | ALSA / Pulse device hint. Leave blank to use the system default. |
| `VOICE_WHISPER_MODEL_PATH` | _empty_ | when `VOICE_STT_ENGINE=whisper` | no | Absolute path to a whisper.cpp `.bin` model. Adapter passes it via `-m`. No symlink needed. |
| `VOICE_PIPER_MODEL_PATH` | _empty_ | when `VOICE_TTS_ENGINE=piper` | no | Absolute path to a Piper `.onnx` voice. Adapter passes it via `--model`. |
| `VOICE_PIPER_CONFIG_PATH` | _empty_ | no | no | Optional path to a Piper `.onnx.json` config. Only needed if it doesn't sit beside the `.onnx`. |
| `VOICE_TTS_PLAYBACK_COMMAND` | `auto` | no | no | `auto` \| `paplay` \| `aplay`. `auto` prefers `paplay` (PipeWire/Bluetooth-safe). |

---

## Authentication (Phase 8)

| Variable | Default | Required | Secret | Notes |
|---|---|---|---|---|
| `ENABLE_AUTH` | `false` | no | no | **Strongly recommended** before binding `--host 0.0.0.0`. |
| `API_SECRET_KEY` | `change-me-before-use` | **when auth is on** | **YES** | Generate with `bash deployment/raspberry-pi/generate-secret.sh`. |
| `AUTH_PROTECT_DASHBOARD` | `true` | no | no | Dashboard requires session cookie. |
| `AUTH_PROTECT_ASK` | `true` | no | no | `/ask` requires API key or session. |
| `AUTH_PROTECT_VOICE` | `true` | no | no | `/voice/test-tts` and `/voice/session-once`. |
| `AUTH_PROTECT_MUTATIONS` | `true` | no | no | `/memory`, `/notes`, `/tasks` (all methods). |
| `AUTH_PROTECT_INTEGRATIONS` | `true` | no | no | `/integrations/*`. |
| `SESSION_COOKIE_NAME` | `rasapi_session` | no | no | Cookie name. |
| `SESSION_TTL_MINUTES` | `720` | no | no | 12 hours. |
| `COOKIE_SECURE` | `false` | no | no | Set `true` only behind HTTPS. |
| `CSRF_COOKIE_NAME` | `rasapi_csrf` | no | no | Cookie name for double-submit token. |

---

## Slack integration (Phase 9)

| Variable | Default | Required | Secret | Notes |
|---|---|---|---|---|
| `ENABLE_SLACK` | `false` | no | no | When false, all Slack endpoints return 409 "not configured". |
| `SLACK_WEBHOOK_URL` | _empty_ | when enabled | **YES** | Incoming webhook only. Never displayed. |
| `SLACK_DEFAULT_CHANNEL` | _empty_ | no | no | Display only. Webhooks ignore the channel attribute. |
| `SLACK_SEND_BRIEFING_ENABLED` | `false` | no | no | Allows the briefing-posting paths. |
| `SLACK_SEND_AUDIT_ALERTS_ENABLED` | `false` | no | no | Reserved for a future alerts feature. |

---

## Home Assistant integration (Phase 9)

| Variable | Default | Required | Secret | Notes |
|---|---|---|---|---|
| `ENABLE_HOME_ASSISTANT` | `false` | no | no | When false, all HA endpoints return 409. |
| `HOME_ASSISTANT_URL` | _empty_ | when enabled | **partial** | URL pointing at your HA instance. Not a secret but not displayed in UI. |
| `HOME_ASSISTANT_TOKEN` | _empty_ | when enabled | **YES** | Long-lived access token. Never displayed. |
| `HOME_ASSISTANT_ALLOWED_ENTITIES` | _empty_ | when enabled | no | Comma-separated entity_ids RasaPi may touch. |
| `HOME_ASSISTANT_ALLOWED_DOMAINS` | `light,switch,sensor` | no | no | Operator can extend; hard-block list overrides. |
| `HOME_ASSISTANT_REQUIRE_CONFIRMATION` | `true` | no | no | Reserved for a future confirmation flow. |

---

## Secrets summary

These are the values that **must never** leak. They are stored in
`.env` only and never appear in the dashboard, audit log, or API
responses:

- `API_SECRET_KEY`
- `SLACK_WEBHOOK_URL`
- `HOME_ASSISTANT_TOKEN`
- Any future cloud API key

After editing any of these, run:

```bash
chmod 600 .env
sudo systemctl restart rasapi
bash deployment/raspberry-pi/check-readiness.sh
```
