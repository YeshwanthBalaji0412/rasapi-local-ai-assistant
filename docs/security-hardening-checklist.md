# RasaPi — Security Hardening Checklist

Run through this list **before** binding RasaPi to anything other than
`127.0.0.1`. It is short on purpose — every item is a real concern.

If any box is unchecked, you are deploying with a known weakness.

---

## Network exposure

- [ ] `ENABLE_AUTH=true` is set **before** systemd binds to `--host 0.0.0.0`.
- [ ] You have a **fresh** `API_SECRET_KEY` generated with
      `bash deployment/raspberry-pi/generate-secret.sh`. The placeholder
      values (`change-me-before-use`, empty string) are NOT in `.env`.
- [ ] You have **not** added a port-forward rule on your home router for
      port 8000. Public exposure is not supported.
- [ ] If you need access from outside the LAN, you've installed
      [Tailscale](https://tailscale.com) on both the Pi and the client.
      See [`deployment/raspberry-pi/remote-access.md`](../deployment/raspberry-pi/remote-access.md).

## Filesystem

- [ ] `.env` permissions are `600`: `stat -c '%a' .env` (Linux) or
      `stat -f '%Lp' .env` (macOS).
- [ ] `backend/data/` permissions are `700`.
- [ ] `logs/` permissions are `700`.
- [ ] No `.env` or `*.db` or audit logs are tracked by git: `git status`
      shows none of those.

## systemd

- [ ] `rasapi.service` runs as `<PI_USER>`, not `root`. Verify with
      `systemctl show rasapi -p User`.
- [ ] `Restart=on-failure` and `RestartSec=5` are in the unit.
- [ ] `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectSystem=full`,
      `ProtectHome=read-only` are in the unit.

## Auth posture

- [ ] All four `AUTH_PROTECT_*` flags are `true` (or you've consciously
      turned some off).
- [ ] `AUTH_PROTECT_INTEGRATIONS=true`.
- [ ] Dashboard `/login` works with the configured secret.
- [ ] `/ask` returns 401 without a key.
- [ ] `/voice/session-once` returns 401 without a key (if voice is on).
- [ ] `/integrations/slack/test` returns 401 without a key (if Slack is on).

## Integrations

- [ ] All integrations you don't use are `ENABLE_*=false`.
- [ ] **Slack:** if enabled, the webhook URL is in `.env` only — never on
      the dashboard, never in a commit, never in a screenshot.
- [ ] **Home Assistant:** if enabled, the token is in `.env` only.
- [ ] **Home Assistant:** `HOME_ASSISTANT_ALLOWED_ENTITIES` lists only
      entities you've explicitly approved.
- [ ] **Home Assistant:** the hard-block list (`lock`,
      `alarm_control_panel`, `cover`, `camera`, `device_tracker`,
      `person`) is intact — you have not added any of these to
      `HOME_ASSISTANT_ALLOWED_DOMAINS`.

## Voice

- [ ] `VOICE_SAVE_AUDIO=false` unless you have a deliberate reason to
      keep wav files.
- [ ] No leftover wav files in `backend/data/audio_tmp/` — they should
      be deleted after every session by default.

## LLM

- [ ] `ENABLE_LOCAL_LLM=false` unless you have Ollama running locally
      AND you've confirmed it doesn't ship logs anywhere.
- [ ] No cloud LLM credentials in `.env` (RasaPi has no cloud LLM
      integration in any phase through 10).

## Operational

- [ ] `bash deployment/raspberry-pi/check-readiness.sh` exits 0.
- [ ] `bash deployment/raspberry-pi/health-check.sh` exits 0.
- [ ] You know how to rotate `API_SECRET_KEY` (see
      [maintenance.md](maintenance.md)). Restarting after rotation
      invalidates every existing session cookie immediately.
- [ ] You know where backups go (`~/rasapi-backups/`) and what they
      contain (DB + audit logs, **not** `.env`).
- [ ] You have a plan for what to do if `API_SECRET_KEY` leaks:
      rotate → restart → audit log review.

---

## If anything is checked "no"

Don't expose the dashboard beyond `127.0.0.1` until you fix it.

Phase 10 specifically does **not** add HTTPS termination, rate limiting,
multi-user accounts, OAuth, public exposure, Docker, or Prometheus.
Those are tracked in [`phase-11-roadmap.md`](phase-11-roadmap.md).
