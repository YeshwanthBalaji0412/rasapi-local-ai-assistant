"""
Briefing formatters (Phase 4).

Converts stored items into plain-text strings for /ask, and raw dicts for
the JSON REST endpoints. The immigration disclaimer is hardcoded here.
"""

from typing import Any


IMMIGRATION_DISCLAIMER = (
    "These are official-source updates only, not legal advice. Verify with "
    "USCIS, your school OGS, or a qualified immigration advisor."
)


_HEADER_LABELS = {
    "world_news": "WORLD NEWS",
    "ai_news": "AI NEWS",
    "tech_news": "TECH NEWS",
    "developer_news": "DEVELOPER NEWS",
    "boston_weather": "WEATHER",
    "immigration_updates": "IMMIGRATION UPDATES",
    "personalized_action_items": "PERSONALIZED",
}


_DISPLAY_ORDER = (
    "world_news",
    "ai_news",
    "tech_news",
    "developer_news",
    "boston_weather",
    "immigration_updates",
)


def format_daily_briefing(
    items_by_category: dict[str, list[dict[str, Any]]],
    *,
    leading_summary: str | None = None,
) -> str:
    if not any(items_by_category.values()):
        return (
            "No briefing items yet. Run POST /briefing/refresh to populate, "
            "or try again in a moment."
        )

    lines: list[str] = ["Here is your daily briefing:"]

    if leading_summary:
        lines.append("")
        lines.append(leading_summary.strip())

    has_immigration = False

    for category in _DISPLAY_ORDER:
        items = items_by_category.get(category) or []
        if not items:
            continue
        lines.append("")
        lines.append(_HEADER_LABELS.get(category, category.upper()))
        for it in items:
            if category == "boston_weather":
                lines.append(f"  {it['title']}")
            else:
                lines.append(f"  - {it['title']} ({it['source_name']})")
        if category == "immigration_updates":
            has_immigration = True

    if has_immigration:
        lines.append("")
        lines.append(IMMIGRATION_DISCLAIMER)

    return "\n".join(lines).strip()


def format_category_briefing(category: str, items: list[dict[str, Any]]) -> str:
    if not items:
        return f"No items in '{category}' yet. Run POST /briefing/refresh."

    header = _HEADER_LABELS.get(category, category.upper())
    lines = [f"{header}:"]
    for it in items:
        lines.append(f"  - {it['title']} ({it['source_name']})")

    if category == "immigration_updates":
        lines.append("")
        lines.append(IMMIGRATION_DISCLAIMER)

    return "\n".join(lines)
