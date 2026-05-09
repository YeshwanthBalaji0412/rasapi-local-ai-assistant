"""
Integration REST endpoints (Phase 9).

  GET  /integrations                                          → registry list
  GET  /integrations/status                                   → alias of above
  POST /integrations/slack/test                                → slack.send_test
  POST /integrations/slack/send-briefing                       → slack.send_briefing
  GET  /integrations/home-assistant/status                     → ha.get_status
  GET  /integrations/home-assistant/entities                   → ha.list_entities
  GET  /integrations/home-assistant/entities/{entity_id}/state → ha.read_state
  POST /integrations/home-assistant/entities/{id}/turn-on      → ha.turn_on
  POST /integrations/home-assistant/entities/{id}/turn-off     → ha.turn_off

When ENABLE_AUTH=true and AUTH_PROTECT_INTEGRATIONS=true, every endpoint
requires API key OR session cookie. Form-POST endpoints additionally
require a matching CSRF token when called via session cookie (browser
flow). API clients with X-RasaPi-Key skip CSRF — standard pattern.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, Request

from integrations import home_assistant as ha
from integrations import registry as integration_registry
from integrations import slack
from security import auth as auth_module
from security.audit_log import audit_logger


router = APIRouter(
    prefix="/integrations",
    tags=["integrations"],
    dependencies=[Depends(auth_module.require_auth_for_integrations)],
)


def _request_id() -> str:
    return f"intg-{uuid.uuid4()}"


async def _csrf_check(request: Request) -> None:
    form = await auth_module.read_form(request)
    if not auth_module.verify_csrf_for_api(request, form):
        audit_logger.log_auth_event(
            request_id=auth_module._audit_id(),
            event_type="csrf_validation_failed",
            outcome="error",
            reason="csrf_mismatch",
        )
        raise HTTPException(status_code=403, detail="CSRF validation failed")


# ─── registry ────────────────────────────────────────────────────────────────


@router.get("")
def list_integrations(request: Request):
    rid = _request_id()
    audit_logger.log_integration_event(
        request_id=rid, event_type="integration_status_viewed"
    )
    return {"integrations": integration_registry.to_safe_dicts()}


@router.get("/status")
def status(request: Request):
    return list_integrations(request)


# ─── Slack ───────────────────────────────────────────────────────────────────


@router.post("/slack/test")
async def slack_test(request: Request):
    await _csrf_check(request)
    rid = _request_id()
    try:
        message = slack.send_test(request_id=rid)
        return {"ok": True, "message": message}
    except slack.SlackNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except slack.SlackError as exc:
        raise HTTPException(status_code=502, detail=f"slack send failed: {exc}")


@router.post("/slack/send-briefing")
async def slack_briefing(request: Request, category: str | None = None):
    await _csrf_check(request)
    rid = _request_id()
    try:
        message = slack.send_briefing(request_id=rid, category=category)
        return {"ok": True, "message": message}
    except slack.SlackNotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except slack.SlackError as exc:
        raise HTTPException(status_code=502, detail=f"slack send failed: {exc}")


# ─── Home Assistant ──────────────────────────────────────────────────────────


@router.get("/home-assistant/status")
def ha_status():
    rid = _request_id()
    try:
        return ha.get_status(request_id=rid)
    except ha.HANotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ha.HAError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/home-assistant/entities")
def ha_list_entities():
    rid = _request_id()
    try:
        return {"entities": ha.list_entities(request_id=rid)}
    except ha.HANotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ha.HAError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/home-assistant/entities/{entity_id}/state")
def ha_state(entity_id: str = Path(..., min_length=1, max_length=200)):
    rid = _request_id()
    try:
        return ha.read_state(request_id=rid, entity_id=entity_id)
    except ha.HANotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ha.HAEntityBlocked as exc:
        raise HTTPException(status_code=400, detail=f"entity blocked: {exc}")
    except ha.HAUnknownEntity as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ha.HAError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/home-assistant/entities/{entity_id}/turn-on")
async def ha_turn_on(request: Request, entity_id: str = Path(..., min_length=1, max_length=200)):
    await _csrf_check(request)
    rid = _request_id()
    try:
        message = ha.turn_on(request_id=rid, entity_id=entity_id)
        return {"ok": True, "message": message}
    except ha.HANotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ha.HAEntityBlocked as exc:
        raise HTTPException(status_code=400, detail=f"entity blocked: {exc}")
    except ha.HAError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/home-assistant/entities/{entity_id}/turn-off")
async def ha_turn_off(request: Request, entity_id: str = Path(..., min_length=1, max_length=200)):
    await _csrf_check(request)
    rid = _request_id()
    try:
        message = ha.turn_off(request_id=rid, entity_id=entity_id)
        return {"ok": True, "message": message}
    except ha.HANotConfigured as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ha.HAEntityBlocked as exc:
        raise HTTPException(status_code=400, detail=f"entity blocked: {exc}")
    except ha.HAError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
