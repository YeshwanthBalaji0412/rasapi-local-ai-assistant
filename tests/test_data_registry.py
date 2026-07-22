"""
Tests for data_sources.registry.
"""
from __future__ import annotations

import pytest

from data_sources.base import DataSource
from data_sources.registry import (
    SourceRegistry,
    get_registry,
    reset_registry_for_tests,
)


class _MockSource(DataSource):
    name = "mock"
    default_ttl_seconds = 60

    def __init__(self, *, enabled: bool = True, disabled_reason: str = "no key"):
        super().__init__()
        self._enabled = enabled
        self._disabled_reason = disabled_reason

    def is_enabled(self) -> bool:
        return self._enabled

    def disabled_reason(self) -> str:
        return self._disabled_reason

    async def _do_fetch(self, key, warnings):
        return None


class _OtherMock(_MockSource):
    name = "other"


class _NamedMock(_MockSource):
    """Subclass that lets tests set a unique name at construction time."""

    def __init__(self, name: str, **kwargs):
        # Set on the instance BEFORE super().__init__ — DataSource.__init__
        # reads self.name via the class attribute; we override it.
        type(self).name = name
        super().__init__(**kwargs)


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_registry_for_tests()
    yield
    reset_registry_for_tests()


# ── registration ───────────────────────────────────────────────────────


def test_register_and_get():
    reg = SourceRegistry()
    src = _MockSource()
    reg.register(src)
    assert reg.get("mock") is src
    assert reg.names() == ["mock"]


def test_register_duplicate_raises():
    reg = SourceRegistry()
    reg.register(_MockSource())
    with pytest.raises(ValueError, match="already registered"):
        reg.register(_MockSource())


def test_register_empty_name_raises():
    reg = SourceRegistry()

    class Nameless(DataSource):
        name = ""

        async def _do_fetch(self, key, warnings):
            return None

    # DataSource.__init__ itself raises for empty name, so we hit that first.
    with pytest.raises(ValueError):
        reg.register(Nameless.__new__(Nameless))  # bypass __init__ to force the registry check


def test_get_missing_returns_none():
    reg = SourceRegistry()
    assert reg.get("nope") is None


def test_names_is_sorted():
    reg = SourceRegistry()
    reg.register(_OtherMock())
    reg.register(_MockSource())
    assert reg.names() == ["mock", "other"]


# ── health tracking ────────────────────────────────────────────────────


def test_health_reflects_enabled_state():
    reg = SourceRegistry()
    reg.register(_MockSource(enabled=True))
    h = reg.health_for("mock")
    assert h is not None
    assert h.enabled is True
    assert h.disabled_reason is None


def test_health_reports_disabled_reason():
    reg = SourceRegistry()
    reg.register(_MockSource(enabled=False, disabled_reason="no api key"))
    h = reg.health_for("mock")
    assert h is not None
    assert h.enabled is False
    assert h.disabled_reason == "no api key"


def test_health_is_live_not_cached():
    """If a source flips its enabled state, health_for reflects it."""
    reg = SourceRegistry()
    src = _MockSource(enabled=True)
    reg.register(src)
    src._enabled = False
    h = reg.health_for("mock")
    assert h is not None
    assert h.enabled is False


def test_record_fetch_updates_health():
    reg = SourceRegistry()
    reg.register(_MockSource())
    reg.record_fetch("mock", ok=True)
    h = reg.health_for("mock")
    assert h is not None
    assert h.last_fetch_ok is True
    assert h.last_fetch_at is not None


def test_all_health_returns_dicts_ready_for_json():
    reg = SourceRegistry()
    reg.register(_MockSource())
    healths = reg.all_health()
    assert len(healths) == 1
    d = healths[0].to_dict()
    for key in ("name", "enabled", "disabled_reason", "last_fetch_at", "last_fetch_ok"):
        assert key in d


# ── singleton ──────────────────────────────────────────────────────────


def test_module_singleton_returns_same_instance():
    r1 = get_registry()
    r2 = get_registry()
    assert r1 is r2


def test_reset_singleton_produces_fresh_instance():
    r1 = get_registry()
    reset_registry_for_tests()
    r2 = get_registry()
    assert r1 is not r2
