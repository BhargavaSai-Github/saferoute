"""Community verification voting router.

Reference: docs/SPEC.md Section 3, Section 7, Section 8
"""

from typing import Optional, Union

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import Settings
from app.deps import (
    AuthenticatedContext,
    get_authenticated_context,
    get_settings,
    require_csrf,
)
from app.services.images import MAX_IMAGE_SIZE_BYTES, ImageTooLargeError
from app.services.voting import (
    VoteResult,
    VoteType,
    VotingError,
    cast_verification_vote,
)

router = APIRouter(tags=["votes"])


@router.post(
    "/reports/{report_id}/vote",
    response_model=None,
    summary="Submit a Verification Vote (confirm, dispute, or fixed)",
)
async def submit_vote(
    report_id: str,
    request: Request,
    vote: str = Form(...),
    image: Optional[UploadFile] = File(default=None),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    _csrf: None = Depends(require_csrf),
    app_settings: Settings = Depends(get_settings),
) -> Union[VoteResult, HTMLResponse, JSONResponse]:
    """Cast a verification vote on an active hazard report."""
    v_norm = vote.strip().lower()
    if v_norm not in ("confirm", "dispute", "fixed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vote must be one of: 'confirm', 'dispute', 'fixed'.",
        )

    after_bytes = None
    after_content_type = None
    if image is not None:
        after_bytes = await image.read(MAX_IMAGE_SIZE_BYTES + 1)
        if len(after_bytes) > MAX_IMAGE_SIZE_BYTES:
            raise ImageTooLargeError()
        after_content_type = image.content_type

    try:
        res = cast_verification_vote(
            report_id=report_id,
            user_id=ctx.user.id,
            vote=v_norm,  # type: ignore[arg-type]
            access_token=ctx.access_token,
            after_image_bytes=after_bytes,
            after_image_content_type=after_content_type,
            app_settings=app_settings,
        )
    except VotingError as v_err:
        raise HTTPException(status_code=v_err.status_code, detail=v_err.user_message)

    # Return partial fragment if HTMX request
    if request.headers.get("hx-request", "").lower() == "true":
        badge_html = f"""
        <div id="vote-feedback" class="p-3 bg-primary-soft text-primary-dark rounded-lg text-sm font-semibold border border-primary/20 flex items-center justify-between">
            <span>Vote recorded: <strong>{v_norm.capitalize()}</strong></span>
            <span class="text-xs text-muted">Confirms: {res.confirm_count} &middot; Severity: {res.severity_score}</span>
        </div>
        """
        return HTMLResponse(content=badge_html, status_code=200)

    return JSONResponse(status_code=200, content=res.model_dump())
