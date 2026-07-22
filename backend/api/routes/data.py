"""
Phase 12 — /data/* routes.

  GET /data/sources           → list every registered DataSource + its health.
                                Reads the module-level SourceRegistry; makes
                                no upstream calls itself.

Later gates mount per-source endpoints (weather, market, news, ...). This
file stays the single mount point for the /data/* prefix.

Auth posture: gated by `require_auth_for_ask` — same policy as /ask. If a
future need arises for a distinct AUTH_PROTECT_DATA flag, add it in
backend/config.py and swap the dependency here. Not warranted at Gate 1.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from data_sources.registry import get_registry
from security import auth as auth_module

router = APIRouter(prefix="/data", tags=["data"])


@router.get(
    "/sources",
    dependencies=[Depends(auth_module.require_auth_for_ask)],
)
async def list_sources() -> dict:
    """Registered sources with health snapshots. Never leaks payloads or keys."""
    registry = get_registry()
    return {
        "sources": [h.to_dict() for h in registry.all_health()],
        "count": len(registry.names()),
    }
