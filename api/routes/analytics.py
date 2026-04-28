"""Analytics endpoints for overview, engagement, and demographics."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Query

from api.deps import CurrentUser, DB
from utils.encryption import decrypt

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analytics"])

_SUPPORTED_ENGAGEMENT_PLATFORMS = {"instagram", "facebook", "youtube"}
_SUPPORTED_DEMOGRAPHIC_PLATFORMS = {"instagram", "facebook"}


def _workspace_id_for(current_user: dict) -> str:
    return current_user.get("default_workspace_id") or current_user["user_id"]


def _iso_since(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _published_match(
    workspace_id: str,
    since_iso: str,
    platform: str | None = None,
    account_id: str | None = None,
) -> dict[str, Any]:
    query: dict[str, Any] = {
        "workspace_id": workspace_id,
        "status": "published",
        "updated_at": {"$gte": since_iso},
    }
    if platform:
        query["platforms"] = platform
    if account_id:
        query["social_account_ids"] = account_id
    return query


def _scheduled_match(
    workspace_id: str,
    platform: str | None = None,
    account_id: str | None = None,
) -> dict[str, Any]:
    query: dict[str, Any] = {
        "workspace_id": workspace_id,
        "status": "scheduled",
    }
    if platform:
        query["platforms"] = platform
    if account_id:
        query["social_account_ids"] = account_id
    return query


def _parse_platform_timestamp(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except Exception:
        return None


def _metric_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _merge_named_counts(items: list[dict[str, Any]], key_name: str) -> list[dict[str, Any]]:
    merged: dict[str, int] = {}
    for item in items:
        key = item.get(key_name)
        if not key:
            continue
        merged[key] = merged.get(key, 0) + _metric_int(item.get("count"))
    return [{key_name: k, "count": v} for k, v in sorted(merged.items(), key=lambda kv: kv[1], reverse=True)]


async def _load_social_accounts(
    db,
    user_id: str,
    platform: str | None = None,
    account_id: str | None = None,
) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"user_id": user_id, "is_active": True}
    if platform:
        query["platform"] = platform
    if account_id:
        query["$or"] = [{"account_id": account_id}, {"id": account_id}]
    cursor = db.social_accounts.find(query, {"_id": 0})
    return await cursor.to_list(length=50)


async def _fetch_account_feed_and_stats(account: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    platform = account.get("platform")
    platform_user_id = account.get("platform_user_id")
    encrypted_token = account.get("access_token")
    if not platform or not platform_user_id or not encrypted_token:
        return [], {}

    try:
        access_token = decrypt(encrypted_token)
    except Exception as exc:
        logger.warning("Failed to decrypt %s token for analytics: %s", platform, exc)
        return [], {}

    if platform == "instagram":
        from backend.app.social.instagram import InstagramAuth

        auth = InstagramAuth()
        feed = await auth.fetch_feed(access_token, platform_user_id, limit=50)
        engagement = await auth.fetch_engagement(access_token, platform_user_id)
        return feed, engagement

    if platform == "facebook":
        from backend.app.social.facebook import FacebookAuth

        auth = FacebookAuth()
        feed = await auth.fetch_page_feed(access_token, platform_user_id, limit=50)
        engagement = await auth.fetch_page_engagement(access_token, platform_user_id)
        return feed, engagement

    if platform == "youtube":
        from backend.app.social.google import GoogleAuth

        auth = GoogleAuth()
        feed = await auth.fetch_youtube_feed(access_token, platform_user_id, limit=50)
        engagement = await auth.fetch_youtube_engagement(access_token, platform_user_id)
        return feed, engagement

    return [], {}


@router.get("/analytics/overview")
async def analytics_overview(
    current_user: CurrentUser,
    db: DB,
    days: int = Query(30, ge=1, le=365),
    platform: str | None = Query(None),
    account_id: str | None = Query(None, alias="accountId"),
):
    workspace_id = _workspace_id_for(current_user)
    since_iso = _iso_since(days)
    published_match = _published_match(workspace_id, since_iso, platform, account_id)
    scheduled_match = _scheduled_match(workspace_id, platform, account_id)
    failed_match = {
        **_published_match(workspace_id, since_iso, platform, account_id),
        "status": "failed",
    }

    import asyncio

    async def _count(q: dict[str, Any]) -> int:
        return await db.posts.count_documents(q)

    published_in_period, scheduled_count, failed_count = await asyncio.gather(
        _count(published_match),
        _count(scheduled_match),
        _count(failed_match),
    )

    platform_pipeline = [
        {"$match": published_match},
        {"$unwind": "$platforms"},
        {"$group": {"_id": "$platforms", "count": {"$sum": 1}}},
    ]
    platform_docs = await db.posts.aggregate(platform_pipeline).to_list(None)
    platform_counts = {d["_id"]: d["count"] for d in platform_docs if d.get("_id")}

    type_pipeline = [
        {"$match": published_match},
        {"$group": {"_id": "$post_type", "count": {"$sum": 1}}},
    ]
    type_docs = await db.posts.aggregate(type_pipeline).to_list(None)
    type_counts = {
        "text": 0,
        "image": 0,
        "video": 0,
    }
    for doc in type_docs:
        key = (doc.get("_id") or "text").lower()
        if "video" in key or key == "reel":
            type_counts["video"] += doc["count"]
        elif "image" in key or "photo" in key:
            type_counts["image"] += doc["count"]
        else:
            type_counts["text"] += doc["count"]

    return {
        "published_in_period": published_in_period,
        "scheduled_count": scheduled_count,
        "failed_count": failed_count,
        "platform_counts": platform_counts,
        "type_counts": type_counts,
        # Legacy aliases retained for any older consumers.
        "total_published": published_in_period,
        "total_scheduled": scheduled_count,
        "total_failed": failed_count,
        "platform_breakdown": platform_counts,
        "days": days,
    }


@router.get("/analytics/timeline")
async def analytics_timeline(
    current_user: CurrentUser,
    db: DB,
    days: int = Query(30, ge=1, le=365),
    platform: str | None = Query(None),
    account_id: str | None = Query(None, alias="accountId"),
):
    workspace_id = _workspace_id_for(current_user)
    since_iso = _iso_since(days)
    match = _published_match(workspace_id, since_iso, platform, account_id)

    pipeline = [
        {"$match": match},
        {"$group": {"_id": {"$substr": ["$updated_at", 0, 10]}, "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    docs = await db.posts.aggregate(pipeline).to_list(None)
    return {"timeline": [{"date": d["_id"], "count": d["count"]} for d in docs if d.get("_id")]}


@router.get("/analytics/engagement")
async def analytics_engagement(
    current_user: CurrentUser,
    db: DB,
    days: int = Query(30, ge=1, le=365),
    platform: str | None = Query(None),
    account_id: str | None = Query(None, alias="accountId"),
):
    accounts = await _load_social_accounts(db, current_user["user_id"], platform, account_id)
    if not accounts:
        return {
            "totals": {"total_posts": 0, "total_likes": 0, "total_comments": 0, "total_shares": 0, "total_views": 0},
            "platform_breakdown": {},
            "top_posts": [],
            "connected_accounts": [],
            "message": "No connected account found for the selected filters.",
        }

    since_dt = datetime.now(timezone.utc) - timedelta(days=days)
    totals = {"total_posts": 0, "total_likes": 0, "total_comments": 0, "total_shares": 0, "total_views": 0}
    platform_breakdown: dict[str, dict[str, int]] = {}
    top_posts: list[dict[str, Any]] = []
    connected_accounts: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for account in accounts:
        plat = account.get("platform")
        if plat not in _SUPPORTED_ENGAGEMENT_PLATFORMS:
            continue

        feed, engagement = await _fetch_account_feed_and_stats(account)
        account_identifier = account.get("account_id") or account.get("id")
        connected_accounts.append(
            {
                "id": account_identifier,
                "account_id": account_identifier,
                "platform": plat,
                "platform_username": account.get("platform_username"),
                "picture_url": account.get("picture_url"),
                "display_name": account.get("display_name"),
                "followers_count": engagement.get("followers") or account.get("followers_count"),
                "following_count": engagement.get("following") or account.get("following_count"),
                "posts_count": engagement.get("posts_count") or account.get("posts_count"),
                "impressions": engagement.get("impressions"),
                "reach": engagement.get("reach"),
                "profile_views": engagement.get("profile_views"),
            }
        )

        if not feed and not engagement:
            errors.append(
                {
                    "account": account.get("platform_username") or account_identifier or plat,
                    "error": "Unable to fetch recent analytics from the platform API.",
                }
            )
            continue

        filtered_feed: list[dict[str, Any]] = []
        for post in feed:
            published_at = _parse_platform_timestamp(post.get("timestamp"))
            if published_at and published_at < since_dt:
                continue
            filtered_feed.append(post)

        plat_totals = platform_breakdown.setdefault(
            plat,
            {"posts": 0, "likes": 0, "comments": 0, "shares": 0, "views": 0},
        )

        for post in filtered_feed:
            likes = _metric_int(post.get("likes"))
            comments = _metric_int(post.get("comments_count"))
            shares = _metric_int(post.get("shares"))
            views = _metric_int(post.get("views"))

            totals["total_posts"] += 1
            totals["total_likes"] += likes
            totals["total_comments"] += comments
            totals["total_shares"] += shares
            totals["total_views"] += views

            plat_totals["posts"] += 1
            plat_totals["likes"] += likes
            plat_totals["comments"] += comments
            plat_totals["shares"] += shares
            plat_totals["views"] += views

            top_posts.append(
                {
                    "platform": plat,
                    "content": post.get("content", ""),
                    "media_url": post.get("media_url"),
                    "post_url": post.get("permalink"),
                    "published_at": post.get("timestamp"),
                    "platform_post_id": post.get("id"),
                    "metrics": {
                        "likes": likes,
                        "comments": comments,
                        "shares": shares,
                        "views": views,
                    },
                }
            )

    top_posts.sort(
        key=lambda post: (
            _metric_int(post["metrics"].get("likes"))
            + _metric_int(post["metrics"].get("comments"))
            + _metric_int(post["metrics"].get("shares"))
            + _metric_int(post["metrics"].get("views"))
        ),
        reverse=True,
    )

    message = None
    if platform and platform not in _SUPPORTED_ENGAGEMENT_PLATFORMS:
        message = f"{platform.title()} account-level analytics are not available yet."
    elif not top_posts and not errors:
        message = "No recent post-level engagement data found for the selected period."

    return {
        "totals": totals,
        "platform_breakdown": platform_breakdown,
        "top_posts": top_posts[:10],
        "connected_accounts": connected_accounts,
        "errors": errors,
        "message": message,
    }


@router.get("/analytics/demographics")
async def analytics_demographics(
    current_user: CurrentUser,
    db: DB,
    platform: str | None = Query(None),
    account_id: str | None = Query(None, alias="accountId"),
):
    if platform and platform not in _SUPPORTED_DEMOGRAPHIC_PLATFORMS:
        return {
            "supported": False,
            "message": f"Demographics are only available for Instagram and Facebook right now.",
        }

    accounts = await _load_social_accounts(db, current_user["user_id"], platform, account_id)
    accounts = [a for a in accounts if a.get("platform") in _SUPPORTED_DEMOGRAPHIC_PLATFORMS]
    if not accounts:
        return {
            "supported": False,
            "message": "Connect an Instagram Business/Creator account or a Facebook Page to view demographics.",
        }

    result = {"age": [], "gender": [], "cities": [], "countries": []}
    accounts_used: list[str] = []
    errors: list[dict[str, str]] = []

    for account in accounts:
        plat = account.get("platform")
        platform_user_id = account.get("platform_user_id")
        encrypted_token = account.get("access_token")
        account_label = account.get("platform_username") or account.get("display_name") or account.get("account_id") or plat

        if not platform_user_id or not encrypted_token:
            errors.append({"account": account_label, "error": "Account is missing platform credentials."})
            continue

        try:
            access_token = decrypt(encrypted_token)
        except Exception:
            errors.append({"account": account_label, "error": "Stored token could not be decrypted."})
            continue

        if plat == "instagram":
            from backend.app.social.instagram import InstagramAuth

            data = await InstagramAuth().fetch_demographics(access_token, platform_user_id)
        else:
            from backend.app.social.facebook import FacebookAuth

            data = await FacebookAuth().fetch_page_demographics(access_token, platform_user_id)

        if not data.get("supported"):
            errors.append({"account": account_label, "error": data.get("error") or "Demographics are not available for this account."})
            continue

        accounts_used.append(account_label)
        result["age"].extend(data.get("age", []))
        result["gender"].extend(data.get("gender", []))
        result["cities"].extend(data.get("cities", []))
        result["countries"].extend(data.get("countries", []))

    if not accounts_used:
        return {
            "supported": False,
            "message": "Connected accounts did not return demographic data. Instagram typically requires a Business/Creator account with at least 100 followers.",
            "errors": errors,
        }

    return {
        "supported": True,
        "accounts_used": accounts_used,
        "errors": errors,
        "demographics": {
            "age": _merge_named_counts(result["age"], "range"),
            "gender": _merge_named_counts(result["gender"], "label"),
            "cities": _merge_named_counts(result["cities"], "name")[:10],
            "countries": _merge_named_counts(result["countries"], "name")[:10],
        },
    }
