# RasaPi — Security Model

This document is the security spec for the running Phase 1 codebase. Every claim here is enforced by code in `backend/security/` and `backend/core/`, and verified by tests in `tests/`.

---

## Threat model

RasaPi runs on a home network and accepts natural-language input that, by design, can trigger system commands. The threats that drive Phase 1's design (and Phase 2's restraint):

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
| **Cloud data exfiltration** | Unintended outbound call | No cloud client imported. Ollama is `localhost` only and is opt-in via `ENABLE_LOCAL_LLM` |
| **LLM tool escalation** | Model output interpreted as a command | `core/local_llm.py` does not import `command_runner`, `allowlist`, or `subprocess`. Output is opaque text. Structural test enforces this in CI. See "LLM cannot execute tools" below. |
| **Prompt-prompt injection via LLM output** | Crafted query causes LLM to emit shell-like text that we then parse | We never parse LLM output for actions. It is a string field in the response. |
| **System-prompt override** | User input attempts to redefine the assistant's role | System prompt is hard-coded in source; user input only fills the `user` message. |
| **Sensitive data persisted to local store (Phase 3)** | User says "remember that my password is …" | `security/sensitive_data.is_sensitive` checks every memory/note write; matches are rejected with a static safe message and audited as `sensitive_memory_blocked`. |
| **LLM writing to memory store (Phase 3)** | Model output interpreted as a memory write | `core/local_llm.py` does not import `core/memory.py` or `core/tasks.py`. Memory writes only happen via the deterministic router or direct REST. Tested in `test_phase3_routing.py::test_llm_response_does_not_create_memory`. |
| **SQL injection via memory value** | User crafts SQL-like value | All writes use parameterized queries (`?` placeholders). Tested in `test_save_memory_uses_parameterized_sql` — a literal `'; DROP TABLE …; --` survives a round-trip and the table remains intact. |
| **Memory leakage to LLM** | List operation results passed back to the model | List results are returned to the user, never re-injected into a prompt. The LLM module receives only the user's current query. |
| **Briefing leaks user data (Phase 4)** | RSS/weather subsystem reads memory/notes/tasks | `backend/briefing/` does not import `core/memory.py`, `core/tasks.py`, `core/command_runner.py`, or `subprocess`. Structural test enforces this. |
| **Briefing path executes commands (Phase 4)** | RSS content interpreted as shell | RSS items are stored verbatim as text and never templated into a shell or template engine. |
| **Personalized briefing leaks personal data** | `personalized_action_items` populated from local memory | Phase 4 leaves this category as a documented empty stub. Populating it requires a future explicit security decision. |
| **LLM summary leaks personal data (Phase 4)** | LLM summary call sends user data | The summary path receives ONLY public source headlines (titles + source names). Test mocks the LLM and inspects call args. Both `ENABLE_LOCAL_LLM` AND `ENABLE_LLM_BRIEFING_SUMMARY` must be true; default is off-off. |
| **Treating immigration content as legal advice** | User acts on briefing as guidance | Hardcoded disclaimer appended to all immigration responses. Test asserts presence on `/ask` and `/briefing/category/immigration_updates`. |
| **Aggressive scraping of public sources** | Repeated `/ask` calls hammer feeds | `BRIEFING_CACHE_MINUTES=60` cap on auto-refresh from `/ask`. Manual `POST /briefing/refresh` is operator-initiated. Per-source timeout `BRIEFING_FETCH_TIMEOUT_SECONDS=10`. |

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

## LLM cannot execute tools (Phase 2)

Phase 2 introduces an optional local LLM fallback. The LLM is **never** an executor — by design, by structure, and by test.

### Where the LLM sits

```
                         router matched? ──yes──► command path (Phase 1)
                              │
                              no
                              │
                ENABLE_LOCAL_LLM == true? ──no──► Phase 1 fallback message
                              │
                              yes
                              ▼
              core/local_llm.generate_chat_response(query)
                              │
                              │  HTTP POST → http://localhost:11434/api/chat
                              │  Body: {model, messages: [system_prompt, user_query], stream: false}
                              │
                              ▼
                       returns: str
                              │
                              ▼
       AskResponse.response = <that string, verbatim>
                              │
                              ▼
                      Client receives JSON
```

The LLM's output never leaves `local_llm.py` as anything other than a `str`. The route handler places it in `AskResponse.response` and returns. That is the entire path.

### Structural guarantees (enforced by tests)

| Guarantee | Test in `tests/test_local_llm.py` |
|---|---|
| `core/local_llm.py` does not import `command_runner`, `allowlist`, or `subprocess` | `test_local_llm_module_does_not_import_executor` (AST check) |
| Even when the LLM returns text like `"run rm -rf /"`, no command runs | `test_llm_response_never_invokes_command_runner` (mocks `run_command` to fail loudly) |
| Known intents short-circuit before any LLM call | `test_known_intent_skips_llm`, `test_command_intent_skips_llm` |
| Disabling the flag truly disables the LLM | `test_fallback_skips_llm_when_disabled` |
| Errors return a static safe string, never crash | `test_ollama_timeout_returns_safe_message`, `test_ollama_connection_error_returns_safe_message` |

### What the LLM is told (system prompt)

The system prompt is **hard-coded** in `core/local_llm.py`. The user's query only ever appears as the `user` message. There is no API surface that lets a query overwrite or extend the system prompt.

```
You are RasaPi, a local conversational assistant running on a Raspberry Pi.
You CANNOT execute commands, access files, modify the system, or take any
action. The user's system tools are handled by a separate router that only
invokes pre-approved commands. Reply only with plain conversational text.
Do not output shell commands, code blocks intended for execution, or
instructions to run code.
```

The system prompt is polish, not enforcement. The real guarantee is that **no executor is reachable from the LLM module.**

### What is NOT sent to the LLM

- `.env` values, secrets, `API_SECRET_KEY`
- Audit log contents
- Filesystem paths or contents
- Conversation history (Phase 3 will introduce this with explicit user opt-in)
- System telemetry, hostnames, IP addresses
- Any field from `Settings` other than the model name and base URL (used for connection only)

The function signature is `generate_chat_response(query: str) -> str`. That is the full input/output surface. No request context, no session, no environment.

### Network egress

The Ollama daemon is expected at `http://localhost:11434`. There is no code path that contacts a non-localhost LLM endpoint. To verify on a Pi:

```bash
sudo netstat -tnp | grep python   # only :8000 (FastAPI) and :11434 (Ollama) should appear
```

A future cloud phase, if ever added, will be a deliberate design decision behind explicit per-request user consent.

---

## Local memory, notes, and tasks (Phase 3)

Phase 3 adds persistent local storage. Two security properties are enforced by code, not just policy.

### 1. Memory and tasks are local-only

- Database file: `backend/data/rasapi.db` (SQLite). Path is gitignored.
- No code path writes memory data to a network socket. Verified by inspection: `core/memory.py` and `core/tasks.py` import only `storage`, `security`, and stdlib.
- The LLM module (`core/local_llm.py`) does not import the storage modules.

### 2. The LLM cannot write to the store

```
        deterministic router  ─────────┐
                                       │
                                       ▼
   user query  ──►  intent matched  ──► core.memory  /  core.tasks  ──► SQLite
                                                            ▲
                                       direct REST ─────────┘
                                       (Pydantic-validated)

   LLM (Phase 2)  ───────────────────►  text response only.
                                       NO arrow into core.memory or core.tasks.
```

The structural guarantee is that `core/local_llm.py` does not import `core/memory.py` or `core/tasks.py`. There is no in-process bridge from the LLM's string output to the storage layer. Tested by `test_llm_response_does_not_create_memory` and `test_llm_response_does_not_create_tasks`: even when the LLM returns text like *"Saved! I'll remember that"*, the row count in `memory_items` remains zero.

### 3. Sensitive-data detection (best-effort, not perfect)

`security/sensitive_data.py` runs on every memory and note write — both `/ask` and direct REST paths. It blocks:

| Pattern | Caught by |
|---|---|
| `my password is …`, `password:` | phrase match |
| `api key is …`, `api_key=…` | phrase match + regex (`sk-…`, `ghp_…`, `xoxb-…`, `AKIA…`) |
| `bearer token`, `secret token` | phrase match |
| `-----BEGIN PRIVATE KEY-----` | phrase match |
| US SSN `123-45-6789` | regex |
| Credit-card-shaped 13–19 digit run | regex (loose, no Luhn) |
| `passport number` phrase | phrase match |
| JWT-shaped tokens | regex |

**This is a practical safety layer, not a DLP product.** Documented in the source file. False negatives are accepted; false positives prefer to over-block. The operator should not deliberately tell RasaPi a secret expecting the detector to handle it.

When the detector matches:
- The write is rejected.
- The user receives a static safe message: *"I can't save sensitive information like passwords, API keys, tokens, or financial identifiers."*
- An audit event is logged with `event_type="sensitive_memory_blocked"` and the **pattern name**, never the matched content.

### 4. SQL injection

All write paths use parameterized queries (`conn.execute(sql, (...))`). A regression test inserts `'; DROP TABLE memory_items; --` as a value, then verifies the value round-trips and the table still exists.

### 5. File permissions (out of scope for Phase 3)

Phase 3 does not enforce a specific filesystem mode on `backend/data/rasapi.db`. The file inherits the umask of the user running the server. Phase 5 deployment will set `chmod 600` on the data directory and document the expected ownership.

---

## Daily briefing (Phase 4)

Phase 4 adds a public-source news + weather digest. Three security properties are enforced by code, not just policy.

### 1. Public sources only, no API keys

The source registry is hardcoded in `backend/briefing/sources.py`. Every URL is publicly accessible. No source requires authentication or sends a user identifier. Open-Meteo (the weather provider) is a free European public-data service with no API key and no per-user tracking.

Outbound HTTPS connections during a briefing refresh are limited to the hosts listed in the `Source` registry plus `api.open-meteo.com`. No other hosts are contacted.

### 2. Briefing cannot read personal data

```
   user query ──► router ──► matched briefing intent ──► briefing/generator
                                                            │
                                                            │  ONLY reads:
                                                            │   - briefing_items / briefing_runs (DB)
                                                            │   - public RSS hosts
                                                            │   - api.open-meteo.com
                                                            │
                                                            └──► NEVER reads:
                                                                  core/memory.py
                                                                  core/tasks.py
                                                                  core/command_runner.py
                                                                  subprocess

   memory_items / notes / tasks tables  ──► reachable only from core/memory and core/tasks
```

A test (`test_briefing_package_does_not_import_memory_or_tasks_or_subprocess`) AST-walks every file in `backend/briefing/` and fails the build if any forbidden import appears. Adding such an import would require deleting the test, which is the kind of change a code reviewer would notice.

### 3. LLM briefing summary is opt-in-opt-in

The Phase 4 generator only invokes the LLM when **both** flags are true:

```
ENABLE_LOCAL_LLM         ENABLE_LLM_BRIEFING_SUMMARY    Behaviour
─────────────────────────────────────────────────────────────────
false (default)          false (default)               No LLM call. Deterministic format.
true                     false (default)               No LLM call. Deterministic format.
false                    true                          No LLM call. Deterministic format.
true                     true                          One sync Ollama call per refresh.
```

When the LLM does run, the prompt contains only:
- The hardcoded system prompt: *"You are summarizing public news headlines into a 2-3 sentence digest. Reply with plain text only."*
- A user message: numbered list of `title (source_name)` for items already fetched from public sources.

It never sees memory, notes, tasks, audit logs, env values, or filesystem content. A test mocks the LLM and inspects call args to ensure no personal data appears.

If the LLM call fails (timeout, connection error), the briefing falls back to the deterministic formatter and audits `llm_briefing_summary_skipped`.

### 4. Immigration disclaimer

Any briefing response that includes USCIS items appends:

> *"These are official-source updates only, not legal advice. Verify with USCIS, your school OGS, or a qualified immigration advisor."*

Hardcoded in `briefing/formatter.py`. Tests verify it appears on both `/ask` immigration responses and the JSON field of `/briefing/category/immigration_updates`.

### 5. Personalized category is a documented empty stub

`personalized_action_items` is registered in `CATEGORIES` and `SOURCES` (kind=`placeholder`) but always returns `[]` from the fetcher. Populating it from the user's memory or tasks would let briefing read personal data, which would weaken the structural guarantees in section 2. Doing so requires an explicit Phase 4.5+ design decision.

### 6. Out-of-scope (deliberately, until later phases)

- Background scheduler — manual refresh only via `POST /briefing/refresh` or auto-refresh on cache miss in `/ask`
- Slack / email delivery
- Cloud LLM summarization
- Embeddings / semantic search
- Custom user-supplied source URLs (registry is hardcoded for review)

---

## Audit logging behaviour

Every relevant event is appended as a single JSON line to `logs/audit-YYYY-MM-DD.jsonl`. Files rotate daily. Entries are append-only and never modified after writing.

### Event types

| `event_type` | Emitted when | Fields |
|---|---|---|
| `request` | `/ask` receives a query | `timestamp`, `request_id`, `query` (truncated to 500 chars) |
| `command_exec` | A command completes (success / error) | `timestamp`, `request_id`, `command`, `args`, `outcome`, `duration_ms` |
| `command_exec` (rejected) | Allowlist validator rejects | as above with `outcome="rejected"`, `reason` |
| `llm_call` | Ollama call completes (success or failure) | `timestamp`, `request_id`, `model`, `outcome` (`success`/`error`), `duration_ms`, `reason` (on error only) |
| `memory_created` / `note_created` / `task_created` | A row was inserted | `timestamp`, `request_id`, `event_type`, `item_type`, `item_id`, `outcome="success"` |
| `memory_listed` / `note_listed` / `task_listed` | A list query was served | `timestamp`, `request_id`, `event_type`, `item_type` |
| `task_completed` | A task was marked done (or attempt) | as above with `item_id`, `outcome` (`success`/`noop`/`error`), `reason` (`already_done`/`not_found`) |
| `sensitive_memory_blocked` | A memory or note write was rejected | `timestamp`, `request_id`, `item_type`, `outcome="blocked"`, `reason` (pattern name, not content) |
| `briefing_refresh_started` / `briefing_refresh_completed` / `briefing_refresh_failed` | Briefing run lifecycle | `timestamp`, `request_id`, `outcome` (`started`/`success`/`partial`/`error`), `category`, `item_count` |
| `briefing_source_failed` | One source raised during refresh | `timestamp`, `request_id`, `source_name`, `category`, `reason` (truncated) |
| `briefing_item_stored` | A new item passed dedup and was inserted | `timestamp`, `request_id`, `source_name`, `category` |
| `briefing_served` | A read query for items was executed | `timestamp`, `request_id`, `category`, `item_count` |
| `weather_fetch_completed` / `weather_fetch_failed` | Open-Meteo call result | `timestamp`, `request_id`, `source_name`, `outcome`, `reason` (on failure) |
| `llm_briefing_summary_used` / `llm_briefing_summary_skipped` | Whether the LLM digest path ran on this request | `timestamp`, `request_id`, `outcome`, `item_count` (when used), `reason` (when skipped due to error) |

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
| User memory, notes, tasks (Phase 3) | Local SQLite at `backend/data/rasapi.db` | No |

No data leaves the Pi unless a future phase explicitly opts the user in to a cloud feature. Phase 1 has no networked egress code paths.
