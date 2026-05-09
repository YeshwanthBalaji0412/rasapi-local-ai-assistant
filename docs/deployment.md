# RasaPi — Deployment

RasaPi is built to be deployed once and forgotten. Phase 6 ships a
turn-key Raspberry Pi setup so the same backend that runs on your
MacBook in development runs unchanged on the Pi as a systemd-managed
local-network service.

## Supported targets

| Target | Status | Guide |
|---|---|---|
| Raspberry Pi 5 (64-bit Pi OS) | ✅ supported | [`deployment/raspberry-pi/setup-pi.md`](../deployment/raspberry-pi/setup-pi.md) |
| Generic Linux host (manual) | ✅ same files apply | follow the Pi guide; substitute paths |
| MacBook / dev machine | ✅ no deployment needed | run `uvicorn` directly per the README |
| Docker / containers | ⏳ future | not in Phase 6 |
| Kubernetes / cloud | ❌ out of scope | RasaPi is local-first by charter |

## Architecture

```
   ┌──────────────────┐  git push   ┌────────────────────────┐
   │  MacBook (dev)   │ ──────────► │  GitHub                │
   └──────────────────┘             │  rasapi-local-ai-…     │
                                    └──────────┬─────────────┘
                                               │ git clone
                                               ▼
   ┌─────────────────────────────────────────────────────────┐
   │                Raspberry Pi 5                           │
   │                                                         │
   │   bash deployment/raspberry-pi/install.sh               │
   │     → backend/.venv                                     │
   │     → pip install -r backend/requirements.txt           │
   │     → backend/data/  (mode 700)                         │
   │     → logs/          (mode 700)                         │
   │     → .env (chmod 600 by user, never overwritten)       │
   │                                                         │
   │   systemd ──► uvicorn main:app  (User=<PI_USER>)        │
   │                  ├── default: 127.0.0.1:8000 (Pi-only) │
   │                  └── alt:     0.0.0.0:8000  (LAN)      │
   └────────────────────────┬────────────────────────────────┘
                            │ http (LAN, no public port-forward)
                            ▼
                       MacBook browser
                       http://<pi-ip>:8000/dashboard
```

## Trust model

Phase 6 ships RasaPi with no authentication; Phase 8 adds an opt-in API-key + dashboard-login layer. The trust model is:

- **127.0.0.1 binding (default):** only processes on the Pi itself can
  reach the dashboard. Effectively a single-user local tool.
- **0.0.0.0 binding (opt-in):** anyone on the same home network can reach
  the dashboard. Safe only on a network you control. Never expose to the
  public internet.

Future authentication, HTTPS, and remote access (e.g. Tailscale) are
deferred — see [`docs/roadmap.md`](roadmap.md).

> **Phase 8 update.** Authentication is now available as an opt-in feature.
> Generate a secret with `bash deployment/raspberry-pi/generate-secret.sh`,
> set `ENABLE_AUTH=true` in `.env`, and follow
> [`deployment/raspberry-pi/remote-access.md`](../deployment/raspberry-pi/remote-access.md)
> for safe LAN/Tailscale exposure. Public-internet port forwarding remains a
> hard "no" regardless of auth state.

## Files shipped in `deployment/raspberry-pi/`

| File | Purpose |
|---|---|
| `setup-pi.md` | The 19-step copy-pasteable Pi setup guide |
| `install.sh` | Idempotent bootstrap (venv, pip, dirs, .env seed). Aborts safely if system packages are missing. |
| `rasapi.service` | systemd unit. Non-root, restart on failure, default localhost binding, commented LAN-binding alternative |
| `env.example.pi` | Pi-tuned defaults (LLM off, briefing on, mask DB path, log level INFO) |
| `smoke-test.sh` | 9 endpoint checks, `BASE_URL` configurable |
| `backup.sh` | Timestamped copy of `rasapi.db` + audit logs. Excludes `.env`. |
| `restore.sh` | Restore from a backup directory. Never touches `.env`. |
| `troubleshooting.md` | Common issues: service won't start, port in use, permission errors, briefing source failures, slow Ollama |
| `audio-setup.md` | Phase 7 — Pi audio devices, espeak/Piper, whisper.cpp, voice CLI smoke |
| `generate-secret.sh` | Phase 8 — print a 256-bit URL-safe `API_SECRET_KEY` |
| `remote-access.md` | Phase 8 — Tailscale instead of port-forwarding, optional UFW, hard rules |
| `integrations.md` | Phase 9 — Slack webhook setup, HA token + allowlist, Alexa future note, hard rules |

## What `install.sh` will not do

- Will not run `sudo apt install` on your behalf — prints the exact
  command and aborts if anything is missing.
- Will not modify the firewall.
- Will not install Ollama. Ollama is optional, documented separately.
- Will not install Tailscale. Tailscale is optional, documented separately.
- Will not overwrite your `.env`.
- Will not modify any file under `/etc/`.

## Update flow

```bash
cd ~/rasapi-local-ai-assistant
git pull --ff-only

cd backend
source .venv/bin/activate
pip install -r requirements.txt
deactivate

sudo systemctl restart rasapi
```

The DB schema is `CREATE TABLE IF NOT EXISTS` everywhere — Phase 6 has no
migration step. If a future phase introduces a migration, this doc will
gain a numbered procedure.

## Backup and restore

```bash
# Backup (safe to run while service is up; for fully consistent snapshot,
# stop the service first):
bash deployment/raspberry-pi/backup.sh
# → ~/rasapi-backups/<utc-timestamp>/{rasapi.db, audit-*.jsonl}

# Restore:
sudo systemctl stop rasapi
bash deployment/raspberry-pi/restore.sh ~/rasapi-backups/<utc-timestamp>
sudo systemctl start rasapi
```

`.env` is intentionally never included in the backup. Treat it as
operator-managed configuration.

## Future deployment phases

- **Phase 7 ✅ — Voice I/O.** Audio in/out via local Whisper + Piper, all on-device.
- **Phase 8 ✅ — Auth + remote access.** API-key + dashboard-login + CSRF + Tailscale guidance. See [`deployment/raspberry-pi/remote-access.md`](../deployment/raspberry-pi/remote-access.md).
- **Phase 9 🟡 — Integrations hub (in progress).** Slack webhook + Home Assistant REST allowlist, Alexa future stub. See [`deployment/raspberry-pi/integrations.md`](../deployment/raspberry-pi/integrations.md).
- **Phase 10 (or later) — HTTPS & rate limiting.** Reverse proxy with TLS, brute-force protection, optional Dockerfile, `/metrics`.

See [`docs/roadmap.md`](roadmap.md).
