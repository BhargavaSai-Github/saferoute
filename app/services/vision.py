"""Vision AI service for automated hazard category suggestions.

Reference: docs/SPEC.md Section 9
"""

import base64
import json
import logging
from typing import Literal, Optional

import httpx
from pydantic import BaseModel

from app.config import Settings, settings

logger = logging.getLogger(__name__)

HazardCategory = Literal["pothole", "road_break", "streetlight", "footpath", "other", "none"]
ALLOWED_CATEGORIES = {"pothole", "road_break", "streetlight", "footpath", "other", "none"}


class SuggestCategoryResponse(BaseModel):
    """Normalized response payload for category suggestion."""

    category: Optional[str] = None
    confidence: Optional[float] = None
    reason: Optional[str] = None


PROMPT_INSTRUCTION = (
    "You are an expert civic infrastructure classifier. Examine this road or sidewalk photograph "
    "and classify the primary hazard into exactly one category: "
    "'pothole', 'road_break', 'streetlight', 'footpath', 'other', or 'none'. "
    "Return STRICTLY valid JSON with three keys: "
    '{"category": "<category>", "confidence": <float between 0.0 and 1.0>, "reason": "<one sentence explanation>"}. '
    "Do not include Markdown backticks or commentary outside the JSON."
)


async def suggest_hazard_category(
    image_bytes: bytes,
    content_type: str = "image/jpeg",
    app_settings: Optional[Settings] = None,
) -> SuggestCategoryResponse:
    """Analyze an uploaded hazard photograph and suggest a category.

    Never raises unhandled exceptions to the caller; returns category=None on
    any configuration, network, timeout, or parsing error so the reporting form
    never breaks.
    """
    cfg = app_settings or settings
    api_key = (cfg.VISION_API_KEY or "").strip()
    if not api_key or api_key in ("your-gemini-or-vision-api-key", "placeholder"):
        logger.info("VISION_API_KEY not configured. Skipping automated AI categorization.")
        return SuggestCategoryResponse(
            category=None,
            confidence=None,
            reason="AI suggestion is currently disabled or unconfigured.",
        )

    # Clean mime type
    mime = content_type.split(";")[0].strip().lower() or "image/jpeg"
    b64_data = base64.b64encode(image_bytes).decode("ascii")

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": PROMPT_INSTRUCTION},
                    {
                        "inline_data": {
                            "mime_type": mime,
                            "data": b64_data,
                        }
                    },
                ]
            }
        ],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.1,
            "maxOutputTokens": 250,
        },
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                logger.warning("Gemini API error %d: %s", resp.status_code, resp.text[:200])
                return SuggestCategoryResponse(
                    category=None,
                    confidence=None,
                    reason="Could not classify image at this time.",
                )

            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return SuggestCategoryResponse(category=None, confidence=None, reason=None)

            text_content = (
                candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            )
            # Remove any stray markdown formatting
            if text_content.startswith("```"):
                text_content = text_content.strip("`").replace("json\n", "", 1).strip()

            parsed = json.loads(text_content)
            category = str(parsed.get("category", "")).strip().lower()
            if category not in ALLOWED_CATEGORIES:
                category = "other"

            confidence = float(parsed.get("confidence", 0.0))
            confidence = max(0.0, min(1.0, confidence))
            reason = str(parsed.get("reason", "")).strip()

            return SuggestCategoryResponse(
                category=category if category != "none" else None,
                confidence=round(confidence, 2),
                reason=reason,
            )
    except Exception as exc:
        logger.warning("Failed to classify hazard image with Vision AI: %s", exc)
        return SuggestCategoryResponse(
            category=None,
            confidence=None,
            reason="AI analysis could not complete.",
        )
