import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from security.sensitive_data import is_sensitive


def test_password_phrase_is_blocked():
    blocked, reason = is_sensitive("my password is hunter2")
    assert blocked is True
    assert reason == "password"


def test_api_key_phrase_is_blocked():
    blocked, reason = is_sensitive("api key is sk-AaBbCcDdEeFfGgHhIiJjKkLl")
    assert blocked is True
    assert reason in {"api_key", "token"}


def test_ssn_pattern_is_blocked():
    blocked, reason = is_sensitive("my number is 123-45-6789")
    assert blocked is True
    assert reason == "ssn"


def test_credit_card_pattern_is_blocked():
    blocked, reason = is_sensitive("card 4111 1111 1111 1111 expires soon")
    assert blocked is True
    assert reason == "credit_card"


def test_private_key_marker_is_blocked():
    blocked, reason = is_sensitive("-----BEGIN PRIVATE KEY-----\nABCDEF")
    assert blocked is True
    assert reason == "private_key"


def test_jwt_pattern_is_blocked():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0LWlkIn0.SflKxwRJSMeKKF0EkXtNKQ"
    blocked, reason = is_sensitive(f"token: {jwt}")
    assert blocked is True


def test_benign_text_is_allowed():
    blocked, reason = is_sensitive("my portfolio domain is yeshwanthbalaji.com")
    assert blocked is False
    assert reason is None


def test_empty_text_is_allowed():
    blocked, reason = is_sensitive("")
    assert blocked is False
