import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import httpx
import pytest

from config import settings
from integrations import slack


_WEBHOOK_CANARY = "https://hooks.slack.com/services/T_CANARY/B_CANARY/SECRET-DO-NOT-LEAK"


@pytest.fixture
def slack_off(monkeypatch):
    monkeypatch.setattr(settings, "enable_slack", False)
    monkeypatch.setattr(settings, "slack_webhook_url", "")


@pytest.fixture
def slack_on(monkeypatch):
    monkeypatch.setattr(settings, "enable_slack", True)
    monkeypatch.setattr(settings, "slack_webhook_url", _WEBHOOK_CANARY)


def _ok_response() -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    return resp


def _err_response(code: int) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = code
    return resp


# ─── configuration sanity ───────────────────────────────────────────────────


def test_disabled_by_default(slack_off):
    assert slack.is_enabled() is False
    assert slack.is_configured() is False


def test_enabled_but_no_url_is_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "enable_slack", True)
    monkeypatch.setattr(settings, "slack_webhook_url", "")
    assert slack.is_configured() is False


# ─── send_test ──────────────────────────────────────────────────────────────


def test_send_test_raises_when_not_configured(slack_off):
    with pytest.raises(slack.SlackNotConfigured):
        slack.send_test(request_id="t-1")


def test_send_test_posts_expected_payload(slack_on):
    with patch("integrations.slack.httpx.post", return_value=_ok_response()) as mock_post:
        msg = slack.send_test(request_id="t-2")
    assert "sent" in msg.lower()
    args, kwargs = mock_post.call_args
    # URL is the configured webhook
    assert args[0] == _WEBHOOK_CANARY
    # Payload is JSON with a `text` field — and matches our test message.
    body = kwargs.get("json", {})
    assert "text" in body
    assert "RasaPi Slack integration test" in body["text"]


def test_send_test_translates_http_500_to_safe_error(slack_on):
    with patch("integrations.slack.httpx.post", return_value=_err_response(500)):
        with pytest.raises(slack.SlackHttpError):
            slack.send_test(request_id="t-3")


# ─── send_briefing ──────────────────────────────────────────────────────────


def test_send_briefing_uses_briefing_formatter(slack_on, monkeypatch):
    """The briefing path must produce the same text as the dashboard
    briefing — never raw LLM output."""
    monkeypatch.setattr(
        "integrations.slack.briefing_generator.get_recent_items_grouped",
        lambda *, request_id: {
            "world_news": [{"title": "Test world headline", "source_name": "BBC"}],
            "ai_news": [], "tech_news": [], "developer_news": [],
            "boston_weather": [], "immigration_updates": [], "personalized_action_items": [],
        },
    )
    captured: dict = {}
    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return _ok_response()
    with patch("integrations.slack.httpx.post", side_effect=fake_post):
        msg = slack.send_briefing(request_id="t-4")
    assert "briefing" in msg.lower()
    text = captured["json"]["text"]
    assert "Test world headline" in text
    assert "RasaPi briefing" in text


# ─── webhook URL is never logged ────────────────────────────────────────────


def test_webhook_url_never_appears_in_audit(slack_on, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "audit_log_dir", str(tmp_path))
    with patch("integrations.slack.httpx.post", return_value=_ok_response()):
        slack.send_test(request_id="t-5")
    # All written audit files
    for f in Path(tmp_path).glob("audit-*.jsonl"):
        body = f.read_text(encoding="utf-8")
        assert _WEBHOOK_CANARY not in body
        # Reason should be present for failed events but never the URL
        assert "hooks.slack.com" not in body
