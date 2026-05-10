# RasaPi — Readiness Checklist

Go / no-go list before considering RasaPi "ready for daily use" or
"ready to be shown to someone else". Designed for personal use — not
production-grade SaaS.

Pair this with [security-hardening-checklist.md](security-hardening-checklist.md)
for the security half of the conversation.

Run the automated half first:

```bash
bash deployment/raspberry-pi/check-readiness.sh
RASA_API_KEY=$YOUR_KEY bash deployment/raspberry-pi/check-readiness.sh
```

Both should exit `0`. If either fails, fix before continuing.

---

## Git hygiene

- [ ] `git status` shows a clean working tree on the Pi.
- [ ] You are on the branch you expect — usually `main` after a fresh clone.
- [ ] No `.env`, `*.db`, `audit-*.jsonl`, or audio files are tracked.
      Verify with: `git ls-files | grep -E '\.env$|\.db$|audit-.*\.jsonl|\.wav$'` →
      should print nothing.
- [ ] The local repo is up to date with `origin`:
      `git fetch && git status -uno`.

## Service

- [ ] `sudo systemctl status rasapi` shows `Active: active (running)`.
- [ ] `sudo systemctl is-enabled rasapi` shows `enabled`.
- [ ] A reboot test passed at least once.
- [ ] `bash deployment/raspberry-pi/health-check.sh` exits `0`.

## HTTP surface

- [ ] `GET /health` returns `200`.
- [ ] `GET /version` returns the expected version string.
- [ ] `GET /readiness` returns `{"ready": true, ...}`.
- [ ] `GET /dashboard` returns `200` or `303` (redirect to `/login`).
- [ ] Auth posture: with `ENABLE_AUTH=true`, all protected endpoints
      return `401` without a key and `200`/`201`/`303` with the key.

## Dashboard

- [ ] `/dashboard` loads from the Pi.
- [ ] `/dashboard` loads from a second device on the LAN (only if you've
      set up LAN binding deliberately — otherwise skip).
- [ ] Every section card renders without errors.
- [ ] No secrets visible in the rendered HTML — quick scan for your
      `API_SECRET_KEY`, Slack URL, HA token.
- [ ] Form buttons (refresh briefing, complete task) work end-to-end.
- [ ] CSRF works: form posts without `_csrf` return `403` (when auth on).

## /ask routing

- [ ] `"what time is it"` → returns the time (`intent=time`).
- [ ] `"hello"` → greeting (`intent=greeting`).
- [ ] `"free memory"` → memory_usage info.
- [ ] `"remember that X"` → `intent=save_memory`, item appears in `/memory`.
- [ ] `"add task Y"` → `intent=add_task`, item appears in `/tasks`.
- [ ] `"what's happening today"` → daily_briefing renders.
- [ ] `"help"` → lists capabilities.
- [ ] An unknown query falls back to `intent=fallback` (or `llm_fallback`
      if `ENABLE_LOCAL_LLM=true`).

## Voice

If `ENABLE_VOICE=true`:

- [ ] `python -m voice.cli status` shows engines and config.
- [ ] `python -m voice.cli tts-test "hello"` produces audible output.
- [ ] `python -m voice.cli once` completes a full record → STT → /ask → TTS cycle.
- [ ] No leftover `*.wav` files in `backend/data/audio_tmp/` after `once` exits.
- [ ] `/voice/session-once` requires auth when auth is enabled.

If voice is disabled, skip the section.

## Memory / notes / tasks

- [ ] Save a memory via `/ask` — `sensitive_memory_blocked` does NOT fire for
      benign content.
- [ ] Attempt to save a sensitive value (`"remember that my password is hunter2"`)
      — `sensitive_memory_blocked` DOES fire, the row is NOT inserted.
- [ ] List memory, notes, tasks via REST.
- [ ] Complete a task via the dashboard button (form + CSRF).

## Briefing

If `ENABLE_BRIEFING=true`:

- [ ] `POST /briefing/refresh` returns 200, item_count > 0.
- [ ] `GET /briefing/daily` renders multi-category text.
- [ ] An immigration item (USCIS source) carries the disclaimer.
- [ ] If a source 4xx/5xx: briefing run still completes with status `partial`.

## Integrations

- [ ] All integrations you don't use are `enabled=false` in `/integrations`.
- [ ] Slack (if enabled): `POST /integrations/slack/test` posts; webhook URL
      not visible in response or audit log.
- [ ] Home Assistant (if enabled): `GET /integrations/home-assistant/status`
      returns reachable; token not visible.
- [ ] Home Assistant `lock.*`, `alarm_control_panel.*`, `cover.*`, `camera.*`,
      `device_tracker.*`, `person.*` rejected with HTTP 400 even when added
      to `HOME_ASSISTANT_ALLOWED_ENTITIES`.

## Backup / restore

- [ ] `bash deployment/raspberry-pi/backup.sh` writes to `~/rasapi-backups/<ts>/`.
- [ ] The backup contains `rasapi.db` and `audit-*.jsonl`.
- [ ] The backup does NOT contain `.env`.
- [ ] You've **actually tested** restore at least once on a non-production
      copy: `restore.sh` then `systemctl status rasapi` then dashboard works.

## Secrets

- [ ] `git log -p -- .env 2>/dev/null | head` returns nothing — `.env` is
      not in git history.
- [ ] `git log --all -p | grep -E '(sk-[A-Za-z0-9]|hooks\.slack\.com|Bearer )' | head`
      returns nothing surprising.
- [ ] No copy of the API key, Slack URL, or HA token in any committed file.

## Tests

- [ ] `python -m pytest tests/` exits `0`. Currently expected: **330+ passing**.
- [ ] No skipped tests with `SKIP_REAL_NETWORK` or similar — RasaPi's test
      suite is fully offline.

---

## When all boxes are checked

You can:
- Use RasaPi daily on the Pi
- Open the dashboard from your MacBook on the LAN (or via Tailscale)
- Demo it to a recruiter or friend without fearing a secret leak
- Leave it running unattended for weeks (until [Phase 11](phase-11-roadmap.md)
  adds the scheduler / watchdog)

## When some boxes are NOT checked

Don't expose the dashboard beyond the Pi until you fix them.
The most common gotchas:
- `ENABLE_AUTH=true` but `API_SECRET_KEY` still the placeholder
- `.env` mode not `600`
- Backup never tested
- A test failure that snuck in during local edits
