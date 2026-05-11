"""
Voice-only response shortener (Phase 11).

The voice path is the only place this runs. /ask, /dashboard, and the
briefing REST endpoints still return the full briefing — TTS is the only
consumer that needs a shorter payload, and shortening here keeps the
briefing module unaware of voice concerns.

Pure functions: no I/O, no side effects, easy to unit-test.
"""

from __future__ import annotations

import re
from typing import Iterable

from briefing.formatter import IMMIGRATION_DISCLAIMER, _HEADER_LABELS


_KNOWN_HEADERS: frozenset[str] = frozenset(_HEADER_LABELS.values())

_ITEM_LINE = re.compile(r"^\s{2}(-\s+)?")


def _is_header(line: str) -> bool:
    return line.strip() in _KNOWN_HEADERS


def _is_item(line: str) -> bool:
    return bool(_ITEM_LINE.match(line))


def _truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    cut = text[:max_chars].rstrip()
    last_period = cut.rfind(". ")
    if last_period >= max_chars * 0.6:
        cut = cut[: last_period + 1]
    return cut.rstrip() + " …"


def shorten_briefing(text: str, *, items_per_category: int, max_chars: int) -> str:
    """Reduce a daily-briefing string to a voice-friendly summary.

    Keeps the intro line, each category header, up to `items_per_category`
    items under each header, and the immigration disclaimer when present.
    Then caps the result at `max_chars`.
    """
    lines = text.splitlines()
    if not lines:
        return text

    output: list[str] = []
    disclaimer_lines: list[str] = []
    current_header: str | None = None
    items_kept_for_current: int = 0
    in_disclaimer = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith(IMMIGRATION_DISCLAIMER[:40]):
            in_disclaimer = True

        if in_disclaimer:
            disclaimer_lines.append(line)
            continue

        if _is_header(line):
            current_header = stripped
            items_kept_for_current = 0
            output.append(line)
            continue

        if current_header is not None and _is_item(line):
            if items_kept_for_current < items_per_category:
                output.append(line)
                items_kept_for_current += 1
            continue

        output.append(line)

    if disclaimer_lines:
        if output and output[-1].strip() != "":
            output.append("")
        output.extend(disclaimer_lines)

    shortened = "\n".join(output).strip()
    return _truncate(shortened, max_chars)


def maybe_shorten_for_voice(
    *,
    intent: str,
    response: str,
    max_spoken_chars: int,
    briefing_items_per_category: int,
) -> str:
    """Entry point called from the voice session.

    For the daily_briefing intent, run the structured shortener. For any
    other intent, just hard-cap the length so an unexpectedly long fallback
    can't hang the TTS engine.
    """
    if not response:
        return response

    if intent == "daily_briefing":
        return shorten_briefing(
            response,
            items_per_category=max(0, briefing_items_per_category),
            max_chars=max(0, max_spoken_chars),
        )

    return _truncate(response, max_spoken_chars)
