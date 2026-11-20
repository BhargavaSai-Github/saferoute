"""Analytics aggregation service for SafeRoute civic statistics and hotspot maps.

Reference: docs/SPEC.md Section 11
"""

from collections import Counter
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.config import Settings, settings
from app.services.supabase_client import (
    create_authenticated_supabase_client,
)

logger = logging.getLogger(__name__)


class AnalyticsData(BaseModel):
    """Aggregated civic awareness metrics."""

    total_reports: int
    open_reports: int
    escalated_reports: int
    fixed_reports: int
    by_category: Dict[str, int]
    by_status: Dict[str, int]
    top_areas: List[Dict[str, Any]]
    heatmap_points: List[List[float]]  # [lat, lng, normalized_intensity]
    verification_rate_pct: float
    duplicate_rate_pct: float
    average_fix_time_hours: Optional[float]
    excluded_seed_data: bool


def get_analytics_metrics(
    access_token: str,
    exclude_seed: bool = False,
    app_settings: Optional[Settings] = None,
) -> AnalyticsData:
    """Fetch and aggregate metrics from public.hazard_reports."""
    cfg = app_settings or settings
    client = create_authenticated_supabase_client(access_token, cfg)

    # 1. Fetch hazard reports
    query = client.table("hazard_reports").select(
        "id, category, status, severity_score, address_text, confirm_count, "
        "duplicate_of, is_seed, created_at, fixed_at, location"
    )
    if exclude_seed:
        query = query.eq("is_seed", False)

    res = query.execute()
    records = res.data or []

    total_count = len(records)
    if total_count == 0:
        return AnalyticsData(
            total_reports=0,
            open_reports=0,
            escalated_reports=0,
            fixed_reports=0,
            by_category={"pothole": 0, "road_break": 0, "streetlight": 0, "footpath": 0, "other": 0},
            by_status={"open": 0, "escalated": 0, "fixed": 0},
            top_areas=[],
            heatmap_points=[],
            verification_rate_pct=0.0,
            duplicate_rate_pct=0.0,
            average_fix_time_hours=None,
            excluded_seed_data=exclude_seed,
        )

    cat_counter: Counter = Counter()
    status_counter: Counter = Counter()
    area_counter: Counter = Counter()
    heatmap_points: List[List[float]] = []

    verified_count = 0
    duplicate_count = 0
    fix_durations_hours: List[float] = []

    for r in records:
        cat = r.get("category", "other")
        stat = r.get("status", "open")
        score = int(r.get("severity_score", 0))
        addr = (r.get("address_text") or "").strip()
        confirms = int(r.get("confirm_count", 0))
        dup_of = r.get("duplicate_of")

        cat_counter[cat] += 1
        status_counter[stat] += 1

        if confirms > 0:
            verified_count += 1
        if dup_of:
            duplicate_count += 1

        if addr:
            # Extract high-level locality if separated by comma
            locality = addr.split(",")[-1].strip() or addr
            area_counter[locality] += 1

        # Check fixed duration
        created_str = r.get("created_at")
        fixed_str = r.get("fixed_at")
        if stat == "fixed" and created_str and fixed_str:
            try:
                c_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                f_dt = datetime.fromisoformat(fixed_str.replace("Z", "+00:00"))
                delta_hrs = (f_dt - c_dt).total_seconds() / 3600.0
                if delta_hrs >= 0:
                    fix_durations_hours.append(delta_hrs)
            except Exception:
                pass

    # 2. Extract heatmap points via reports_in_bounds or direct PostGIS function
    try:
        # Hyderabad bounding box query
        bounds_res = client.rpc(
            "reports_in_bounds",
            {
                "min_lat": 17.0,
                "min_lng": 78.0,
                "max_lat": 18.0,
                "max_lng": 79.0,
                "category_filter": None,
                "status_filter": None,
            },
        ).execute()

        for b in bounds_res.data or []:
            if exclude_seed and b.get("is_seed"):
                continue
            lat = float(b.get("lat", 0.0))
            lng = float(b.get("lng", 0.0))
            sc = int(b.get("severity_score", 0))
            # Normalized intensity 0.2 to 1.0
            intensity = max(0.2, min(1.0, sc / 100.0))
            heatmap_points.append([lat, lng, round(intensity, 2)])
    except Exception as exc:
        logger.warning("Could not query reports_in_bounds for heatmap: %s", exc)

    top_areas_list = [
        {"name": area, "count": count}
        for area, count in area_counter.most_common(5)
    ]

    avg_fix_time = (
        round(sum(fix_durations_hours) / len(fix_durations_hours), 1)
        if fix_durations_hours
        else None
    )

    return AnalyticsData(
        total_reports=total_count,
        open_reports=status_counter["open"],
        escalated_reports=status_counter["escalated"],
        fixed_reports=status_counter["fixed"],
        by_category=dict(cat_counter),
        by_status=dict(status_counter),
        top_areas=top_areas_list,
        heatmap_points=heatmap_points,
        verification_rate_pct=round((verified_count / total_count) * 100.0, 1),
        duplicate_rate_pct=round((duplicate_count / total_count) * 100.0, 1),
        average_fix_time_hours=avg_fix_time,
        excluded_seed_data=exclude_seed,
    )
