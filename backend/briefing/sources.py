"""
Briefing source registry (Phase 4).

Sources are hardcoded in version-controlled Python — never read from a
config file or env, and never overridable at runtime. URLs change,
sources go away; updating this file is intentional and reviewable.

Categories:
  - world_news, ai_news, tech_news, developer_news
  - boston_weather (single non-RSS source)
  - immigration_updates (USCIS only; legal disclaimer required)
  - personalized_action_items (placeholder, intentionally empty in Phase 4)

`personalized_action_items` is reserved as a future hook. Populating it
from the user's local memory/tasks/notes would require a deliberate
security decision later — see docs/security-model.md.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    name: str
    category: str
    kind: str  # 'rss' | 'weather' | 'placeholder'
    url: str | None = None


CATEGORIES: tuple[str, ...] = (
    "world_news",
    "ai_news",
    "tech_news",
    "developer_news",
    "boston_weather",
    "immigration_updates",
    "personalized_action_items",
)


SOURCES: tuple[Source, ...] = (
    # ── world ─────────────────────────────────────────────────────────────
    Source("BBC World", "world_news", "rss", "http://feeds.bbci.co.uk/news/world/rss.xml"),
    Source("NPR Top Stories", "world_news", "rss", "https://feeds.npr.org/1001/rss.xml"),
    # ── AI ────────────────────────────────────────────────────────────────
    Source("Hugging Face Blog", "ai_news", "rss", "https://huggingface.co/blog/feed.xml"),
    Source("Google AI Blog", "ai_news", "rss", "https://blog.google/technology/ai/rss/"),
    # ── tech ──────────────────────────────────────────────────────────────
    Source("Ars Technica", "tech_news", "rss", "https://feeds.arstechnica.com/arstechnica/index"),
    Source("The Verge", "tech_news", "rss", "https://www.theverge.com/rss/index.xml"),
    # ── developer ─────────────────────────────────────────────────────────
    Source("Hacker News", "developer_news", "rss", "https://hnrss.org/frontpage"),
    # ── weather (Open-Meteo, no API key) ──────────────────────────────────
    Source("Open-Meteo (Boston)", "boston_weather", "weather", None),
    # ── immigration (official sources only) ───────────────────────────────
    Source("USCIS News", "immigration_updates", "rss",
           "https://www.uscis.gov/news/rss-feed/news-releases/feed"),
    # ── reserved ──────────────────────────────────────────────────────────
    Source("Personalized (reserved)", "personalized_action_items", "placeholder", None),
)


def list_sources_safe() -> list[dict]:
    """Public-facing source listing for /briefing/sources."""
    return [
        {"name": s.name, "category": s.category, "kind": s.kind, "url": s.url}
        for s in SOURCES
    ]


def is_valid_category(category: str) -> bool:
    return category in CATEGORIES
