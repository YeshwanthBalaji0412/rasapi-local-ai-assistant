"""
Dashboard routes (Phase 5).

  - GET  /dashboard                       → server-rendered HTML
  - GET  /dashboard/health                → JSON health snapshot
  - GET  /dashboard/audit/recent          → JSON list of latest events
  - GET  /dashboard/security-events       → JSON list of security events
  - POST /dashboard/briefing/refresh      → triggers briefing.refresh, redirect
  - POST /dashboard/tasks/{id}/complete   → marks task done, redirect

Local-only by design. Bind the server to localhost in production.
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, Path as FPath, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from briefing import generator as briefing_generator
from core import tasks as tasks_service
from dashboard import service as dashboard_service
from security.audit_log import audit_logger


_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_class=HTMLResponse)
def get_dashboard(request: Request):
    request_id = f"dash-{uuid.uuid4()}"
    audit_logger.log_dashboard_event(
        request_id=request_id, event_type="dashboard_viewed"
    )
    view_model = dashboard_service.build_view_model()
    return templates.TemplateResponse(
        request=request, name="dashboard.html", context=view_model
    )


@router.get("/dashboard/health")
def get_dashboard_health():
    request_id = f"dash-{uuid.uuid4()}"
    audit_logger.log_dashboard_event(
        request_id=request_id, event_type="dashboard_health_viewed"
    )
    return dashboard_service.get_health()


@router.get("/dashboard/audit/recent")
def get_dashboard_audit(limit: int = 25):
    request_id = f"dash-{uuid.uuid4()}"
    audit_logger.log_dashboard_event(
        request_id=request_id, event_type="dashboard_audit_viewed"
    )
    return {"events": dashboard_service.get_audit_recent(limit=limit)}


@router.get("/dashboard/security-events")
def get_dashboard_security():
    request_id = f"dash-{uuid.uuid4()}"
    audit_logger.log_dashboard_event(
        request_id=request_id, event_type="dashboard_security_events_viewed"
    )
    return {"events": dashboard_service.get_security_events()}


@router.post("/dashboard/briefing/refresh")
def post_dashboard_briefing_refresh():
    request_id = f"dash-{uuid.uuid4()}"
    audit_logger.log_dashboard_event(
        request_id=request_id,
        event_type="dashboard_briefing_refresh_requested",
    )
    briefing_generator.refresh_briefing(request_id=request_id)
    return RedirectResponse(url="/dashboard", status_code=303)


@router.post("/dashboard/tasks/{task_id}/complete")
def post_dashboard_task_complete(task_id: int = FPath(..., ge=1)):
    request_id = f"dash-{uuid.uuid4()}"
    ok, msg = tasks_service.complete_task(task_id=task_id, request_id=request_id)
    audit_logger.log_dashboard_event(
        request_id=request_id,
        event_type="dashboard_task_completed",
        outcome="success" if ok else "error",
        reason=None if ok else msg,
    )
    return RedirectResponse(url="/dashboard", status_code=303)
