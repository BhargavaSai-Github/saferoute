"""Community verification voting, comments, and administrative escalation services.

Reference: docs/SPEC.md Section 3, Section 7, Section 8
"""

import logging
from typing import Any, Dict, List, Literal, Optional
import uuid

from pydantic import BaseModel, Field

from app.config import Settings, settings
from app.services.images import build_hazard_storage_path, validate_and_strip_exif
from app.services.supabase_client import (
    create_authenticated_supabase_client,
)

logger = logging.getLogger(__name__)

VoteType = Literal["confirm", "dispute", "fixed"]


class VotingError(Exception):
    """Domain error for voting operations."""

    def __init__(self, user_message: str, status_code: int = 400) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.status_code = status_code


class CommentOut(BaseModel):
    """Output contract for report comment."""

    id: str
    report_id: str
    user_id: str
    author_name: str
    body: str
    created_at: str


class VoteResult(BaseModel):
    """Result returned after submitting a verification vote."""

    report_id: str
    vote: VoteType
    confirm_count: int
    dispute_count: int
    fixed_count: int
    new_status: str
    severity_score: int
    confidence: str


def cast_verification_vote(
    report_id: str,
    user_id: str,
    vote: VoteType,
    access_token: str,
    after_image_bytes: Optional[bytes] = None,
    after_image_content_type: Optional[str] = None,
    app_settings: Optional[Settings] = None,
) -> VoteResult:
    """Submit a confirm, dispute, or fixed vote under the user's RLS context.

    Enforces that users cannot vote on their own reports.
    SQL triggers automatically recompute severity scores, confidence, and fixed threshold.
    """
    cfg = app_settings or settings
    client = create_authenticated_supabase_client(access_token, cfg)

    # 1. Fetch report to check ownership and active status
    rep_res = (
        client.table("hazard_reports")
        .select("id, reporter_id, status, confirm_count, dispute_count, fixed_count, severity_score, confidence")
        .eq("id", report_id)
        .limit(1)
        .execute()
    )
    if not rep_res.data:
        raise VotingError("Hazard report not found.", status_code=404)

    report = rep_res.data[0]
    if report.get("reporter_id") == user_id:
        raise VotingError("You cannot vote on your own hazard report.", status_code=400)

    # 2. Insert verification vote into public.verifications
    try:
        client.table("verifications").insert(
            {
                "report_id": report_id,
                "user_id": user_id,
                "vote": vote,
            }
        ).execute()
    except Exception as exc:
        err_msg = str(exc).lower()
        if "unique" in err_msg or "conflict" in err_msg or "already exists" in err_msg:
            raise VotingError(f"You have already submitted a '{vote}' vote for this hazard.", status_code=409)
        if "self_vote" in err_msg:
            raise VotingError("You cannot vote on your own hazard report.", status_code=400)
        logger.error("Failed to insert verification vote: %s", exc)
        raise VotingError("Failed to record vote. Please try again.", status_code=400)

    # 3. Optional after-photo upload if voting fixed
    if vote == "fixed" and after_image_bytes:
        try:
            processed = validate_and_strip_exif(after_image_bytes, after_image_content_type)
            storage_path = build_hazard_storage_path(user_id, report_id, processed.extension)
            client.storage.from_("hazard-photos").upload(
                path=storage_path,
                file=processed.content,
                file_options={"content-type": processed.content_type, "upsert": "false"},
            )
            client.table("report_images").insert(
                {
                    "report_id": report_id,
                    "storage_path": storage_path,
                    "kind": "after",
                }
            ).execute()
        except Exception as img_exc:
            logger.warning("Failed to store fixed after-photo: %s", img_exc)

    # 4. Fetch updated report status after triggers recomputed
    updated_rep = (
        client.table("hazard_reports")
        .select("confirm_count, dispute_count, fixed_count, status, severity_score, confidence")
        .eq("id", report_id)
        .limit(1)
        .execute()
    )
    row = updated_rep.data[0] if updated_rep.data else report

    return VoteResult(
        report_id=report_id,
        vote=vote,
        confirm_count=int(row.get("confirm_count", 0)),
        dispute_count=int(row.get("dispute_count", 0)),
        fixed_count=int(row.get("fixed_count", 0)),
        new_status=str(row.get("status", "open")),
        severity_score=int(row.get("severity_score", 0)),
        confidence=str(row.get("confidence", "low")),
    )


def add_report_comment(
    report_id: str,
    user_id: str,
    body: str,
    access_token: str,
    app_settings: Optional[Settings] = None,
) -> CommentOut:
    """Add a new comment to a hazard report."""
    text = (body or "").strip()
    if not text:
        raise VotingError("Comment body cannot be empty.", status_code=400)
    if len(text) > 1000:
        raise VotingError("Comment cannot exceed 1000 characters.", status_code=400)

    cfg = app_settings or settings
    client = create_authenticated_supabase_client(access_token, cfg)

    # Insert comment
    res = (
        client.table("comments")
        .insert({"report_id": report_id, "user_id": user_id, "body": text})
        .execute()
    )
    if not res.data:
        raise VotingError("Could not submit comment.", status_code=400)

    created = res.data[0]
    # Fetch user profile for name
    prof_res = client.table("profiles").select("full_name").eq("id", user_id).limit(1).execute()
    author_name = prof_res.data[0].get("full_name") if prof_res.data else "Citizen"

    return CommentOut(
        id=str(created.get("id")),
        report_id=report_id,
        user_id=user_id,
        author_name=author_name or "Citizen",
        body=text,
        created_at=str(created.get("created_at")),
    )


def get_report_comments(
    report_id: str,
    access_token: str,
    app_settings: Optional[Settings] = None,
) -> List[CommentOut]:
    """Retrieve all comments for a hazard report."""
    cfg = app_settings or settings
    client = create_authenticated_supabase_client(access_token, cfg)

    # Fetch comments and profiles
    com_res = (
        client.table("comments")
        .select("id, report_id, user_id, body, created_at, profiles(full_name)")
        .eq("report_id", report_id)
        .order("created_at", desc=False)
        .execute()
    )

    comments: List[CommentOut] = []
    for c in com_res.data or []:
        prof = c.get("profiles") or {}
        name = prof.get("full_name") if isinstance(prof, dict) else "Citizen"
        comments.append(
            CommentOut(
                id=str(c.get("id")),
                report_id=report_id,
                user_id=str(c.get("user_id")),
                author_name=name or "Citizen",
                body=str(c.get("body", "")),
                created_at=str(c.get("created_at")),
            )
        )
    return comments


def escalate_report(
    report_id: str,
    admin_id: str,
    authority_name: str,
    note: str,
    access_token: str,
    app_settings: Optional[Settings] = None,
) -> Dict[str, Any]:
    """Record administrative escalation and update report status to 'escalated'."""
    auth_name = (authority_name or "").strip()
    if not auth_name:
        raise VotingError("Authority name is required for escalation.", status_code=400)

    cfg = app_settings or settings
    client = create_authenticated_supabase_client(access_token, cfg)

    # Insert escalation record
    esc_res = (
        client.table("escalations")
        .insert(
            {
                "report_id": report_id,
                "escalated_by": admin_id,
                "authority_name": auth_name,
                "note": (note or "").strip(),
            }
        )
        .execute()
    )

    # Update report status
    client.table("hazard_reports").update(
        {"status": "escalated", "escalated_at": "now()"}
    ).eq("id", report_id).execute()

    return {
        "status": "escalated",
        "authority_name": auth_name,
        "note": note,
        "report_id": report_id,
    }
