from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

TIKTOK_ANALYTICS_SNAPSHOT_COLLECTION = "tiktok_analytics_snapshots"
TIKTOK_ANALYTICS_BACKGROUND_REFRESH_SECONDS = 24 * 60 * 60


def _snapshot_date_value(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        value = value.astimezone(timezone.utc).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value.isoformat()
    string_value = str(value).strip()
    return string_value or None


def normalize_tiktok_snapshot_posts(posts: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for post in posts or []:
        metrics = post.get("metrics") or {}
        post_id = (
            post.get("platform_post_id")
            or post.get("id")
            or post.get("uri")
            or post.get("permalink")
        )
        if not post_id:
            continue
        normalized.append(
            {
                "video_id": str(post_id),
                "published_at": post.get("published_at") or post.get("timestamp"),
                "title": post.get("content", ""),
                "cover_image_url": post.get("media_url"),
                "share_url": post.get("post_url") or post.get("permalink"),
                "like_count": int(metrics.get("likes") or post.get("likes") or 0),
                "comment_count": int(metrics.get("comments") or post.get("comments_count") or 0),
                "share_count": int(metrics.get("shares") or post.get("shares") or 0),
                "view_count": int(metrics.get("views") or post.get("views") or 0),
            }
        )
    return normalized


async def store_tiktok_analytics_snapshot(
    db,
    *,
    account_id: str,
    user_id: str | None,
    platform_user_id: str | None,
    snapshot_date: date | datetime | str,
    follower_count: int,
    following_count: int,
    likes_count: int,
    video_count: int,
    posts: list[dict[str, Any]],
    source_mode: str,
    captured_at: datetime | None = None,
) -> None:
    stored_at = captured_at or datetime.now(timezone.utc)
    as_of_date = _snapshot_date_value(snapshot_date)
    if not as_of_date:
        return

    normalized_posts = normalize_tiktok_snapshot_posts(posts)
    await db[TIKTOK_ANALYTICS_SNAPSHOT_COLLECTION].update_one(
        {
            "account_id": account_id,
            "platform": "tiktok",
            "report_type": "daily_account_snapshot",
            "snapshot_date": as_of_date,
        },
        {
            "$set": {
                "user_id": user_id,
                "platform_user_id": platform_user_id,
                "follower_count": int(follower_count or 0),
                "following_count": int(following_count or 0),
                "likes_count": int(likes_count or 0),
                "video_count": int(video_count or 0),
                "posts": normalized_posts,
                "top_posts": normalized_posts[:10],
                "source_mode": source_mode,
                "captured_at": stored_at,
                "updated_at": stored_at,
            },
            "$setOnInsert": {
                "created_at": stored_at,
            },
        },
        upsert=True,
    )


async def load_tiktok_analytics_snapshots(
    db,
    *,
    account_id: str,
    since_date: date | datetime | str | None = None,
) -> list[dict[str, Any]]:
    query: dict[str, Any] = {
        "account_id": account_id,
        "platform": "tiktok",
        "report_type": "daily_account_snapshot",
    }
    normalized_since = _snapshot_date_value(since_date)
    if normalized_since:
        query["snapshot_date"] = {"$gte": normalized_since}
    cursor = db[TIKTOK_ANALYTICS_SNAPSHOT_COLLECTION].find(query, {"_id": 0}).sort("snapshot_date", 1)
    return await cursor.to_list(length=400)


async def load_latest_tiktok_snapshot_before(
    db,
    *,
    account_id: str,
    before_date: date | datetime | str,
) -> dict[str, Any] | None:
    normalized_before = _snapshot_date_value(before_date)
    if not normalized_before:
        return None
    return await db[TIKTOK_ANALYTICS_SNAPSHOT_COLLECTION].find_one(
        {
            "account_id": account_id,
            "platform": "tiktok",
            "report_type": "daily_account_snapshot",
            "snapshot_date": {"$lt": normalized_before},
        },
        sort=[("snapshot_date", -1), ("captured_at", -1)],
    )
