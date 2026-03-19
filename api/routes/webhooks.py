"""
Webhook ingestion — EC13: HMAC verification, timestamp guard, dedup via Redis SET NX.
Stores raw payload. Updates post status from platform event data.
Platform-specific signature logic: Facebook/Instagram use X-Hub-Signature-256,
YouTube uses a different auth header.
"""
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from api.deps import DB, CacheRedis

logger = logging.getLogger(__name__)
router = APIRouter(tags=["webhooks"])

_TIMESTAMP_TOLERANCE_SECONDS = 300  # 5 minutes
_DEDUP_TTL_SECONDS = 86400          # 24 hours


# ── Response model ────────────────────────────────────────────────────────────

class WebhookAckResponse(BaseModel):
    received: bool = True


# ── Entry point ───────────────────────────────────────────────────────────────

@router.post("/webhooks/{platform}", response_model=WebhookAckResponse)
async def receive_webhook(
    platform: str,
    request: Request,
    db: DB,
    cache_redis: CacheRedis,
) -> WebhookAckResponse:
    raw_body = await request.body()
    headers = request.headers

    # 1. Signature verification (platform-specific)
    _verify_signature(platform, raw_body, headers)

    # 2. Parse payload
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    # 3. Timestamp guard — reject stale webhooks
    event_timestamp = _extract_timestamp(platform, payload, headers)
    if event_timestamp is not None:
        age_seconds = time.time() - event_timestamp
        if age_seconds > _TIMESTAMP_TOLERANCE_SECONDS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Webhook timestamp too old — possible replay attack",
            )

    # 4. Deduplication via Redis SET NX (24h TTL)
    event_id = _extract_event_id(platform, payload)
    if event_id:
        dedup_key = f"webhook_dedup:{platform}:{event_id}"
        is_new = await cache_redis.set(dedup_key, "1", ex=_DEDUP_TTL_SECONDS, nx=True)
        if not is_new:
            logger.info("Duplicate webhook ignored: platform=%s event_id=%s", platform, event_id)
            return WebhookAckResponse()

    # 5. Store raw event for audit trail
    now = datetime.now(timezone.utc)
    await db.webhook_events.insert_one({
        "platform": platform,
        "event_id": event_id,
        "payload": payload,
        "raw_body": raw_body.decode("utf-8", errors="replace"),
        "received_at": now,
        "processed": False,
    })

    # 6. Update post status from payload
    await _process_webhook_payload(platform, payload, db)

    return WebhookAckResponse()


# ── Signature verification ────────────────────────────────────────────────────

def _verify_signature(platform: str, body: bytes, headers) -> None:
    if platform in ("facebook", "instagram"):
        _verify_hub_signature_256(body, headers)
    elif platform == "youtube":
        _verify_youtube_auth(headers)
    else:
        logger.warning("No signature verification configured for platform: %s", platform)


def _verify_hub_signature_256(body: bytes, headers) -> None:
    """Facebook/Instagram HMAC-SHA256 via X-Hub-Signature-256 header."""
    sig_header = headers.get("x-hub-signature-256", "")
    if not sig_header.startswith("sha256="):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed X-Hub-Signature-256",
        )

    app_secret = os.environ.get("META_APP_SECRET", "")
    if not app_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook secret not configured",
        )

    expected = "sha256=" + hmac.new(
        app_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, sig_header):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )


def _verify_youtube_auth(headers) -> None:
    """YouTube uses X-Goog-Channel-Token for push notification auth."""
    token = headers.get("x-goog-channel-token", "")
    expected_token = os.environ.get("YOUTUBE_WEBHOOK_TOKEN", "")
    if not expected_token:
        logger.warning("YOUTUBE_WEBHOOK_TOKEN not set — skipping YouTube webhook auth")
        return
    if not hmac.compare_digest(token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid YouTube webhook token",
        )


# ── Payload processing ────────────────────────────────────────────────────────

def _extract_event_id(platform: str, payload: dict) -> str | None:
    extractors = {
        "facebook": lambda p: p.get("entry", [{}])[0].get("id"),
        "instagram": lambda p: p.get("entry", [{}])[0].get("id"),
        "youtube": lambda p: p.get("id"),
        "twitter": lambda p: p.get("id_str"),
        "linkedin": lambda p: p.get("eventId"),
        "tiktok": lambda p: p.get("event_id"),
    }
    extractor = extractors.get(platform)
    return extractor(payload) if extractor else None


def _extract_timestamp(platform: str, payload: dict, headers) -> float | None:
    """Return UNIX timestamp from payload or headers, None if unavailable."""
    # Facebook/Instagram embed timestamp in entry
    if platform in ("facebook", "instagram"):
        entries = payload.get("entry", [])
        if entries and "time" in entries[0]:
            return float(entries[0]["time"])
    # YouTube uses X-Goog-Resource-State; timestamp from headers
    if platform == "youtube":
        ts = headers.get("x-goog-message-number")
        return None  # YouTube doesn't include timestamps in headers
    return None


async def _process_webhook_payload(platform: str, payload: dict, db) -> None:
    """Map platform webhook event to post status updates."""
    if platform in ("facebook", "instagram"):
        await _process_meta_webhook(payload, db)
    elif platform == "youtube":
        await _process_youtube_webhook(payload, db)
    else:
        logger.info("No status update handler for platform: %s", platform)


async def _process_meta_webhook(payload: dict, db) -> None:
    now = datetime.now(timezone.utc)
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            val = change.get("value", {})
            platform_post_id = val.get("post_id") or val.get("media_id")
            if not platform_post_id:
                continue
            await db.posts.update_one(
                {"platform_results.facebook.platform_post_id": platform_post_id},
                {"$set": {"platform_results.facebook.status": "published", "updated_at": now}},
            )


async def _process_youtube_webhook(payload: dict, db) -> None:
    now = datetime.now(timezone.utc)
    video_id = payload.get("id")
    if video_id:
        await db.posts.update_one(
            {"platform_results.youtube.platform_post_id": video_id},
            {"$set": {"platform_results.youtube.status": "published", "updated_at": now}},
        )
