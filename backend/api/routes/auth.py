"""
Auth routes (Phase 8): login form, login submit, logout.

The login form is the only browser path to obtain a session cookie. The
same shared secret (settings.api_secret_key) authenticates API clients
via X-RasaPi-Key / Authorization Bearer headers — those don't go through
this router.
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config import settings
from security import auth as auth_module
from security.audit_log import audit_logger


_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


router = APIRouter(tags=["auth"])


def _render_login(request: Request, error: str | None = None, next_url: str = "/dashboard") -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "error": error,
            "next_url": next_url,
            "auth_misconfigured": settings.enable_auth and not auth_module._is_secret_configured(),
        },
    )


@router.get("/login", response_class=HTMLResponse)
def get_login(request: Request, next: str = "/dashboard"):
    next_url = auth_module.safe_next_url(next)
    if auth_module.is_dashboard_authenticated(request):
        return RedirectResponse(url=next_url, status_code=303)
    error_param = request.query_params.get("error")
    error = "Invalid key. Try again." if error_param else None
    return _render_login(request, error=error, next_url=next_url)


@router.post("/login")
async def post_login(request: Request):
    form = await auth_module.read_form(request)
    api_key = form.get("api_key", "").strip()
    next_url = auth_module.safe_next_url(form.get("next"))
    request_id = auth_module._audit_id()

    if not settings.enable_auth:
        # Login isn't meaningful when auth is off — but we still want a sane
        # response so operators don't get a 500. Just send them home.
        return RedirectResponse(url=next_url, status_code=303)

    if not auth_module._is_secret_configured():
        audit_logger.log_auth_event(
            request_id=request_id,
            event_type="auth_login_failed",
            outcome="error",
            reason="auth_misconfigured",
        )
        return _render_login(
            request,
            error="Auth is enabled but no API_SECRET_KEY is configured.",
            next_url=next_url,
        )

    if auth_module.verify_api_key(api_key):
        token = auth_module.create_session_cookie()
        response = RedirectResponse(url=next_url, status_code=303)
        auth_module.set_session_cookie(response, token)
        audit_logger.log_auth_event(
            request_id=request_id,
            event_type="auth_login_success",
            outcome="success",
        )
        return response

    audit_logger.log_auth_event(
        request_id=request_id,
        event_type="auth_login_failed",
        outcome="error",
        reason="bad_key",
    )
    # Use a redirect with ?error so refreshing doesn't resubmit the form.
    return RedirectResponse(
        url=f"/login?error=1&next={next_url}", status_code=303
    )


@router.post("/logout")
def post_logout(request: Request):
    request_id = auth_module._audit_id()
    response = RedirectResponse(url="/login", status_code=303)
    auth_module.clear_session_cookie(response)
    audit_logger.log_auth_event(
        request_id=request_id,
        event_type="auth_logout",
        outcome="success",
    )
    return response
