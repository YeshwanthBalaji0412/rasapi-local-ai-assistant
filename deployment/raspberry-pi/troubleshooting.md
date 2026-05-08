# RasaPi — Raspberry Pi Troubleshooting

Common issues and how to diagnose them. Pair these notes with
`journalctl -u rasapi -f`.

## Service won't start

**Symptom:** `sudo systemctl status rasapi` shows `failed`.

```bash
sudo systemctl status rasapi
journalctl -u rasapi -n 50 --no-pager
```

Most common causes:

- `<PI_USER>` placeholder was not substituted in the unit file. Re-run the
  `sed | sudo tee` line in step 9 of `setup-pi.md`.
- `WorkingDirectory` does not match the actual repo location.
- `.env` is missing or unreadable by the service user. Confirm:
  ```bash
  ls -la ~/rasapi-local-ai-assistant/.env
  # should be -rw------- owned by your user
  ```

## Port 8000 already in use

```bash
sudo lsof -iTCP:8000 -sTCP:LISTEN
```

Kill the conflicting process or change the port. If you change it:

- Update `ExecStart` in `/etc/systemd/system/rasapi.service`
- `sudo systemctl daemon-reload && sudo systemctl restart rasapi`
- Re-run the smoke test with `BASE_URL=http://127.0.0.1:<new-port>`.

## "Permission denied" writing to data/ or logs/

The service runs as your user (not root). Confirm:

```bash
ls -ld ~/rasapi-local-ai-assistant/backend/data
ls -ld ~/rasapi-local-ai-assistant/logs
```

Both should be owned by your user with mode `700`. Fix with:

```bash
chmod 700 ~/rasapi-local-ai-assistant/backend/data ~/rasapi-local-ai-assistant/logs
chown -R "$USER:$USER" ~/rasapi-local-ai-assistant/backend/data ~/rasapi-local-ai-assistant/logs
```

## Dashboard reachable from the Pi but not from MacBook

The default unit binds to `127.0.0.1` (Pi-local only). To allow LAN
access, follow step 11 in `setup-pi.md`. Verify with:

```bash
ss -tlnp | grep 8000
# Should show 0.0.0.0:8000 (LAN) or 127.0.0.1:8000 (local-only).
```

Also confirm your home network firewall isn't blocking — many Pi
distributions ship without `ufw` enabled, but if you've turned it on:

```bash
sudo ufw status
```

## Briefing source failures

Hugging Face / Google AI / NPR / Hacker News mirror occasionally rate-limit
or move feed URLs. Symptom: `briefing_source_failed` in the dashboard's
Security Events section.

```bash
curl -I "<the failing URL>"   # check whether it's a transient 4xx/5xx
```

A single source failing is non-fatal — RasaPi runs the rest and marks the
run `partial`. If a source breaks permanently, update the URL in
`backend/briefing/sources.py` and `git pull` the change.

## Open-Meteo (weather) timing out

Open-Meteo is normally rock-solid. If it's down, the briefing falls back
to a partial run. The dashboard's weather card shows nothing. Try:

```bash
curl -s "https://api.open-meteo.com/v1/forecast?latitude=42.36&longitude=-71.06&current_weather=true"
```

If that succeeds from the Pi but RasaPi still reports failures, increase
`BRIEFING_FETCH_TIMEOUT_SECONDS` in `.env` and restart the service.

## Ollama enabled but every LLM call times out

CPU inference on a Pi 5 is slow. Options:

- Keep `ENABLE_LOCAL_LLM=false` and rely on Phase 1 + Phase 3 commands.
- Use a smaller model. `llama3.2:1b` is the sweet spot for Pi 5.
- Raise `LOCAL_LLM_TIMEOUT_SECONDS=60` in `.env`.
- Run Ollama on a faster machine and point `OLLAMA_BASE_URL` at it.

## Smoke test fails on `save_memory`

The smoke test inserts a single memory item ("my project is RasaPi"). If
this fails, the service can't write to SQLite. Check:

```bash
ls -la ~/rasapi-local-ai-assistant/backend/data/
journalctl -u rasapi -n 50 | grep -i sqlite
```

Permission errors are the most common cause — see "Permission denied"
above.

## "Module not found" after `git pull`

A new release added a Python dependency. Re-install:

```bash
cd ~/rasapi-local-ai-assistant/backend
source .venv/bin/activate
pip install -r requirements.txt
deactivate
sudo systemctl restart rasapi
```

## Dashboard shows no audit events

Either no actions have been triggered yet, or the audit log dir doesn't
exist. Run a request and check:

```bash
curl -X POST http://127.0.0.1:8000/ask -H 'Content-Type: application/json' -d '{"query":"hello"}'
ls ~/rasapi-local-ai-assistant/logs/
# audit-YYYY-MM-DD.jsonl should appear
```
