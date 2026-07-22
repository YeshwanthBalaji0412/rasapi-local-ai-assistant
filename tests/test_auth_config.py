import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from config import settings
from security import auth as auth_module


def test_auth_disabled_by_default():
    assert settings.enable_auth is False


def test_auth_protect_flags_default_to_true():
    """When ENABLE_AUTH=true is flipped, the four AUTH_PROTECT_* flags
    default to true so the protection kicks in immediately."""
    assert settings.auth_protect_dashboard is True
    assert settings.auth_protect_ask is True
    assert settings.auth_protect_voice is True
    assert settings.auth_protect_mutations is True


def test_session_defaults():
    assert settings.session_cookie_name == "rasapi_session"
    assert settings.session_ttl_minutes == 720
    assert settings.cookie_secure is False
    assert settings.csrf_cookie_name == "rasapi_csrf"


def test_default_secret_is_placeholder():
    """The shipped default must NOT look like a real secret."""
    assert settings.api_secret_key in auth_module.PLACEHOLDER_KEYS
    assert auth_module._is_secret_configured() is False


def test_placeholder_set_covers_historical_variants():
    """Every placeholder string that has ever shipped in an env template must
    still be recognized. Removing entries here could silently accept a public
    string as a real secret after an upgrade."""
    required = {
        "",
        "change-me-before-use",
        "replace-with-output-of-generate-secret-sh",
        "replace-with-output-of-openssl-rand-hex-32",
    }
    assert required.issubset(auth_module.PLACEHOLDER_KEYS)


def test_auth_module_uses_compare_digest():
    """Constant-time comparison everywhere. Any `==` against api_secret_key
    would be a security regression."""
    from pathlib import Path
    src = Path(auth_module.__file__).read_text(encoding="utf-8")
    assert "compare_digest" in src
    # Reject naive equality of provided to the secret. We allow the
    # placeholder set membership check (`in _PLACEHOLDER_KEYS`) which is
    # testing strings, not the active secret.
    forbidden = "settings.api_secret_key =="
    assert forbidden not in src
    forbidden = "== settings.api_secret_key"
    assert forbidden not in src
