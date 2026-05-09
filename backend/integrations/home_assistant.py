"""
Home Assistant integration via REST API + long-lived access token (Phase 9).

Two-layer allowlist before any HA call:
  1. Domain check — entity domain must be in HOME_ASSISTANT_ALLOWED_DOMAINS
     and not in HARD_BLOCK_DOMAINS (always rejected).
  2. Entity-id check — when HOME_ASSISTANT_ALLOWED_ENTITIES is non-empty,
     the entity_id must appear there. When empty, any entity in an
     allowed domain is accepted.

The bearer token is read from settings.home_assistant_token and is sent
ONLY in the Authorization header to the configured HA URL. It never
appears in API responses, audit log entries, or dashboard HTML.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from config import settings
from security.audit_log import audit_logger


logger = logging.getLogger(__name__)


_TIMEOUT_SECONDS = 10


# Domains that are always rejected even if listed in
# HOME_ASSISTANT_ALLOWED_ENTITIES. Operator cannot override this.
HARD_BLOCK_DOMAINS: frozenset[str] = frozenset({
    "lock",
    "alarm_control_panel",
    "cover",
    "camera",
    "device_tracker",
    "person",
})

# Methods supported by RasaPi for write actions in Phase 9.
_ACTION_DOMAINS: frozenset[str] = frozenset({"light", "switch"})


# ─── exceptions ─────────────────────────────────────────────────────────────


class HAError(Exception):
    """Home Assistant call failed."""


class HANotConfigured(HAError):
    """Integration is disabled or URL/token is missing."""


class HAEntityBlocked(HAError):
    """Entity is in a hard-blocked domain or not on the operator allowlist."""


class HAUnknownEntity(HAError):
    """Entity not present in HA or filtered by allowlist."""


class HAHttpError(HAError):
    """HA returned a non-2xx response, or the request timed out."""


# ─── public surface ─────────────────────────────────────────────────────────


def is_enabled() -> bool:
    return bool(settings.enable_home_assistant)


def is_configured() -> bool:
    return is_enabled() and bool(
        settings.home_assistant_url.strip()
        and settings.home_assistant_token.strip()
    )


def allowed_domains() -> set[str]:
    raw = settings.home_assistant_allowed_domains or ""
    return {d.strip() for d in raw.split(",") if d.strip()}


def allowed_entities() -> set[str]:
    raw = settings.home_assistant_allowed_entities or ""
    return {e.strip() for e in raw.split(",") if e.strip()}


def safe_status() -> dict[str, Any]:
    """Snapshot for the registry/dashboard. No URL, no token."""
    return {
        "enabled": is_enabled(),
        "configured": is_configured(),
        "allowed_domains": sorted(allowed_domains()),
        "allowed_entity_count": len(allowed_entities()),
        "hard_blocked_domains": sorted(HARD_BLOCK_DOMAINS),
        "require_confirmation": settings.home_assistant_require_confirmation,
    }


def is_entity_allowed(entity_id: str, *, for_action: bool = False) -> tuple[bool, str | None]:
    """
    Returns (allowed, reason). reason is None when allowed.
    Use for_action=True for turn_on/turn_off — that further restricts
    to the {light, switch} domains.
    """
    if not entity_id or "." not in entity_id:
        return (False, "malformed_entity_id")
    domain = entity_id.split(".", 1)[0]

    if domain in HARD_BLOCK_DOMAINS:
        return (False, f"hard_blocked_domain:{domain}")

    domains = allowed_domains()
    if domain not in domains:
        return (False, f"domain_not_allowed:{domain}")

    if for_action and domain not in _ACTION_DOMAINS:
        return (False, f"domain_not_actionable:{domain}")

    entities = allowed_entities()
    if entities and entity_id not in entities:
        return (False, "entity_not_in_allowlist")

    return (True, None)


# ─── HTTP wrappers ──────────────────────────────────────────────────────────


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.home_assistant_token}",
        "Content-Type": "application/json",
    }


def _ensure_configured(request_id: str, event_type: str) -> None:
    if not is_configured():
        audit_logger.log_integration_event(
            request_id=request_id,
            event_type=event_type,
            outcome="error",
            integration="home_assistant",
            reason="not_configured",
        )
        raise HANotConfigured(
            "Home Assistant is not enabled or URL/token is empty."
        )


def _http_get(path: str, *, request_id: str, event_type: str) -> dict[str, Any] | list[Any]:
    url = settings.home_assistant_url.rstrip("/") + path
    try:
        response = httpx.get(url, headers=_headers(), timeout=_TIMEOUT_SECONDS)
    except httpx.TimeoutException as exc:
        audit_logger.log_integration_event(
            request_id=request_id,
            event_type=event_type,
            outcome="error",
            integration="home_assistant",
            reason="timeout",
        )
        raise HAHttpError("Home Assistant request timed out") from exc
    except httpx.RequestError as exc:
        audit_logger.log_integration_event(
            request_id=request_id,
            event_type=event_type,
            outcome="error",
            integration="home_assistant",
            reason="connection_error",
        )
        raise HAHttpError("Home Assistant request failed") from exc

    if response.status_code == 404:
        raise HAUnknownEntity(f"Home Assistant returned 404 for {path}")
    if response.status_code >= 400:
        audit_logger.log_integration_event(
            request_id=request_id,
            event_type=event_type,
            outcome="error",
            integration="home_assistant",
            reason=f"http_{response.status_code}",
        )
        raise HAHttpError(f"Home Assistant returned HTTP {response.status_code}")

    try:
        return response.json()
    except ValueError as exc:
        raise HAHttpError("Home Assistant returned non-JSON response") from exc


def _http_post(path: str, *, json_body: dict, request_id: str, event_type: str) -> Any:
    url = settings.home_assistant_url.rstrip("/") + path
    try:
        response = httpx.post(
            url, headers=_headers(), json=json_body, timeout=_TIMEOUT_SECONDS
        )
    except httpx.TimeoutException as exc:
        audit_logger.log_integration_event(
            request_id=request_id,
            event_type=event_type,
            outcome="error",
            integration="home_assistant",
            reason="timeout",
        )
        raise HAHttpError("Home Assistant request timed out") from exc
    except httpx.RequestError as exc:
        audit_logger.log_integration_event(
            request_id=request_id,
            event_type=event_type,
            outcome="error",
            integration="home_assistant",
            reason="connection_error",
        )
        raise HAHttpError("Home Assistant request failed") from exc

    if response.status_code >= 400:
        audit_logger.log_integration_event(
            request_id=request_id,
            event_type=event_type,
            outcome="error",
            integration="home_assistant",
            reason=f"http_{response.status_code}",
        )
        raise HAHttpError(f"Home Assistant returned HTTP {response.status_code}")

    try:
        return response.json()
    except ValueError:
        return None


# ─── operations ─────────────────────────────────────────────────────────────


def get_status(*, request_id: str) -> dict[str, Any]:
    """Verify HA reachability. Returns {reachable, version}."""
    _ensure_configured(request_id, "home_assistant_status_checked")
    data = _http_get("/api/", request_id=request_id, event_type="home_assistant_status_checked")
    if not isinstance(data, dict):
        raise HAHttpError("Home Assistant returned an unexpected payload shape")
    audit_logger.log_integration_event(
        request_id=request_id,
        event_type="home_assistant_status_checked",
        outcome="success",
        integration="home_assistant",
    )
    return {
        "reachable": True,
        "message": data.get("message", ""),
        "version": data.get("version", ""),
    }


def list_entities(*, request_id: str) -> list[dict[str, Any]]:
    """Return only entities in allowed_domains AND (allowed_entities or empty)."""
    _ensure_configured(request_id, "home_assistant_entity_listed")
    data = _http_get(
        "/api/states", request_id=request_id, event_type="home_assistant_entity_listed"
    )
    if not isinstance(data, list):
        raise HAHttpError("Home Assistant /api/states did not return a list")

    out: list[dict[str, Any]] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        entity_id = row.get("entity_id", "")
        ok, _ = is_entity_allowed(entity_id, for_action=False)
        if not ok:
            continue
        attrs = row.get("attributes") or {}
        out.append(
            {
                "entity_id": entity_id,
                "state": row.get("state"),
                "friendly_name": attrs.get("friendly_name", ""),
                "domain": entity_id.split(".", 1)[0],
            }
        )

    audit_logger.log_integration_event(
        request_id=request_id,
        event_type="home_assistant_entity_listed",
        outcome="success",
        integration="home_assistant",
    )
    return out


def read_state(*, request_id: str, entity_id: str) -> dict[str, Any]:
    _ensure_configured(request_id, "home_assistant_state_read")
    ok, reason = is_entity_allowed(entity_id, for_action=False)
    if not ok:
        audit_logger.log_integration_event(
            request_id=request_id,
            event_type="home_assistant_action_blocked",
            outcome="blocked",
            integration="home_assistant",
            target=entity_id,
            reason=reason,
        )
        raise HAEntityBlocked(reason or "blocked")

    try:
        data = _http_get(
            f"/api/states/{entity_id}",
            request_id=request_id,
            event_type="home_assistant_state_read",
        )
    except HAUnknownEntity:
        audit_logger.log_integration_event(
            request_id=request_id,
            event_type="home_assistant_state_read",
            outcome="error",
            integration="home_assistant",
            target=entity_id,
            reason="not_found",
        )
        raise

    audit_logger.log_integration_event(
        request_id=request_id,
        event_type="home_assistant_state_read",
        outcome="success",
        integration="home_assistant",
        target=entity_id,
    )
    if not isinstance(data, dict):
        raise HAHttpError("Home Assistant state response was not an object")
    return {
        "entity_id": data.get("entity_id"),
        "state": data.get("state"),
        "attributes": data.get("attributes") or {},
    }


def _service_call(action: str, *, request_id: str, entity_id: str) -> str:
    """Internal: turn_on / turn_off shared path."""
    _ensure_configured(request_id, "home_assistant_action_requested")
    ok, reason = is_entity_allowed(entity_id, for_action=True)
    if not ok:
        audit_logger.log_integration_event(
            request_id=request_id,
            event_type="home_assistant_action_blocked",
            outcome="blocked",
            integration="home_assistant",
            target=entity_id,
            reason=reason,
        )
        raise HAEntityBlocked(reason or "blocked")

    audit_logger.log_integration_event(
        request_id=request_id,
        event_type="home_assistant_action_requested",
        outcome="started",
        integration="home_assistant",
        target=entity_id,
        reason=action,
    )

    domain = entity_id.split(".", 1)[0]
    _http_post(
        f"/api/services/{domain}/{action}",
        json_body={"entity_id": entity_id},
        request_id=request_id,
        event_type="home_assistant_action_requested",
    )

    audit_logger.log_integration_event(
        request_id=request_id,
        event_type="home_assistant_action_completed",
        outcome="success",
        integration="home_assistant",
        target=entity_id,
        reason=action,
    )
    return f"OK — {action.replace('_', ' ')} on {entity_id}."


def turn_on(*, request_id: str, entity_id: str) -> str:
    return _service_call("turn_on", request_id=request_id, entity_id=entity_id)


def turn_off(*, request_id: str, entity_id: str) -> str:
    return _service_call("turn_off", request_id=request_id, entity_id=entity_id)


# ─── /ask handlers ──────────────────────────────────────────────────────────


def _resolve_entity_from_phrase(phrase: str, *, for_action: bool) -> str | None:
    """
    Map a spoken/typed name to an entity_id from the allowlist.
    "desk light" → "light.desk_light" iff allowed.

    Resolution rules:
      - normalize to lowercase, strip, replace spaces with underscores
      - search HOME_ASSISTANT_ALLOWED_ENTITIES for one whose last segment
        matches the normalized phrase exactly
      - for_action=True restricts to {light, switch}
    """
    norm = phrase.strip().lower().replace(" ", "_")
    if not norm:
        return None
    for entity_id in allowed_entities():
        if "." not in entity_id:
            continue
        domain, last = entity_id.split(".", 1)
        if for_action and domain not in _ACTION_DOMAINS:
            continue
        if last == norm:
            ok, _ = is_entity_allowed(entity_id, for_action=for_action)
            if ok:
                return entity_id
    return None


def handle_ha_status(query: str, request_id: str) -> str:
    if not is_configured():
        return "Home Assistant is not enabled or URL/token is empty."
    try:
        info = get_status(request_id=request_id)
        version = info.get("version", "")
        return f"Home Assistant is reachable (version {version})." if version else "Home Assistant is reachable."
    except HAError as exc:
        return f"Home Assistant check failed: {exc}"


def _ha_action_handler(query: str, request_id: str, *, action: str) -> str:
    if not is_configured():
        return "Home Assistant is not enabled or URL/token is empty."
    prefix_options = (
        f"{action.replace('_', ' ')} ",  # e.g. "turn on "
    )
    rest = ""
    lower = query.lower()
    for prefix in prefix_options:
        idx = lower.find(prefix)
        if idx != -1:
            rest = query[idx + len(prefix):].strip()
            break
    if not rest:
        return "Tell me which device — for example 'turn on desk light'."

    entity_id = _resolve_entity_from_phrase(rest, for_action=True)
    if entity_id is None:
        return f"I don't have a smart-home device named '{rest}'."

    try:
        if action == "turn_on":
            return turn_on(request_id=request_id, entity_id=entity_id)
        return turn_off(request_id=request_id, entity_id=entity_id)
    except HAEntityBlocked as exc:
        return f"That device is blocked by the safety allowlist ({exc})."
    except HAError as exc:
        return f"Home Assistant action failed: {exc}"


def handle_ha_turn_on(query: str, request_id: str) -> str:
    return _ha_action_handler(query, request_id, action="turn_on")


def handle_ha_turn_off(query: str, request_id: str) -> str:
    return _ha_action_handler(query, request_id, action="turn_off")
