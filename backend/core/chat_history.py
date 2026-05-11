"""
In-memory chat history for the /assistant page (Phase 11).

Phase 3 says the LLM cannot write memory. Chat history is therefore *not*
treated as Phase 3 memory:
  - It lives in-process only (no SQLite, no audit log payload, no disk).
  - It evicts on logout, session expiry, or process restart.
  - It is capped per session.
  - It is keyed by session token when auth is on, or by client IP when
    auth is off (preserves single-user local-dev workflow).

This module exists so the assistant page can re-render the last few
exchanges after a form POST/redirect cycle, not as a long-term memory
substitute. Anything important must still go through "remember that …"
which writes to the audited memory store.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import Lock


MAX_EXCHANGES = 10


@dataclass(frozen=True)
class Exchange:
    query: str
    response: str
    intent: str
    source: str


_store: dict[str, deque[Exchange]] = {}
_lock = Lock()


def append(session_key: str, exchange: Exchange) -> None:
    if not session_key:
        return
    with _lock:
        bucket = _store.get(session_key)
        if bucket is None:
            bucket = deque(maxlen=MAX_EXCHANGES)
            _store[session_key] = bucket
        bucket.append(exchange)


def recent(session_key: str) -> list[Exchange]:
    if not session_key:
        return []
    with _lock:
        bucket = _store.get(session_key)
        if bucket is None:
            return []
        return list(bucket)


def clear(session_key: str) -> None:
    if not session_key:
        return
    with _lock:
        _store.pop(session_key, None)


def clear_all() -> None:
    """Used by tests and by future logout-everywhere flows."""
    with _lock:
        _store.clear()
