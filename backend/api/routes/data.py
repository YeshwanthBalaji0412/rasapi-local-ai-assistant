"""
Phase 12 — /data/* routes.

  GET /data/sources               → list every registered DataSource + health.
  GET /data/{source_name}         → fetch data with the source's default key.
  GET /data/{source_name}/{key}   → fetch data for the given key.

The registry is consulted at request time; unknown names return 404. The
same envelope shape is returned by every source, so the UI can render
`data`, `warnings`, and staleness uniformly.

Auth posture: gated by `require_auth_for_ask` — same policy as /ask. A
dedicated AUTH_PROTECT_DATA flag can be added if the operator needs
differentiated posture later.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

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


@router.get(
    "/{source_name}",
    dependencies=[Depends(auth_module.require_auth_for_ask)],
)
async def fetch_default(source_name: str) -> dict:
    return await _fetch(source_name, "")


@router.get(
    "/{source_name}/{key:path}",
    dependencies=[Depends(auth_module.require_auth_for_ask)],
)
async def fetch_keyed(source_name: str, key: str) -> dict:
    return await _fetch(source_name, key)


async def _fetch(source_name: str, key: str) -> dict:
    registry = get_registry()
    source = registry.get(source_name)
    if source is None:
        raise HTTPException(status_code=404, detail=f"unknown source: {source_name!r}")

    envelope = await source.fetch(key)
    registry.record_fetch(source_name, ok=envelope.data is not None)
    return envelope.to_dict()
