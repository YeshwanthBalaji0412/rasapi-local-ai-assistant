"""
Data expansion layer (Phase 12).

Provides read-only, cache-backed access to a set of public information sources
(weather, news, market, trending, currency, jobs, ...). The layer is:

  - Read-only. Every /data/* endpoint is GET; no source writes are permitted.
  - Cache-first. In-memory hot cache backed by SQLite so restarts don't
    trigger a thundering herd against upstream feeds.
  - Fail-open. Timeouts and errors return `{"data": null, "warnings": [...]}`
    instead of 500ing. Stale cache is served on upstream failure when
    DATA_STALE_FALLBACK=true.
  - Opt-in per source. Missing API keys / disabled flags surface as a
    `disabled` health status, not an error.

This module is deliberately isolated from the LLM code path. The local LLM
cannot import `data_sources` and cannot reach any /data/* endpoint — enforced
by AST tests in tests/test_llm_isolation.py.
"""

from .base import DataSource, Envelope, SourceResult
from .cache import CacheEntry, TwoLayerCache
from .registry import SourceHealth, SourceRegistry, get_registry, reset_registry_for_tests

__all__ = [
    "DataSource",
    "Envelope",
    "SourceResult",
    "CacheEntry",
    "TwoLayerCache",
    "SourceHealth",
    "SourceRegistry",
    "get_registry",
    "reset_registry_for_tests",
]
