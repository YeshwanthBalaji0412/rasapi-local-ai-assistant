"""
Source implementations for the Phase 12 data layer.

Each source is a subclass of data_sources.base.DataSource. Sources register
themselves with the module-level SourceRegistry via `register_all_sources()`,
which the app's lifespan hook invokes once at startup.

Gate 2 (this file): weather, on_this_day, currency — all free-tier, no keys.
Gate 3+: RSS/news, HN/GitHub trending, Finnhub market, Greenhouse/Lever jobs.

Sources never leak upstream URLs, API keys, or raw HTTP responses. The
Envelope wire shape is uniform across every source so the UI can render
data + warnings without per-source logic.
"""
from __future__ import annotations

from data_sources.cache import TwoLayerCache
from data_sources.registry import get_registry

from .currency import CurrencySource
from .on_this_day import OnThisDaySource
from .weather import WeatherSource

__all__ = [
    "CurrencySource",
    "OnThisDaySource",
    "WeatherSource",
    "register_all_sources",
]


# Module-level cache shared by all sources. Constructed lazily on first
# register_all_sources() call so tests using a fresh registry get a fresh
# cache too.
_shared_cache: TwoLayerCache | None = None


def register_all_sources(cache: TwoLayerCache | None = None) -> None:
    """Instantiate every source and register it with the singleton registry.

    Safe to call multiple times: re-registration is a no-op if the source
    is already present.
    """
    global _shared_cache
    if cache is not None:
        _shared_cache = cache
    if _shared_cache is None:
        _shared_cache = TwoLayerCache()

    registry = get_registry()
    for cls in (WeatherSource, OnThisDaySource, CurrencySource):
        if registry.get(cls.name) is not None:
            continue
        registry.register(cls(cache=_shared_cache))
