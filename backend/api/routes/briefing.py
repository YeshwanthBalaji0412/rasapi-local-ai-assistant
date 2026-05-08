"""
Direct REST endpoints for the daily briefing (Phase 4).

These share the same generator / formatter as the conversational /ask
path. Sensitive-data check does not apply (no user input is stored);
sources are hardcoded and outputs are public-by-source-of-truth.
"""

import uuid

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel

from briefing import generator, sources
from briefing.formatter import (
    IMMIGRATION_DISCLAIMER,
    format_category_briefing,
    format_daily_briefing,
)


router = APIRouter(prefix="/briefing", tags=["briefing"])


class SourceEntry(BaseModel):
    name: str
    category: str
    kind: str
    url: str | None


class SourcesResponse(BaseModel):
    sources: list[SourceEntry]
    categories: list[str]


class RefreshResponse(BaseModel):
    run_id: int
    item_count: int
    status: str
    errors: list[dict]


class BriefingItem(BaseModel):
    id: int
    category: str
    source_name: str
    title: str
    url: str | None
    published_at: str | None
    fetched_at: str
    summary: str | None


class CategoryBriefingResponse(BaseModel):
    category: str
    items: list[BriefingItem]
    text: str
    disclaimer: str | None = None


class DailyBriefingResponse(BaseModel):
    text: str
    items_by_category: dict[str, list[BriefingItem]]
    disclaimer: str | None = None


@router.get("/sources", response_model=SourcesResponse)
def get_sources() -> SourcesResponse:
    return SourcesResponse(
        sources=[SourceEntry(**s) for s in sources.list_sources_safe()],
        categories=list(sources.CATEGORIES),
    )


@router.post("/refresh", response_model=RefreshResponse)
def post_refresh() -> RefreshResponse:
    request_id = f"rest-{uuid.uuid4()}"
    result = generator.refresh_briefing(request_id=request_id)
    return RefreshResponse(**result)


@router.get("/daily", response_model=DailyBriefingResponse)
def get_daily() -> DailyBriefingResponse:
    request_id = f"rest-{uuid.uuid4()}"
    if not generator._has_fresh_run(briefing_type="daily"):
        generator.refresh_briefing(request_id=request_id, briefing_type="daily")

    grouped = generator.get_recent_items_grouped(request_id=request_id)
    text = format_daily_briefing(grouped)

    has_immigration = bool(grouped.get("immigration_updates"))

    return DailyBriefingResponse(
        text=text,
        items_by_category={
            cat: [BriefingItem(**it) for it in items]
            for cat, items in grouped.items()
        },
        disclaimer=IMMIGRATION_DISCLAIMER if has_immigration else None,
    )


@router.get("/category/{category}", response_model=CategoryBriefingResponse)
def get_category(category: str = Path(..., min_length=1, max_length=64)) -> CategoryBriefingResponse:
    if not sources.is_valid_category(category):
        raise HTTPException(status_code=400, detail=f"Unknown category '{category}'.")

    request_id = f"rest-{uuid.uuid4()}"
    items = generator.get_recent_items(
        request_id=request_id, category=category, limit=50
    )
    text = format_category_briefing(category, items)

    return CategoryBriefingResponse(
        category=category,
        items=[BriefingItem(**it) for it in items],
        text=text,
        disclaimer=IMMIGRATION_DISCLAIMER if category == "immigration_updates" else None,
    )


@router.get("", response_model=DailyBriefingResponse)
def get_briefing_root() -> DailyBriefingResponse:
    """Alias for /briefing/daily."""
    return get_daily()
