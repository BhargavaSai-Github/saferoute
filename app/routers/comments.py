"""Community comments router for hazard reports.

Reference: docs/SPEC.md Section 7, Section 8
"""

from typing import List, Union

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import Settings
from app.deps import (
    AuthenticatedContext,
    get_authenticated_context,
    get_settings,
    require_csrf,
)
from app.services.voting import (
    CommentOut,
    VotingError,
    add_report_comment,
    get_report_comments,
)

router = APIRouter(tags=["comments"])


@router.get(
    "/reports/{report_id}/comments",
    response_model=List[CommentOut],
    summary="List Comments on a Hazard Report",
)
async def list_comments(
    report_id: str,
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    app_settings: Settings = Depends(get_settings),
) -> List[CommentOut]:
    """Retrieve discussion comments for the specified hazard report."""
    return get_report_comments(report_id, ctx.access_token, app_settings)


@router.post(
    "/reports/{report_id}/comments",
    response_model=None,
    summary="Post a Comment to a Hazard Report",
)
async def create_comment(
    report_id: str,
    request: Request,
    body: str = Form(...),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    _csrf: None = Depends(require_csrf),
    app_settings: Settings = Depends(get_settings),
) -> Union[CommentOut, HTMLResponse, JSONResponse]:
    """Add a new comment under the user's authenticated context."""
    try:
        new_comment = add_report_comment(
            report_id=report_id,
            user_id=ctx.user.id,
            body=body,
            access_token=ctx.access_token,
            app_settings=app_settings,
        )
    except VotingError as v_err:
        raise HTTPException(status_code=v_err.status_code, detail=v_err.user_message)

    if request.headers.get("hx-request", "").lower() == "true":
        comment_html = f"""
        <div class="p-3.5 bg-canvas border border-border rounded-lg space-y-1">
            <div class="flex items-center justify-between">
                <span class="text-xs font-bold text-ink">{new_comment.author_name}</span>
                <span class="text-[11px] text-muted">Just now</span>
            </div>
            <p class="text-sm text-ink leading-relaxed">{new_comment.body}</p>
        </div>
        """
        return HTMLResponse(content=comment_html, status_code=201)

    return JSONResponse(status_code=201, content=new_comment.model_dump())
