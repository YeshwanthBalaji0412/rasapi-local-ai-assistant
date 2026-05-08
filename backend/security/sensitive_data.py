"""
Sensitive-data detector (Phase 3).

This is a *practical* safety layer, not a perfect data-loss-prevention system.
It catches obvious patterns that should never be persisted as a casual memory
or note: passwords, API keys, tokens, private keys, SSNs, credit-card-shaped
numbers, and a few well-known phrases.

Limitations (by design):
  - No Luhn validation on card numbers — false positives possible on long
    digit runs, false negatives on obfuscated numbers.
  - No entropy-based secret detection.
  - English-only phrase matching.
  - Catches "my password is hunter2" but not "the secret recipe is salt".

If a write reaches this detector, the user has typed something the assistant
should refuse to store. Better to occasionally over-block than to ever
accidentally persist a credential.
"""

import re


# Phrases that strongly suggest a secret is about to be stated.
# The check is substring-in-lowered-text, so these match flexibly.
_PHRASE_PATTERNS: list[tuple[str, str]] = [
    ("password", "my password is"),
    ("password", "password is "),
    ("password", "password: "),
    ("password", "passwd:"),
    ("password", "my pin is"),
    ("api_key", "api key is"),
    ("api_key", "api_key="),
    ("api_key", "api-key:"),
    ("api_key", "apikey:"),
    ("token", "access token is"),
    ("token", "bearer token"),
    ("token", "secret token"),
    ("token", "auth token"),
    ("secret", "the secret is"),
    ("secret", "client secret"),
    ("private_key", "-----begin"),
    ("private_key", "private key:"),
    ("passport", "passport number"),
    ("passport", "my passport is"),
]


# Regex patterns. Compiled once.
_REGEX_PATTERNS: list[tuple[str, re.Pattern]] = [
    # US SSN: 3-2-4 with hyphens (the canonical format).
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    # Credit-card-shaped: 13–19 digits with optional spaces or dashes.
    # Loose on purpose; spec says practical, not perfect.
    ("credit_card", re.compile(r"\b(?:\d[ -]?){12,18}\d\b")),
    # OpenAI / Anthropic / GitHub-style key prefixes.
    ("api_key", re.compile(r"\b(sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|xoxb-[A-Za-z0-9-]{20,})\b")),
    # AWS access key ID shape.
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    # JWT-shaped tokens: three base64url segments separated by dots.
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
]


def is_sensitive(text: str) -> tuple[bool, str | None]:
    """
    Return (True, pattern_name) if `text` looks like it contains a secret,
    otherwise (False, None). The pattern name is suitable for audit logging
    and is not the matched content.
    """
    if not text:
        return (False, None)

    lowered = text.lower()
    for label, phrase in _PHRASE_PATTERNS:
        if phrase in lowered:
            return (True, label)

    for label, pattern in _REGEX_PATTERNS:
        if pattern.search(text):
            return (True, label)

    return (False, None)


REJECTION_MESSAGE = (
    "I can't save sensitive information like passwords, API keys, tokens, "
    "or financial identifiers."
)
