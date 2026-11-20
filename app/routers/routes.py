"""Hazard-aware route planning router.

Reference: docs/SPEC.md Section 4, Section 10
"""

from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.config import Settings
from app.deps import (
    AuthenticatedContext,
    get_authenticated_context,
    get_current_user,
    get_settings,
    require_csrf,
)
from app.services.auth import AuthenticatedUser
from app.services.routing import RoutePlanResponse, plan_hazard_aware_route
from app.services.session import issue_csrf_cookie

router = APIRouter(tags=["routes"])


@router.get("/routes", summary="Hazard-Aware Route Planner Page")
async def routes_page(
    request: Request,
    response: Response,
    current_user: AuthenticatedUser = Depends(get_current_user),
    app_settings: Settings = Depends(get_settings),
) -> Response:
    """Render the route planning workspace."""
    templates = Jinja2Templates(directory="app/templates")
    csrf_token = request.cookies.get(app_settings.CSRF_COOKIE_NAME, "")
    if not csrf_token:
        csrf_token = issue_csrf_cookie(response, app_settings)

    map_config = {
        "fallbackLat": app_settings.DEFAULT_MAP_LAT,
        "fallbackLng": app_settings.DEFAULT_MAP_LNG,
        "defaultZoom": app_settings.DEFAULT_MAP_ZOOM,
    }

    return templates.TemplateResponse(
        request=request,
        name="routes.html",
        context={
            "current_user": current_user,
            "active_nav": "routes",
            "csrf_token": csrf_token,
            "map_config": map_config,
        },
    )


@router.post(
    "/api/routes/plan",
    response_model=RoutePlanResponse,
    summary="Calculate Safety-Weighted Routes with Hazard Buffer Annotations",
)
async def plan_route(
    request: Request,
    start_lat: float = Form(...),
    start_lng: float = Form(...),
    end_lat: float = Form(...),
    end_lng: float = Form(...),
    ctx: AuthenticatedContext = Depends(get_authenticated_context),
    _csrf: None = Depends(require_csrf),
    app_settings: Settings = Depends(get_settings),
) -> RoutePlanResponse:
    """Calculate route candidates with OSRM and evaluate risk score from hazards."""
    if not (-90 <= start_lat <= 90 and -180 <= start_lng <= 180):
        raise HTTPException(status_code=400, detail="Invalid start coordinates.")
    if not (-90 <= end_lat <= 90 and -180 <= end_lng <= 180):
        raise HTTPException(status_code=400, detail="Invalid end coordinates.")

    return await plan_hazard_aware_route(
        start_lat=start_lat,
        start_lng=start_lng,
        end_lat=end_lat,
        end_lng=end_lng,
        access_token=ctx.access_token,
        app_settings=app_settings,
    )
