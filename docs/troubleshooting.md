# RasaPi — Troubleshooting

Cross-phase troubleshooting. For deployment-specific issues see
[`deployment/raspberry-pi/troubleshooting.md`](../deployment/raspberry-pi/troubleshooting.md).
For audio-specific issues see [`deployment/raspberry-pi/audio-setup.md`](../deployment/raspberry-pi/audio-setup.md).

Quick triage:

```bash
bash deployment/raspberry-pi/doctor.sh
bash deployment/raspberry-pi/check-readiness.sh
```

---

## Dashboard

### Dashboard not loading

```bash
sudo systemctl status rasapi
curl -i http://127.0.0.1:8000/health
```

- If `systemctl status` shows `failed`, check `journalctl -u rasapi -n 50`.
- If `/health` doesn't respond, port 8000 may be in use or the unit isn't bound where you think — see `doctor.sh` output.

### Dashboard returns 302 to /login but I didn't enable auth

You probably enabled `ENABLE_AUTH=true` somewhere. Check `.env` and
restart. Or sign in with the configured `API_SECRET_KEY`.

### 401 Unauthorized on `/ask`, `/memory`, `/voice/...`

Auth is on. Either:

- Send `X-RasaPi-Key: <your-key>` header
- Or sign in to the dashboard first (cookie session)

If neither works, the secret in `.env` may not match the key you're
sending. Regenerate:

```bash
bash deployment/raspberry-pi/generate-secret.sh
# paste into backend/.env, then:
sudo systemctl restart rasapi
```

### 401 that survives multiple key rotations

If you're rotating the key, restarting, and still getting 401 against your
freshly-generated key — you're almost certainly editing the **wrong** `.env`
file.

**The service reads `backend/.env`, not the repo-root `.env`.**

Older installs sometimes ended up with a repo-root `.env` (from an earlier
`install.sh`) sitting alongside a distinct `backend/.env` (created manually or
by hand-copying an example). Only `backend/.env` matters at runtime.

Check both:

```bash
ls -la ~/rasapi-local-ai-assistant/.env ~/rasapi-local-ai-assistant/backend/.env
```

If a repo-root `.env` exists, delete it or move it into `backend/`:

```bash
# Only run this after confirming backend/.env either doesn't exist or
# doesn't have anything you want to keep.
mv ~/rasapi-local-ai-assistant/.env ~/rasapi-local-ai-assistant/backend/.env
sudo systemctl restart rasapi
```

`doctor.sh` will surface the same warning if you re-run it after upgrading to
the fix (v0.11.1 or later).

### Login doesn't set a cookie

- Are you POSTing as `application/x-www-form-urlencoded`? curl's `-d` does this by default.
- Is `COOKIE_SECURE=true` while you're on HTTP? Browser will reject the cookie. Set `COOKIE_SECURE=false` for HTTP / LAN access.
- Is `.env` actually loaded? `bash deployment/raspberry-pi/doctor.sh` shows the .env key count.

### "CSRF validation failed" in the audit log

The dashboard form did not include the `_csrf` token, or the token didn't
match the cookie. Hard refresh the dashboard page (Cmd-Shift-R / Ctrl-F5)
to get a fresh CSRF cookie.

---

## Voice

### "Voice disabled" message

`ENABLE_VOICE=false`. Set it to `true` in `.env`, restart.

### No sound from the speaker

```bash
aplay -l
aplay -D plughw:0,0 /tmp/test.wav
```

If `aplay` works but RasaPi doesn't, check `VOICE_DEVICE_OUTPUT` in `.env`.

### Microphone not detected

```bash
arecord -l
arecord -D plughw:1,0 -d 5 -f S16_LE -c 1 -r 16000 /tmp/test.wav
aplay /tmp/test.wav
```

Update `VOICE_DEVICE_INPUT` in `.env` to match what `arecord -l` shows.

### Whisper returns a blank transcript

Common causes:
- Mic capture level is too low (`alsamixer` → F4 capture view → raise levels)
- Recording is silence (try again, speak clearly)
- Wrong sample rate — RasaPi records at 16000 Hz mono; some USB mics need explicit configuration

### Whisper says "Whisper model not found"

`VOICE_STT_ENGINE=whisper` but `VOICE_WHISPER_MODEL_PATH` is empty or
points at a file that doesn't exist. As of Phase 10, the adapter
requires the path to be explicit — **no symlink under
`backend/models/` is needed any more**.

```bash
# Verify the path resolves:
grep ^VOICE_WHISPER_MODEL_PATH ~/rasapi-local-ai-assistant/.env

# Fix:
sudo nano ~/rasapi-local-ai-assistant/.env
chmod 600 ~/rasapi-local-ai-assistant/.env
sudo systemctl restart rasapi
```

Example value: `/home/<PI_USER>/whisper.cpp/models/ggml-tiny.en.bin`.

### Piper says "Piper model not found"

Same shape as Whisper, but for the TTS side. As of Phase 10, **no
wrapper script is needed** — RasaPi's adapter passes `--model` itself.

```bash
grep ^VOICE_PIPER_MODEL_PATH ~/rasapi-local-ai-assistant/.env
```

Set `VOICE_PIPER_MODEL_PATH=/home/<PI_USER>/piper-voices/en_US-amy-low.onnx`
(or wherever you put the voice file). The `.onnx.json` config must sit
beside the `.onnx`. If it can't, set `VOICE_PIPER_CONFIG_PATH` explicitly.

### TTS plays through HDMI / wrong output instead of Bluetooth headset

On Pi distros with PipeWire or PulseAudio (most modern setups), `aplay`
goes to the wrong card. Switch to `paplay`:

```env
VOICE_TTS_PLAYBACK_COMMAND=paplay   # or 'auto' which prefers paplay
```

Make sure paplay is installed:

```bash
which paplay || sudo apt install pulseaudio-utils
sudo systemctl restart rasapi
```

If you'd rather force raw ALSA (e.g. you've intentionally disabled
PipeWire), use `VOICE_TTS_PLAYBACK_COMMAND=aplay` and set
`VOICE_DEVICE_OUTPUT` to the right `plughw:X,Y`.

### Bluetooth headset mic doesn't capture

Bluetooth headsets default to A2DP (high-quality playback, **no mic**).
You need to switch to HSP/HFP mode (lower quality, mic enabled).

```bash
pactl list cards short
# find your bluetooth card, then:
pactl set-card-profile <card-name> headset_head_unit
```

Some Pi distributions need `pulseaudio-module-bluetooth` installed.

### TTS hangs or times out when speaking the daily briefing

Fixed in Phase 11. The voice path now passes briefing responses through
`voice/briefing_shortener.py`, which keeps one item per category and
caps the spoken payload to `VOICE_MAX_SPOKEN_CHARS` (default 1200).

If you want longer or shorter spoken briefings, tune `.env`:

```env
VOICE_MAX_SPOKEN_CHARS=1200
VOICE_BRIEFING_ITEMS_PER_CATEGORY=1
```

`/ask`, `/briefing/daily`, and the dashboard still show the full
briefing — the shortener only affects what the TTS engine receives.

---

## Integrations

### Slack returns 409 "not configured"

`ENABLE_SLACK=false` or `SLACK_WEBHOOK_URL` is empty. Set both in `.env`
and restart.

### Slack returns 502 "slack send failed"

The webhook posted but Slack returned a non-2xx response. Check the
webhook URL is still valid (Slack may have rotated it). The audit log
records the error reason (`http_<code>`, `timeout`, `connection_error`)
without the URL.

### Home Assistant entity blocked

The entity is either:
- In the hard-block list (`lock`, `alarm_control_panel`, `cover`, `camera`, `device_tracker`, `person`) — **cannot be overridden by env**, by design
- Not in your `HOME_ASSISTANT_ALLOWED_ENTITIES` list
- In an unsupported domain (turn-on/off only works on `light` and `switch`)

The audit log records `home_assistant_action_blocked` with a `reason` field that says exactly which check failed.

### Home Assistant connection error

```bash
curl -H "Authorization: Bearer $HA_TOKEN" $HOME_ASSISTANT_URL/api/
```

If this fails from the Pi but works from your laptop, check:
- HA is reachable from the Pi's network
- Token hasn't been revoked
- HA URL includes the port (default `:8123`)

---

## Systemd / service

### `rasapi.service` failed to start

```bash
sudo systemctl status rasapi
journalctl -u rasapi -n 50 --no-pager
```

Common causes:
- `<PI_USER>` placeholder not substituted in the unit file
- `WorkingDirectory` doesn't match the actual repo path
- `.env` unreadable by the service user
- Python venv missing → run `install.sh`

### Port 8000 not reachable from the LAN

The default systemd unit binds to `127.0.0.1`. To accept LAN connections,
edit `/etc/systemd/system/rasapi.service`, change `--host 127.0.0.1` to
`--host 0.0.0.0`, then:

```bash
sudo systemctl daemon-reload
sudo systemctl restart rasapi
ss -tlnp | grep 8000
```

> Only do this on a trusted network. Enable auth first.

### Pi reboots but RasaPi doesn't auto-start

```bash
sudo systemctl is-enabled rasapi          # should say "enabled"
sudo systemctl enable rasapi              # if it isn't
```

---

## Git / update

### Git pull conflicts during update

`update-rasapi.sh` refuses to run with uncommitted changes. Either:

```bash
cd ~/rasapi-local-ai-assistant
git status
git stash                                  # save your local edits
bash deployment/raspberry-pi/update-rasapi.sh
git stash pop                              # restore them after
```

Or commit/discard before updating.

### Database path accidentally becomes `backend/backend/data/...`

This happens if your `.env` sets `DATABASE_PATH=backend/data/rasapi.db`
but you're running the server from inside `backend/`. The relative path
resolves to `backend/backend/data/`.

Fix: use `DATABASE_PATH=data/rasapi.db` if your working directory is
`backend/`, **or** `DATABASE_PATH=backend/data/rasapi.db` if your
working directory is the project root.

The systemd unit ships with `WorkingDirectory=…/rasapi-local-ai-assistant/backend`,
so use the project-root-relative path **without** the leading `backend/`
when running via systemd.

`bash deployment/raspberry-pi/doctor.sh` warns when it finds
`backend/backend/` on disk.

---

## Auth

### "auth misconfigured" returned from protected endpoints

`ENABLE_AUTH=true` but `API_SECRET_KEY` is still the placeholder
(`change-me-before-use` or `replace-with-output-of-generate-secret-sh`)
or empty. Generate a real value:

```bash
bash deployment/raspberry-pi/generate-secret.sh
# paste into .env, then:
sudo systemctl restart rasapi
```

---

## When in doubt

```bash
bash deployment/raspberry-pi/doctor.sh
```

If the issue isn't covered here or there, open an issue on GitHub with
the doctor output attached (sanitize any IPs or hostnames you don't want
public — the script never prints secrets).
