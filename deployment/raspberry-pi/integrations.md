# RasaPi — Integrations (Phase 9)

Phase 9 adds an opt-in integrations layer so RasaPi can talk to a few
trusted external systems. Two real integrations and one documented stub:

| Integration | Direction | Auth needed | Phase 9 status |
|---|---|---|---|
| Slack | RasaPi → Slack (post only) | webhook URL | ✅ working |
| Home Assistant | RasaPi → HA (read + actuate) | long-lived token | ✅ working |
| Alexa | RasaPi ↔ Alexa | n/a | 🟡 future stub only |

All integrations are **disabled by default**. Each has its own `ENABLE_*`
flag in `.env` and an explicit allowlist before any external call.

---

## Slack (incoming webhook)

### What it can do

- **Send a fixed test notification** ("✅ RasaPi Slack integration test")
- **Post the daily briefing** (or one specific category) — uses the same
  formatter the dashboard does

### What it deliberately cannot do

- ❌ Reply to messages
- ❌ Handle slash commands
- ❌ Post arbitrary user-supplied or LLM-generated text
- ❌ Listen to a channel
- ❌ Use bot tokens or OAuth

### Setup

1. **Create an incoming webhook in Slack.**
   - Slack → "Apps" → Browse → Incoming Webhooks → Add to a Slack workspace.
   - Choose a channel. Slack will mint a URL like:
     `https://hooks.slack.com/services/T01.../B02.../xxxxxxxxxxxxxx`
2. **Paste the URL into `.env`** (locked down with `chmod 600 .env`):

   ```env
   ENABLE_SLACK=true
   SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...
   SLACK_DEFAULT_CHANNEL=#rasapi
   SLACK_SEND_BRIEFING_ENABLED=true
   ```

3. **Restart the service:**

   ```bash
   sudo systemctl restart rasapi
   ```

4. **Smoke-test it:**

   ```bash
   curl -X POST http://127.0.0.1:8000/integrations/slack/test \
     -H "X-RasaPi-Key: $YOUR_KEY"          # only if ENABLE_AUTH=true
   ```

   You should see the test message in your Slack channel and `slack_test_sent`
   in the audit log.

### What the audit log records

- `slack_test_sent` / `slack_test_failed`
- `slack_briefing_sent` / `slack_briefing_failed`

The webhook URL is **never** written to the audit log, **never** appears
in API responses, and **never** appears in the dashboard.

---

## Home Assistant (REST API + long-lived token)

### What it can do

- Check HA reachability (`GET /api/`)
- List allowed entities only (server-side filtered)
- Read state of an allowed entity
- Turn on / turn off an allowed light or switch

### What it deliberately cannot do

- ❌ Call arbitrary HA services (`scene.activate`, `script.run`, etc.)
- ❌ Touch entities outside the operator's allowlist
- ❌ Touch hard-blocked domains: `lock`, `alarm_control_panel`, `cover`,
  `camera`, `device_tracker`, `person` — even if you add them to
  `HOME_ASSISTANT_ALLOWED_ENTITIES`
- ❌ Mutate HA configuration

### Setup

1. **Generate a long-lived access token** in Home Assistant:
   - Profile (bottom-left) → "Long-Lived Access Tokens" → Create Token.
   - Name it `rasapi`. Copy the value — it's shown only once.

2. **Decide which entities RasaPi may touch.** Browse `Developer Tools →
   States` in HA and pick a small set. Examples:

   ```
   light.desk_light
   switch.fan
   sensor.living_room_temperature
   ```

3. **Edit `.env`:**

   ```env
   ENABLE_HOME_ASSISTANT=true
   HOME_ASSISTANT_URL=http://homeassistant.local:8123
   HOME_ASSISTANT_TOKEN=<paste the long-lived token>
   HOME_ASSISTANT_ALLOWED_ENTITIES=light.desk_light,switch.fan,sensor.living_room_temperature
   HOME_ASSISTANT_ALLOWED_DOMAINS=light,switch,sensor
   ```

4. **Restart and smoke-test:**

   ```bash
   sudo systemctl restart rasapi

   curl -H "X-RasaPi-Key: $YOUR_KEY" \
     http://127.0.0.1:8000/integrations/home-assistant/status

   curl -H "X-RasaPi-Key: $YOUR_KEY" \
     http://127.0.0.1:8000/integrations/home-assistant/entities

   curl -X POST -H "X-RasaPi-Key: $YOUR_KEY" \
     http://127.0.0.1:8000/integrations/home-assistant/entities/light.desk_light/turn-on
   ```

5. **From `/ask`:**

   ```bash
   curl -X POST -H "X-RasaPi-Key: $YOUR_KEY" \
     -H 'Content-Type: application/json' \
     -d '{"query":"turn on desk light"}' \
     http://127.0.0.1:8000/ask
   ```

   The deterministic intent router parses `"desk light"` → matches against
   `HOME_ASSISTANT_ALLOWED_ENTITIES` → finds `light.desk_light` → calls HA.
   No LLM is in the loop.

### Adding an entity safely

1. Add it to `HOME_ASSISTANT_ALLOWED_ENTITIES`.
2. Confirm its domain is in `HOME_ASSISTANT_ALLOWED_DOMAINS` (or add it
   if it's a new domain — but never add `lock`, `alarm_control_panel`,
   `cover`, `camera`, `device_tracker`, or `person`).
3. Restart RasaPi.
4. Test via `GET /integrations/home-assistant/entities/<id>/state` first
   before issuing actions.

### What the audit log records

- `home_assistant_status_checked`
- `home_assistant_entity_listed`
- `home_assistant_state_read`
- `home_assistant_action_requested`
- `home_assistant_action_completed`
- `home_assistant_action_blocked` (when allowlist rejects)

The token is **never** written to the audit log, **never** appears in
API responses, and **never** appears in the dashboard. Every HA HTTP
call carries the token only in the `Authorization: Bearer …` request
header.

---

## Alexa (future)

Direct Alexa integration is **not** implemented in Phase 9 because it
typically requires:

- A public HTTPS endpoint (we explicitly don't expose one)
- An Alexa Skill in the Alexa Developer Console
- OAuth account linking

Two safer patterns the project will consider in a later phase:

1. **RasaPi → Home Assistant → Alexa-compatible devices.**
   Configure HA's [Nabu Casa](https://www.nabucasa.com/) or another Alexa
   bridge in HA, then control devices via the existing Phase 9 HA path.
   RasaPi never talks to Amazon directly.

2. **Alexa Skill → RasaPi via Tailscale + auth.**
   Once Phase 9+ adds HTTPS termination (reverse proxy) and RasaPi can
   be reached over Tailscale or behind Caddy/nginx, an Alexa skill could
   POST to `/ask` with an API key. This requires more infrastructure than
   Phase 9 is ready for.

The dashboard shows Alexa as a registry stub with `status: "future"`.

---

## Hard rules (regardless of integration)

- **Tokens and webhook URLs live in `.env` only.** Never the database,
  never the dashboard, never API responses, never audit logs.
- **No arbitrary URLs from `/ask`.** The router only knows the URLs in
  settings, loaded once at startup.
- **No arbitrary HA service names.** Only `turn_on` / `turn_off` (on
  `light` / `switch`) and state reads through the REST surface.
- **Authentication strongly recommended** before binding RasaPi to
  `0.0.0.0`. See `deployment/raspberry-pi/remote-access.md` and the
  Phase 8 setup notes.
- **Rotate secrets** if anything looks compromised. Both Slack
  webhook URLs and HA long-lived tokens can be revoked from their
  respective UIs and replaced in `.env`.
