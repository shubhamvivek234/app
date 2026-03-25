"""
Celery task definitions — standalone publish logic (no server.py import).
Replaces APScheduler-based scheduling with Celery Beat (every 30s).

Worker: celery -A celery_app worker --loglevel=info --concurrency=4
Beat:   celery -A celery_app beat --loglevel=info
"""
import asyncio
import hashlib
import logging
import os
import random
import re
import tempfile
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent.resolve()
load_dotenv(ROOT_DIR / ".env")

from celery_app import celery_app, is_shutdown_requested
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")


# ── async_task decorator ──────────────────────────────────────────────────────

def async_task(fn):
    """Decorator to run an async function inside a Celery task's sync context."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(fn(*args, **kwargs))
        finally:
            loop.close()
    return wrapper


def get_db():
    """Get a fresh MongoDB client for this task. Each task creates its own connection."""
    client = AsyncIOMotorClient(
        MONGO_URL,
        maxPoolSize=10,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
    )
    return client[DB_NAME]


# ── In-memory rate limiter (token bucket, per worker process) ─────────────────
# Key: "{platform}:{user_id}" → {"tokens": N, "reset_at": float_timestamp}
_rate_limit_buckets: Dict[str, Dict] = {}
# Key: "{platform}:{user_id}" → pause_until float_timestamp (after 429)
_rate_limit_paused: Dict[str, float] = {}

PLATFORM_HOURLY_LIMITS = {
    "instagram": 25, "facebook": 25, "twitter": 50,
    "linkedin": 100, "youtube": 10, "tiktok": 20,
    "bluesky": 100, "threads": 25, "default": 50,
}

BACKOFF_MINUTES = [5, 15, 60]
MAX_RETRIES = 3

# ── EC5 + EC8: Permanent error classification ─────────────────────────────────
# Errors that should NEVER be retried — retrying causes platform account bans.
PERMANENT_ERRORS: Dict[str, list] = {
    "instagram": [
        "invalid parameter", "media type", "media posted", "not a valid",
        "oauthexception", "error validating application", "permission denied",
        "content policy", "#100", "#200", "#10", "account disabled",
        "user not found", "business account required", "spam", "inappropriate",
    ],
    "facebook": [
        "invalid oauth", "#200", "#190", "#10", "application request limit",
        "permission denied", "content policy", "spam", "account disabled",
        "invalid parameter", "oauthexception",
    ],
    "twitter": [
        "duplicate content", "187", "261", "326", "suspended",
        "account suspended", "read-only", "content policy",
    ],
    "linkedin": [
        "unauthorized", "forbidden", "revoked", "content policy",
        "invalid share", "cannot create", "permission denied",
    ],
    "youtube": [
        "content policy", "community guidelines", "duplicate video",
        "account suspended", "forbidden", "quotaexceeded", "invalid credentials",
    ],
    "tiktok": [
        "content policy", "spam", "account banned", "unauthorized",
        "permission denied", "forbidden",
    ],
    "default": [
        "account suspended", "account banned", "content policy", "spam",
        "permanently blocked", "invalid credentials",
    ],
}

# EC24: Permission revocation error patterns — mark account inactive on match.
REVOCATION_ERRORS: Dict[str, list] = {
    "instagram": ["#190", "token has expired", "session has been invalidated", "access revoked"],
    "facebook": ["#190", "invalid_token", "token has expired", "access_token"],
    "twitter": ["89", "invalid or expired token", "could not authenticate"],
    "linkedin": ["401", "revoked", "expired"],
    "youtube": ["invalid_grant", "token has been expired or revoked"],
    "tiktok": ["access_token_invalid", "permission denied"],
}


def is_permanent_error(error_str: str, platform: str) -> bool:
    """Return True if this error must never be retried (EC5 + EC8)."""
    s = error_str.lower()
    patterns = PERMANENT_ERRORS.get(platform, []) + PERMANENT_ERRORS["default"]
    return any(p in s for p in patterns)


def is_revocation_error(error_str: str, platform: str) -> bool:
    """Return True if the user revoked app permissions on the platform (EC24)."""
    s = error_str.lower()
    patterns = REVOCATION_ERRORS.get(platform, [])
    return any(p in s for p in patterns)


# EC16: Ghost account — platform banned/suspended the account. Must never retry,
# must mark account inactive and cascade all queued posts on that platform.
GHOST_ACCOUNT_ERRORS: Dict[str, list] = {
    "instagram": ["account disabled", "user not found", "#368", "user_not_found"],
    "facebook": ["account disabled", "#368", "page removed", "account blocked"],
    "twitter": ["account suspended", "326", "account is suspended", "user is suspended"],
    "linkedin": ["account restricted", "account suspended", "member account is suspended"],
    "youtube": ["account suspended", "channel has been terminated", "suspended account"],
    "tiktok": ["account banned", "account suspended", "account has been suspended"],
    "default": ["account suspended", "account banned", "account disabled", "account blocked",
                "account terminated", "account has been suspended"],
}


def is_ghost_account_error(error_str: str, platform: str) -> bool:
    """Return True if the platform has banned or suspended the linked account (EC16)."""
    s = error_str.lower()
    patterns = GHOST_ACCOUNT_ERRORS.get(platform, []) + GHOST_ACCOUNT_ERRORS["default"]
    return any(p in s for p in patterns)


# ── EC14: Account-level rate limit (shared social accounts across team users) ─
# Key is per-social_account_id so shared accounts share the same budget.
_account_rate_limit_paused: Dict[str, float] = {}


def check_account_rate_limit(account_id: str, platform: str) -> bool:
    """Block if this specific social account is rate-limited (EC14)."""
    key = f"acct:{platform}:{account_id}"
    now_ts = datetime.now(timezone.utc).timestamp()
    if key in _account_rate_limit_paused:
        if now_ts < _account_rate_limit_paused[key]:
            return False
        del _account_rate_limit_paused[key]
    return True


def record_account_rate_limit(account_id: str, platform: str, retry_after_seconds: int = 3600):
    key = f"acct:{platform}:{account_id}"
    _account_rate_limit_paused[key] = datetime.now(timezone.utc).timestamp() + retry_after_seconds


def check_rate_limit(user_id: str, platform: str) -> bool:
    """Returns True if OK to call platform API, False if rate limited."""
    key = f"{platform}:{user_id}"
    now_ts = datetime.now(timezone.utc).timestamp()

    if key in _rate_limit_paused:
        if now_ts < _rate_limit_paused[key]:
            return False
        del _rate_limit_paused[key]

    bucket = _rate_limit_buckets.get(key)
    if not bucket or now_ts > bucket["reset_at"]:
        limit = PLATFORM_HOURLY_LIMITS.get(platform, PLATFORM_HOURLY_LIMITS["default"])
        _rate_limit_buckets[key] = {"tokens": limit, "reset_at": now_ts + 3600}
        bucket = _rate_limit_buckets[key]

    if bucket["tokens"] <= 0:
        return False

    bucket["tokens"] -= 1
    return True


def record_rate_limit_hit(user_id: str, platform: str, retry_after_seconds: int = 3600):
    """Record a 429 response — pause this (user, platform) pair."""
    key = f"{platform}:{user_id}"
    _rate_limit_paused[key] = datetime.now(timezone.utc).timestamp() + retry_after_seconds
    logger.warning(f"Rate limit recorded for {platform}:{user_id}, paused for {retry_after_seconds}s")


def get_next_retry_at(retry_count: int) -> datetime:
    """Exponential backoff: 5min → 15min → 60min → 180min."""
    idx = min(retry_count, len(BACKOFF_MINUTES) - 1)
    return datetime.now(timezone.utc) + timedelta(minutes=BACKOFF_MINUTES[idx])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_media_url(url: str) -> str:
    """
    Resolve media URLs for use in Celery workers.
    - https://... → use as-is (R2/CDN)
    - http://localhost/... or /uploads/... → rewrite to SERVICE_URL or local file path
    """
    if not url:
        return url
    if url.startswith("https://"):
        return url

    service_url = os.environ.get("BACKEND_PUBLIC_URL", "http://api:8001")

    if url.startswith("/"):
        # Relative path → try local file first, then construct full URL
        local_path = f"/app{url}"  # Docker maps uploads to /app/uploads
        if os.path.exists(local_path):
            return f"file://{local_path}"
        return f"{service_url}{url}"

    if "localhost" in url or "127.0.0.1" in url:
        # Replace localhost with service hostname
        return re.sub(r"https?://(localhost|127\.0\.0\.1)(:\d+)?", service_url, url)

    return url


async def _download_url_to_temp(url: str, suffix: str = ".mp4") -> Optional[str]:
    """Download a URL to a temp file, return local path. Caller must delete."""
    if url.startswith("file://"):
        # Already a local file — just return the path directly (no copy needed)
        local_path = url[7:]  # strip "file://"
        return local_path if os.path.exists(local_path) else None
    try:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    tmp.write(chunk)
        tmp.close()
        return tmp.name
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        return None


async def publish_to_platform(platform: str, account: dict, post_doc: dict, trace_id: str) -> dict:
    """
    Publish content to a single platform.
    Returns:
      {"status": "success", "platform_post_id": "..."}
      {"status": "awaiting_ig_processing", "container_id": "..."}  — Instagram video
      {"status": "failed", "error": "...", "rate_limited": True, "retry_after_seconds": N}
      {"status": "failed", "error": "..."}
    """
    access_token = account.get("access_token", "")
    content = post_doc.get("content", "")
    media_urls = post_doc.get("media_urls", [])
    video_url = post_doc.get("video_url")
    media_url = media_urls[0] if media_urls else video_url
    # Resolve URLs so Celery workers can reach local/localhost media
    media_url = _resolve_media_url(media_url) if media_url else None
    video_url = _resolve_media_url(video_url) if video_url else None
    post_id = post_doc.get("id", "")
    account_id = account.get("id", "")

    # EC1: Idempotency key — check Redis before hitting the platform API.
    # Key is deterministic: if this worker already published, return cached result.
    idem_key = f"idempotency:{post_id}:{platform}"
    try:
        import json as _json
        r = await _get_redis()
        cached = await r.get(idem_key)
        if cached:
            data = _json.loads(cached)
            logger.info(f"[{trace_id}] EC1: idempotency hit for {platform}/{post_id} → {data}")
            return {"status": "success", "platform_post_id": data.get("platform_post_id", "")}
    except Exception as _ie:
        logger.warning(f"[{trace_id}] EC1: idempotency Redis check failed: {_ie}")

    # EC14: Account-level rate limit (shared accounts across team users)
    if not check_account_rate_limit(account_id, platform):
        return {"status": "failed", "error": f"Account-level rate limit active for {platform}", "rate_limited": True, "retry_after_seconds": 3600}

    def is_rate_limit_error(error_str: str) -> bool:
        s = error_str.lower()
        return any(k in s for k in ["429", "rate limit", "too many requests", "quota", "ratelimit"])

    def extract_retry_after(error_str: str) -> int:
        m = re.search(r"retry.after[:\s]+(\d+)", error_str, re.IGNORECASE)
        return int(m.group(1)) if m else 3600

    try:
        if platform == "twitter":
            from app.social.twitter import TwitterAuth
            twitter = TwitterAuth()

            # EC30: GIF → MP4 conversion for Twitter (Twitter requires native GIF upload, not URL).
            # Animated GIFs uploaded as image URLs are rejected; convert to MP4 first.
            processed_media_urls: list = list(media_urls or [])
            for idx, url in enumerate(processed_media_urls):
                if url and url.lower().endswith(".gif"):
                    try:
                        converted = await _convert_gif_to_mp4(url, trace_id)
                        if converted:
                            processed_media_urls[idx] = converted
                            logger.info(f"[{trace_id}] EC30: GIF→MP4 converted for Twitter: {url} → {converted}")
                    except Exception as _ge:
                        logger.warning(f"[{trace_id}] EC30: GIF conversion failed ({url}): {_ge} — using original")

            result = await twitter.publish_tweet(access_token, content, processed_media_urls)
            return {"status": "success", "platform_post_id": str(result or "")}

        elif platform == "instagram":
            from app.social.instagram import InstagramAuth
            ig = InstagramAuth()
            ig_user_id = account.get("platform_user_id", "")

            if video_url:
                container_id = await ig.create_video_container(access_token, ig_user_id, video_url, content)
                return {
                    "status": "awaiting_ig_processing",
                    "container_id": container_id,
                    "container_created_at": datetime.now(timezone.utc).isoformat(),  # EC4
                }
            else:
                pub_url = media_url or ""
                result = await ig.publish_to_instagram(access_token, ig_user_id, pub_url, content, "IMAGE")
                # EC20/EC21: Check for error in response body even on apparent success
                if isinstance(result, dict) and result.get("error"):
                    raise Exception(str(result["error"]))
                platform_post_id = str(result.get("id", result) if isinstance(result, dict) else result)
                await _write_idempotency_key(idem_key, platform_post_id)
                return {"status": "success", "platform_post_id": platform_post_id}

        elif platform == "facebook":
            from app.social.facebook import FacebookAuth
            fb = FacebookAuth()
            page_id = account.get("platform_user_id", "")
            page_token = account.get("page_access_token", access_token)
            if media_url:
                result = await fb.publish_to_facebook(page_token, page_id, media_url, content)
            else:
                async with httpx.AsyncClient() as http_client:
                    resp = await http_client.post(
                        f"https://graph.facebook.com/{os.environ.get('FACEBOOK_API_VERSION', 'v21.0')}/{page_id}/feed",
                        data={"message": content, "access_token": page_token}
                    )
                    resp.raise_for_status()
                    result = resp.json()
            # EC20: Facebook returns HTTP 200 with {"error": {...}} on soft failures
            if isinstance(result, dict) and result.get("error"):
                err = result["error"]
                raise Exception(f"Facebook API error: {err.get('message', str(err))}")
            platform_post_id = str(result.get("id", result) if isinstance(result, dict) else result)
            await _write_idempotency_key(idem_key, platform_post_id)
            return {"status": "success", "platform_post_id": platform_post_id}

        elif platform == "linkedin":
            from app.social.linkedin import LinkedInAuth
            li = LinkedInAuth()
            person_urn = account.get("platform_user_id", "")
            result = await li.publish_post(access_token, person_urn, content, media_urls)
            platform_post_id = str(result or "")
            await _write_idempotency_key(idem_key, platform_post_id)
            return {"status": "success", "platform_post_id": platform_post_id}

        elif platform == "youtube":
            from app.social.google import GoogleAuth
            yt = GoogleAuth()
            if not video_url:
                return {"status": "failed", "error": "YouTube requires a video file"}

            title = post_doc.get("video_title") or "Untitled"
            cover_image = post_doc.get("cover_image_url")
            tmp_path = None

            try:
                ext = video_url.rsplit(".", 1)[-1].lower() if "." in video_url.split("/")[-1] else "mp4"
                tmp_path = await _download_url_to_temp(video_url, suffix=f".{ext}")
                if not tmp_path:
                    return {"status": "failed", "error": "Failed to download video for YouTube upload"}

                privacy = post_doc.get("youtube_privacy", "public")
                try:
                    result = await yt.upload_video(access_token, tmp_path, title, content, cover_image_path=cover_image, privacy_status=privacy)
                    platform_post_id = str(result or "")
                    await _write_idempotency_key(idem_key, platform_post_id)
                    return {"status": "success", "platform_post_id": platform_post_id}
                except ValueError as e:
                    if "AuthError" in str(e):
                        # EC18: Distributed lock prevents concurrent token refresh race
                        refresh_token = account.get("refresh_token", "")
                        if refresh_token:
                            lock_key = f"token_refresh_lock:{account_id}"
                            try:
                                r = await _get_redis()
                                acquired = await r.set(lock_key, "1", nx=True, ex=30)
                                if not acquired:
                                    # Another worker is refreshing — wait then re-read token from DB
                                    await asyncio.sleep(5)
                                    _db = get_db()
                                    fresh_acct = await _db.social_accounts.find_one({"id": account_id}, {"_id": 0})
                                    new_access = (fresh_acct or {}).get("access_token", access_token)
                                else:
                                    new_tokens = await yt.refresh_access_token(refresh_token)
                                    new_access = new_tokens.get("access_token", "")
                                    if new_access:
                                        _db = get_db()
                                        await _db.social_accounts.update_one(
                                            {"id": account_id},
                                            {"$set": {"access_token": new_access, "token_refreshed_at": datetime.now(timezone.utc).isoformat()}}
                                        )
                                    await r.delete(lock_key)
                                if new_access:
                                    result = await yt.upload_video(new_access, tmp_path, title, content, cover_image_path=cover_image, privacy_status=privacy)
                                    platform_post_id = str(result or "")
                                    await _write_idempotency_key(idem_key, platform_post_id)
                                    return {"status": "success", "platform_post_id": platform_post_id}
                            except Exception as refresh_err:
                                return {"status": "failed", "error": f"Token refresh failed: {refresh_err}"}
                    raise  # re-raise for outer handler
            finally:
                if tmp_path:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

        elif platform == "tiktok":
            from app.social.tiktok import TikTokAuth
            tiktok = TikTokAuth()
            if not video_url:
                return {"status": "failed", "error": "TikTok requires a video file"}
            tiktok_privacy = post_doc.get("tiktok_privacy", "SELF_ONLY")
            tiktok_allow_duet = post_doc.get("tiktok_allow_duet", False)
            tiktok_allow_stitch = post_doc.get("tiktok_allow_stitch", False)
            tiktok_allow_comment = post_doc.get("tiktok_allow_comment", True)
            result = await tiktok.publish_video(
                access_token=access_token,
                video_url=video_url,
                caption=content,
                privacy=tiktok_privacy,
                allow_duet=tiktok_allow_duet,
                allow_stitch=tiktok_allow_stitch,
                allow_comments=tiktok_allow_comment,
            )
            # EC20/EC21: TikTok error check in body
            if isinstance(result, dict) and result.get("error", {}).get("code", 0) != 0:
                raise Exception(f"TikTok error: {result['error']}")
            publish_id = result.get("publish_id", "") if isinstance(result, dict) else str(result or "")
            await _write_idempotency_key(idem_key, publish_id)
            return {"status": "success", "platform_post_id": publish_id}

        elif platform == "discord":
            from app.social.discord import DiscordWebhook
            from utils.encryption import decrypt
            # access_token for Discord is the encrypted webhook URL
            try:
                webhook_url = decrypt(access_token)
            except Exception:
                return {"status": "failed", "error": "Discord webhook URL could not be decrypted — reconnect the channel", "permanent": True}

            channel_label = account.get("platform_username", "Discord channel")
            await DiscordWebhook.post_message(webhook_url, content, username="SocialEntangler")
            await _write_idempotency_key(idem_key, f"discord_{account_id}")
            return {"status": "success", "platform_post_id": f"discord_{account_id}"}

        elif platform in ("bluesky", "threads"):
            return {"status": "failed", "error": f"{platform.title()} publishing not yet configured"}

        else:
            return {"status": "failed", "error": f"Unknown platform: {platform}"}

    except Exception as e:
        error_str = str(e)
        logger.error(f"[{trace_id}] Platform {platform} publish error: {error_str}")

        # EC24: Revocation → mark account inactive (don't retry)
        if is_revocation_error(error_str, platform) and account_id:
            try:
                _db = get_db()
                await _db.social_accounts.update_one(
                    {"id": account_id},
                    {"$set": {"is_active": False, "disconnected_reason": "permission_revoked", "disconnected_at": datetime.now(timezone.utc).isoformat()}}
                )
                logger.warning(f"[{trace_id}] EC24: {platform} account {account_id} marked inactive — permission revoked")
            except Exception:
                pass
            return {"status": "failed", "error": f"Permission revoked on {platform}: {error_str}", "permanent": True}

        # EC16: Ghost account — platform banned/suspended the linked account.
        # Mark account inactive and cascade all queued posts on this platform to permanently_failed.
        if is_ghost_account_error(error_str, platform) and account_id:
            try:
                _db = get_db()
                account_doc = await _db.social_accounts.find_one({"id": account_id}, {"_id": 0, "user_id": 1})
                user_id = (account_doc or {}).get("user_id")
                await _db.social_accounts.update_one(
                    {"id": account_id},
                    {"$set": {"is_active": False, "disconnected_reason": "account_banned_by_platform",
                              "disconnected_at": datetime.now(timezone.utc).isoformat()}}
                )
                logger.warning(f"[{trace_id}] EC16: {platform} account {account_id} marked inactive — account banned/suspended by platform")
                # Cascade: mark all queued/publishing posts on this platform as permanently_failed
                if user_id:
                    result = await _db.posts.update_many(
                        {"user_id": user_id, "platforms": platform, "status": {"$in": ["scheduled", "publishing"]}},
                        {"$set": {
                            f"platform_results.{platform}.status": "permanently_failed",
                            f"platform_results.{platform}.error": f"Account banned/suspended by {platform}",
                            f"platform_results.{platform}.permanent_reason": "ghost_account_detected",
                        }}
                    )
                    logger.warning(f"[{trace_id}] EC16: Cascaded {result.modified_count} queued posts to permanently_failed — ghost account on {platform}")
            except Exception as _ghost_err:
                logger.error(f"[{trace_id}] EC16: Ghost account cascade error: {_ghost_err}")
            return {"status": "failed", "error": f"Account banned/suspended on {platform}: {error_str}", "permanent": True}

        if is_rate_limit_error(error_str):
            record_account_rate_limit(account_id, platform)
            return {
                "status": "failed",
                "error": error_str,
                "rate_limited": True,
                "retry_after_seconds": extract_retry_after(error_str),
            }
        return {"status": "failed", "error": error_str}


async def _cleanup_post_media(post_doc: dict):
    """Delete R2 objects and local files for a post after it reaches terminal state."""
    import boto3
    from botocore.client import Config

    media_urls = post_doc.get("media_urls", [])
    video_url = post_doc.get("video_url")
    all_urls = [u for u in media_urls + ([video_url] if video_url else []) if u]

    storage_backend = os.environ.get("STORAGE_BACKEND", "local")

    for url in all_urls:
        try:
            if storage_backend == "r2" and "r2.cloudflarestorage.com" in url:
                # Extract object key from URL and delete from R2
                r2_bucket = os.environ.get("CLOUDFLARE_R2_BUCKET_NAME", "socialentangler-media")
                # URL format: https://{endpoint}/{bucket}/{key} or https://{cdn}/{key}
                parts = url.split(r2_bucket + "/", 1)
                if len(parts) == 2:
                    object_key = parts[1].split("?")[0]
                    s3 = boto3.client(
                        "s3",
                        endpoint_url=os.environ.get("CLOUDFLARE_R2_ENDPOINT"),
                        aws_access_key_id=os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID"),
                        aws_secret_access_key=os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY"),
                        config=Config(signature_version="s3v4"),
                        region_name="auto",
                    )
                    s3.delete_object(Bucket=r2_bucket, Key=object_key)
                    logger.info(f"Deleted R2 object: {object_key}")
            elif url.startswith("/uploads/") or url.startswith("file://"):
                local_path = url.replace("file://", "").replace("/uploads/", "/app/uploads/")
                if os.path.exists(local_path):
                    os.unlink(local_path)
                    logger.info(f"Deleted local file: {local_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup media {url}: {e}")


async def _finalise_post_status(db, post_id: str, post_doc: dict, platform_results: dict, now: datetime):
    """
    Compute overall post status from platform_results and write to MongoDB.
    Sends DLQ notification if all terminal and any permanently failed.
    """
    statuses = [pr["status"] for pr in platform_results.values()]
    all_success = all(s == "success" for s in statuses)
    all_terminal = all(s in ("success", "permanently_failed") for s in statuses)
    any_success = any(s == "success" for s in statuses)

    if all_success:
        post_status = "published"
    elif all_terminal and any_success:
        post_status = "partial"
    elif all_terminal and not any_success:
        post_status = "failed"
    else:
        post_status = "publishing"

    update_fields = {
        "platform_results": platform_results,
        "status": post_status,
        "updated_at": now.isoformat(),
    }
    if post_status == "published":
        update_fields["published_at"] = now.isoformat()

    failed_platforms = {
        p: pr.get("error", "Unknown")
        for p, pr in platform_results.items()
        if pr["status"] == "permanently_failed"
    }
    if failed_platforms:
        update_fields["failure_reason"] = "; ".join(f"{p}: {err}" for p, err in failed_platforms.items())

    # EC17: Write Redis confirmation BEFORE MongoDB so a Mongo timeout after a
    # successful publish never causes a phantom re-publish on the next worker run.
    try:
        r = await _get_redis()
        import json as _json
        for plat, pr in platform_results.items():
            if pr["status"] == "success":
                await r.setex(
                    f"published:{post_id}:{plat}",
                    172800,  # 48-hour TTL
                    _json.dumps({"platform_post_id": pr.get("platform_post_id", ""), "at": now.isoformat()}),
                )
    except Exception as _re:
        logger.warning(f"Redis confirmation write failed for {post_id}: {_re}")

    await db.posts.update_one({"id": post_id}, {"$set": update_fields})

    # Clean up media files when post reaches a terminal state
    if post_status in ("published", "failed", "partial") and all_terminal:
        try:
            await _cleanup_post_media(post_doc)
        except Exception as e:
            logger.warning(f"Media cleanup failed for post {post_id}: {e}")

    # Notify via Redis pubsub (best-effort — never fail a publish because of it)
    await _notify_post_update_task(db, post_doc.get("user_id", ""), post_id, post_status, platform_results)

    if post_status in ("failed", "partial") and all_terminal:
        user_doc = await db.users.find_one(
            {"user_id": post_doc["user_id"]},
            {"_id": 0, "email": 1, "name": 1}
        )
        if user_doc and RESEND_API_KEY:
            trace_id = post_doc.get("trace_id", "")
            await _send_dlq_notification(user_doc, post_doc, failed_platforms, trace_id, platform_results)


_redis_pool: Optional[Any] = None


async def _get_redis():
    global _redis_pool
    import redis.asyncio as aioredis
    if _redis_pool is None:
        _redis_pool = aioredis.ConnectionPool.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            max_connections=10,
            decode_responses=True,
        )
    return aioredis.Redis(connection_pool=_redis_pool)


async def _write_idempotency_key(idem_key: str, platform_post_id: str):
    """EC1: Write idempotency key after successful publish so duplicate runs are no-ops."""
    try:
        import json as _json
        r = await _get_redis()
        await r.setex(idem_key, 86400, _json.dumps({"platform_post_id": platform_post_id}))
    except Exception as e:
        logger.warning(f"EC1: Failed to write idempotency key {idem_key}: {e}")


async def _convert_gif_to_mp4(gif_url: str, trace_id: str) -> Optional[str]:
    """
    EC30: Download a GIF and convert it to MP4 using ffmpeg.
    Returns path to the converted MP4 (in /tmp) or None on failure.
    Twitter's media upload API accepts native GIF or MP4; MP4 is preferred for animated content.
    ffmpeg args are passed as a fixed list — no shell interpolation, no injection risk.
    """
    import uuid as _uuid
    import asyncio as _asyncio
    import httpx as _httpx

    tmp_gif = f"/tmp/gif_{_uuid.uuid4().hex}.gif"
    tmp_mp4 = f"/tmp/gif_{_uuid.uuid4().hex}.mp4"

    try:
        async with _httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(gif_url)
            resp.raise_for_status()
            with open(tmp_gif, "wb") as f:
                f.write(resp.content)

        # Safe: using create_subprocess_exec with a fixed argument list (no shell=True)
        ffmpeg_args = [
            "ffmpeg", "-y", "-i", tmp_gif,
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            tmp_mp4,
        ]
        proc = await _asyncio.create_subprocess_exec(
            *ffmpeg_args,
            stdout=_asyncio.subprocess.DEVNULL,
            stderr=_asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()
        if proc.returncode == 0 and os.path.exists(tmp_mp4):
            return tmp_mp4
    except Exception as e:
        logger.warning(f"[{trace_id}] EC30: GIF conversion error: {e}")
    finally:
        if os.path.exists(tmp_gif):
            os.remove(tmp_gif)

    return None


async def _notify_post_update_task(db, user_id: str, post_id: str, status: str, platform_results: dict):
    """Push a post-update event to the Redis pubsub channel for SSE delivery. Best-effort."""
    try:
        import json
        r = await _get_redis()
        payload = json.dumps({"post_id": post_id, "status": status, "platform_results": platform_results})
        await r.publish(f"post_updates:{user_id}", payload)
    except Exception:
        pass  # SSE is best-effort


async def _send_dlq_notification(user_doc: dict, post_doc: dict, failed_platforms: dict, trace_id: str, platform_results: dict):
    """Send email showing per-platform results for permanently failed posts."""
    if not RESEND_API_KEY:
        return

    import resend as resend_lib
    resend_lib.api_key = RESEND_API_KEY

    email = user_doc.get("email")
    name = user_doc.get("name", "there")
    content_preview = (post_doc.get("content", "") or "")[:100]

    platform_rows = ""
    for platform, pr in platform_results.items():
        if pr["status"] == "success":
            platform_rows += (
                f'<tr><td style="padding:8px;border-bottom:1px solid #eee;">{platform.title()}</td>'
                f'<td style="padding:8px;border-bottom:1px solid #eee;color:#16A34A;">Published</td></tr>'
            )
        elif pr["status"] == "permanently_failed":
            err = pr.get("error", "Unknown error")[:120]
            platform_rows += (
                f'<tr><td style="padding:8px;border-bottom:1px solid #eee;">{platform.title()}</td>'
                f'<td style="padding:8px;border-bottom:1px solid #eee;color:#DC2626;">Failed after 3 attempts: {err}</td></tr>'
            )
        else:
            platform_rows += (
                f'<tr><td style="padding:8px;border-bottom:1px solid #eee;">{platform.title()}</td>'
                f'<td style="padding:8px;border-bottom:1px solid #eee;color:#D97706;">Retrying ({pr.get("retries", 0)}/3)</td></tr>'
            )

    failed_count = len(failed_platforms)
    total_count = len(platform_results)
    succeeded_count = sum(1 for pr in platform_results.values() if pr["status"] == "success")

    subject_line = (
        f"Post failed on {failed_count} platform{'s' if failed_count > 1 else ''} - SocialEntangler"
        if succeeded_count > 0
        else "Post failed to publish - SocialEntangler"
    )

    html_content = f"""<!DOCTYPE html>
<html>
<head>
<style>
  body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
  .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
  .alert {{ background: #FEF2F2; border-left: 4px solid #EF4444; padding: 16px; border-radius: 4px; margin: 16px 0; }}
  .code {{ background: #F3F4F6; padding: 4px 8px; border-radius: 4px; font-family: monospace; font-size: 12px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
</style>
</head>
<body>
<div class="container">
  <h2>Publishing Report</h2>
  <p>Hi {name},</p>
  <p>Your post was published to <strong>{succeeded_count}/{total_count}</strong> platforms.
     {f'{failed_count} platform{"s" if failed_count > 1 else ""} failed after 3 retry attempts.' if failed_count else ''}</p>
  <div class="alert">
    <p><strong>Content:</strong> {content_preview}{'...' if len(post_doc.get('content', '')) > 100 else ''}</p>
    <p><strong>Trace ID:</strong> <span class="code">{trace_id}</span></p>
  </div>
  <h3>Platform Results</h3>
  <table>
    <thead><tr>
      <th style="text-align:left;padding:8px;border-bottom:2px solid #ddd;">Platform</th>
      <th style="text-align:left;padding:8px;border-bottom:2px solid #ddd;">Status</th>
    </tr></thead>
    <tbody>{platform_rows}</tbody>
  </table>
  <p>You can retry failed platforms from your <a href="{FRONTEND_URL}/content">Content Library</a>.</p>
  <p style="color:#888;font-size:12px;">If this keeps happening, contact support with Trace ID: <span class="code">{trace_id}</span></p>
</div>
</body>
</html>"""

    try:
        import asyncio as _asyncio
        params = {
            "from": SENDER_EMAIL,
            "to": [email],
            "subject": subject_line,
            "html": html_content,
        }
        await _asyncio.to_thread(resend_lib.Emails.send, params)
        logger.info(f"DLQ notification sent to {email} for post {post_doc.get('id')}")
    except Exception as e:
        logger.error(f"Failed to send DLQ notification: {e}")


# ── Celery Tasks ──────────────────────────────────────────────────────────────

@celery_app.task(
    name="celery_tasks.process_scheduled_posts_task",
    bind=True,
    max_retries=0,
    soft_time_limit=25,
    time_limit=28,
)
@async_task
async def process_scheduled_posts_task(self):
    """
    Process all posts due for publishing.
    Runs every 30 seconds via Beat schedule.
    """
    if is_shutdown_requested():
        logger.info("Shutdown requested, skipping process_scheduled_posts_task")
        return

    db = get_db()
    import uuid as _uuid

    try:
        now = datetime.now(timezone.utc)

        # Atomically claim up to 50 posts due for processing.
        claimed_posts = []
        for _ in range(50):
            claimed = await db.posts.find_one_and_update(
                {
                    "status": {"$in": ["scheduled", "publishing"]},
                    "scheduled_time": {"$lte": now.isoformat()},
                    "$or": [
                        {"claimed_at": {"$exists": False}},
                        {"claimed_at": {"$lte": (now - timedelta(minutes=5)).isoformat()}}
                    ]
                },
                {"$set": {"claimed_at": now.isoformat()}},
                return_document=True
            )
            if not claimed:
                break
            claimed_posts.append(claimed)

        if not claimed_posts:
            return

        logger.info(f"Celery claimed {len(claimed_posts)} posts for processing")

        for post_doc in claimed_posts:
            post_id = post_doc["id"]
            user_id = post_doc["user_id"]
            trace_id = post_doc.get("trace_id") or str(_uuid.uuid4())[:8]
            platforms = post_doc.get("platforms", [])
            platform_results = post_doc.get("platform_results", {})

            # Initialise missing platform entries
            for p in platforms:
                if p not in platform_results:
                    platform_results[p] = {"status": "pending", "retries": 0}

            # Load user's connected accounts
            user_accounts = await db.social_accounts.find(
                {"user_id": user_id, "is_active": True}, {"_id": 0}
            ).to_list(100)
            accounts_by_platform = {acc["platform"]: acc for acc in user_accounts}

            # Process each platform independently
            for platform in platforms:
                pr = platform_results.get(platform, {"status": "pending", "retries": 0})

                if pr["status"] in ("success", "permanently_failed"):
                    continue

                if pr["status"] == "awaiting_ig_processing":
                    continue

                next_retry_at = pr.get("next_retry_at")
                if next_retry_at:
                    try:
                        retry_dt = datetime.fromisoformat(next_retry_at)
                        if retry_dt.tzinfo is None:
                            retry_dt = retry_dt.replace(tzinfo=timezone.utc)
                        if retry_dt > now:
                            logger.debug(f"[{trace_id}] {platform}: backoff until {next_retry_at}, skipping")
                            continue
                    except Exception:
                        pass

                if pr.get("retries", 0) >= MAX_RETRIES:
                    pr["status"] = "permanently_failed"
                    platform_results[platform] = pr
                    continue

                if not check_rate_limit(user_id, platform):
                    logger.warning(f"[{trace_id}] {platform} rate limit — skipping (not a failure)")
                    continue

                account = accounts_by_platform.get(platform)
                if not account:
                    pr["status"] = "permanently_failed"
                    pr["error"] = f"No connected {platform} account found"
                    platform_results[platform] = pr
                    continue

                jitter_secs = random.uniform(0, 15)
                await asyncio.sleep(jitter_secs)

                logger.info(
                    f"[{trace_id}] Publishing post {post_id} to {platform} "
                    f"(attempt {pr.get('retries', 0) + 1}/{MAX_RETRIES})"
                )
                result = await publish_to_platform(platform, account, post_doc, trace_id)

                if result["status"] == "success":
                    pr["status"] = "success"
                    pr["platform_post_id"] = result.get("platform_post_id", "")
                    pr["published_at"] = now.isoformat()
                    pr.pop("next_retry_at", None)
                    logger.info(f"[{trace_id}] {platform} succeeded for post {post_id}")

                elif result["status"] == "awaiting_ig_processing":
                    pr["status"] = "awaiting_ig_processing"
                    pr["container_id"] = result.get("container_id")
                    pr["access_token_snapshot"] = account.get("access_token", "")
                    pr["ig_user_id_snapshot"] = account.get("platform_user_id", "")
                    logger.info(
                        f"[{trace_id}] Instagram video container {result.get('container_id')} "
                        f"created — awaiting processing"
                    )

                elif result.get("rate_limited"):
                    retry_after = result.get("retry_after_seconds", 3600)
                    record_rate_limit_hit(user_id, platform, retry_after)
                    logger.warning(f"[{trace_id}] {platform} 429 — paused {retry_after}s, not counted as retry")

                else:
                    pr["retries"] = pr.get("retries", 0) + 1
                    pr["error"] = result.get("error", "Unknown error")
                    pr["last_attempt"] = now.isoformat()

                    # EC5: Classify permanent errors — never retry, prevents account bans
                    is_perm = result.get("permanent", False) or is_permanent_error(pr["error"], platform)

                    if is_perm or pr["retries"] >= MAX_RETRIES:
                        pr["status"] = "permanently_failed"
                        pr["permanent_reason"] = "error_classified_permanent" if is_perm else "max_retries_exceeded"
                        logger.error(
                            f"[{trace_id}] {platform} permanently failed for post {post_id}: {pr['error']}"
                        )
                    else:
                        pr["status"] = "failed"
                        pr["next_retry_at"] = get_next_retry_at(pr["retries"]).isoformat()
                        logger.warning(
                            f"[{trace_id}] {platform} attempt {pr['retries']}/{MAX_RETRIES}, "
                            f"next retry at {pr['next_retry_at']}"
                        )

                platform_results[platform] = pr

            await _finalise_post_status(db, post_id, post_doc, platform_results, now)

    except Exception as e:
        logger.error(f"process_scheduled_posts_task error: {e}", exc_info=True)
        raise


@celery_app.task(
    name="celery_tasks.check_instagram_containers_task",
    bind=True,
    max_retries=0,
    soft_time_limit=25,
    time_limit=28,
)
@async_task
async def check_instagram_containers_task(self):
    """
    Poll Instagram video containers that are still processing.
    Non-blocking — never holds the thread waiting for Instagram.
    Runs every 30 seconds via Beat schedule.
    """
    if is_shutdown_requested():
        logger.info("Shutdown requested, skipping check_instagram_containers_task")
        return

    db = get_db()

    try:
        now = datetime.now(timezone.utc)
        posts = await db.posts.find(
            {"status": "publishing", "platform_results.instagram.status": "awaiting_ig_processing"},
            {"_id": 0}
        ).to_list(50)

        for post_doc in posts:
            post_id = post_doc["id"]
            trace_id = post_doc.get("trace_id", "")
            platform_results = post_doc.get("platform_results", {})
            ig_pr = platform_results.get("instagram", {})
            container_id = ig_pr.get("container_id")
            access_token = ig_pr.get("access_token_snapshot", "")
            ig_user_id = ig_pr.get("ig_user_id_snapshot", "")

            if not container_id:
                continue

            # EC4: Container expiry — Instagram containers expire after 24h.
            # If expired, mark permanently failed so a new container is created on retry.
            container_created_at_str = ig_pr.get("container_created_at")
            if container_created_at_str:
                try:
                    container_created_at = datetime.fromisoformat(container_created_at_str)
                    if container_created_at.tzinfo is None:
                        container_created_at = container_created_at.replace(tzinfo=timezone.utc)
                    if (now - container_created_at).total_seconds() > 82800:  # 23h safety margin
                        ig_pr["status"] = "permanently_failed"
                        ig_pr["error"] = "Instagram video container expired (24h limit) — requeue to re-create"
                        platform_results["instagram"] = ig_pr
                        await _finalise_post_status(db, post_id, post_doc, platform_results, now)
                        logger.warning(f"[{trace_id}] EC4: Instagram container {container_id} expired for post {post_id}")
                        continue
                except Exception:
                    pass

            try:
                from app.social.instagram import InstagramAuth
                ig = InstagramAuth()
                status_code = await ig.check_container_status(access_token, container_id)

                if status_code == "FINISHED":
                    try:
                        publish_result = await ig.publish_container(access_token, ig_user_id, container_id)
                        ig_pr["status"] = "success"
                        ig_pr["platform_post_id"] = str(publish_result or "")
                        ig_pr["published_at"] = now.isoformat()
                        logger.info(f"[{trace_id}] Instagram container {container_id} published for post {post_id}")
                    except Exception as pub_err:
                        err_str = str(pub_err)
                        # EC29: Error code 9007 = media already published — treat as success
                        if "9007" in err_str or "already been published" in err_str.lower():
                            logger.info(f"[{trace_id}] EC29: Instagram container already published (9007) — treating as success")
                            ig_pr["status"] = "success"
                            ig_pr["platform_post_id"] = container_id  # use container_id as fallback post ID
                            ig_pr["published_at"] = now.isoformat()
                        else:
                            raise

                elif status_code == "ERROR":
                    ig_pr["retries"] = ig_pr.get("retries", 0) + 1
                    if ig_pr["retries"] >= MAX_RETRIES:
                        ig_pr["status"] = "permanently_failed"
                        ig_pr["error"] = "Instagram video processing failed"
                    else:
                        ig_pr["status"] = "failed"
                        ig_pr["error"] = "Instagram video processing error — will retry"
                        ig_pr["next_retry_at"] = get_next_retry_at(ig_pr["retries"]).isoformat()
                    logger.error(f"[{trace_id}] Instagram container {container_id} ERROR for post {post_id}")

                else:
                    # Still IN_PROGRESS — check again next tick
                    logger.debug(f"[{trace_id}] Instagram container {container_id} still processing ({status_code})")
                    continue

            except Exception as e:
                logger.error(f"[{trace_id}] Instagram container check failed: {e}")
                continue

            platform_results["instagram"] = ig_pr
            await _finalise_post_status(db, post_id, post_doc, platform_results, now)

    except Exception as e:
        logger.error(f"check_instagram_containers_task error: {e}", exc_info=True)
        raise


@celery_app.task(
    name="celery_tasks.expire_pending_review_task",
    bind=True,
    max_retries=0,
    soft_time_limit=25,
    time_limit=28,
)
@async_task
async def expire_pending_review_task(self):
    """
    Expire posts stuck in pending_review past their scheduled_time.
    Runs every 5 minutes via Beat schedule.
    """
    if is_shutdown_requested():
        logger.info("Shutdown requested, skipping expire_pending_review_task")
        return

    db = get_db()
    now = datetime.now(timezone.utc)

    try:
        result = await db.posts.update_many(
            {
                "status": "pending_review",
                "scheduled_time": {"$lt": now.isoformat()},
            },
            {"$set": {"status": "expired_approval"}},
        )
        if result.modified_count:
            logger.info(f"Expired {result.modified_count} pending_review posts")
    except Exception as e:
        logger.error(f"expire_pending_review_task error: {e}", exc_info=True)
        raise


@celery_app.task(
    name="celery_tasks.beat_heartbeat_task",
    bind=True,
    max_retries=0,
    soft_time_limit=5,
    time_limit=8,
)
@async_task
async def beat_heartbeat_task(self):
    """Write beat_tick_at to Redis. If this key is older than 90s, Beat is unhealthy."""
    r = await _get_redis()
    await r.set("beat_tick_at", datetime.now(timezone.utc).isoformat(), ex=120)


# ── EC6: Proactive OAuth Token Refresh ───────────────────────────────────────

@celery_app.task(
    name="celery_tasks.refresh_expiring_tokens_task",
    bind=True,
    max_retries=0,
    soft_time_limit=120,
    time_limit=150,
)
@async_task
async def refresh_expiring_tokens_task(self):
    """
    EC6: Proactively refresh OAuth tokens expiring within the next 24 hours.
    Runs every 30 minutes via Beat. Covers Instagram, Facebook, LinkedIn,
    Twitter, and TikTok (YouTube token refresh already happens inline in
    publish_to_platform).
    """
    db = _get_db()
    now = datetime.now(timezone.utc)
    refresh_window = now + timedelta(hours=24)

    # Find active accounts with tokens expiring soon
    cursor = db.social_accounts.find({
        "is_active": True,
        "refresh_token": {"$exists": True, "$ne": None},
        "token_expiry": {"$gt": now.isoformat(), "$lt": refresh_window.isoformat()},
        "platform": {"$in": ["instagram", "facebook", "linkedin", "twitter", "tiktok"]},
    })

    refreshed = failed = 0
    async for account in cursor:
        platform = account.get("platform", "")
        account_id = account.get("id", "")
        refresh_token = account.get("refresh_token", "")
        if not refresh_token or not account_id:
            continue

        # Distributed lock so only one worker refreshes at a time per account (EC18)
        lock_key = f"token_refresh_lock:{account_id}"
        try:
            r = await _get_redis()
            acquired = await r.set(lock_key, "1", nx=True, ex=60)
            if not acquired:
                continue  # Another worker is handling this account

            new_access = new_refresh = new_expiry = None

            if platform == "instagram":
                import httpx as _httpx
                async with _httpx.AsyncClient() as client:
                    resp = await client.get(
                        "https://graph.instagram.com/refresh_access_token",
                        params={"grant_type": "ig_refresh_token", "access_token": account.get("access_token", "")},
                    )
                    data = resp.json()
                if data.get("access_token"):
                    new_access = data["access_token"]
                    expires_in = int(data.get("expires_in", 5184000))  # 60 days default
                    new_expiry = (now + timedelta(seconds=expires_in)).isoformat()

            elif platform == "facebook":
                import httpx as _httpx
                fb_app_id = os.environ.get("FACEBOOK_APP_ID", "")
                fb_app_secret = os.environ.get("FACEBOOK_APP_SECRET", "")
                if fb_app_id and fb_app_secret:
                    async with _httpx.AsyncClient() as client:
                        resp = await client.get(
                            "https://graph.facebook.com/oauth/access_token",
                            params={
                                "grant_type": "fb_exchange_token",
                                "client_id": fb_app_id,
                                "client_secret": fb_app_secret,
                                "fb_exchange_token": account.get("access_token", ""),
                            },
                        )
                        data = resp.json()
                    if data.get("access_token"):
                        new_access = data["access_token"]
                        expires_in = int(data.get("expires_in", 5184000))
                        new_expiry = (now + timedelta(seconds=expires_in)).isoformat()

            elif platform == "linkedin":
                import httpx as _httpx
                li_client_id = os.environ.get("LINKEDIN_CLIENT_ID", "")
                li_client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET", "")
                if li_client_id and li_client_secret:
                    async with _httpx.AsyncClient() as client:
                        resp = await client.post(
                            "https://www.linkedin.com/oauth/v2/accessToken",
                            data={
                                "grant_type": "refresh_token",
                                "refresh_token": refresh_token,
                                "client_id": li_client_id,
                                "client_secret": li_client_secret,
                            },
                        )
                        data = resp.json()
                    if data.get("access_token"):
                        new_access = data["access_token"]
                        new_refresh = data.get("refresh_token", refresh_token)
                        expires_in = int(data.get("expires_in", 5184000))
                        new_expiry = (now + timedelta(seconds=expires_in)).isoformat()

            elif platform == "twitter":
                import httpx as _httpx
                import base64 as _base64
                tw_client_id = os.environ.get("TWITTER_CLIENT_ID", "")
                tw_client_secret = os.environ.get("TWITTER_CLIENT_SECRET", "")
                if tw_client_id and tw_client_secret:
                    creds = _base64.b64encode(f"{tw_client_id}:{tw_client_secret}".encode()).decode()
                    async with _httpx.AsyncClient() as client:
                        resp = await client.post(
                            "https://api.twitter.com/2/oauth2/token",
                            headers={"Authorization": f"Basic {creds}"},
                            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
                        )
                        data = resp.json()
                    if data.get("access_token"):
                        new_access = data["access_token"]
                        new_refresh = data.get("refresh_token", refresh_token)
                        expires_in = int(data.get("expires_in", 7200))
                        new_expiry = (now + timedelta(seconds=expires_in)).isoformat()

            elif platform == "tiktok":
                import httpx as _httpx
                tk_client_key = os.environ.get("TIKTOK_CLIENT_KEY", "")
                tk_client_secret = os.environ.get("TIKTOK_CLIENT_SECRET", "")
                if tk_client_key and tk_client_secret:
                    async with _httpx.AsyncClient() as client:
                        resp = await client.post(
                            "https://open.tiktokapis.com/v2/oauth/token/",
                            data={
                                "client_key": tk_client_key,
                                "client_secret": tk_client_secret,
                                "grant_type": "refresh_token",
                                "refresh_token": refresh_token,
                            },
                        )
                        data = resp.json()
                    if data.get("data", {}).get("access_token"):
                        new_access = data["data"]["access_token"]
                        new_refresh = data["data"].get("refresh_token", refresh_token)
                        expires_in = int(data["data"].get("expires_in", 86400))
                        new_expiry = (now + timedelta(seconds=expires_in)).isoformat()

            if new_access:
                update_fields: dict = {
                    "access_token": new_access,
                    "updated_at": now.isoformat(),
                }
                if new_refresh:
                    update_fields["refresh_token"] = new_refresh
                if new_expiry:
                    update_fields["token_expiry"] = new_expiry
                await db.social_accounts.update_one(
                    {"id": account_id},
                    {"$set": update_fields}
                )
                refreshed += 1
                logger.info(f"EC6: Proactively refreshed {platform} token for account {account_id}")
            else:
                failed += 1
                logger.warning(f"EC6: Token refresh skipped/failed for {platform} account {account_id}")

        except Exception as exc:
            failed += 1
            logger.error(f"EC6: Token refresh error for account {account_id}: {exc}")
        finally:
            try:
                r = await _get_redis()
                await r.delete(lock_key)
            except Exception:
                pass

    logger.info(f"EC6: Token refresh sweep done — refreshed={refreshed} failed={failed}")
