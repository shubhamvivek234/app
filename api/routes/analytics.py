"""Analytics endpoints for overview, engagement, and demographics."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Query

from api.deps import CurrentUser, DB
from utils.encryption import decrypt

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analytics"])

_PLATFORM_ANALYTICS_CAPABILITIES: dict[str, dict[str, Any]] = {
    "instagram": {"live_feed": True},
    "facebook": {"live_feed": True},
    "youtube": {"live_feed": True},
    "twitter": {
        "live_feed": True,
        "message": "X can show recent posts plus likes, replies, and reposts. View counts are not available from the current API integration.",
    },
    "threads": {
        "live_feed": True,
        "message": "Threads can show recent posts plus likes, replies, reposts, and views when Meta returns them.",
    },
    "bluesky": {
        "live_feed": True,
        "message": "Bluesky can show recent posts plus likes, replies, and reposts. View counts are not available from the API.",
    },
    "tiktok": {
        "live_feed": True,
        "message": "TikTok analytics depend on the scopes granted when the account was connected. If video list access is unavailable, Unravler falls back to posts published from the app.",
    },
    "pinterest": {
        "live_feed": True,
        "message": "Pinterest can show pins with saves, comments, and impressions when the API returns them. Share counts are not available.",
    },
    "mastodon": {
        "live_feed": True,
        "message": "Mastodon can show recent statuses plus favourites, replies, and boosts. View counts are not available.",
    },
    "linkedin": {
        "live_feed": False,
        "message": "LinkedIn's current integration can show publishing history, but not organic post engagement metrics.",
    },
    "discord": {
        "live_feed": False,
        "message": "Discord uses incoming webhooks for publishing, so analytics can only show posts published from Unravler.",
    },
    "snapchat": {
        "live_feed": False,
        "message": "Snapchat's current integration does not expose organic post analytics through the connected account APIs.",
    },
}
_SUPPORTED_ENGAGEMENT_PLATFORMS = {
    platform for platform, capability in _PLATFORM_ANALYTICS_CAPABILITIES.items() if capability.get("live_feed")
}
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
        query["$or"] = [{"social_account_ids": account_id}, {"account_ids": account_id}]
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
        query["$or"] = [{"social_account_ids": account_id}, {"account_ids": account_id}]
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


def _platform_message(platform: str | None) -> str | None:
    if not platform:
        return None
    return (_PLATFORM_ANALYTICS_CAPABILITIES.get(platform) or {}).get("message")


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
    from api.routes.accounts import _hydrate_social_account_metadata

    query: dict[str, Any] = {"user_id": user_id, "is_active": True}
    if platform:
        query["platform"] = platform
    if account_id:
        query["$or"] = [{"account_id": account_id}, {"id": account_id}]
    cursor = db.social_accounts.find(query, {"_id": 0})
    docs = await cursor.to_list(length=50)
    return [await _hydrate_social_account_metadata(db, doc) for doc in docs]


def _pick_facebook_page(account: dict[str, Any], pages: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not pages:
        return None
    platform_user_id = str(account.get("platform_user_id") or "")
    return next((page for page in pages if str(page.get("id")) == platform_user_id), None) or pages[0]


async def _fetch_account_feed_and_stats(db, account: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
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
        return [_standardize_feed_post(post) for post in feed], engagement

    if platform == "facebook":
        from backend.app.social.facebook import FacebookAuth

        auth = FacebookAuth()
        feed = await auth.fetch_page_feed(access_token, platform_user_id, limit=50)
        engagement = await auth.fetch_page_engagement(access_token, platform_user_id)
        if not feed and not engagement:
            try:
                pages = await auth.get_accounts(access_token)
                selected_page = _pick_facebook_page(account, pages)
                if selected_page:
                    page_id = str(selected_page.get("id", "")) or platform_user_id
                    page_token = selected_page.get("access_token") or access_token
                    feed = await auth.fetch_page_feed(page_token, page_id, limit=50)
                    engagement = await auth.fetch_page_engagement(page_token, page_id)
            except Exception as exc:
                logger.warning("Failed to resolve Facebook page analytics for %s: %s", platform_user_id, exc)
        return [_standardize_feed_post(post) for post in feed], engagement

    if platform == "youtube":
        from api.routes.accounts import _get_youtube_access_token
        from backend.app.social.google import GoogleAuth

        auth = GoogleAuth()
        try:
            channel = await auth.get_channel_info(access_token)
        except Exception:
            access_token = await _get_youtube_access_token(db, account, force_refresh=True)
            channel = await auth.get_channel_info(access_token)

        channel_id = str(channel.get("id") or platform_user_id)
        feed = await auth.fetch_youtube_feed(access_token, channel_id, limit=50)
        engagement = await auth.fetch_youtube_engagement(access_token, channel_id)
        return [_standardize_feed_post(post) for post in feed], engagement

    if platform == "twitter":
        from api.routes.accounts import _get_twitter_access_token
        from backend.app.social.twitter import TwitterAuth

        auth = TwitterAuth()
        try:
            profile = await auth.get_user_profile(access_token)
        except Exception:
            access_token = await _get_twitter_access_token(db, account, force_refresh=True)
            profile = await auth.get_user_profile(access_token)

        twitter_user_id = str(profile.get("id") or platform_user_id)
        feed = await auth.fetch_tweets(access_token, twitter_user_id, limit=50)
        engagement = await auth.fetch_engagement(access_token, twitter_user_id)
        return [_standardize_feed_post(post) for post in feed], engagement

    if platform == "threads":
        from backend.app.social.threads import ThreadsAuth

        auth = ThreadsAuth()
        profile = await auth.get_user_profile(access_token)
        threads_user_id = str(profile.get("id") or platform_user_id)
        feed = await auth.fetch_posts(access_token, threads_user_id, limit=50)
        return [_standardize_feed_post(post) for post in feed], {
            "display_name": profile.get("name") or account.get("display_name") or account.get("platform_username"),
        }

    if platform == "bluesky":
        from backend.app.social.bluesky import BlueskyAuth

        auth = BlueskyAuth()
        profile = await auth.get_user_profile(access_token, platform_user_id)
        handle = profile.get("username") or account.get("platform_username") or platform_user_id
        feed = await auth.fetch_posts(access_token, handle, limit=50)
        return [
            _standardize_feed_post(post) for post in feed
        ], {
            "followers": profile.get("followers_count"),
            "following": profile.get("following_count"),
            "posts_count": profile.get("posts_count"),
        }

    if platform == "tiktok":
        from backend.app.social.tiktok import TikTokAuth

        auth = TikTokAuth()
        feed = await auth.fetch_posts(access_token, limit=50)
        profile = await auth.get_user_profile(access_token)
        return [_standardize_feed_post(post) for post in feed], {
            "profile_views": None,
            "display_name": profile.get("name"),
        }

    if platform == "pinterest":
        from backend.app.social.pinterest import PinterestAuth

        auth = PinterestAuth()
        feed = await auth.fetch_pins(access_token, limit=50)
        profile = await auth.get_user_profile(access_token)
        return [_standardize_feed_post(post) for post in feed], {
            "display_name": profile.get("business_name") or profile.get("username"),
        }

    if platform == "mastodon":
        from backend.app.social.mastodon import MastodonAuth

        instance_url = (account.get("metadata") or {}).get("instance_url")
        if not instance_url:
            return [], {}

        auth = MastodonAuth()
        profile = await auth.get_user_profile(instance_url, access_token)
        feed = await auth.fetch_posts(instance_url, access_token, str(profile.get("id") or platform_user_id), limit=50)
        return [_standardize_feed_post(post) for post in feed], {
            "followers": profile.get("followers_count"),
            "following": profile.get("following_count"),
            "posts_count": profile.get("posts_count"),
        }

    return [], {}


def _db_post_media_url(post: dict[str, Any]) -> str | None:
    thumbnails = post.get("thumbnail_urls") or []
    media_urls = post.get("media_urls") or []
    return (thumbnails[0] if thumbnails else None) or (media_urls[0] if media_urls else None) or post.get("video_url")


def _db_post_media_type(post: dict[str, Any]) -> str:
    post_type = str(post.get("post_type") or "").lower()
    if post.get("video_url") or "video" in post_type or post_type == "reel":
        return "VIDEO"
    if _db_post_media_url(post):
        return "IMAGE"
    return "TEXT"


async def _fetch_db_published_posts(
    db,
    user_id: str,
    account: dict[str, Any],
    limit: int = 50,
) -> list[dict[str, Any]]:
    platform = account.get("platform")
    account_identifier = account.get("account_id") or account.get("id")
    if not platform or not account_identifier:
        return []

    cursor = db.posts.find(
        {
            "user_id": user_id,
            "platforms": platform,
            "$or": [{"social_account_ids": account_identifier}, {"account_ids": account_identifier}],
            "status": {"$in": ["published", "partial"]},
        },
        {
            "_id": 0,
            "id": 1,
            "content": 1,
            "media_urls": 1,
            "thumbnail_urls": 1,
            "video_url": 1,
            "post_type": 1,
            "published_at": 1,
            "updated_at": 1,
            "platform_results": 1,
            "platform_post_urls": 1,
        },
    ).sort("updated_at", -1)

    docs = await cursor.to_list(length=limit)
    feed: list[dict[str, Any]] = []
    for post in docs:
        platform_result = (post.get("platform_results") or {}).get(platform, {})
        if post.get("status") == "partial" and platform_result.get("status") not in {"success", "published"}:
            continue
        feed.append(
            {
                "id": platform_result.get("platform_post_id") or post.get("id"),
                "content": post.get("content", ""),
                "media_url": _db_post_media_url(post),
                "media_type": _db_post_media_type(post),
                "timestamp": platform_result.get("published_at") or post.get("published_at") or post.get("updated_at"),
                "likes": 0,
                "comments_count": 0,
                "shares": 0,
                "views": 0,
                "permalink": platform_result.get("post_url") or (post.get("platform_post_urls") or {}).get(platform),
                "platform": platform,
            }
        )
    return feed


def _normalize_connected_account(account: dict[str, Any], engagement: dict[str, Any]) -> dict[str, Any]:
    platform = account.get("platform")
    followers_count = next(
        (
            value
            for value in (
                engagement.get("followers"),
                engagement.get("fans"),
                engagement.get("subscribers"),
                account.get("followers_count"),
            )
            if value is not None
        ),
        None,
    )
    following_count = next(
        (value for value in (engagement.get("following"), account.get("following_count")) if value is not None),
        None,
    )
    posts_count = next(
        (value for value in (engagement.get("posts_count"), engagement.get("video_count"), account.get("posts_count")) if value is not None),
        None,
    )
    impressions = engagement.get("impressions")
    if impressions is None and platform == "youtube":
        impressions = engagement.get("total_views")

    return {
        "id": account.get("account_id") or account.get("id"),
        "account_id": account.get("account_id") or account.get("id"),
        "platform": platform,
        "platform_username": account.get("platform_username"),
        "picture_url": account.get("picture_url"),
        "display_name": account.get("display_name"),
        "followers_count": followers_count,
        "following_count": following_count,
        "posts_count": posts_count,
        "impressions": impressions,
        "reach": engagement.get("reach"),
        "profile_views": engagement.get("profile_views"),
    }


def _standardize_feed_post(post: dict[str, Any]) -> dict[str, Any]:
    metrics = post.get("metrics") or {}
    return {
        "id": post.get("id") or post.get("platform_post_id") or post.get("uri"),
        "content": post.get("content", ""),
        "media_url": post.get("media_url"),
        "video_url": post.get("video_url"),
        "media_type": post.get("media_type"),
        "timestamp": post.get("timestamp") or post.get("published_at") or post.get("created_at"),
        "permalink": post.get("permalink") or post.get("post_url") or post.get("url"),
        "likes": post.get("likes", metrics.get("likes")),
        "comments_count": post.get(
            "comments_count",
            post.get("replies", metrics.get("comments_count", metrics.get("comments", metrics.get("replies")))),
        ),
        "shares": post.get(
            "shares",
            post.get("retweets", metrics.get("shares", metrics.get("reblogs", metrics.get("reposts", metrics.get("retweet_count"))))),
        ),
        "views": post.get("views", metrics.get("views", metrics.get("impressions"))),
    }


def _normalize_feed_post(account: dict[str, Any], post: dict[str, Any]) -> dict[str, Any]:
    likes = _metric_int(post.get("likes"))
    comments = _metric_int(post.get("comments_count"))
    shares = _metric_int(post.get("shares"))
    views = _metric_int(post.get("views"))
    return {
        "id": post.get("id"),
        "platform": account.get("platform"),
        "account_id": account.get("account_id") or account.get("id"),
        "account_username": account.get("platform_username") or account.get("display_name"),
        "content": post.get("content", ""),
        "media_url": post.get("media_url"),
        "video_url": post.get("video_url"),
        "media_type": post.get("media_type"),
        "published_at": post.get("timestamp"),
        "post_url": post.get("permalink"),
        "metrics": {
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "views": views,
        },
    }


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

    # When an analytics account is explicitly selected, local published-post
    # history may be empty even though the connected platform account has live
    # content (for example, YouTube videos posted directly on YouTube). In that
    # case, fall back to the platform feed for overview counts.
    if account_id and platform in _SUPPORTED_ENGAGEMENT_PLATFORMS and published_in_period == 0:
        accounts = await _load_social_accounts(db, current_user["user_id"], platform, account_id)
        fallback_platform_counts: dict[str, int] = {}
        fallback_type_counts = {"text": 0, "image": 0, "video": 0}
        fallback_published_count = 0
        since_dt = datetime.now(timezone.utc) - timedelta(days=days)

        for account in accounts:
            try:
                feed, _ = await _fetch_account_feed_and_stats(db, account)
            except Exception as exc:
                logger.warning("Failed overview feed fallback for %s account %s: %s", platform, account_id, exc)
                continue

            in_period_posts = []
            for post in feed:
                ts = _parse_platform_timestamp(post.get("timestamp"))
                if ts and ts < since_dt:
                    continue
                in_period_posts.append(post)

            if not in_period_posts:
                continue

            fallback_published_count += len(in_period_posts)
            fallback_platform_counts[account.get("platform", platform)] = (
                fallback_platform_counts.get(account.get("platform", platform), 0) + len(in_period_posts)
            )
            for post in in_period_posts:
                media_type = str(post.get("media_type") or "").upper()
                if media_type == "VIDEO":
                    fallback_type_counts["video"] += 1
                elif media_type == "IMAGE":
                    fallback_type_counts["image"] += 1
                else:
                    fallback_type_counts["text"] += 1

        if fallback_published_count:
            published_in_period = fallback_published_count
            platform_counts = fallback_platform_counts
            type_counts = fallback_type_counts

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
        feed: list[dict[str, Any]] = []
        engagement: dict[str, Any] = {}
        if plat in _SUPPORTED_ENGAGEMENT_PLATFORMS:
            feed, engagement = await _fetch_account_feed_and_stats(db, account)

        connected_accounts.append(_normalize_connected_account(account, engagement))

        if not feed:
            feed = await _fetch_db_published_posts(db, current_user["user_id"], account, limit=50)

        if not feed and not engagement:
            account_identifier = account.get("account_id") or account.get("id")
            if plat in _SUPPORTED_ENGAGEMENT_PLATFORMS:
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
    if platform:
        message = _platform_message(platform)
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

    merged = {
        "age": _merge_named_counts(result["age"], "range"),
        "gender": _merge_named_counts(result["gender"], "label"),
        "cities": _merge_named_counts(result["cities"], "name")[:10],
        "countries": _merge_named_counts(result["countries"], "name")[:10],
    }

    if not any(merged.values()):
        return {
            "supported": False,
            "message": "Demographics are not available for this account yet. Instagram typically requires a Business/Creator account with at least 100 followers before follower demographics appear.",
            "accounts_used": accounts_used,
            "errors": errors,
        }

    return {
        "supported": True,
        "accounts_used": accounts_used,
        "errors": errors,
        "demographics": merged,
    }


@router.get("/publish/feed")
async def publish_feed(
    current_user: CurrentUser,
    db: DB,
    platform: str | None = Query(None),
    account_id: str | None = Query(None, alias="accountId"),
    limit: int = Query(50, ge=1, le=100),
):
    accounts = await _load_social_accounts(db, current_user["user_id"], platform, account_id)
    if not accounts:
        return {
            "posts": [],
            "connected_accounts": [],
            "message": "No connected account found for the selected filters.",
        }

    posts: list[dict[str, Any]] = []
    connected_accounts: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for account in accounts:
        plat = account.get("platform")
        account_identifier = account.get("account_id") or account.get("id")
        connected_accounts.append(
            {
                "id": account_identifier,
                "account_id": account_identifier,
                "platform": plat,
                "platform_username": account.get("platform_username"),
                "display_name": account.get("display_name"),
                "picture_url": account.get("picture_url"),
            }
        )

        if plat not in _SUPPORTED_ENGAGEMENT_PLATFORMS:
            feed = []
        else:
            feed, _ = await _fetch_account_feed_and_stats(db, account)

        if not feed:
            feed = await _fetch_db_published_posts(db, current_user["user_id"], account, limit=limit)
        if not feed:
            errors.append(
                {
                    "account": account.get("platform_username") or account_identifier or plat or "unknown",
                    "error": "No recent posts were returned from the platform API or local publish history.",
                }
            )
            continue

        posts.extend(_normalize_feed_post(account, post) for post in feed[:limit])

    posts.sort(
        key=lambda post: _parse_platform_timestamp(post.get("published_at")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    return {
        "posts": posts[:limit],
        "connected_accounts": connected_accounts,
        "errors": errors,
    }
