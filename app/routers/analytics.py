"""Civic analytics and road hazard statistics router.

Reference: docs/SPEC.md Section 4, Section 11
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from app.config import Settings
from app.deps import (
    AuthenticatedContext,
    get_authenticated_context,
    get_current_user,
    get_settings,
)
from app.services.analytics import AnalyticsData, get_analytics_metrics
from app.services.auth import AuthenticatedUser
from app.services.session import issue_csrf_cookie

router = APIRouter(tags=["analytics"])


@router.get("/analytics", summary="Civic Safety Analytics Dashboard")
async def analytics_page(
    request: Request,
    response: Response,
    current_user: AuthenticatedUser = Depends(get_current_user),
    app_settings: Settings = Depends(get_settings),
) -> Response:
    """Render the civic analytics dashboard."""
    templates = Jinja2Templates(directory="app/templates")
    csrf_token = request.cookies.get(app_settings.CSRF_COOKIE_NAME, "")
    if not csrf_token:
        csrf_token = issue_csrf_cookie(response, app_settings)

    return templates.TemplateResponse(
        request=request,
        name="analytics.html",
        context={
            "current_user": current_user,
            "active_nav": "analytics",
            "csrf_token": csrf_token,
        },
    )


@router.get(
    "/api/analytics/data",
    response_model=AnalyticsData,
    summary="Get Aggregated Road Hazard Metrics and Heatmap Points",
)
async def get_analytics_data(
    exclude_seed: bool = Query(default=False),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    app_settings: Settings = Depends(get_settings),
) -> AnalyticsData:
    """Query live metrics, category breakdowns, and heatmap coordinates."""
    return get_analytics_metrics(
        access_token=ctx.access_token,
        exclude_seed=exclude_seed,
        app_settings=app_settings,
    )
