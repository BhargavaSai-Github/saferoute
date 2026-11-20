"""Administrative escalation management router.

Reference: docs/SPEC.md Section 3, Section 4, Section 8
"""

from typing import Any, Dict, List, Union

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.config import Settings
from app.deps import (
    AuthenticatedContext,
    get_authenticated_context,
    get_settings,
    require_admin,
    require_csrf,
)
from app.services.auth import AuthenticatedUser
from app.services.session import issue_csrf_cookie
from app.services.supabase_client import create_authenticated_supabase_client
from app.services.voting import VotingError, escalate_report

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/escalations", summary="Municipal Escalations Dashboard")
async def escalations_page(
    request: Request,
    response: Response,
    current_user: AuthenticatedUser = Depends(require_admin),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    app_settings: Settings = Depends(get_settings),
) -> Response:
    """Render the admin escalations dashboard listing high-priority hazards."""
    templates = Jinja2Templates(directory="app/templates")
    csrf_token = request.cookies.get(app_settings.CSRF_COOKIE_NAME, "")
    if not csrf_token:
        csrf_token = issue_csrf_cookie(response, app_settings)

    # Fetch reports where escalation is recommended or status is escalated
    client = create_authenticated_supabase_client(ctx.access_token, app_settings)
    res = (
        client.table("hazard_reports")
        .select("id, category, description, address_text, severity_score, confirm_count, status, escalation_recommended, created_at")
        .or_("escalation_recommended.eq.true,status.eq.escalated,severity_score.gte.70")
        .order("severity_score", desc=True)
        .limit(100)
        .execute()
    )
    escalations = res.data or []

    return templates.TemplateResponse(
        request=request,
        name="admin_escalations.html",
        context={
            "current_user": current_user,
            "active_nav": "escalations",
            "csrf_token": csrf_token,
            "escalations": escalations,
        },
    )


@router.post("/escalations/{report_id}", response_model=None, summary="Mark Report as Escalated to Municipal Authority")
async def mark_escalated(
    report_id: str,
    request: Request,
    authority_name: str = Form(...),
    note: str = Form(default=""),
    current_user: AuthenticatedUser = Depends(require_admin),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    _csrf: None = Depends(require_csrf),
    app_settings: Settings = Depends(get_settings),
) -> Union[Dict[str, Any], HTMLResponse]:
    """Record municipal escalation note and update status to 'escalated'."""
    try:
        result = escalate_report(
            report_id=report_id,
            admin_id=current_user.id,
            authority_name=authority_name,
            note=note,
            access_token=ctx.access_token,
            app_settings=app_settings,
        )
    except VotingError as v_err:
        raise HTTPException(status_code=v_err.status_code, detail=v_err.user_message)

    if request.headers.get("hx-request", "").lower() == "true":
        return HTMLResponse(
            content=f"""
            <span class="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold sr-severity-high border">
                Escalated to {authority_name}
            </span>
            """,
            status_code=200,
        )

    return JSONResponse(status_code=200, content=result)
