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
from typing import Dict, Optional

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

BACKOFF_MINUTES = [5, 15, 60, 180]
MAX_RETRIES = 5


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

async def _download_url_to_temp(url: str, suffix: str = ".mp4") -> Optional[str]:
    """Download a URL to a temp file, return local path. Caller must delete."""
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
            result = await twitter.publish_tweet(access_token, content, media_urls or [])
            return {"status": "success", "platform_post_id": str(result or "")}

        elif platform == "instagram":
            from app.social.instagram import InstagramAuth
            ig = InstagramAuth()
            ig_user_id = account.get("platform_user_id", "")

            if video_url:
                container_id = await ig.create_video_container(access_token, ig_user_id, video_url, content)
                return {"status": "awaiting_ig_processing", "container_id": container_id}
            else:
                pub_url = media_url or ""
                result = await ig.publish_to_instagram(access_token, ig_user_id, pub_url, content, "IMAGE")
                return {"status": "success", "platform_post_id": str(result)}

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
                        f"https://graph.facebook.com/v19.0/{page_id}/feed",
                        data={"message": content, "access_token": page_token}
                    )
                    resp.raise_for_status()
                    result = resp.json().get("id", "")
            return {"status": "success", "platform_post_id": str(result)}

        elif platform == "linkedin":
            from app.social.linkedin import LinkedInAuth
            li = LinkedInAuth()
            person_urn = account.get("platform_user_id", "")
            result = await li.publish_post(access_token, person_urn, content, media_urls)
            return {"status": "success", "platform_post_id": str(result)}

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

                result = await yt.upload_video(access_token, tmp_path, title, content, cover_image_path=cover_image)
                return {"status": "success", "platform_post_id": str(result)}
            finally:
                if tmp_path:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

        elif platform == "tiktok":
            return {"status": "failed", "error": "TikTok publishing not yet configured — add credentials"}

        elif platform in ("bluesky", "threads"):
            return {"status": "failed", "error": f"{platform.title()} publishing not yet configured"}

        else:
            return {"status": "failed", "error": f"Unknown platform: {platform}"}

    except Exception as e:
        error_str = str(e)
        logger.error(f"[{trace_id}] Platform {platform} publish error: {error_str}")

        if is_rate_limit_error(error_str):
            return {
                "status": "failed",
                "error": error_str,
                "rate_limited": True,
                "retry_after_seconds": extract_retry_after(error_str),
            }
        return {"status": "failed", "error": error_str}


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

    await db.posts.update_one({"id": post_id}, {"$set": update_fields})

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


async def _notify_post_update_task(db, user_id: str, post_id: str, status: str, platform_results: dict):
    """Push a post-update event to the Redis pubsub channel for SSE delivery. Best-effort."""
    try:
        import json
        import redis.asyncio as aioredis
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        r = aioredis.from_url(redis_url, decode_responses=True)
        payload = json.dumps({"post_id": post_id, "status": status, "platform_results": platform_results})
        await r.publish(f"post_updates:{user_id}", payload)
        await r.aclose()
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

                    if pr["retries"] >= MAX_RETRIES:
                        pr["status"] = "permanently_failed"
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

            try:
                from app.social.instagram import InstagramAuth
                ig = InstagramAuth()
                status_code = await ig.check_container_status(access_token, container_id)

                if status_code == "FINISHED":
                    publish_result = await ig.publish_container(access_token, ig_user_id, container_id)
                    ig_pr["status"] = "success"
                    ig_pr["platform_post_id"] = publish_result
                    ig_pr["published_at"] = now.isoformat()
                    logger.info(
                        f"[{trace_id}] Instagram container {container_id} published for post {post_id}"
                    )

                elif status_code == "ERROR":
                    ig_pr["retries"] = ig_pr.get("retries", 0) + 1
                    if ig_pr["retries"] >= MAX_RETRIES:
                        ig_pr["status"] = "permanently_failed"
                        ig_pr["error"] = "Instagram video processing failed"
                    else:
                        ig_pr["status"] = "failed"
                        ig_pr["error"] = "Instagram video processing error — will retry"
                        ig_pr["next_retry_at"] = get_next_retry_at(ig_pr["retries"]).isoformat()
                    logger.error(
                        f"[{trace_id}] Instagram container {container_id} ERROR for post {post_id}"
                    )

                else:
                    # Still IN_PROGRESS — check again next tick
                    logger.debug(
                        f"[{trace_id}] Instagram container {container_id} still processing ({status_code})"
                    )
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
