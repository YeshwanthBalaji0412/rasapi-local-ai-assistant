import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from config import settings
from integrations import registry


_SLACK_CANARY = "https://hooks.slack.com/services/CANARY/SHOULD-NOT-LEAK/12345"
_HA_TOKEN_CANARY = "ha-token-CANARY-DO-NOT-LEAK-99999"


def test_registry_lists_all_three_integrations():
    entries = registry.list_integrations()
    keys = {e.key for e in entries}
    assert keys == {"slack", "home_assistant", "alexa_future_stub"}


def test_all_integrations_disabled_by_default():
    entries = registry.list_integrations()
    for e in entries:
        assert e.enabled is False
    # alexa stub stays "future"
    alexa = next(e for e in entries if e.key == "alexa_future_stub")
    assert alexa.status == "future"


def test_slack_webhook_never_appears_in_registry(monkeypatch):
    monkeypatch.setattr(settings, "enable_slack", True)
    monkeypatch.setattr(settings, "slack_webhook_url", _SLACK_CANARY)
    blob = repr(registry.to_safe_dicts())
    assert _SLACK_CANARY not in blob


def test_home_assistant_token_never_appears_in_registry(monkeypatch):
    monkeypatch.setattr(settings, "enable_home_assistant", True)
    monkeypatch.setattr(settings, "home_assistant_url", "http://ha.local:8123")
    monkeypatch.setattr(settings, "home_assistant_token", _HA_TOKEN_CANARY)
    blob = repr(registry.to_safe_dicts())
    assert _HA_TOKEN_CANARY not in blob


def test_safe_dicts_contains_no_url_or_token_keys():
    """Even when integrations are configured, the public dict must not
    expose webhook URL or HA URL/token field names."""
    forbidden_keys = {"slack_webhook_url", "home_assistant_token", "home_assistant_url"}
    for entry in registry.to_safe_dicts():
        leaked = forbidden_keys & set(entry.keys())
        assert not leaked, f"registry leaks keys: {leaked}"
