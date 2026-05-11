# RasaPi — Maintenance Guide

Routine maintenance tasks. None of these scripts modify your `.env`,
database, or audit logs without explicit operator consent.

---

## Update from GitHub

```bash
cd ~/rasapi-local-ai-assistant
bash deployment/raspberry-pi/update-rasapi.sh
```

What it does:
- Refuses to run if there are uncommitted local changes
- `git pull --ff-only`
- Reinstalls Python requirements into `backend/.venv`
- Restarts `rasapi.service`
- Probes `/health`

If you have local commits you want to keep, push them first or rebase
manually before running the script.

---

## Restart the service

```bash
sudo systemctl restart rasapi          # graceful restart
sudo systemctl status  rasapi
sudo journalctl -u rasapi -f           # live logs
```

---

## View logs

| Source | Command |
|---|---|
| systemd journal | `sudo journalctl -u rasapi -f` |
| Audit log (today) | `tail -n 100 ~/rasapi-local-ai-assistant/logs/audit-$(date -u +%Y-%m-%d).jsonl` |
| Event-type histogram | `bash deployment/raspberry-pi/doctor.sh` |
| All audit files | `ls -la ~/rasapi-local-ai-assistant/logs/` |

The audit log never contains secrets or audio bytes — see
[security-model.md](security-model.md) for the full schema.

---

## Clear old audit logs

Audit logs rotate daily (`audit-YYYY-MM-DD.jsonl`). RasaPi does not
auto-prune them. Two ways to clean up:

```bash
# Manual one-shot:
find ~/rasapi-local-ai-assistant/logs/ -name 'audit-*.jsonl' -mtime +30 -print
find ~/rasapi-local-ai-assistant/logs/ -name 'audit-*.jsonl' -mtime +30 -delete

# Phase 11 — scripted, dry-run first:
bash deployment/raspberry-pi/run-log-cleanup.sh --dry-run
bash deployment/raspberry-pi/run-log-cleanup.sh
```

The scripted form also prunes old temp audio files. Tune retention with
`LOG_RETENTION_DAYS=30` and `AUDIO_TMP_RETENTION_HOURS=24`. Schedule it
via cron or a systemd timer — see
[`deployment/raspberry-pi/scheduler.md`](../deployment/raspberry-pi/scheduler.md).

Consider backing up first if you care about long-term forensics.

---

## Backup database + audit logs

```bash
bash deployment/raspberry-pi/backup.sh
# → ~/rasapi-backups/<utc-timestamp>/{rasapi.db, audit-*.jsonl}

# Phase 11 — same backup, plus rotation of snapshots older than 14 days:
bash deployment/raspberry-pi/run-backup.sh
```

`.env` is **intentionally not included** — treat it as operator-managed
config. The script never copies it. Tune retention with
`BACKUP_RETENTION_DAYS=14`. Schedule via cron or a systemd timer —
see [`deployment/raspberry-pi/scheduler.md`](../deployment/raspberry-pi/scheduler.md).

For a fully consistent SQLite snapshot, stop the service first:

```bash
sudo systemctl stop rasapi
bash deployment/raspberry-pi/backup.sh
sudo systemctl start rasapi
```

---

## Restore from backup

```bash
sudo systemctl stop rasapi
bash deployment/raspberry-pi/restore.sh ~/rasapi-backups/<utc-timestamp>
sudo systemctl start rasapi
sudo systemctl status rasapi
```

Restore only touches `backend/data/rasapi.db` and `logs/audit-*.jsonl`.
Your `.env` and venv are left alone.

---

## Rotate the API secret

If you suspect `API_SECRET_KEY` has been exposed:

```bash
# 1. Generate a new one (does not write anywhere):
bash deployment/raspberry-pi/generate-secret.sh

# 2. Paste it into .env:
sudo nano ~/rasapi-local-ai-assistant/.env
chmod 600 ~/rasapi-local-ai-assistant/.env

# 3. Restart — this invalidates every existing session cookie because
#    stateless cookies are signed with the old secret.
sudo systemctl restart rasapi
```

You'll need to log in to the dashboard again with the new secret. API
clients (`X-RasaPi-Key` / `Authorization: Bearer`) need to be updated
to the new value.

---

## Check disk usage

```bash
df -h ~/rasapi-local-ai-assistant
du -sh ~/rasapi-local-ai-assistant/backend/data ~/rasapi-local-ai-assistant/logs 2>/dev/null
```

The SQLite file grows slowly (memory, tasks, notes, briefing items).
The audit log grows roughly proportionally to request volume. Phase 10
does not auto-prune either.

---

## Check service health

The fastest one-liner:

```bash
bash deployment/raspberry-pi/health-check.sh
```

The full audit:

```bash
bash deployment/raspberry-pi/check-readiness.sh
```

When something is off and you don't know what:

```bash
bash deployment/raspberry-pi/doctor.sh
```

Scheduled watchdog (Phase 11) — checks systemd, `/health`, `/readiness`,
and disk usage in one shot; emits an optional Slack alert on failure:

```bash
bash deployment/raspberry-pi/run-health-watchdog.sh
```

Tune `WATCHDOG_DISK_THRESHOLD_PCT=90`. Wire it up via cron or systemd
timer per [`deployment/raspberry-pi/scheduler.md`](../deployment/raspberry-pi/scheduler.md).

None of these scripts print secrets or modify state.

---

## Re-install the Python venv

If the venv breaks (e.g. you upgraded Python system-wide):

```bash
cd ~/rasapi-local-ai-assistant
rm -rf backend/.venv
bash deployment/raspberry-pi/install.sh
```

`install.sh` is idempotent and will not overwrite your `.env`.

---

## What NOT to delete

| File / dir | Why |
|---|---|
| `.env` | Configuration + secrets. Backup separately if needed. |
| `backend/data/rasapi.db` | Your memory, notes, tasks, and briefing history. |
| `logs/audit-*.jsonl` | The audit trail. Useful for forensics. |
| `backend/.venv` | Run `install.sh` to recreate if you do delete this. |
| `~/whisper.cpp/models/*.bin` | Whisper model files. Not committed to git. Re-download from the whisper.cpp upstream if lost. Point `VOICE_WHISPER_MODEL_PATH` at the new location. |
| `~/piper-voices/*.onnx*` | Piper voice files. Not committed to git. Re-download from Hugging Face if lost. Point `VOICE_PIPER_MODEL_PATH` at the new location. |

Everything else can be regenerated from git. Model files (Whisper `.bin`,
Piper `.onnx`/`.onnx.json`) are deliberately **not** in the repo — they're
large and operator-managed.

---

## How to recover if `.env` is wrong

Symptoms: `rasapi.service` keeps restarting, `journalctl -u rasapi` shows
config errors, dashboard returns 5xx, or `auth_misconfigured` shows up in
the audit log.

```bash
# 1. Stop the service so it stops crash-looping:
sudo systemctl stop rasapi

# 2. Compare your .env to the shipped example:
diff ~/rasapi-local-ai-assistant/.env \
     ~/rasapi-local-ai-assistant/deployment/raspberry-pi/env.example.pi

# 3. Common fixes:
#    - DATABASE_PATH should NOT be backend/backend/data/... (avoid nesting)
#    - VOICE_AUDIO_TEMP_DIR should NOT be backend/backend/data/...
#    - API_SECRET_KEY should not be the placeholder when ENABLE_AUTH=true

# 4. Re-validate:
chmod 600 ~/rasapi-local-ai-assistant/.env
sudo systemctl start rasapi
bash deployment/raspberry-pi/check-readiness.sh
```

If you've lost the file entirely, copy the example and fill it in:

```bash
cp ~/rasapi-local-ai-assistant/deployment/raspberry-pi/env.example.pi \
   ~/rasapi-local-ai-assistant/.env
chmod 600 ~/rasapi-local-ai-assistant/.env
sudo nano ~/rasapi-local-ai-assistant/.env
```
