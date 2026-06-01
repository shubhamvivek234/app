"""
Phase 6 — Platform analytics collection.
Collects post-publish metrics at 24h and 7d intervals.
Stores aggregated stats in analytics collection.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx

from celery_workers.async_runner import run_async
from celery_workers.celery_app import celery_app
from db.mongo import get_client
from utils.encryption import decrypt, encrypt
from utils.youtube_geography import (
    YOUTUBE_GEOGRAPHY_BACKGROUND_REFRESH_SECONDS,
    compute_youtube_settled_window,
    normalize_youtube_geography_rows,
    store_youtube_geography_snapshot,
)
from utils.tiktok_analytics import (
    TIKTOK_ANALYTICS_BACKGROUND_REFRESH_SECONDS,
    store_tiktok_analytics_snapshot,
)

logger = logging.getLogger(__name__)

# Beat registrations
celery_app.conf.beat_schedule.update({
    "collect-analytics-24h": {
        "task": "celery_workers.tasks.analytics.collect_analytics",
        "schedule": 6 * 3600,   # every 6 hours
        "args": ("24h",),
        "options": {"queue": "default"},
    },
    "collect-analytics-7d": {
        "task": "celery_workers.tasks.analytics.collect_analytics",
        "schedule": 24 * 3600,  # daily
        "args": ("7d",),
        "options": {"queue": "default"},
    },
    "refresh-youtube-geography-snapshots": {
        "task": "celery_workers.tasks.analytics.refresh_youtube_geography_snapshots",
        "schedule": YOUTUBE_GEOGRAPHY_BACKGROUND_REFRESH_SECONDS,
        "options": {"queue": "default"},
    },
    "refresh-tiktok-analytics-snapshots": {
        "task": "celery_workers.tasks.analytics.refresh_tiktok_analytics_snapshots",
        "schedule": TIKTOK_ANALYTICS_BACKGROUND_REFRESH_SECONDS,
        "options": {"queue": "default"},
    },
})


@celery_app.task(name="celery_workers.tasks.analytics.collect_analytics")
def collect_analytics(window: str = "24h") -> dict:
    """Collect engagement metrics for recently-published posts."""
    return run_async(_async_collect(window))


@celery_app.task(name="celery_workers.tasks.analytics.refresh_youtube_geography_snapshots")
def refresh_youtube_geography_snapshots() -> dict:
    """Refresh lag-adjusted YouTube geography snapshots for active accounts."""
    return run_async(_async_refresh_youtube_geography_snapshots())


@celery_app.task(name="celery_workers.tasks.analytics.refresh_tiktok_analytics_snapshots")
def refresh_tiktok_analytics_snapshots() -> dict:
    """Refresh daily TikTok analytics snapshots for active accounts."""
    return run_async(_async_refresh_tiktok_analytics_snapshots())


async def _async_collect(window: str) -> dict:
    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    now = datetime.now(timezone.utc)
    if window == "24h":
        since = now - timedelta(hours=24)
    else:
        since = now - timedelta(days=7)

    # Find posts published in the window
    cursor = db.posts.find(
        {
            "status": "published",
            "updated_at": {"$gte": since},
            "platform_results": {"$exists": True},
        },
        {"id": 1, "platforms": 1, "platform_results": 1, "workspace_id": 1},
        limit=500,
    )

    collected = 0
    async for post in cursor:
        for platform, result in post.get("platform_results", {}).items():
            platform_post_id = result.get("platform_post_id")
            if not platform_post_id or result.get("status") != "published":
                continue

            # Fetch metrics from platform API
            metrics = await _fetch_platform_metrics(
                db, platform, platform_post_id, post["workspace_id"]
            )
            if not metrics:
                continue

            # Upsert analytics document
            await db.analytics.update_one(
                {
                    "post_id": post["id"],
                    "platform": platform,
                    "window": window,
                },
                {
                    "$set": {
                        "post_id": post["id"],
                        "platform": platform,
                        "platform_post_id": platform_post_id,
                        "workspace_id": post["workspace_id"],
                        "window": window,
                        "metrics": metrics,
                        "collected_at": now,
                    }
                },
                upsert=True,
            )
            collected += 1

    logger.info("analytics: collected %d data points for window=%s", collected, window)
    return {"collected": collected, "window": window}


async def _get_youtube_worker_access_token(db, account: dict) -> str:
    encrypted_access_token = account.get("access_token")
    if not encrypted_access_token:
        raise ValueError("Missing YouTube access token")

    access_token = decrypt(encrypted_access_token)
    refresh_token_encrypted = account.get("refresh_token")

    expires_at = account.get("expires_at") or account.get("token_expiry")
    expires_dt = None
    if isinstance(expires_at, str) and expires_at:
        try:
            expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except Exception:
            expires_dt = None
    elif isinstance(expires_at, datetime):
        expires_dt = expires_at

    if isinstance(expires_dt, datetime) and expires_dt.tzinfo is None:
        expires_dt = expires_dt.replace(tzinfo=timezone.utc)

    is_expired = isinstance(expires_dt, datetime) and expires_dt <= datetime.now(timezone.utc)
    if not is_expired:
        return access_token

    if not refresh_token_encrypted:
        return access_token

    refresh_token = decrypt(refresh_token_encrypted)

    from backend.app.social.google import GoogleAuth

    refreshed = await GoogleAuth().refresh_access_token(refresh_token)
    new_access_token = refreshed.get("access_token")
    if not new_access_token:
        raise ValueError("Failed to refresh YouTube access token")

    now = datetime.now(timezone.utc)
    updates: dict[str, object] = {
        "access_token": encrypt(new_access_token),
        "token_error": None,
        "updated_at": now,
    }
    expires_in = refreshed.get("expires_in")
    if expires_in:
        expires_at_value = now + timedelta(seconds=int(expires_in))
        updates["expires_at"] = expires_at_value
        updates["token_expiry"] = expires_at_value
    new_refresh_token = refreshed.get("refresh_token")
    if new_refresh_token:
        updates["refresh_token"] = encrypt(new_refresh_token)

    await db.social_accounts.update_one(
        {"account_id": account.get("account_id")},
        {"$set": updates},
    )
    account.update(updates)
    return new_access_token


async def _async_refresh_youtube_geography_snapshots() -> dict:
    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    from backend.app.social.google import GoogleAuth

    auth = GoogleAuth()
    cursor = db.social_accounts.find(
        {"platform": "youtube", "is_active": True},
        {
            "_id": 0,
            "account_id": 1,
            "id": 1,
            "user_id": 1,
            "platform_user_id": 1,
            "access_token": 1,
            "refresh_token": 1,
            "expires_at": 1,
            "token_expiry": 1,
        },
    )

    accounts_seen = 0
    snapshots_written = 0
    empty_queries = 0
    failed_queries = 0

    async for account in cursor:
        accounts_seen += 1
        account_id = account.get("account_id") or account.get("id")
        try:
            access_token = await _get_youtube_worker_access_token(db, account)
        except Exception as exc:
            failed_queries += 1
            logger.warning("youtube geography refresh: failed to get token for %s: %s", account_id, exc)
            continue

        for window_days in (7, 30, 90):
            effective_start_date, effective_end_date, _ = compute_youtube_settled_window(window_days)
            for metric in ("views", "estimatedMinutesWatched"):
                try:
                    rows = await auth.query_analytics_report(
                        access_token,
                        metrics=[metric],
                        start_date=effective_start_date,
                        end_date=effective_end_date,
                        dimensions=["country"],
                        sort=[f"-{metric}"],
                        max_results=25,
                    )
                except Exception as exc:
                    failed_queries += 1
                    logger.warning(
                        "youtube geography refresh: query failed for %s window=%sd metric=%s: %s",
                        account_id,
                        window_days,
                        metric,
                        exc,
                    )
                    continue

                normalized_rows = normalize_youtube_geography_rows(rows, value_key=metric)
                if not normalized_rows:
                    empty_queries += 1
                    continue

                await store_youtube_geography_snapshot(
                    db,
                    account_id=account_id,
                    user_id=account.get("user_id"),
                    channel_id=account.get("platform_user_id"),
                    metric=metric,
                    window_days=window_days,
                    rows=normalized_rows,
                    effective_start_date=effective_start_date,
                    effective_end_date=effective_end_date,
                    fetched_at=datetime.now(timezone.utc),
                )
                snapshots_written += 1

    logger.info(
        "youtube geography refresh: accounts=%d snapshots_written=%d empty_queries=%d failed_queries=%d",
        accounts_seen,
        snapshots_written,
        empty_queries,
        failed_queries,
    )
    return {
        "accounts_seen": accounts_seen,
        "snapshots_written": snapshots_written,
        "empty_queries": empty_queries,
        "failed_queries": failed_queries,
    }


async def _fetch_tiktok_db_published_posts(db, user_id: str, account: dict, limit: int = 50) -> list[dict]:
    account_identifier = account.get("account_id") or account.get("id")
    if not account_identifier:
        return []

    cursor = db.posts.find(
        {
            "user_id": user_id,
            "platforms": "tiktok",
            "$or": [
                {"social_account_ids": account_identifier},
                {"account_ids": account_identifier},
                {"platform_account_ids": account_identifier},
                {"social_account_id": account_identifier},
            ],
            "status": {"$in": ["published", "partial"]},
        },
        {
            "_id": 0,
            "id": 1,
            "content": 1,
            "media_urls": 1,
            "thumbnail_urls": 1,
            "video_url": 1,
            "updated_at": 1,
            "published_at": 1,
            "platform_results": 1,
            "platform_post_urls": 1,
        },
    ).sort("updated_at", -1)

    docs = await cursor.to_list(length=limit)
    normalized: list[dict] = []
    for post in docs:
        platform_result = (post.get("platform_results") or {}).get("tiktok", {})
        if post.get("status") == "partial" and platform_result.get("status") not in {"success", "published"}:
            continue
        normalized.append(
            {
                "platform_post_id": platform_result.get("platform_post_id") or post.get("id"),
                "content": post.get("content", ""),
                "media_url": ((post.get("thumbnail_urls") or [None])[0] or (post.get("media_urls") or [None])[0] or post.get("video_url")),
                "post_url": platform_result.get("post_url") or (post.get("platform_post_urls") or {}).get("tiktok"),
                "metrics": {
                    "likes": 0,
                    "comments": 0,
                    "shares": 0,
                    "views": 0,
                },
                "published_at": platform_result.get("published_at") or post.get("published_at") or post.get("updated_at"),
            }
        )
    return normalized


async def _async_refresh_tiktok_analytics_snapshots() -> dict:
    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    try:
        from backend.app.social.tiktok import TikTokAuth
    except ModuleNotFoundError:
        from app.social.tiktok import TikTokAuth

    auth = TikTokAuth()
    cursor = db.social_accounts.find(
        {"platform": "tiktok", "is_active": True},
        {
            "_id": 0,
            "account_id": 1,
            "id": 1,
            "user_id": 1,
            "platform_user_id": 1,
            "access_token": 1,
        },
    )

    accounts_seen = 0
    snapshots_written = 0
    fallback_used = 0
    failed_queries = 0
    captured_at = datetime.now(timezone.utc)
    snapshot_date = captured_at.date()

    async for account in cursor:
        accounts_seen += 1
        account_id = account.get("account_id") or account.get("id")
        encrypted_token = account.get("access_token")
        if not encrypted_token:
            failed_queries += 1
            logger.warning("tiktok analytics refresh: missing token for %s", account_id)
            continue

        try:
            access_token = decrypt(encrypted_token)
            profile = await auth.get_user_profile(access_token)
        except Exception as exc:
            failed_queries += 1
            logger.warning("tiktok analytics refresh: failed to fetch profile for %s: %s", account_id, exc)
            continue

        source_mode = "live"
        try:
            posts = await auth.fetch_posts(access_token, limit=50)
        except Exception as exc:
            logger.warning("tiktok analytics refresh: video.list failed for %s: %s", account_id, exc)
            posts = []

        if not posts:
            source_mode = "db_fallback"
            fallback_used += 1
            posts = await _fetch_tiktok_db_published_posts(db, account.get("user_id"), account, limit=50)

        await store_tiktok_analytics_snapshot(
            db,
            account_id=account_id,
            user_id=account.get("user_id"),
            platform_user_id=account.get("platform_user_id"),
            snapshot_date=snapshot_date,
            follower_count=profile.get("followers_count") or 0,
            following_count=profile.get("following_count") or 0,
            likes_count=profile.get("likes_count") or 0,
            video_count=profile.get("video_count") or 0,
            posts=posts,
            source_mode=source_mode,
            captured_at=captured_at,
        )
        snapshots_written += 1

    logger.info(
        "tiktok analytics refresh: accounts=%s snapshots_written=%s fallback_used=%s failed_queries=%s",
        accounts_seen,
        snapshots_written,
        fallback_used,
        failed_queries,
    )
    return {
        "accounts_seen": accounts_seen,
        "snapshots_written": snapshots_written,
        "fallback_used": fallback_used,
        "failed_queries": failed_queries,
    }


async def _fetch_platform_metrics(
    db, platform: str, platform_post_id: str, workspace_id: str
) -> dict | None:
    """Fetch engagement metrics from platform API. Returns None on error."""
    # Look up account credentials for this workspace + platform
    account = await db.social_accounts.find_one(
        {"workspace_id": workspace_id, "platform": platform, "active": True}
    )
    if not account:
        return None

    access_token = decrypt(account.get("access_token_encrypted", ""))
    if not access_token:
        return None

    fetchers = {
        "instagram": _fetch_instagram_metrics,
        "facebook": _fetch_facebook_metrics,
        "youtube": _fetch_youtube_metrics,
        "twitter": _fetch_twitter_metrics,
    }
    fetcher = fetchers.get(platform)
    if not fetcher:
        return None

    try:
        return await fetcher(platform_post_id, access_token)
    except Exception as exc:
        logger.warning("Failed to fetch %s analytics for %s: %s", platform, platform_post_id, exc)
        return None


async def _fetch_instagram_metrics(post_id: str, access_token: str) -> dict:
    fields = "like_count,comments_count,reach,impressions,saved,shares"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"https://graph.instagram.com/{post_id}/insights",
            params={"metric": fields, "access_token": access_token},
        )
    if resp.status_code != 200:
        return {}
    data = resp.json().get("data", [])
    return {item["name"]: item.get("values", [{}])[0].get("value", 0) for item in data}


async def _fetch_facebook_metrics(post_id: str, access_token: str) -> dict:
    fields = "likes.summary(true),comments.summary(true),shares,impressions"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"https://graph.facebook.com/{os.environ.get('FACEBOOK_API_VERSION', 'v21.0')}/{post_id}",
            params={"fields": fields, "access_token": access_token},
        )
    if resp.status_code != 200:
        return {}
    data = resp.json()
    return {
        "likes": data.get("likes", {}).get("summary", {}).get("total_count", 0),
        "comments": data.get("comments", {}).get("summary", {}).get("total_count", 0),
        "shares": data.get("shares", {}).get("count", 0),
    }


async def _fetch_youtube_metrics(video_id: str, access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "statistics", "id": video_id},
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        return {}
    items = resp.json().get("items", [])
    if not items:
        return {}
    stats = items[0].get("statistics", {})
    return {
        "views": int(stats.get("viewCount", 0)),
        "likes": int(stats.get("likeCount", 0)),
        "comments": int(stats.get("commentCount", 0)),
    }


async def _fetch_twitter_metrics(tweet_id: str, access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"https://api.twitter.com/2/tweets/{tweet_id}",
            params={"tweet.fields": "public_metrics"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        return {}
    public = resp.json().get("data", {}).get("public_metrics", {})
    return {
        "likes": public.get("like_count", 0),
        "retweets": public.get("retweet_count", 0),
        "replies": public.get("reply_count", 0),
        "impressions": public.get("impression_count", 0),
    }
