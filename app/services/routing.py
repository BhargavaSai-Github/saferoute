"""Hazard-aware route planning service integrating OSRM and PostGIS hazards_near_route.

Reference: docs/SPEC.md Section 10
"""

import json
import logging
import math
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field

from app.config import Settings, settings
from app.services.supabase_client import (
    SupabaseConfigError,
    create_authenticated_supabase_client,
)

logger = logging.getLogger(__name__)


class RouteHazardItem(BaseModel):
    """Hazard located within the buffer distance of a route."""

    id: str
    category: str
    description: str
    lat: float
    lng: float
    address_text: Optional[str] = None
    severity_score: int
    severity_band: str
    distance_to_route_m: float


class RouteOption(BaseModel):
    """Evaluated route candidate with safety score and hazard annotations."""

    route_index: int
    summary: str
    distance_meters: float
    distance_km: float
    duration_seconds: float
    duration_minutes: float
    route_risk: float
    route_score: float
    is_safest: bool = False
    is_fastest: bool = False
    hazard_count: int = 0
    hazards: List[RouteHazardItem] = []
    geometry: Dict[str, Any]  # GeoJSON LineString geometry


class RoutePlanResponse(BaseModel):
    """Full response for route planning request."""

    routes: List[RouteOption]
    disclaimer: str = (
        "Routes are ranked using community-reported hazards only. "
        "This does not guarantee any route is safe."
    )


def _get_severity_multiplier(score: int) -> float:
    if score >= 70:
        return 1.0
    if score >= 40:
        return 0.8
    return 0.5


def _get_severity_band(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


# Fallback demo route around Kukatpally Y Junction -> JNTU / Hitec City
DEMO_FALLBACK_COORDINATES = [
    [78.4138, 17.4849],
    [78.4120, 17.4865],
    [78.4060, 17.4910],
    [78.4010, 17.4930],
    [78.3950, 17.4960],
    [78.3912, 17.4981],
]


def _build_fallback_route(
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
) -> List[Dict[str, Any]]:
    """Synthesize a clean geometric fallback if the external OSRM service is unreachable."""
    coords = [
        [start_lng, start_lat],
        [(start_lng + end_lng) / 2 + 0.002, (start_lat + end_lat) / 2 + 0.001],
        [end_lng, end_lat],
    ]
    # Simple direct distance approximation in meters
    d_lat = (end_lat - start_lat) * 111000
    d_lng = (end_lng - start_lng) * 111000 * math.cos(math.radians(start_lat))
    dist = math.sqrt(d_lat * d_lat + d_lng * d_lng)
    duration = dist / 8.33  # ~30 km/h average city driving

    return [
        {
            "distance": dist,
            "duration": duration,
            "geometry": {
                "type": "LineString",
                "coordinates": coords,
            },
            "legs": [{"summary": "Direct Connecting Road"}],
        }
    ]


async def plan_hazard_aware_route(
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
    access_token: str,
    app_settings: Optional[Settings] = None,
) -> RoutePlanResponse:
    """Plan routes via OSRM, evaluate hazards along the corridor, and rank by safety."""
    cfg = app_settings or settings
    buffer_m = cfg.ROUTE_HAZARD_BUFFER_METERS

    # 1. Query OSRM API with alternatives=true
    osrm_url = (
        f"https://router.project-osrm.org/route/v1/driving/"
        f"{start_lng},{start_lat};{end_lng},{end_lat}"
        f"?overview=full&geometries=geojson&alternatives=true"
    )

    raw_routes: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(osrm_url)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == "Ok" and data.get("routes"):
                    raw_routes = data["routes"]
    except Exception as exc:
        logger.warning("OSRM request failed (%s). Falling back to direct corridor geometry.", exc)

    if not raw_routes:
        raw_routes = _build_fallback_route(start_lat, start_lng, end_lat, end_lng)

    # 2. Query PostGIS RPC hazards_near_route for each route candidate
    evaluated_routes: List[RouteOption] = []
    client = create_authenticated_supabase_client(access_token, cfg)

    for idx, r in enumerate(raw_routes):
        geom = r.get("geometry", {})
        dist_m = float(r.get("distance", 0.0))
        dur_s = float(r.get("duration", 0.0))
        dur_min = dur_s / 60.0

        legs = r.get("legs", [])
        summary = legs[0].get("summary", "") if legs else f"Route {idx + 1}"
        if not summary:
            summary = f"Route {idx + 1}"

        # PostGIS lookup for hazards along the route
        route_hazards: List[RouteHazardItem] = []
        route_risk = 0.0

        try:
            rpc_res = client.rpc(
                "hazards_near_route",
                {"route_geojson": geom, "buffer_m": buffer_m},
            ).execute()

            for item in rpc_res.data or []:
                score = int(item.get("severity_score", 0))
                band = _get_severity_band(score)
                mult = _get_severity_multiplier(score)
                route_risk += score * mult

                route_hazards.append(
                    RouteHazardItem(
                        id=str(item.get("id")),
                        category=str(item.get("category")),
                        description=str(item.get("description", "")),
                        lat=float(item.get("lat")),
                        lng=float(item.get("lng")),
                        address_text=item.get("address_text"),
                        severity_score=score,
                        severity_band=band,
                        distance_to_route_m=round(float(item.get("distance_to_route_m", 0.0)), 1),
                    )
                )
        except Exception as rpc_exc:
            logger.warning("hazards_near_route RPC failed for route %d: %s", idx, rpc_exc)

        # Spec formula: route_score = duration_minutes + (0.05 * route_risk)
        route_score = dur_min + (0.05 * route_risk)

        evaluated_routes.append(
            RouteOption(
                route_index=idx,
                summary=summary,
                distance_meters=round(dist_m, 1),
                distance_km=round(dist_m / 1000.0, 2),
                duration_seconds=round(dur_s, 1),
                duration_minutes=round(dur_min, 1),
                route_risk=round(route_risk, 1),
                route_score=round(route_score, 1),
                hazard_count=len(route_hazards),
                hazards=route_hazards,
                geometry=geom,
            )
        )

    # Determine fastest and safest routes
    if evaluated_routes:
        min_score = min(opt.route_score for opt in evaluated_routes)
        min_dur = min(opt.duration_minutes for opt in evaluated_routes)
        for opt in evaluated_routes:
            if math.isclose(opt.route_score, min_score, rel_tol=1e-5):
                opt.is_safest = True
            if math.isclose(opt.duration_minutes, min_dur, rel_tol=1e-5):
                opt.is_fastest = True

    return RoutePlanResponse(routes=evaluated_routes)
