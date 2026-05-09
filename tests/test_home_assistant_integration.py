import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import httpx
import pytest

from config import settings
from integrations import home_assistant as ha


_HA_URL = "http://ha.local:8123"
_HA_TOKEN_CANARY = "ha-token-CANARY-DO-NOT-LEAK-9b3f7a"


@pytest.fixture
def ha_off(monkeypatch):
    monkeypatch.setattr(settings, "enable_home_assistant", False)


@pytest.fixture
def ha_on(monkeypatch):
    monkeypatch.setattr(settings, "enable_home_assistant", True)
    monkeypatch.setattr(settings, "home_assistant_url", _HA_URL)
    monkeypatch.setattr(settings, "home_assistant_token", _HA_TOKEN_CANARY)
    monkeypatch.setattr(
        settings, "home_assistant_allowed_domains", "light,switch,sensor"
    )
    monkeypatch.setattr(
        settings,
        "home_assistant_allowed_entities",
        "light.desk_light,switch.fan,sensor.living_temp",
    )


def _ok_get(payload):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = payload
    return resp


def _ok_post():
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = []
    return resp


def _err(code: int):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = code
    resp.json.return_value = {}
    return resp


# ─── configuration sanity ───────────────────────────────────────────────────


def test_disabled_by_default(ha_off):
    assert ha.is_configured() is False


def test_enabled_but_no_url_is_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "enable_home_assistant", True)
    monkeypatch.setattr(settings, "home_assistant_url", "")
    monkeypatch.setattr(settings, "home_assistant_token", "")
    assert ha.is_configured() is False


def test_get_status_raises_when_not_configured(ha_off):
    with pytest.raises(ha.HANotConfigured):
        ha.get_status(request_id="r-1")


# ─── allowlist enforcement ──────────────────────────────────────────────────


def test_lock_domain_always_blocked_even_in_allowlist(monkeypatch):
    monkeypatch.setattr(settings, "enable_home_assistant", True)
    monkeypatch.setattr(settings, "home_assistant_url", _HA_URL)
    monkeypatch.setattr(settings, "home_assistant_token", _HA_TOKEN_CANARY)
    monkeypatch.setattr(
        settings, "home_assistant_allowed_domains", "light,switch,sensor,lock"
    )
    monkeypatch.setattr(
        settings, "home_assistant_allowed_entities", "lock.front_door"
    )
    ok, reason = ha.is_entity_allowed("lock.front_door", for_action=True)
    assert ok is False
    assert "hard_blocked_domain" in reason


def test_unknown_domain_rejected(ha_on):
    ok, reason = ha.is_entity_allowed("scene.evening", for_action=True)
    assert ok is False
    assert "domain_not_allowed" in reason


def test_action_only_allowed_on_light_or_switch(ha_on):
    ok, _ = ha.is_entity_allowed("sensor.living_temp", for_action=True)
    # Sensor is in allowlist + allowed domains, but turn_on/off can't apply.
    assert ok is False


def test_state_read_allowed_on_sensor(ha_on):
    ok, _ = ha.is_entity_allowed("sensor.living_temp", for_action=False)
    assert ok is True


def test_entity_not_in_allowlist_rejected(ha_on):
    ok, reason = ha.is_entity_allowed("light.bedroom", for_action=True)
    assert ok is False
    assert "entity_not_in_allowlist" in reason


# ─── happy paths ────────────────────────────────────────────────────────────


def test_get_status_calls_api_with_bearer_token(ha_on):
    captured = {}
    def fake_get(url, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        return _ok_get({"message": "API running.", "version": "2026.5.0"})
    with patch("integrations.home_assistant.httpx.get", side_effect=fake_get):
        info = ha.get_status(request_id="r-2")
    assert info["reachable"] is True
    assert info["version"] == "2026.5.0"
    # Token is sent in Authorization header — never in response, never in URL.
    assert captured["headers"]["Authorization"] == f"Bearer {_HA_TOKEN_CANARY}"
    assert _HA_TOKEN_CANARY not in captured["url"]
    assert _HA_TOKEN_CANARY not in repr(info)


def test_list_entities_filters_by_allowlist(ha_on):
    fake_states = [
        {"entity_id": "light.desk_light", "state": "on", "attributes": {"friendly_name": "Desk"}},
        {"entity_id": "light.bedroom", "state": "off", "attributes": {}},  # not in allowlist
        {"entity_id": "switch.fan", "state": "on", "attributes": {}},
        {"entity_id": "lock.front_door", "state": "locked", "attributes": {}},  # blocked
        {"entity_id": "scene.evening", "state": "on", "attributes": {}},  # wrong domain
    ]
    with patch("integrations.home_assistant.httpx.get", return_value=_ok_get(fake_states)):
        rows = ha.list_entities(request_id="r-3")
    ids = {r["entity_id"] for r in rows}
    assert ids == {"light.desk_light", "switch.fan"}


def test_turn_on_light_calls_correct_service(ha_on):
    captured = {}
    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _ok_post()
    with patch("integrations.home_assistant.httpx.post", side_effect=fake_post):
        msg = ha.turn_on(request_id="r-4", entity_id="light.desk_light")
    assert "OK" in msg
    assert captured["url"] == f"{_HA_URL}/api/services/light/turn_on"
    assert captured["json"] == {"entity_id": "light.desk_light"}
    assert captured["headers"]["Authorization"] == f"Bearer {_HA_TOKEN_CANARY}"


def test_turn_off_switch_calls_correct_service(ha_on):
    captured = {}
    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        return _ok_post()
    with patch("integrations.home_assistant.httpx.post", side_effect=fake_post):
        ha.turn_off(request_id="r-5", entity_id="switch.fan")
    assert captured["url"] == f"{_HA_URL}/api/services/switch/turn_off"


def test_read_state_calls_states_endpoint(ha_on):
    payload = {
        "entity_id": "sensor.living_temp",
        "state": "21.5",
        "attributes": {"unit_of_measurement": "°C"},
    }
    with patch("integrations.home_assistant.httpx.get", return_value=_ok_get(payload)):
        result = ha.read_state(request_id="r-6", entity_id="sensor.living_temp")
    assert result["state"] == "21.5"


def test_blocked_entity_raises_before_http_call(ha_on):
    with patch("integrations.home_assistant.httpx.post") as mock_post:
        with pytest.raises(ha.HAEntityBlocked):
            ha.turn_on(request_id="r-7", entity_id="lock.front_door")
    mock_post.assert_not_called()


def test_token_never_appears_in_audit(ha_on, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "audit_log_dir", str(tmp_path))
    with patch("integrations.home_assistant.httpx.get", return_value=_ok_get({"version": "x"})):
        ha.get_status(request_id="r-8")
    for f in Path(tmp_path).glob("audit-*.jsonl"):
        body = f.read_text(encoding="utf-8")
        assert _HA_TOKEN_CANARY not in body


# ─── /ask handler entity-name resolution ────────────────────────────────────


def test_resolve_entity_from_phrase_finds_match(ha_on):
    eid = ha._resolve_entity_from_phrase("desk light", for_action=True)
    assert eid == "light.desk_light"


def test_resolve_entity_from_phrase_returns_none_for_unknown(ha_on):
    assert ha._resolve_entity_from_phrase("garage door", for_action=True) is None


def test_resolve_entity_from_phrase_skips_non_action_domain(ha_on):
    # sensor.living_temp is allowed for reads only. The phrase "living temp"
    # should not resolve when for_action=True.
    assert ha._resolve_entity_from_phrase("living temp", for_action=True) is None
