"""
Dashboard routes (Phase 5, extended in Phase 8).

  - GET  /dashboard                       → server-rendered HTML
  - GET  /dashboard/health                → JSON health snapshot (always public)
  - GET  /dashboard/audit/recent          → JSON list of latest events
  - GET  /dashboard/security-events       → JSON list of security events
  - POST /dashboard/briefing/refresh      → triggers briefing.refresh, redirect
  - POST /dashboard/tasks/{id}/complete   → marks task done, redirect

Phase 8 additions:
  - When ENABLE_AUTH=true and AUTH_PROTECT_DASHBOARD=true, GET requests
    redirect unauthenticated browsers to /login?next=<original-path>.
  - All dashboard form POSTs require a valid CSRF token (double-submit
    cookie pattern). When auth is off, CSRF is skipped to preserve the
    existing local workflow.
  - The dashboard renders a "Security" card showing flags only.
"""

import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Path as FPath, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from briefing import generator as briefing_generator
from config import settings
from core import tasks as tasks_service
from dashboard import service as dashboard_service
from security import auth as auth_module
from security.audit_log import audit_logger


_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


router = APIRouter(tags=["dashboard"])


def _login_redirect(request: Request) -> RedirectResponse:
    next_path = quote(request.url.path or "/dashboard", safe="/")
    return RedirectResponse(url=f"/login?next={next_path}", status_code=303)


def _check_dashboard_auth(request: Request) -> RedirectResponse | None:
    """Returns a redirect-to-login response if the browser must authenticate,
    else None."""
    if auth_module.is_dashboard_authenticated(request):
        return None
    request_id = auth_module._audit_id()
    audit_logger.log_auth_event(
        request_id=request_id,
        event_type="auth_required_missing",
        outcome="error",
        reason="dashboard_no_session",
    )
    return _login_redirect(request)


async def _check_csrf(request: Request) -> dict[str, str]:
    """Read the form body and validate the double-submit CSRF token.
    Raises 403 on mismatch (when auth is on). Returns the parsed form."""
    form = await auth_module.read_form(request)
    if not auth_module.verify_csrf(request, form):
        audit_logger.log_auth_event(
            request_id=auth_module._audit_id(),
            event_type="csrf_validation_failed",
            outcome="error",
            reason="csrf_mismatch",
        )
        raise HTTPException(status_code=403, detail="CSRF validation failed")
    return form


@router.get("/dashboard", response_class=HTMLResponse)
def get_dashboard(request: Request):
    redirect = _check_dashboard_auth(request)
    if redirect is not None:
        return redirect

    request_id = f"dash-{uuid.uuid4()}"
    audit_logger.log_dashboard_event(
        request_id=request_id, event_type="dashboard_viewed"
    )

    # Determine the CSRF token BEFORE rendering so it can go in the template.
    existing = request.cookies.get(settings.csrf_cookie_name)
    if existing and len(existing) >= 16:
        csrf_token = existing
        set_new_cookie = False
    else:
        csrf_token = auth_module.issue_csrf_token()
        set_new_cookie = True

    view_model = dashboard_service.build_view_model()
    view_model["csrf_token"] = csrf_token

    response = templates.TemplateResponse(
        request=request, name="dashboard.html", context=view_model
    )
    if set_new_cookie:
        response.set_cookie(
            key=settings.csrf_cookie_name,
            value=csrf_token,
            max_age=settings.session_ttl_minutes * 60,
            httponly=False,
            samesite="lax",
            secure=settings.cookie_secure,
            path="/",
        )
    return response


@router.get("/dashboard/health")
def get_dashboard_health():
    request_id = f"dash-{uuid.uuid4()}"
    audit_logger.log_dashboard_event(
        request_id=request_id, event_type="dashboard_health_viewed"
    )
    return dashboard_service.get_health()


@router.get("/dashboard/audit/recent")
def get_dashboard_audit(request: Request, limit: int = 25):
    if not auth_module.is_dashboard_authenticated(request):
        raise HTTPException(status_code=401, detail="auth required")
    request_id = f"dash-{uuid.uuid4()}"
    audit_logger.log_dashboard_event(
        request_id=request_id, event_type="dashboard_audit_viewed"
    )
    return {"events": dashboard_service.get_audit_recent(limit=limit)}


@router.get("/dashboard/security-events")
def get_dashboard_security(request: Request):
    if not auth_module.is_dashboard_authenticated(request):
        raise HTTPException(status_code=401, detail="auth required")
    request_id = f"dash-{uuid.uuid4()}"
    audit_logger.log_dashboard_event(
        request_id=request_id, event_type="dashboard_security_events_viewed"
    )
    return {"events": dashboard_service.get_security_events()}


@router.post("/dashboard/briefing/refresh")
async def post_dashboard_briefing_refresh(request: Request):
    redirect = _check_dashboard_auth(request)
    if redirect is not None:
        return redirect
    await _check_csrf(request)
    request_id = f"dash-{uuid.uuid4()}"
    audit_logger.log_dashboard_event(
        request_id=request_id,
        event_type="dashboard_briefing_refresh_requested",
    )
    briefing_generator.refresh_briefing(request_id=request_id)
    return RedirectResponse(url="/dashboard", status_code=303)


@router.post("/dashboard/tasks/{task_id}/complete")
async def post_dashboard_task_complete(
    request: Request, task_id: int = FPath(..., ge=1)
):
    redirect = _check_dashboard_auth(request)
    if redirect is not None:
        return redirect
    await _check_csrf(request)
    request_id = f"dash-{uuid.uuid4()}"
    ok, msg = tasks_service.complete_task(task_id=task_id, request_id=request_id)
    audit_logger.log_dashboard_event(
        request_id=request_id,
        event_type="dashboard_task_completed",
        outcome="success" if ok else "error",
        reason=None if ok else msg,
    )
    return RedirectResponse(url="/dashboard", status_code=303)
