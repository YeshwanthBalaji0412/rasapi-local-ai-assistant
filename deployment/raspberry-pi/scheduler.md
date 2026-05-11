# Scheduler (Phase 11)

RasaPi does not run an in-process scheduler. Instead, four small scripts in
this directory are designed to be invoked by `cron` or by `systemd .timer`
units. They are safe to run on demand, idempotent, and exit non-zero on
failure so external schedulers can detect problems.

| Script | What it does |
|---|---|
| `run-daily-briefing.sh` | Calls `POST /briefing/refresh` on the local backend |
| `run-backup.sh` | Wraps `backup.sh` and rotates old snapshots in `~/rasapi-backups/` |
| `run-health-watchdog.sh` | Probes systemd + `/health` + `/readiness` + disk; optional Slack alert |
| `run-log-cleanup.sh` | Prunes old audit JSONL files and old temp audio files |

All four accept `--dry-run` where it makes sense (`run-backup.sh`,
`run-log-cleanup.sh`). None of them ever start, stop, or restart the
backend. None of them ever print API keys, webhook URLs, or env values.

## Option A: cron

Edit the `yesh` user's crontab:

```bash
crontab -e -u yesh
```

Add the four lines below. They use absolute paths so cron's empty PATH
doesn't break the scripts.

```cron
# Refresh the daily briefing each morning at 06:30 local
30 6 * * * /usr/bin/bash /home/yesh/rasapi-local-ai-assistant/deployment/raspberry-pi/run-daily-briefing.sh

# Daily snapshot at 03:15 local, then rotate snapshots older than BACKUP_RETENTION_DAYS
15 3 * * * /usr/bin/bash /home/yesh/rasapi-local-ai-assistant/deployment/raspberry-pi/run-backup.sh

# Watchdog every 15 minutes
*/15 * * * * /usr/bin/bash /home/yesh/rasapi-local-ai-assistant/deployment/raspberry-pi/run-health-watchdog.sh

# Log + audio cleanup at 04:00 local
0 4 * * * /usr/bin/bash /home/yesh/rasapi-local-ai-assistant/deployment/raspberry-pi/run-log-cleanup.sh
```

Cron output is delivered to the user's mailbox by default. If you don't
want mail, redirect to a file or `2>&1 | logger -t rasapi-cron`.

## Option B: systemd timers

Example unit files ship in this directory:

- `rasapi-watchdog.timer` + `rasapi-watchdog.service`
- `rasapi-briefing.timer` + `rasapi-briefing.service`

Install:

```bash
sudo cp deployment/raspberry-pi/rasapi-watchdog.timer  /etc/systemd/system/
sudo cp deployment/raspberry-pi/rasapi-watchdog.service /etc/systemd/system/
sudo cp deployment/raspberry-pi/rasapi-briefing.timer  /etc/systemd/system/
sudo cp deployment/raspberry-pi/rasapi-briefing.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rasapi-watchdog.timer
sudo systemctl enable --now rasapi-briefing.timer
```

Check status:

```bash
systemctl list-timers --all | grep rasapi
journalctl -u rasapi-watchdog.service --since "1 hour ago"
```

Backup and log-cleanup unit files are not shipped — copy the watchdog
pair, change `Description=`, the `ExecStart=` script path, and the
`OnCalendar=` cadence.

## Slack alerts from the watchdog

The watchdog sends a Slack alert only when at least one check fails AND
a webhook URL is available. Pick one of:

```bash
# Option 1 — environment variable (visible to anything that can read the env)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/... \
  bash deployment/raspberry-pi/run-health-watchdog.sh

# Option 2 — file (chmod 600, owned by the service user)
sudo install -d -o yesh -g yesh -m 700 /etc/rasapi
sudo install -m 600 -o yesh -g yesh /dev/stdin /etc/rasapi/slack-webhook <<< "https://hooks.slack.com/services/..."
```

The webhook URL is never printed by the script and never logged. Alert
body is a fixed template: hostname (short), UTC timestamp, and one
bullet per failing check. No request bodies, no audit content, no keys.

## Retention windows

These are read from environment variables, with safe defaults that
match `backend/config.py`:

| Variable | Default | Used by |
|---|---|---|
| `LOG_RETENTION_DAYS` | 30 | `run-log-cleanup.sh` |
| `AUDIO_TMP_RETENTION_HOURS` | 24 | `run-log-cleanup.sh` |
| `BACKUP_RETENTION_DAYS` | 14 | `run-backup.sh` |
| `WATCHDOG_DISK_THRESHOLD_PCT` | 90 | `run-health-watchdog.sh` |

The backend also surfaces the configured values (booleans + integers only,
never paths or secrets) in `GET /config/status` under the `scheduler` key.

## Safety properties

- No script writes outside `~/rasapi-backups/`, `logs/`, or
  `backend/data/audio_tmp/`.
- No script ever calls `systemctl restart` or `systemctl stop`.
- No script reads or echoes `.env`, `api_secret_key`, or webhook URLs.
- All four scripts use `set -euo pipefail`. A missing variable or a
  failing command aborts immediately.
- `run-log-cleanup.sh` uses hardcoded relative paths (`logs/`,
  `backend/data/audio_tmp/`) — an attacker who can set env vars cannot
  redirect deletion to `/etc` or `/home`.
- `run-backup.sh` refuses to operate when `BACKUP_ROOT` is empty or `/`.
