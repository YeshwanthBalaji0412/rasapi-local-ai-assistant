# RasaPi — Raspberry Pi 5 Setup Guide

End-to-end instructions for running RasaPi on a Raspberry Pi 5 as an
always-on local-first assistant server. After this guide, you will have
the FastAPI backend and dashboard running under systemd, accessible over
your home LAN, and surviving reboots.

> ⚠️ **Local-only.** Phase 6 has no authentication. Do not port-forward
> RasaPi to the public internet. Bind to `127.0.0.1` for Pi-only use, or
> `0.0.0.0` for trusted home-LAN use. That is the entire trust model.

---

## What you need

- Raspberry Pi 5 (8 GB recommended)
- Raspberry Pi OS 64-bit (Bookworm or newer)
- A reliable power supply and SD card / SSD
- SSH access to the Pi
- Pi connected to your home network
- A MacBook (or any client) on the same network

Phase 6 makes **no** assumption about Ollama. You can deploy the backend
and dashboard without a local LLM. Adding Ollama is an optional appendix
at the end of this guide.

---

## 1. Update the Pi

```bash
sudo apt update
sudo apt upgrade -y
```

## 2. Install required system packages (one-time)

If `install.sh` reports any of these missing in step 4, run:

```bash
sudo apt install -y python3 python3-venv python3-pip git
```

## 3. Clone the repo

```bash
cd ~
git clone https://github.com/YeshwanthBalaji0412/rasapi-local-ai-assistant.git
cd rasapi-local-ai-assistant
```

## 4. Run the installer

```bash
bash deployment/raspberry-pi/install.sh
```

What it does:

- Verifies `python3`, `python3-venv`, `python3-pip`, `git`
- Creates `backend/.venv`
- `pip install -r backend/requirements.txt`
- Creates `backend/data/` and `logs/` with mode `700`
- Copies `deployment/raspberry-pi/env.example.pi` → `.env` (only if `.env` does not yet exist)

It does **not** install system packages, modify the firewall, or store
secrets.

## 5. Lock down `.env`

```bash
chmod 600 .env
```

Open it and adjust values. At minimum, generate a real `API_SECRET_KEY`:

```bash
openssl rand -hex 32
# paste the output as the value of API_SECRET_KEY in .env
nano .env
```

## 6. Manual sanity run

```bash
cd ~/rasapi-local-ai-assistant/backend
source .venv/bin/activate
uvicorn main:app --host 127.0.0.1 --port 8000
```

You should see `Uvicorn running on http://127.0.0.1:8000`.

## 7. Health check (from the Pi itself)

In a second SSH session:

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","version":"0.6.0","assistant":"RasaPi"}
```

## 8. Run the smoke test

```bash
bash deployment/raspberry-pi/smoke-test.sh
```

You should see ~9 PASS lines. If anything fails, check
[`troubleshooting.md`](troubleshooting.md).

Stop the manual `uvicorn` (Ctrl-C) before continuing — systemd will manage
it from here on.

## 9. Install the systemd service

The shipped unit uses `<PI_USER>` as a placeholder. Substitute your real
username (whatever `whoami` prints) when installing:

```bash
sed "s|<PI_USER>|$USER|g" deployment/raspberry-pi/rasapi.service \
  | sudo tee /etc/systemd/system/rasapi.service > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable rasapi
sudo systemctl start rasapi
```

## 10. Verify the service

```bash
sudo systemctl status rasapi
# look for: Active: active (running)

curl http://127.0.0.1:8000/health
```

Stream logs:

```bash
journalctl -u rasapi -f
```

## 11. (Optional) Switch to LAN binding

By default the service binds to `127.0.0.1`, so the dashboard is reachable
from the Pi only. To reach it from your MacBook over the home network:

```bash
sudo nano /etc/systemd/system/rasapi.service
# Comment the --host 127.0.0.1 ExecStart line.
# Uncomment the --host 0.0.0.0 ExecStart line.

sudo systemctl daemon-reload
sudo systemctl restart rasapi
```

> ⚠️ Only do this on a trusted home network. Do **not** port-forward
> port 8000 to the public internet. There is no authentication.

Find the Pi's LAN IP:

```bash
hostname -I | awk '{print $1}'
# e.g. 192.168.1.50
```

## 12. Open the dashboard from your MacBook

In your MacBook browser:

```
http://<PI_LAN_IP>:8000/dashboard
```

You should see the RasaPi dashboard.

## 13. Reboot test

```bash
sudo reboot
```

Wait ~30 seconds, SSH back in, and check:

```bash
sudo systemctl status rasapi
# Active: active (running)
```

The service should be up automatically.

## 14. Updating from GitHub

```bash
cd ~/rasapi-local-ai-assistant
git pull --ff-only

cd backend
source .venv/bin/activate
pip install -r requirements.txt
deactivate

sudo systemctl restart rasapi
sudo systemctl status rasapi
```

## 15. Backup your data

```bash
bash deployment/raspberry-pi/backup.sh
# → ~/rasapi-backups/<timestamp>/
#   - rasapi.db
#   - audit-*.jsonl
# (.env is intentionally not included)
```

## 16. Restore from backup

```bash
sudo systemctl stop rasapi
bash deployment/raspberry-pi/restore.sh ~/rasapi-backups/<timestamp>
sudo systemctl start rasapi
```

## 17. Stop / remove the service

```bash
sudo systemctl stop rasapi
sudo systemctl disable rasapi
sudo rm /etc/systemd/system/rasapi.service
sudo systemctl daemon-reload
```

## 18. File permission summary

| Path | Mode | Why |
|---|---|---|
| `.env` | `600` | Contains API secret key |
| `backend/data/` | `700` | SQLite database |
| `logs/` | `700` | Audit log files |

## 19. Troubleshooting

See [`troubleshooting.md`](troubleshooting.md) for common issues:
service won't start, port already in use, permission errors, weather
endpoint failing, briefing source timeouts.

---

## Optional: Local LLM on Raspberry Pi

The backend works fine without Ollama — keep `ENABLE_LOCAL_LLM=false`
until you've confirmed dashboard + briefing work end-to-end.

If you want to try Ollama on the Pi:

```bash
# Install Ollama (its installer adds a systemd service named `ollama`)
curl -fsSL https://ollama.com/install.sh | sh

# Pull a small model (1B parameter — fits comfortably on Pi 5)
ollama pull llama3.2:1b
ollama list
```

Then in `.env`:

```env
ENABLE_LOCAL_LLM=true
LOCAL_LLM_MODEL=llama3.2:1b
```

Restart RasaPi:

```bash
sudo systemctl restart rasapi
```

Inference on the Pi will be slow (CPU-only). If responses time out, raise
`LOCAL_LLM_TIMEOUT_SECONDS` or keep the LLM running on a faster machine
(e.g. your MacBook) and point `OLLAMA_BASE_URL` at it.

---

## Optional: Secure remote access via Tailscale (future)

Out of scope for Phase 6. If you ever want to reach the dashboard from
outside your home network, install [Tailscale](https://tailscale.com/)
on both the Pi and your client device. The dashboard then becomes
reachable at `http://<pi-tailscale-name>:8000` only over the encrypted
tailnet — no public port-forward, no inbound holes in your router.

Phase 6 deliberately does not configure Tailscale. That stays a manual,
explicit user action.
