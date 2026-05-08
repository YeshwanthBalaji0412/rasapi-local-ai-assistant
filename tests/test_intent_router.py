import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from core.intent_router import route, list_intents


def test_greeting_intent_no_command():
    result = route("hello there", request_id="test-1")
    assert result.intent == "greeting"
    assert "RasaPi" in result.response


def test_help_intent_lists_capabilities():
    result = route("what can you do?", request_id="test-2")
    assert result.intent == "help"
    assert "current date and time" in result.response.lower() or "time" in result.response.lower()


def test_time_intent_runs_date_command():
    result = route("what time is it", request_id="test-3")
    assert result.intent == "time"
    # `date` is available on macOS and Pi — output is non-empty
    assert len(result.response) > 0


def test_unknown_query_returns_fallback():
    result = route("write a poem about ducks", request_id="test-4")
    assert result.intent == "fallback"
    assert "phase 2" in result.response.lower()


def test_disk_intent_routes_to_df():
    result = route("how much disk space do I have", request_id="test-5")
    assert result.intent == "disk"


def test_case_insensitive_matching():
    result = route("HELLO", request_id="test-6")
    assert result.intent == "greeting"


def test_list_intents_excludes_fallback():
    intents = list_intents()
    names = [i["name"] for i in intents]
    assert "fallback" not in names
    assert "time" in names
    assert "help" in names


def test_list_intents_has_required_fields():
    intents = list_intents()
    for i in intents:
        assert "name" in i and "description" in i and "keywords" in i
        assert isinstance(i["keywords"], list)
