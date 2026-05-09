# RasaPi — Remote Access (Phase 8)

> **Do not port-forward port 8000 to the public internet.** RasaPi has
> no rate limiting, no DDoS protection, and no formal security review.
> Phase 8 adds API-key auth, but auth alone is not enough to safely
> publish a service to the open internet.

If you want to reach RasaPi from outside your home, use a private mesh
network instead. Tailscale is the recommended option. This document
explains why and how.

---

## The three access modes

| Mode | systemd `--host` | Auth required? | Who can reach it |
|---|---|---|---|
| **A. Pi-local only** (default Phase 6) | `127.0.0.1` | No | only processes on the Pi |
| **B. Trusted home LAN** | `0.0.0.0` | **strongly recommended** | every device on your home WiFi |
| **C. Tailscale (private mesh)** | `0.0.0.0` (Tailscale interface) | **required** | only your tailnet devices |

You step from A → B → C as your needs grow. Each step **adds** exposure;
each step should also **add** a security control.

---

## A. Pi-local only — the default

The shipped `rasapi.service` binds to `127.0.0.1`. Only `curl
http://127.0.0.1:8000` from the Pi itself works. This is the safest mode
and is fine if you SSH into the Pi to interact with RasaPi.

No auth required for this mode. You could turn it on anyway as practice.

## B. Trusted home LAN — `--host 0.0.0.0`

Edit the systemd unit (Phase 6, step 11 in `setup-pi.md`) and uncomment
the `0.0.0.0` line. Now your MacBook can hit
`http://<pi-lan-ip>:8000/dashboard`.

**Turn auth ON before doing this.**

```bash
# 1. Generate a fresh secret
bash deployment/raspberry-pi/generate-secret.sh
# → paste the output as API_SECRET_KEY in .env

# 2. Enable auth
sed -i 's/^ENABLE_AUTH=.*/ENABLE_AUTH=true/' .env
chmod 600 .env

# 3. Restart
sudo systemctl restart rasapi

# 4. Verify
curl -s -o /dev/null -w "%{http_code}\n" http://<pi-lan-ip>:8000/ask \
  -H 'Content-Type: application/json' -d '{"query":"hello"}'
# → 401  (good)

curl -s http://<pi-lan-ip>:8000/ask \
  -H 'Content-Type: application/json' \
  -H "X-RasaPi-Key: $(cat ~/.rasapi-key 2>/dev/null || echo PASTE_YOUR_KEY)" \
  -d '{"query":"hello"}' | python3 -m json.tool
# → 200 + greeting
```

The dashboard now redirects to `/login` if you visit it without a
session. Paste the same secret to sign in.

### Optional: UFW restricting port 8000 to the LAN

If your Pi is dual-homed (e.g. Tailscale + LAN) and you only want LAN
access:

```bash
# allow port 8000 only on the LAN interface (replace eth0/wlan0 to match)
sudo ufw allow in on wlan0 to any port 8000
sudo ufw deny in to any port 8000
sudo ufw enable
```

Don't run `ufw enable` blindly — test SSH stays reachable first.

## C. Tailscale (private mesh) — RECOMMENDED for off-LAN access

[Tailscale](https://tailscale.com) puts your devices on a private,
encrypted, peer-to-peer network. Each device gets a stable hostname like
`pi.tail-cafe.ts.net`. Nothing is exposed to the public internet.

### Install on the Pi

```bash
# On the Pi:
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
# (follow the printed URL on your laptop to authorize the Pi)

# Confirm:
tailscale ip -4
# 100.x.y.z
```

### Bind RasaPi to listen on the Tailscale interface

`--host 0.0.0.0` will work — Tailscale traffic comes in on the same
listener. The `tailscale0` interface is private to your tailnet, so
this does **not** expose RasaPi publicly.

### Lock it down further (optional)

```bash
# Tailscale has its own firewall (ACLs) — by default everyone in
# your tailnet can reach the Pi. Restrict to specific devices via
# the Tailscale admin console.

# Or with UFW, allow only the tailscale0 interface:
sudo ufw allow in on tailscale0 to any port 8000
sudo ufw deny in to any port 8000
sudo ufw enable
```

### Access from your MacBook

```bash
# After installing Tailscale on the Mac and signing in:
open http://pi.tail-cafe.ts.net:8000/dashboard
```

You'll get the dashboard login page (assuming `ENABLE_AUTH=true`).

---

## What Phase 8 does NOT add

- ❌ HTTPS / TLS termination — Tailscale provides transport encryption
  on its mesh. For LAN-only HTTP, traffic is unencrypted. Phase 9 may
  add a reverse proxy with HTTPS.
- ❌ Public exposure / port forwarding — never appropriate for RasaPi.
- ❌ Rate limiting / brute-force protection — coming in a future phase.
- ❌ Multi-user accounts / OAuth — single shared secret only.
- ❌ Tailscale install automation — installing Tailscale is your
  explicit choice. RasaPi only documents the pattern.

---

## Hard rules

- **Never** add a port-forward rule on your home router for port 8000.
- **Always** enable auth before binding to `0.0.0.0`.
- **Rotate** `API_SECRET_KEY` if you suspect it's leaked. Stateless
  cookies sign with the current secret, so rotation invalidates every
  session immediately.
- **Treat** your `.env` like `~/.ssh/id_rsa`: `chmod 600 .env`, never
  commit it.
