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

from celery_workers.celery_app import celery_app
from db.mongo import get_client
from utils.encryption import decrypt

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
})


@celery_app.task(name="celery_workers.tasks.analytics.collect_analytics")
def collect_analytics(window: str = "24h") -> dict:
    """Collect engagement metrics for recently-published posts."""
    return asyncio.get_event_loop().run_until_complete(_async_collect(window))


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
            f"https://graph.facebook.com/v19.0/{post_id}",
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
