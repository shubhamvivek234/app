"""Analytics endpoints for overview, engagement, and demographics."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from api.deps import CurrentUser, DB
from utils.encryption import decrypt
from utils.observability import capture_degraded_event, event_log, shorten_provider_error
from utils.youtube_geography import (
    YOUTUBE_GEOGRAPHY_DEFAULT_EMPTY_MESSAGE,
    build_youtube_geography_payload,
    compute_youtube_settled_window,
    load_latest_youtube_geography_snapshot,
    merge_youtube_geography_payloads,
    normalize_youtube_geography_rows,
    store_youtube_geography_snapshot,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analytics"])

_PLATFORM_ANALYTICS_CAPABILITIES: dict[str, dict[str, Any]] = {
    "instagram": {
        "live_feed": True,
        "supports": {
            "followers_total": True,
            "followers_growth": True,
            "reach": True,
            "impressions": True,
            "likes": True,
            "comments": True,
            "shares": False,
            "views": False,
        },
    },
    "facebook": {
        "live_feed": True,
        "supports": {
            "followers_total": True,
            "followers_growth": True,
            "reach": True,
            "impressions": True,
            "likes": True,
            "comments": True,
            "shares": True,
            "views": False,
        },
    },
    "youtube": {
        "live_feed": True,
        "supports": {
            "followers_total": True,
            "followers_growth": True,
            "reach": False,
            "impressions": False,
            "likes": True,
            "comments": True,
            "shares": True,
            "views": True,
        },
        "message": "YouTube can show subscribers plus organic video metrics. Reach is not exposed like Meta-style account reach.",
    },
    "twitter": {
        "live_feed": True,
        "message": "X can show recent posts plus likes, replies, and reposts. View counts are not available from the current API integration.",
        "supports": {
            "followers_total": True,
            "followers_growth": False,
            "reach": False,
            "impressions": False,
            "likes": True,
            "comments": True,
            "shares": True,
            "views": False,
        },
    },
    "threads": {
        "live_feed": True,
        "message": "Threads can show recent posts plus likes, replies, reposts, and views when Meta returns them.",
        "supports": {
            "followers_total": False,
            "followers_growth": False,
            "reach": False,
            "impressions": False,
            "likes": True,
            "comments": True,
            "shares": True,
            "views": True,
        },
    },
    "bluesky": {
        "live_feed": True,
        "message": "Bluesky can show recent posts plus likes, replies, and reposts. View counts are not available from the API.",
        "supports": {
            "followers_total": True,
            "followers_growth": False,
            "reach": False,
            "impressions": False,
            "likes": True,
            "comments": True,
            "shares": True,
            "views": False,
        },
    },
    "tiktok": {
        "live_feed": True,
        "message": "TikTok analytics depend on the scopes granted when the account was connected. If video list access is unavailable, Unravler falls back to posts published from the app.",
        "supports": {
            "followers_total": True,
            "followers_growth": False,
            "reach": False,
            "impressions": False,
            "likes": True,
            "comments": True,
            "shares": True,
            "views": True,
        },
    },
    "pinterest": {
        "live_feed": True,
        "message": "Pinterest can show pins with saves, comments, and impressions when the API returns them. Share counts are not available.",
        "supports": {
            "followers_total": False,
            "followers_growth": False,
            "reach": False,
            "impressions": True,
            "likes": True,
            "comments": True,
            "shares": False,
            "views": True,
        },
    },
    "mastodon": {
        "live_feed": True,
        "message": "Mastodon can show recent statuses plus favourites, replies, and boosts. View counts are not available.",
        "supports": {
            "followers_total": True,
            "followers_growth": False,
            "reach": False,
            "impressions": False,
            "likes": True,
            "comments": True,
            "shares": True,
            "views": False,
        },
    },
    "linkedin": {
        "live_feed": True,
        "message": "LinkedIn can show follower totals, follower growth, and organization impressions when the connected account has analytics scopes and page admin access. Post engagement metrics remain limited.",
        "supports": {
            "followers_total": True,
            "followers_growth": True,
            "reach": True,
            "impressions": True,
            "likes": False,
            "comments": False,
            "shares": False,
            "views": False,
        },
    },
    "discord": {
        "live_feed": False,
        "message": "Discord uses incoming webhooks for publishing, so analytics can only show posts published from Unravler.",
        "supports": {
            "followers_total": False,
            "followers_growth": False,
            "reach": False,
            "impressions": False,
            "likes": False,
            "comments": False,
            "shares": False,
            "views": False,
        },
    },
    "snapchat": {
        "live_feed": False,
        "message": "Snapchat's current integration does not expose organic post analytics through the connected account APIs.",
        "supports": {
            "followers_total": False,
            "followers_growth": False,
            "reach": False,
            "impressions": False,
            "likes": False,
            "comments": False,
            "shares": False,
            "views": False,
        },
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


def _platform_supports(platform: str | None) -> dict[str, bool]:
    if not platform:
        return {}
    return ((_PLATFORM_ANALYTICS_CAPABILITIES.get(platform) or {}).get("supports") or {}).copy()


def _account_error_label(account: dict[str, Any]) -> str:
    return (
        account.get("platform_username")
        or account.get("display_name")
        or account.get("account_id")
        or account.get("id")
        or account.get("platform")
        or "unknown"
    )


def _analytics_error_message(platform: str | None, exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, str) and detail.strip():
            message = detail.strip()
        else:
            message = str(exc).strip()
    else:
        message = str(exc).strip()
    if not message:
        message = "Unable to fetch recent analytics from the platform API."
    if platform == "twitter" and "CreditsDepleted" in message:
        return "X API credits are depleted for this connected developer account. Live X analytics are temporarily unavailable."
    if platform == "bluesky" and ("Failed to fetch Bluesky profile" in message or "Bluesky session expired" in message):
        return "Bluesky session expired. Reconnect the account if automatic refresh could not restore access."
    if platform == "youtube" and ("Failed to refresh token" in message or "YouTube access was revoked or expired" in message):
        return "YouTube access was revoked or expired. Reconnect the account to restore analytics."
    return message


def _append_account_error(errors: list[dict[str, str]], account: dict[str, Any], message: str) -> bool:
    label = _account_error_label(account)
    entry = {"account": label, "error": message}
    if entry in errors:
        return False
    errors.append(entry)
    return True


def _has_account_error(errors: list[dict[str, str]], account: dict[str, Any]) -> bool:
    label = _account_error_label(account)
    return any(item.get("account") == label for item in errors)


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


def _account_identifier_matches(account: dict[str, Any], account_id: str) -> bool:
    target = str(account_id or "").strip().lower()
    if not target:
        return False
    identifiers = {
        str(account.get("account_id") or "").strip().lower(),
        str(account.get("id") or "").strip().lower(),
        str(account.get("platform_user_id") or "").strip().lower(),
        str(account.get("platform_username") or "").strip().lower(),
        str(account.get("display_name") or "").strip().lower(),
    }
    identifiers.discard("")
    return target in identifiers


async def _load_social_accounts_for_report(
    db,
    user_id: str,
    platform: str,
    account_id: str | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    accounts = await _load_social_accounts(db, user_id, platform, account_id)
    if accounts or not account_id:
        return accounts, False

    fallback_accounts = await _load_social_accounts(db, user_id, platform, None)
    exact_matches = [account for account in fallback_accounts if _account_identifier_matches(account, account_id)]
    if exact_matches:
        return exact_matches, True

    if len(fallback_accounts) == 1:
        return fallback_accounts, True

    return [], False


def _pick_facebook_page(account: dict[str, Any], pages: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not pages:
        return None
    platform_user_id = str(account.get("platform_user_id") or "")
    return next((page for page in pages if str(page.get("id")) == platform_user_id), None) or pages[0]


async def _fetch_account_feed_and_stats(
    db,
    account: dict[str, Any],
    days: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    platform = account.get("platform")
    platform_user_id = account.get("platform_user_id")
    encrypted_token = account.get("access_token")
    if not platform or not platform_user_id or not encrypted_token:
        return [], {}

    try:
        access_token = decrypt(encrypted_token)
    except Exception as exc:
        event_log(
            logger,
            "warning",
            "analytics.provider.fetch_failed",
            exc_info=exc,
            route="/analytics/*",
            platform=platform,
            account_id=account.get("account_id") or account.get("id"),
            failure_type="token_decrypt_failed",
            provider_error=shorten_provider_error(exc),
            fetch_mode="api",
            outcome="failed",
        )
        return [], {}

    if platform == "instagram":
        from backend.app.social.instagram import InstagramAuth

        auth = InstagramAuth()
        feed = await auth.fetch_feed(access_token, platform_user_id, limit=50)
        engagement = await auth.fetch_engagement(access_token, platform_user_id, days=days)
        return [_standardize_feed_post(post) for post in feed], engagement

    if platform == "facebook":
        from backend.app.social.facebook import FacebookAuth

        auth = FacebookAuth()
        feed = await auth.fetch_page_feed(access_token, platform_user_id, limit=50)
        engagement = await auth.fetch_page_engagement(access_token, platform_user_id, days=days)
        if not feed and not engagement:
            try:
                pages = await auth.get_accounts(access_token)
                selected_page = _pick_facebook_page(account, pages)
                if selected_page:
                    page_id = str(selected_page.get("id", "")) or platform_user_id
                    page_token = selected_page.get("access_token") or access_token
                    feed = await auth.fetch_page_feed(page_token, page_id, limit=50)
                    engagement = await auth.fetch_page_engagement(page_token, page_id, days=days)
            except Exception as exc:
                event_log(
                    logger,
                    "warning",
                    "analytics.provider.fallback_failed",
                    exc_info=exc,
                    route="/analytics/*",
                    platform=platform,
                    account_id=account.get("account_id") or account.get("id"),
                    failure_type="facebook_page_resolution_failed",
                    provider_error=shorten_provider_error(exc),
                    fetch_mode="api_fallback",
                    outcome="failed",
                )
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
        engagement = await auth.fetch_youtube_engagement(access_token, channel_id, days=days)
        return [_standardize_feed_post(post) for post in feed], engagement

    if platform == "linkedin":
        from api.routes.accounts import _get_linkedin_access_token
        from backend.app.social.linkedin import LinkedInAuth

        auth = LinkedInAuth()
        try:
            profile = await auth.get_user_profile(access_token)
        except Exception:
            access_token = await _get_linkedin_access_token(db, account, force_refresh=True)
            profile = await auth.get_user_profile(access_token)

        engagement = await auth.fetch_audience_analytics(access_token, account, days=days)
        engagement["display_name"] = (
            profile.get("name")
            or profile.get("email")
            or account.get("display_name")
            or account.get("platform_username")
        )
        return [], engagement

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
        from api.routes.accounts import _get_bluesky_access_token
        from backend.app.social.bluesky import BlueskyAuth

        auth = BlueskyAuth()
        try:
            profile = await auth.get_user_profile(
                access_token,
                platform_user_id,
                fallback_actor=account.get("platform_username"),
            )
        except Exception:
            access_token = await _get_bluesky_access_token(db, account, force_refresh=True)
            profile = await auth.get_user_profile(
                access_token,
                platform_user_id,
                fallback_actor=account.get("platform_username"),
            )
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
            "followers": profile.get("followers_count"),
            "following": profile.get("following_count"),
            "posts_count": profile.get("video_count"),
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
    supports = _platform_supports(platform)
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
        "followers_growth": engagement.get("followers_growth"),
        "following_count": following_count,
        "posts_count": posts_count,
        "impressions": impressions,
        "reach": engagement.get("reach"),
        "profile_views": engagement.get("profile_views"),
        "supports": supports,
        "message": _platform_message(platform),
    }


def _maybe_add_metric(target: dict[str, int], key: str, value: Any) -> bool:
    if value is None:
        return False
    target[key] = target.get(key, 0) + _metric_int(value)
    return True


def _aggregate_account_overview(accounts: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {
        "followers_total": 0,
        "followers_growth": 0,
        "reach": 0,
        "impressions": 0,
        "profile_views": 0,
    }
    supported_by_metric = {key: 0 for key in totals}

    for account in accounts:
        supports = account.get("supports") or {}
        if supports.get("followers_total") and _maybe_add_metric(totals, "followers_total", account.get("followers_count")):
            supported_by_metric["followers_total"] += 1
        if supports.get("followers_growth") and _maybe_add_metric(totals, "followers_growth", account.get("followers_growth")):
            supported_by_metric["followers_growth"] += 1
        if supports.get("reach") and _maybe_add_metric(totals, "reach", account.get("reach")):
            supported_by_metric["reach"] += 1
        if supports.get("impressions") and _maybe_add_metric(totals, "impressions", account.get("impressions")):
            supported_by_metric["impressions"] += 1
        if _maybe_add_metric(totals, "profile_views", account.get("profile_views")):
            supported_by_metric["profile_views"] += 1

    return {
        "followers_total": totals["followers_total"] if supported_by_metric["followers_total"] else None,
        "followers_growth": totals["followers_growth"] if supported_by_metric["followers_growth"] else None,
        "reach": totals["reach"] if supported_by_metric["reach"] else None,
        "impressions": totals["impressions"] if supported_by_metric["impressions"] else None,
        "profile_views": totals["profile_views"] if supported_by_metric["profile_views"] else None,
        "supported_accounts": supported_by_metric,
    }


def _standardize_feed_post(post: dict[str, Any]) -> dict[str, Any]:
    metrics = post.get("metrics") or {}
    return {
        "id": post.get("id") or post.get("platform_post_id") or post.get("uri"),
        "content": post.get("content", ""),
        "media_url": post.get("media_url"),
        "video_url": post.get("video_url"),
        "media_type": post.get("media_type"),
        "post_type": post.get("post_type") or post.get("media_type"),
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
        "quotes": post.get("quotes", metrics.get("quotes", metrics.get("quoteCount"))),
    }


def _normalize_feed_post(account: dict[str, Any], post: dict[str, Any]) -> dict[str, Any]:
    likes = _metric_int(post.get("likes"))
    comments = _metric_int(post.get("comments_count"))
    shares = _metric_int(post.get("shares"))
    views = _metric_int(post.get("views"))
    quotes = _metric_int(post.get("quotes"))
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
            "quotes": quotes,
        },
    }


def _instagram_post_type(post: dict[str, Any]) -> str:
    media_type = str(post.get("media_type") or "").upper()
    if media_type == "CAROUSEL_ALBUM":
        return "carousel"
    if media_type == "REELS":
        return "reel"
    if media_type == "VIDEO":
        return "video"
    if media_type == "IMAGE":
        return "image"
    return "text"


def _bluesky_post_type(post: dict[str, Any]) -> str:
    media_type = str(post.get("post_type") or post.get("media_type") or "").upper()
    if media_type == "IMAGE":
        return "image"
    if media_type == "VIDEO":
        return "video"
    if media_type == "LINK":
        return "link"
    if media_type == "QUOTED":
        return "quoted"
    return "text"


def _pct_change(current: int | float, previous: int | float) -> float | None:
    if previous in (None, 0):
        if current:
            return 100.0
        return 0.0
    return round(((current - previous) / previous) * 100, 1)


def _youtube_period_bounds(days: int) -> tuple[datetime.date, datetime.date, datetime.date, datetime.date]:
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=max(days - 1, 0))
    previous_end = start_date - timedelta(days=1)
    previous_start = previous_end - timedelta(days=max(days - 1, 0))
    return start_date, end_date, previous_start, previous_end


async def _resolve_youtube_geography_payload(
    db: DB,
    *,
    account: dict[str, Any],
    metric: str,
    metric_label: str,
    query_rows: list[dict[str, Any]],
    effective_start_date,
    effective_end_date,
    is_lag_adjusted: bool,
) -> dict[str, Any]:
    account_id = account.get("account_id") or account.get("id")
    normalized_rows = normalize_youtube_geography_rows(query_rows, value_key=metric)
    if normalized_rows:
        fetched_at = datetime.now(timezone.utc)
        await store_youtube_geography_snapshot(
            db,
            account_id=account_id,
            user_id=account.get("user_id"),
            channel_id=account.get("platform_user_id"),
            metric=metric,
            window_days=account.get("_youtube_window_days") or 30,
            rows=normalized_rows,
            effective_start_date=effective_start_date,
            effective_end_date=effective_end_date,
            fetched_at=fetched_at,
        )
        return build_youtube_geography_payload(
            rows=normalized_rows,
            metric_label=metric_label,
            effective_start_date=effective_start_date,
            effective_end_date=effective_end_date,
            last_refreshed_at=fetched_at,
            source="live",
            provider_message=None,
            is_lag_adjusted=is_lag_adjusted,
            is_snapshot_fallback=False,
        )

    snapshot = await load_latest_youtube_geography_snapshot(
        db,
        account_id=account_id,
        metric=metric,
        window_days=account.get("_youtube_window_days") or 30,
    )
    if snapshot and snapshot.get("rows"):
        return build_youtube_geography_payload(
            rows=snapshot.get("rows") or [],
            metric_label=metric_label,
            effective_start_date=snapshot.get("effective_start_date"),
            effective_end_date=snapshot.get("effective_end_date"),
            last_refreshed_at=snapshot.get("last_refreshed_at"),
            source="snapshot",
            provider_message=None,
            is_lag_adjusted=bool(is_lag_adjusted or snapshot.get("effective_end_date") != effective_end_date.isoformat()),
            is_snapshot_fallback=True,
        )

    return build_youtube_geography_payload(
        rows=[],
        metric_label=metric_label,
        effective_start_date=effective_start_date,
        effective_end_date=effective_end_date,
        last_refreshed_at=None,
        source="empty",
        provider_message=YOUTUBE_GEOGRAPHY_DEFAULT_EMPTY_MESSAGE,
        is_lag_adjusted=is_lag_adjusted,
        is_snapshot_fallback=False,
    )


def _youtube_posts_in_window(posts: list[dict[str, Any]], start_date, end_date) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for post in posts:
        when = _parse_platform_timestamp(post.get("timestamp"))
        if when and start_date <= when.date() <= end_date:
            filtered.append(post)
    return filtered


def _youtube_total_engagement(post: dict[str, Any]) -> int:
    return _metric_int(post.get("likes")) + _metric_int(post.get("comments_count")) + _metric_int(post.get("shares"))


def _youtube_metric_label(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").title()


_YOUTUBE_AGE_GROUP_LABELS = {
    "AGE_13_17": "13-17",
    "AGE_18_24": "18-24",
    "AGE_25_34": "25-34",
    "AGE_35_44": "35-44",
    "AGE_45_54": "45-54",
    "AGE_55_64": "55-64",
    "AGE_65_": "65+",
}

_YOUTUBE_GENDER_LABELS = {
    "FEMALE": "Female",
    "MALE": "Male",
    "USER_SPECIFIED": "User Specified",
    "GENDER_OTHER": "Other",
}

_YOUTUBE_TRAFFIC_SOURCE_LABELS = {
    "ADVERTISING": "Advertising",
    "ANNOTATION": "Annotations",
    "CAMPAIGN_CARD": "Campaign Card",
    "END_SCREEN": "End Screen",
    "EXT_URL": "External Sites",
    "HASHTAGS": "Hashtags",
    "LIVE_REDIRECT": "Live Redirect",
    "NO_LINK_EMBEDDED": "Embedded",
    "NO_LINK_OTHER": "Other",
    "NOTIFICATION": "Notifications",
    "PLAYLIST": "Playlist",
    "PRODUCT_PAGE": "Product Page",
    "PROMOTED": "Promoted",
    "RELATED_VIDEO": "Related Video",
    "SHORTS": "Shorts Feed",
    "SOUND_PAGE": "Sound Page",
    "SUBSCRIBER": "Subscribers",
    "YT_CHANNEL": "Channel Page",
    "YT_OTHER_PAGE": "Other YouTube Page",
    "YT_SEARCH": "YouTube Search",
}

_YOUTUBE_PLAYBACK_LOCATION_LABELS = {
    "ON_YOUTUBE": "On YouTube",
    "EMBEDDED": "Embedded",
    "EXTERNAL_APP": "External App",
    "WATCH": "Watch Page",
    "CHANNEL": "Channel Page",
}

_YOUTUBE_OPERATING_SYSTEM_LABELS = {
    "ANDROID": "Android",
    "BLACKBERRY": "BlackBerry",
    "CHROMECAST": "Chromecast",
    "CHROMEOS": "Chrome OS",
    "DESKTOP": "Desktop",
    "FIREFOX": "Firefox",
    "IOS": "iOS",
    "LINUX": "Linux",
    "MACINTOSH": "macOS",
    "NINTENDO": "Nintendo",
    "PLAYSTATION": "PlayStation",
    "SMART_TV": "Smart TV",
    "TVHTML5": "TV",
    "UNKNOWN": "Unknown",
    "WII": "Wii",
    "WINDOWS": "Windows",
    "XBOX": "Xbox",
}

_YOUTUBE_DEVICE_TYPE_LABELS = {
    "DESKTOP": "Desktop",
    "MOBILE": "Mobile",
    "TABLET": "Tablet",
    "TV": "TV",
    "GAME_CONSOLE": "Game Console",
    "UNKNOWN": "Unknown",
}

_YOUTUBE_SUBSCRIBED_STATUS_LABELS = {
    "SUBSCRIBED": "Subscribed",
    "UNSUBSCRIBED": "Non Subscribed",
}

_YOUTUBE_CREATOR_CONTENT_TYPE_LABELS = {
    "SHORTS": "Shorts",
    "VIDEO_ON_DEMAND": "Long-form Video",
    "LIVE_STREAM": "Live Stream",
}

_YOUTUBE_LIVE_ON_DEMAND_LABELS = {
    "LIVE": "Live",
    "ON_DEMAND": "On Demand",
}

_YOUTUBE_SHARING_SERVICE_LABELS = {
    "COPY_TO_CLIPBOARD": "Copy Link",
    "EMBED": "Embed",
    "EMAIL": "Email",
    "FACEBOOK": "Facebook",
    "FACEBOOK_MESSENGER": "Messenger",
    "GMAIL": "Gmail",
    "INSTAGRAM": "Instagram",
    "LINE": "LINE",
    "OTHER": "Other",
    "PINTEREST": "Pinterest",
    "REDDIT": "Reddit",
    "SMS": "SMS",
    "TELEGRAM": "Telegram",
    "TUMBLR": "Tumblr",
    "TWITTER": "X / Twitter",
    "UNKNOWN": "Unknown",
    "WHATS_APP": "WhatsApp",
}


def _youtube_named_breakdown(
    rows: list[dict[str, Any]],
    dimension_key: str,
    value_keys: list[str],
    label_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        raw_value = str(row.get(dimension_key) or "")
        if not raw_value:
            continue
        label = (label_map or {}).get(raw_value.upper()) or _youtube_metric_label(raw_value)
        item = {"value": raw_value, "label": label}
        for key in value_keys:
            item[key] = row.get(key) or 0
        normalized.append(item)
    normalized.sort(key=lambda item: sum(_metric_int(item.get(key)) for key in value_keys), reverse=True)
    return normalized


def _youtube_country_breakdown(rows: list[dict[str, Any]], metric_key: str) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        country_code = str(row.get("country") or "").upper()
        if not country_code:
            continue
        normalized.append(
            {
                "country_code": country_code,
                "count": row.get(metric_key) or 0,
            }
        )
    normalized.sort(key=lambda item: _metric_int(item.get("count")), reverse=True)
    return normalized


def _merge_youtube_series(items: list[list[dict[str, Any]]]) -> list[dict[str, int | float]]:
    merged: dict[str, float] = {}
    for series in items:
        for point in series or []:
            date_key = point.get("date")
            if not date_key:
                continue
            merged[date_key] = merged.get(date_key, 0) + float(point.get("count") or 0)
    return [
        {"date": date_key, "count": int(value) if float(value).is_integer() else round(value, 4)}
        for date_key, value in sorted(merged.items())
    ]


def _merge_named_metrics(
    items: list[dict[str, Any]],
    key_name: str,
    metric_keys: list[str],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in items:
        key = str(item.get(key_name) or "")
        if not key:
            continue
        row = merged.setdefault(key, {key_name: key})
        if "label" in item and item.get("label") and not row.get("label"):
            row["label"] = item.get("label")
        if "country_code" in item and item.get("country_code") and not row.get("country_code"):
            row["country_code"] = item.get("country_code")
        for metric_key in metric_keys:
            row[metric_key] = row.get(metric_key, 0) + float(item.get(metric_key) or 0)
    normalized: list[dict[str, Any]] = []
    for row in merged.values():
        for metric_key in metric_keys:
            value = float(row.get(metric_key) or 0)
            row[metric_key] = int(value) if value.is_integer() else round(value, 4)
        normalized.append(row)
    normalized.sort(
        key=lambda row: sum(float(row.get(metric_key) or 0) for metric_key in metric_keys),
        reverse=True,
    )
    return normalized


def _merge_named_weighted_metrics(
    items: list[dict[str, Any]],
    key_name: str,
    additive_metric_keys: list[str],
    average_metric_keys: list[str],
    *,
    weight_key: str = "views",
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in items:
        key = str(item.get(key_name) or "")
        if not key:
            continue
        row = merged.setdefault(
            key,
            {
                key_name: key,
                "_weight_total": 0.0,
                **{f"_{metric_key}_weighted": 0.0 for metric_key in average_metric_keys},
            },
        )
        if item.get("label") and not row.get("label"):
            row["label"] = item.get("label")
        weight_value = float(item.get(weight_key) or 0)
        row["_weight_total"] += weight_value
        for metric_key in additive_metric_keys:
            row[metric_key] = row.get(metric_key, 0) + float(item.get(metric_key) or 0)
        for metric_key in average_metric_keys:
            row[f"_{metric_key}_weighted"] += float(item.get(metric_key) or 0) * weight_value

    normalized: list[dict[str, Any]] = []
    for row in merged.values():
        weight_total = float(row.pop("_weight_total", 0) or 0)
        for metric_key in additive_metric_keys:
            value = float(row.get(metric_key) or 0)
            row[metric_key] = int(value) if value.is_integer() else round(value, 4)
        for metric_key in average_metric_keys:
            weighted_total = float(row.pop(f"_{metric_key}_weighted", 0) or 0)
            value = (weighted_total / weight_total) if weight_total > 0 else 0.0
            row[metric_key] = int(value) if float(value).is_integer() else round(value, 4)
        normalized.append(row)

    ranking_keys = additive_metric_keys or average_metric_keys
    normalized.sort(
        key=lambda row: sum(float(row.get(metric_key) or 0) for metric_key in ranking_keys),
        reverse=True,
    )
    return normalized


def _youtube_series_from_rows(rows: list[dict[str, Any]], value_key: str) -> list[dict[str, int | float]]:
    return [
        {
            "date": str(row.get("day")),
            "count": int(row.get(value_key) or 0)
            if float(row.get(value_key) or 0).is_integer()
            else round(float(row.get(value_key) or 0), 4),
        }
        for row in rows
        if row.get("day")
    ]


def _youtube_watch_quality_series_from_rows(rows: list[dict[str, Any]]) -> list[dict[str, int | float]]:
    normalized: list[dict[str, int | float]] = []
    for row in rows:
        if not row.get("day"):
            continue
        normalized.append(
            {
                "date": str(row.get("day")),
                "engaged_views": _metric_int(row.get("engagedViews")),
                "average_view_duration_seconds": round(float(row.get("averageViewDuration") or 0), 4),
                "average_view_percentage": round(float(row.get("averageViewPercentage") or 0), 4),
                "views": _metric_int(row.get("views")),
            }
        )
    return normalized


def _merge_youtube_watch_quality_series(items: list[list[dict[str, Any]]]) -> list[dict[str, int | float]]:
    merged: dict[str, dict[str, float]] = {}
    for series in items:
        for point in series or []:
            date_key = str(point.get("date") or "")
            if not date_key:
                continue
            row = merged.setdefault(
                date_key,
                {
                    "engaged_views": 0.0,
                    "views": 0.0,
                    "_duration_weighted": 0.0,
                    "_percentage_weighted": 0.0,
                },
            )
            views = float(point.get("views") or 0)
            row["engaged_views"] += float(point.get("engaged_views") or 0)
            row["views"] += views
            row["_duration_weighted"] += float(point.get("average_view_duration_seconds") or 0) * views
            row["_percentage_weighted"] += float(point.get("average_view_percentage") or 0) * views

    normalized: list[dict[str, int | float]] = []
    for date_key in sorted(merged.keys()):
        row = merged[date_key]
        views = float(row.get("views") or 0)
        avg_duration = (float(row.get("_duration_weighted") or 0) / views) if views > 0 else 0.0
        avg_percentage = (float(row.get("_percentage_weighted") or 0) / views) if views > 0 else 0.0
        normalized.append(
            {
                "date": date_key,
                "engaged_views": int(row["engaged_views"]) if float(row["engaged_views"]).is_integer() else round(float(row["engaged_views"]), 4),
                "views": int(views) if views.is_integer() else round(views, 4),
                "average_view_duration_seconds": int(avg_duration) if float(avg_duration).is_integer() else round(avg_duration, 4),
                "average_view_percentage": int(avg_percentage) if float(avg_percentage).is_integer() else round(avg_percentage, 4),
            }
        )
    return normalized


def _youtube_video_card(video: dict[str, Any] | None) -> dict[str, Any] | None:
    if not video:
        return None
    return {
        "id": video.get("id"),
        "title": video.get("title") or video.get("content") or "",
        "content": video.get("content") or video.get("title") or "",
        "thumbnail_url": video.get("thumbnail_url") or video.get("media_url"),
        "timestamp": video.get("timestamp"),
        "permalink": video.get("permalink"),
        "views": _metric_int(video.get("views")),
        "estimated_minutes_watched": round(float(video.get("estimated_minutes_watched") or 0), 4),
        "likes": _metric_int(video.get("likes")),
        "comments": _metric_int(video.get("comments_count")),
        "shares": _metric_int(video.get("shares")),
        "engagement": _metric_int(video.get("engagement")),
    }


def _youtube_grouped_breakdown(
    rows: list[dict[str, Any]],
    dimension_key: str,
    value_keys: list[str],
    label_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    named = _youtube_named_breakdown(rows, dimension_key, value_keys, label_map)
    merged = _merge_named_metrics(named, "value", value_keys)
    for row in merged:
        row["label"] = row.get("label") or _youtube_metric_label(str(row.get("value") or ""))
    return merged


def _bluesky_post_engagement(post: dict[str, Any]) -> int:
    return (
        _metric_int(post.get("likes"))
        + _metric_int(post.get("comments_count"))
        + _metric_int(post.get("shares"))
        + _metric_int(post.get("quotes"))
    )


def _bluesky_post_engagement_rate(post: dict[str, Any], followers_total: int) -> float:
    if followers_total <= 0:
        return 0.0
    return round((_bluesky_post_engagement(post) / followers_total) * 100, 1)


def _series_from_dates(points: list[datetime]) -> list[dict[str, int]]:
    counts: dict[str, int] = {}
    for point in points:
        date_key = point.date().isoformat()
        counts[date_key] = counts.get(date_key, 0) + 1
    return [{"date": date_key, "count": counts[date_key]} for date_key in sorted(counts.keys())]


def _bluesky_metric_series(
    posts: list[dict[str, Any]],
    current_since: datetime,
    metric: str,
) -> list[dict[str, int]]:
    counts: dict[str, int] = {}
    for post in posts:
        ts = _parse_platform_timestamp(post.get("timestamp"))
        if ts and ts < current_since:
            continue
        if not ts:
            continue
        date_key = ts.date().isoformat()
        if metric == "posts":
            value = 1
        elif metric == "engagement":
            value = _bluesky_post_engagement(post)
        elif metric == "likes":
            value = _metric_int(post.get("likes"))
        elif metric == "replies":
            value = _metric_int(post.get("comments_count"))
        elif metric == "reposts":
            value = _metric_int(post.get("shares"))
        elif metric == "quotes":
            value = _metric_int(post.get("quotes"))
        else:
            value = 0
        counts[date_key] = counts.get(date_key, 0) + value
    return [{"date": date_key, "count": counts[date_key]} for date_key in sorted(counts.keys())]


def _merge_bluesky_metric_series(items: list[list[dict[str, int]]]) -> list[dict[str, int]]:
    merged: dict[str, int] = {}
    for series in items:
        for point in series:
            date_key = point.get("date")
            if not date_key:
                continue
            merged[date_key] = merged.get(date_key, 0) + _metric_int(point.get("count"))
    return [{"date": date_key, "count": merged[date_key]} for date_key in sorted(merged.keys())]


def _percentage_change(current: int | None, previous: int | None) -> float | None:
    if current is None or previous is None:
        return None
    if previous == 0:
        if current == 0:
            return 0.0
        return 100.0
    return round(((current - previous) / abs(previous)) * 100, 1)


def _merge_date_counts(series_list: list[list[dict[str, Any]]]) -> list[dict[str, int]]:
    merged: dict[str, int] = {}
    for series in series_list:
        for point in series:
            date = point.get("date")
            if not date:
                continue
            merged[date] = merged.get(date, 0) + _metric_int(point.get("count"))
    return [{"date": date, "count": merged[date]} for date in sorted(merged.keys())]


def _summarize_instagram_period(
    feed: list[dict[str, Any]],
    current_since: datetime,
    previous_since: datetime,
) -> dict[str, Any]:
    current_posts: list[dict[str, Any]] = []
    previous_posts: list[dict[str, Any]] = []

    for post in feed:
        ts = _parse_platform_timestamp(post.get("timestamp"))
        if not ts:
            current_posts.append(post)
            continue
        if ts >= current_since:
            current_posts.append(post)
        elif ts >= previous_since:
            previous_posts.append(post)

    def _post_engagement(post: dict[str, Any]) -> int:
        return _metric_int(post.get("likes")) + _metric_int(post.get("comments_count"))

    current_total_engagement = sum(_post_engagement(post) for post in current_posts)
    previous_total_engagement = sum(_post_engagement(post) for post in previous_posts)

    type_summary: dict[str, dict[str, int]] = {}
    reels: list[dict[str, Any]] = []

    for post in current_posts:
        post_type = _instagram_post_type(post)
        engagement = _post_engagement(post)
        bucket = type_summary.setdefault(post_type, {"posts": 0, "engagement": 0})
        bucket["posts"] += 1
        bucket["engagement"] += engagement
        if post_type == "reel":
            reels.append(post)

    type_order = ["image", "carousel", "video", "reel", "text"]
    type_labels = {
        "image": "Images",
        "carousel": "Carousels",
        "video": "Videos",
        "reel": "Reels",
        "text": "Text",
    }
    engagement_by_type = [
        {
            "type": key,
            "label": type_labels[key],
            "posts": type_summary.get(key, {}).get("posts", 0),
            "engagement": type_summary.get(key, {}).get("engagement", 0),
        }
        for key in type_order
        if type_summary.get(key)
    ]

    top_post = max(current_posts, key=_post_engagement, default=None)
    top_reel = max(reels, key=_post_engagement, default=None)
    reel_engagement = sum(_post_engagement(post) for post in reels)
    previous_reels = [post for post in previous_posts if _instagram_post_type(post) == "reel"]
    previous_reel_engagement = sum(_post_engagement(post) for post in previous_reels)

    return {
        "total_posts": len(current_posts),
        "avg_posts_per_day": round(len(current_posts) / max((current_since - previous_since).days, 1), 2),
        "total_engagement": current_total_engagement,
        "avg_engagement_per_post": round(current_total_engagement / len(current_posts), 2) if current_posts else 0,
        "avg_engagement_per_day": round(current_total_engagement / max((current_since - previous_since).days, 1), 2),
        "total_posts_change_pct": _percentage_change(len(current_posts), len(previous_posts)),
        "total_engagement_change_pct": _percentage_change(current_total_engagement, previous_total_engagement),
        "engagement_by_type": engagement_by_type,
        "top_post": top_post,
        "reels": {
            "total_reels": len(reels),
            "total_engagement": reel_engagement,
            "total_reels_change_pct": _percentage_change(len(reels), len(previous_reels)),
            "total_engagement_change_pct": _percentage_change(reel_engagement, previous_reel_engagement),
            "top_reel": top_reel,
        },
    }


@router.get("/analytics/instagram-report")
async def analytics_instagram_report(
    current_user: CurrentUser,
    db: DB,
    days: int = Query(30, ge=1, le=365),
    account_id: str | None = Query(None, alias="accountId"),
):
    accounts = await _load_social_accounts(db, current_user["user_id"], "instagram", account_id)
    if not accounts:
        return {
            "supported": False,
            "message": "Connect an Instagram Business or Creator account to view this report.",
        }

    current_since = datetime.now(timezone.utc) - timedelta(days=days)
    previous_since = current_since - timedelta(days=days)
    all_current_feed: list[dict[str, Any]] = []
    follower_series: list[list[dict[str, Any]]] = []
    summary_totals = {
        "followers_total": 0,
        "new_followers": 0,
        "reach": 0,
        "impressions": 0,
        "profile_views": 0,
    }
    demographics_bucket = {"age": [], "gender": [], "cities": [], "countries": []}
    accounts_used: list[str] = []
    errors: list[dict[str, str]] = []
    demographics_errors: list[dict[str, str]] = []

    from backend.app.social.instagram import InstagramAuth

    auth = InstagramAuth()

    for account in accounts:
        label = _account_error_label(account)
        platform_user_id = account.get("platform_user_id")
        encrypted_token = account.get("access_token")
        if not platform_user_id or not encrypted_token:
            _append_account_error(errors, account, "Account is missing platform credentials.")
            continue

        try:
            access_token = decrypt(encrypted_token)
        except Exception:
            _append_account_error(errors, account, "Stored token could not be decrypted.")
            continue

        try:
            feed = await auth.fetch_feed(access_token, platform_user_id, limit=100)
            engagement = await auth.fetch_engagement(access_token, platform_user_id, days=days)
            growth = await auth.fetch_follower_growth(access_token, platform_user_id, days=days)
        except Exception as exc:
            _append_account_error(errors, account, _analytics_error_message("instagram", exc))
            continue

        if not feed:
            feed = await _fetch_db_published_posts(db, current_user["user_id"], account, limit=100)

        all_current_feed.extend(feed)
        summary_totals["followers_total"] += _metric_int(engagement.get("followers"))
        summary_totals["new_followers"] += _metric_int(
            growth.get("growth") if growth.get("supported") else engagement.get("followers_growth")
        )
        summary_totals["reach"] += _metric_int(engagement.get("reach"))
        summary_totals["impressions"] += _metric_int(engagement.get("impressions"))
        summary_totals["profile_views"] += _metric_int(engagement.get("profile_views"))
        if growth.get("growth_series"):
            follower_series.append(growth["growth_series"])

        demographics = await auth.fetch_demographics(access_token, platform_user_id)
        if demographics.get("supported"):
            accounts_used.append(label)
            demographics_bucket["age"].extend(demographics.get("age", []))
            demographics_bucket["gender"].extend(demographics.get("gender", []))
            demographics_bucket["cities"].extend(demographics.get("cities", []))
            demographics_bucket["countries"].extend(demographics.get("countries", []))
        else:
            demographics_errors.append(
                {
                    "account": label,
                    "error": demographics.get("error")
                    or "Demographics are not available for this Instagram account yet.",
                }
            )

    if not any(summary_totals.values()) and not all_current_feed and errors:
        return {
            "supported": False,
            "message": "Unable to load Instagram analytics for the selected account.",
            "errors": errors,
        }

    period_summary = _summarize_instagram_period(all_current_feed, current_since, previous_since)
    merged_demographics = {
        "age": _merge_named_counts(demographics_bucket["age"], "range"),
        "gender": _merge_named_counts(demographics_bucket["gender"], "label"),
        "cities": _merge_named_counts(demographics_bucket["cities"], "name")[:10],
        "countries": _merge_named_counts(demographics_bucket["countries"], "name")[:10],
    }

    def _normalize_top_entry(post: dict[str, Any] | None) -> dict[str, Any] | None:
        if not post:
            return None
        return {
            "id": post.get("id"),
            "content": post.get("content", ""),
            "media_url": post.get("media_url"),
            "video_url": post.get("video_url"),
            "media_type": post.get("media_type"),
            "timestamp": post.get("timestamp"),
            "permalink": post.get("permalink"),
            "engagement": _metric_int(post.get("likes")) + _metric_int(post.get("comments_count")),
            "likes": _metric_int(post.get("likes")),
            "comments": _metric_int(post.get("comments_count")),
        }

    report = {
        "supported": True,
        "days": days,
        "summary": {
            "followers_total": summary_totals["followers_total"],
            "new_followers": summary_totals["new_followers"],
            "avg_new_followers_per_day": round(summary_totals["new_followers"] / max(days, 1), 2),
            "reach": summary_totals["reach"],
            "impressions": summary_totals["impressions"],
            "profile_views": summary_totals["profile_views"],
            "post_summary": {
                "total_posts": period_summary["total_posts"],
                "avg_posts_per_day": round(period_summary["total_posts"] / max(days, 1), 2),
                "total_engagement": period_summary["total_engagement"],
                "avg_engagement_per_post": period_summary["avg_engagement_per_post"],
                "avg_engagement_per_day": round(period_summary["total_engagement"] / max(days, 1), 2),
                "total_posts_change_pct": period_summary["total_posts_change_pct"],
                "total_engagement_change_pct": period_summary["total_engagement_change_pct"],
                "top_post": _normalize_top_entry(period_summary["top_post"]),
                "engagement_by_type": period_summary["engagement_by_type"],
            },
            "reels_summary": {
                "total_reels": period_summary["reels"]["total_reels"],
                "total_engagement": period_summary["reels"]["total_engagement"],
                "total_reels_change_pct": period_summary["reels"]["total_reels_change_pct"],
                "total_engagement_change_pct": period_summary["reels"]["total_engagement_change_pct"],
                "top_reel": _normalize_top_entry(period_summary["reels"]["top_reel"]),
            },
        },
        "audience": {
            "follower_growth": _merge_date_counts(follower_series),
            "demographics_supported": bool(any(merged_demographics.values())),
            "demographics_message": (
                None
                if any(merged_demographics.values())
                else "Follower demographics are only available when Instagram returns insights for this Business/Creator account, typically after the account has enough audience data."
            ),
            "accounts_used": accounts_used,
            "demographics": merged_demographics,
        },
        "errors": errors,
        "demographics_errors": demographics_errors,
    }
    return report


@router.get("/analytics/youtube-report")
async def analytics_youtube_report(
    current_user: CurrentUser,
    db: DB,
    days: int = Query(30, ge=1, le=365),
    account_id: str | None = Query(None, alias="accountId"),
    group_by: str = Query("day", alias="groupBy", pattern="^(day|week|month|quarter)$"),
):
    accounts, fallback_used = await _load_social_accounts_for_report(
        db,
        current_user["user_id"],
        "youtube",
        account_id,
    )
    if not accounts:
        return {
            "supported": False,
            "message": "Connect a YouTube account to view this report.",
            "days": days,
            "group_by": group_by,
        }

    from api.routes.accounts import _get_youtube_access_token
    from backend.app.social.google import GoogleAuth

    auth = GoogleAuth()
    start_date, end_date, previous_start, previous_end = _youtube_period_bounds(days)
    geography_start_date, geography_end_date, geography_is_lag_adjusted = compute_youtube_settled_window(
        days,
        selected_end_date=end_date,
    )
    all_feed: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    message: str | None = None
    analytics_enabled = False
    card_metrics_supported = False
    optional_support = {
        "subscriber_geography": True,
        "views_geography": True,
        "minutes_geography": True,
        "traffic_source": True,
        "playback_location": True,
        "device_type": True,
        "subscribed_status": True,
        "search_terms": True,
        "watch_quality": True,
        "viewer_demographics": True,
        "operating_system": True,
        "content_type_breakdown": True,
        "sharing_services": True,
        "retention": True,
    }

    audience_summary = {
        "subscribers_count": 0,
        "subscribers_gained": 0,
        "subscribers_lost": 0,
    }
    post_summary = {
        "videos": 0,
        "engagement": 0,
    }
    cards_summary = {
        "card_impressions": 0,
        "card_teaser_impressions": 0,
        "card_clicks": 0,
        "card_teaser_clicks": 0,
    }
    watch_quality_summary = {
        "engaged_views": 0,
        "views_weight": 0,
        "avg_duration_weighted": 0.0,
        "avg_percentage_weighted": 0.0,
    }
    previous_watch_quality_summary = {
        "engaged_views": 0,
        "views_weight": 0,
        "avg_duration_weighted": 0.0,
        "avg_percentage_weighted": 0.0,
    }
    previous_totals = {
        "subscribers_gained": 0,
        "subscribers_lost": 0,
        "videos": 0,
        "engagement": 0,
        "views": 0,
        "estimated_minutes_watched": 0.0,
        "card_impressions": 0,
        "card_teaser_impressions": 0,
        "card_clicks": 0,
        "card_teaser_clicks": 0,
    }

    subscriber_growth_series: list[list[dict[str, Any]]] = []
    views_series: list[list[dict[str, Any]]] = []
    minutes_series: list[list[dict[str, Any]]] = []
    watch_quality_series: list[list[dict[str, Any]]] = []
    subscriber_geo_items: list[dict[str, Any]] = []
    views_geo_payloads: list[dict[str, Any]] = []
    minutes_geo_payloads: list[dict[str, Any]] = []
    traffic_source_items: list[dict[str, Any]] = []
    playback_location_items: list[dict[str, Any]] = []
    operating_system_items: list[dict[str, Any]] = []
    device_type_items: list[dict[str, Any]] = []
    subscribed_status_items: list[dict[str, Any]] = []
    search_term_items: list[dict[str, Any]] = []
    creator_content_type_items: list[dict[str, Any]] = []
    live_on_demand_items: list[dict[str, Any]] = []
    sharing_service_items: list[dict[str, Any]] = []
    demographic_age_items: list[dict[str, Any]] = []
    demographic_gender_items: list[dict[str, Any]] = []
    demographic_matrix_items: list[dict[str, Any]] = []
    top_videos_by_views: list[dict[str, Any]] = []
    top_videos_by_minutes: list[dict[str, Any]] = []
    retention_video_ids: list[str] = []
    retention_payloads: dict[str, dict[str, Any]] = {}

    async def safe_query(
        access_token: str,
        metrics: list[str],
        *,
        dimensions: list[str] | None = None,
        filters: dict[str, str] | None = None,
        sort: list[str] | None = None,
        max_results: int | None = None,
        label: str,
        critical: bool = False,
        start_date_override=None,
        end_date_override=None,
        query_kind: str = "generic",
    ) -> list[dict[str, Any]]:
        nonlocal analytics_enabled, message, card_metrics_supported
        try:
            query_start = start_date_override or start_date
            query_end = end_date_override or end_date
            if query_kind == "totals":
                rows = await auth.query_channel_analytics_totals(
                    access_token,
                    metrics=metrics,
                    start_date=query_start,
                    end_date=query_end,
                )
            elif query_kind == "time_series":
                rows = await auth.query_channel_analytics_time_series(
                    access_token,
                    metrics=metrics,
                    start_date=query_start,
                    end_date=query_end,
                    dimension=(dimensions or ["day"])[0],
                )
            elif query_kind == "dimension_breakdown":
                rows = await auth.query_channel_dimension_breakdown(
                    access_token,
                    metrics=metrics,
                    start_date=query_start,
                    end_date=query_end,
                    dimensions=dimensions or [],
                    filters=filters,
                    sort=sort,
                    max_results=max_results,
                )
            elif query_kind == "retention":
                rows = await auth.query_video_retention(
                    access_token,
                    video_id=(filters or {}).get("video", ""),
                    start_date=query_start,
                    end_date=query_end,
                )
            else:
                rows = await auth.query_analytics_report(
                    access_token,
                    metrics=metrics,
                    start_date=query_start,
                    end_date=query_end,
                    dimensions=dimensions,
                    filters=filters,
                    sort=sort,
                    max_results=max_results,
                )
            analytics_enabled = True
            if label == "cards":
                card_metrics_supported = True
            return rows
        except Exception as exc:
            if not critical and label in optional_support:
                optional_support[label] = False
            if critical and not message:
                message = _analytics_error_message("youtube", exc)
            event_log(
                logger,
                "warning",
                "analytics.provider.fetch_failed",
                exc_info=exc,
                route="/analytics/youtube-report",
                platform="youtube",
                failure_type=f"youtube_{label}_failed",
                provider_error=shorten_provider_error(exc),
                fetch_mode="api",
                outcome="degraded",
            )
            capture_degraded_event(
                "analytics.provider.fetch_failed",
                platform="youtube",
                route="/analytics/youtube-report",
                failure_type=f"youtube_{label}_failed",
                provider_error=shorten_provider_error(exc),
            )
            return []

    async def safe_previous_totals(
        access_token: str,
        metrics: list[str],
    ) -> dict[str, int | float]:
        nonlocal analytics_enabled
        try:
            rows = await auth.query_channel_analytics_totals(
                access_token,
                metrics=metrics,
                start_date=previous_start,
                end_date=previous_end,
            )
            analytics_enabled = True
            totals: dict[str, int | float] = {}
            for row in rows:
                for key in metrics:
                    totals[key] = totals.get(key, 0) + float(row.get(key) or 0)
            return totals
        except Exception:
            return {}

    async def resolve_geography_payload_with_recent_fallback(
        access_token: str,
        *,
        account: dict[str, Any],
        metric: str,
        metric_label: str,
        label: str,
    ) -> dict[str, Any]:
        rows = await safe_query(
            access_token,
            [metric],
            dimensions=["country"],
            sort=[f"-{metric}"],
            max_results=25,
            label=label,
            start_date_override=geography_start_date,
            end_date_override=geography_end_date,
            query_kind="dimension_breakdown",
        )
        effective_start_date = geography_start_date
        effective_end_date = geography_end_date
        is_lag_adjusted = geography_is_lag_adjusted

        if geography_is_lag_adjusted and not normalize_youtube_geography_rows(rows, value_key=metric):
            recent_rows = await safe_query(
                access_token,
                [metric],
                dimensions=["country"],
                sort=[f"-{metric}"],
                max_results=25,
                label=f"{label}_current_window",
                start_date_override=start_date,
                end_date_override=end_date,
                query_kind="dimension_breakdown",
            )
            if normalize_youtube_geography_rows(recent_rows, value_key=metric):
                rows = recent_rows
                effective_start_date = start_date
                effective_end_date = end_date
                is_lag_adjusted = False

        return await _resolve_youtube_geography_payload(
            db,
            account=account,
            metric=metric,
            metric_label=metric_label,
            query_rows=rows,
            effective_start_date=effective_start_date,
            effective_end_date=effective_end_date,
            is_lag_adjusted=is_lag_adjusted,
        )

    for account in accounts:
        account["_youtube_window_days"] = days
        label = _account_error_label(account)
        encrypted_token = account.get("access_token")
        platform_user_id = account.get("platform_user_id")
        if not encrypted_token:
            _append_account_error(errors, account, "Account is missing platform credentials.")
            continue

        try:
            access_token = decrypt(encrypted_token)
        except Exception:
            _append_account_error(errors, account, "Stored token could not be decrypted.")
            continue

        try:
            channel = await auth.get_channel_info(access_token)
        except Exception:
            try:
                access_token = await _get_youtube_access_token(db, account, force_refresh=True)
                channel = await auth.get_channel_info(access_token)
            except Exception as exc:
                _append_account_error(errors, account, _analytics_error_message("youtube", exc))
                continue

        channel_id = str(channel.get("id") or platform_user_id or "")
        engagement_snapshot = await auth.fetch_youtube_engagement(access_token, channel_id, days=days)
        audience_summary["subscribers_count"] += _metric_int(
            engagement_snapshot.get("subscribers") or channel.get("subscribers")
        )

        try:
            feed = await auth.fetch_youtube_feed(access_token, channel_id, limit=100)
        except Exception as exc:
            event_log(
                logger,
                "warning",
                "analytics.provider.fetch_failed",
                exc_info=exc,
                route="/analytics/youtube-report",
                platform="youtube",
                account_id=account.get("account_id") or account.get("id"),
                failure_type="youtube_feed_failed",
                provider_error=shorten_provider_error(exc),
                fetch_mode="api",
                outcome="degraded",
            )
            feed = []

        feed = [_standardize_feed_post(post) for post in (feed or [])]
        if not feed:
            fallback_posts = await _fetch_db_published_posts(db, current_user["user_id"], account, limit=100)
            feed = [_standardize_feed_post(post) for post in fallback_posts]
        all_feed.extend(feed)

        current_feed = _youtube_posts_in_window(feed, start_date, end_date)
        previous_feed = _youtube_posts_in_window(feed, previous_start, previous_end)
        post_summary["videos"] += len(current_feed)
        previous_totals["videos"] += len(previous_feed)

        daily_subscriber_rows = await safe_query(
            access_token,
            ["subscribersGained", "subscribersLost"],
            dimensions=["day"],
            label="subscriber_growth",
            critical=True,
            query_kind="time_series",
        )
        if daily_subscriber_rows:
            subscriber_growth_series.append(
                [
                    {
                        "date": str(row.get("day")),
                        "gained": _metric_int(row.get("subscribersGained")),
                        "lost": _metric_int(row.get("subscribersLost")),
                        "net": _metric_int(row.get("subscribersGained")) - _metric_int(row.get("subscribersLost")),
                    }
                    for row in daily_subscriber_rows
                    if row.get("day")
                ]
            )
            audience_summary["subscribers_gained"] += sum(_metric_int(row.get("subscribersGained")) for row in daily_subscriber_rows)
            audience_summary["subscribers_lost"] += sum(_metric_int(row.get("subscribersLost")) for row in daily_subscriber_rows)
        else:
            audience_summary["subscribers_gained"] += _metric_int(engagement_snapshot.get("subscribers_gained"))
            audience_summary["subscribers_lost"] += _metric_int(engagement_snapshot.get("subscribers_lost"))

        totals_rows = await safe_query(
            access_token,
            ["likes", "comments", "shares", "views", "estimatedMinutesWatched"],
            label="totals",
            critical=True,
            query_kind="totals",
        )
        account_period_views = _metric_int(engagement_snapshot.get("period_views"))
        if totals_rows:
            post_summary["engagement"] += sum(
                _metric_int(row.get("likes")) + _metric_int(row.get("comments")) + _metric_int(row.get("shares"))
                for row in totals_rows
            )
            account_period_views = sum(_metric_int(row.get("views")) for row in totals_rows)
            previous_period_totals = await safe_previous_totals(
                access_token,
                ["likes", "comments", "shares", "views", "estimatedMinutesWatched", "subscribersGained", "subscribersLost"],
            )
            previous_totals["engagement"] += _metric_int(previous_period_totals.get("likes")) + _metric_int(previous_period_totals.get("comments")) + _metric_int(previous_period_totals.get("shares"))
            previous_totals["views"] += float(previous_period_totals.get("views") or 0)
            previous_totals["estimated_minutes_watched"] += float(previous_period_totals.get("estimatedMinutesWatched") or 0)
            previous_totals["subscribers_gained"] += _metric_int(previous_period_totals.get("subscribersGained"))
            previous_totals["subscribers_lost"] += _metric_int(previous_period_totals.get("subscribersLost"))
        else:
            post_summary["engagement"] += (
                _metric_int(engagement_snapshot.get("period_likes"))
                + _metric_int(engagement_snapshot.get("period_comments"))
                + _metric_int(engagement_snapshot.get("period_shares"))
            )

        daily_views_rows = await safe_query(
            access_token,
            ["views", "estimatedMinutesWatched"],
            dimensions=["day"],
            label="views_minutes_series",
            critical=True,
            query_kind="time_series",
        )
        if daily_views_rows:
            views_series.append(_youtube_series_from_rows(daily_views_rows, "views"))
            minutes_series.append(_youtube_series_from_rows(daily_views_rows, "estimatedMinutesWatched"))
        elif engagement_snapshot.get("period_views") is not None or engagement_snapshot.get("period_minutes_watched") is not None:
            synthetic_date = end_date.isoformat()
            views_series.append([{"date": synthetic_date, "count": _metric_int(engagement_snapshot.get("period_views"))}])
            minutes_series.append([{"date": synthetic_date, "count": float(engagement_snapshot.get("period_minutes_watched") or 0)}])

        watch_quality_totals_rows = await safe_query(
            access_token,
            ["engagedViews", "averageViewDuration", "averageViewPercentage", "views"],
            label="watch_quality",
            query_kind="totals",
        )
        if watch_quality_totals_rows:
            for row in watch_quality_totals_rows:
                views_weight = _metric_int(row.get("views"))
                watch_quality_summary["engaged_views"] += _metric_int(row.get("engagedViews"))
                watch_quality_summary["views_weight"] += views_weight
                watch_quality_summary["avg_duration_weighted"] += float(row.get("averageViewDuration") or 0) * views_weight
                watch_quality_summary["avg_percentage_weighted"] += float(row.get("averageViewPercentage") or 0) * views_weight

            previous_watch_quality_rows = await safe_previous_totals(
                access_token,
                ["engagedViews", "averageViewDuration", "averageViewPercentage", "views"],
            )
            previous_views_weight = _metric_int(previous_watch_quality_rows.get("views"))
            previous_watch_quality_summary["engaged_views"] += _metric_int(previous_watch_quality_rows.get("engagedViews"))
            previous_watch_quality_summary["views_weight"] += previous_views_weight
            previous_watch_quality_summary["avg_duration_weighted"] += float(previous_watch_quality_rows.get("averageViewDuration") or 0) * previous_views_weight
            previous_watch_quality_summary["avg_percentage_weighted"] += float(previous_watch_quality_rows.get("averageViewPercentage") or 0) * previous_views_weight

        watch_quality_daily_rows = await safe_query(
            access_token,
            ["engagedViews", "averageViewDuration", "averageViewPercentage", "views"],
            dimensions=["day"],
            label="watch_quality",
            query_kind="time_series",
        )
        if watch_quality_daily_rows:
            watch_quality_series.append(_youtube_watch_quality_series_from_rows(watch_quality_daily_rows))

        top_videos_by_view_rows = await safe_query(
            access_token,
            ["views", "estimatedMinutesWatched", "likes", "comments", "shares"],
            dimensions=["video"],
            sort=["-views"],
            max_results=25,
            label="top_videos_by_views",
            query_kind="dimension_breakdown",
        )
        top_videos_by_minutes_rows = await safe_query(
            access_token,
            ["views", "estimatedMinutesWatched", "likes", "comments", "shares"],
            dimensions=["video"],
            sort=["-estimatedMinutesWatched"],
            max_results=25,
            label="top_videos_by_minutes",
            query_kind="dimension_breakdown",
        )
        unique_video_ids = {
            str(row.get("video") or "")
            for row in [*(top_videos_by_view_rows or []), *(top_videos_by_minutes_rows or [])]
            if row.get("video")
        }
        if unique_video_ids:
            details = await auth.fetch_video_details(access_token, sorted(unique_video_ids))

            def build_top_video_items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
                items: list[dict[str, Any]] = []
                for row in rows:
                    video_id = str(row.get("video") or "")
                    detail = details.get(video_id, {})
                    snippet = detail.get("snippet", {})
                    stats = detail.get("statistics", {})
                    item = {
                        "id": video_id,
                        "title": snippet.get("title") or "",
                        "content": snippet.get("title") or "",
                        "thumbnail_url": (snippet.get("thumbnails") or {}).get("high", {}).get("url"),
                        "timestamp": snippet.get("publishedAt"),
                        "permalink": f"https://youtube.com/watch?v={video_id}" if video_id else None,
                        "views": _metric_int(row.get("views") or stats.get("viewCount")),
                        "estimated_minutes_watched": round(float(row.get("estimatedMinutesWatched") or 0), 4),
                        "likes": _metric_int(row.get("likes") or stats.get("likeCount")),
                        "comments": _metric_int(row.get("comments") or stats.get("commentCount")),
                        "comments_count": _metric_int(row.get("comments") or stats.get("commentCount")),
                        "shares": _metric_int(row.get("shares")),
                    }
                    item["engagement"] = item["likes"] + item["comments"] + item["shares"]
                    items.append(item)
                return items

            top_videos_by_views.extend(build_top_video_items(top_videos_by_view_rows or []))
            top_videos_by_minutes.extend(build_top_video_items(top_videos_by_minutes_rows or []))

            ordered_retention_video_ids: list[str] = []
            for item in [*top_videos_by_views[:5], *top_videos_by_minutes[:5]]:
                video_id = str(item.get("id") or "")
                if video_id and video_id not in ordered_retention_video_ids:
                    ordered_retention_video_ids.append(video_id)

            for video_id in ordered_retention_video_ids:
                retention_rows = await safe_query(
                    access_token,
                    ["audienceWatchRatio", "relativeRetentionPerformance"],
                    filters={"video": video_id},
                    label="retention",
                    query_kind="retention",
                )
                if not retention_rows:
                    continue
                detail = details.get(video_id, {})
                snippet = detail.get("snippet", {})
                retention_payloads[video_id] = {
                    "video_id": video_id,
                    "title": snippet.get("title") or "",
                    "thumbnail_url": (snippet.get("thumbnails") or {}).get("high", {}).get("url"),
                    "published_at": snippet.get("publishedAt"),
                    "series": [
                        {
                            "elapsed_video_time_ratio": round(float(row.get("elapsedVideoTimeRatio") or 0), 4),
                            "audience_watch_ratio": round(float(row.get("audienceWatchRatio") or 0), 4),
                            "relative_retention_performance": round(float(row.get("relativeRetentionPerformance") or 0), 4),
                        }
                        for row in retention_rows
                        if row.get("elapsedVideoTimeRatio") is not None
                    ],
                }
                if retention_payloads[video_id]["series"]:
                    retention_video_ids.append(video_id)

        subscriber_geo_rows = await safe_query(
            access_token,
            ["subscribersGained"],
            dimensions=["country"],
            sort=["-subscribersGained"],
            max_results=25,
            label="subscriber_geography",
            query_kind="dimension_breakdown",
        )
        subscriber_geo_items.extend(
            [
                {
                    "country_code": str(row.get("country") or "").upper(),
                    "count": _metric_int(row.get("subscribersGained")),
                }
                for row in subscriber_geo_rows
                if row.get("country")
            ]
        )

        views_geo_payloads.append(
            await resolve_geography_payload_with_recent_fallback(
                access_token,
                account=account,
                metric="views",
                metric_label="Views",
                label="views_geography",
            )
        )

        minutes_geo_payloads.append(
            await resolve_geography_payload_with_recent_fallback(
                access_token,
                account=account,
                metric="estimatedMinutesWatched",
                metric_label="Minutes Watched",
                label="minutes_geography",
            )
        )

        traffic_source_items.extend(
            _youtube_named_breakdown(
                await safe_query(
                    access_token,
                    ["views", "estimatedMinutesWatched"],
                    dimensions=["insightTrafficSourceType"],
                    sort=["-views"],
                    max_results=25,
                    label="traffic_source",
                    query_kind="dimension_breakdown",
                ),
                "insightTrafficSourceType",
                ["views", "estimatedMinutesWatched"],
                _YOUTUBE_TRAFFIC_SOURCE_LABELS,
            )
        )

        playback_location_items.extend(
            _youtube_named_breakdown(
                await safe_query(
                    access_token,
                    ["views", "estimatedMinutesWatched"],
                    dimensions=["insightPlaybackLocationType"],
                    sort=["-views"],
                    max_results=25,
                    label="playback_location",
                    query_kind="dimension_breakdown",
                ),
                "insightPlaybackLocationType",
                ["views", "estimatedMinutesWatched"],
                _YOUTUBE_PLAYBACK_LOCATION_LABELS,
            )
        )

        operating_system_items.extend(
            _youtube_named_breakdown(
                await safe_query(
                    access_token,
                    ["views", "estimatedMinutesWatched"],
                    dimensions=["operatingSystem"],
                    sort=["-views"],
                    max_results=25,
                    label="operating_system",
                    query_kind="dimension_breakdown",
                ),
                "operatingSystem",
                ["views", "estimatedMinutesWatched"],
                _YOUTUBE_OPERATING_SYSTEM_LABELS,
            )
        )

        device_type_items.extend(
            _youtube_named_breakdown(
                await safe_query(
                    access_token,
                    ["views"],
                    dimensions=["deviceType"],
                    sort=["-views"],
                    max_results=25,
                    label="device_type",
                    query_kind="dimension_breakdown",
                ),
                "deviceType",
                ["views"],
                _YOUTUBE_DEVICE_TYPE_LABELS,
            )
        )

        subscribed_status_items.extend(
            _youtube_named_breakdown(
                await safe_query(
                    access_token,
                    ["views", "estimatedMinutesWatched"],
                    dimensions=["subscribedStatus"],
                    sort=["-views"],
                    max_results=25,
                    label="subscribed_status",
                    query_kind="dimension_breakdown",
                ),
                "subscribedStatus",
                ["views", "estimatedMinutesWatched"],
                _YOUTUBE_SUBSCRIBED_STATUS_LABELS,
            )
        )

        creator_content_type_items.extend(
            _youtube_named_breakdown(
                await safe_query(
                    access_token,
                    ["views", "estimatedMinutesWatched", "engagedViews", "averageViewDuration", "averageViewPercentage"],
                    dimensions=["creatorContentType"],
                    sort=["-views"],
                    max_results=25,
                    label="content_type_breakdown",
                    query_kind="dimension_breakdown",
                ),
                "creatorContentType",
                ["views", "estimatedMinutesWatched", "engagedViews", "averageViewDuration", "averageViewPercentage"],
                _YOUTUBE_CREATOR_CONTENT_TYPE_LABELS,
            )
        )

        live_on_demand_items.extend(
            _youtube_named_breakdown(
                await safe_query(
                    access_token,
                    ["views", "estimatedMinutesWatched", "engagedViews", "averageViewDuration", "averageViewPercentage"],
                    dimensions=["liveOrOnDemand"],
                    sort=["-views"],
                    max_results=25,
                    label="content_type_breakdown",
                    query_kind="dimension_breakdown",
                ),
                "liveOrOnDemand",
                ["views", "estimatedMinutesWatched", "engagedViews", "averageViewDuration", "averageViewPercentage"],
                _YOUTUBE_LIVE_ON_DEMAND_LABELS,
            )
        )

        search_term_rows = await safe_query(
            access_token,
            ["views", "estimatedMinutesWatched"],
            dimensions=["insightTrafficSourceDetail"],
            filters={"insightTrafficSourceType": "YT_SEARCH"},
            sort=["-views"],
            max_results=20,
            label="search_terms",
            query_kind="dimension_breakdown",
        )
        search_term_items.extend(
            [
                {
                    "term": str(row.get("insightTrafficSourceDetail") or ""),
                    "views": _metric_int(row.get("views")),
                    "estimated_minutes_watched": round(float(row.get("estimatedMinutesWatched") or 0), 4),
                }
                for row in search_term_rows
                if row.get("insightTrafficSourceDetail")
            ]
        )

        demographic_rows = await safe_query(
            access_token,
            ["viewerPercentage"],
            dimensions=["ageGroup", "gender"],
            sort=["-viewerPercentage"],
            max_results=100,
            label="viewer_demographics",
            query_kind="dimension_breakdown",
        )
        demographic_weight = max(account_period_views, 1)
        account_age_percentages: dict[str, float] = {}
        account_gender_percentages: dict[str, float] = {}
        for row in demographic_rows:
            age_key = str(row.get("ageGroup") or "").upper()
            gender_key = str(row.get("gender") or "").upper()
            viewer_percentage = round(float(row.get("viewerPercentage") or 0), 4)
            if not age_key or not gender_key:
                continue
            account_age_percentages[age_key] = account_age_percentages.get(age_key, 0.0) + viewer_percentage
            account_gender_percentages[gender_key] = account_gender_percentages.get(gender_key, 0.0) + viewer_percentage
            demographic_matrix_items.append(
                {
                    "value": f"{age_key}:{gender_key}",
                    "label": f"{_YOUTUBE_AGE_GROUP_LABELS.get(age_key) or _youtube_metric_label(age_key)} / {_YOUTUBE_GENDER_LABELS.get(gender_key) or _youtube_metric_label(gender_key)}",
                    "age_group": age_key,
                    "age_group_label": _YOUTUBE_AGE_GROUP_LABELS.get(age_key) or _youtube_metric_label(age_key),
                    "gender": gender_key,
                    "gender_label": _YOUTUBE_GENDER_LABELS.get(gender_key) or _youtube_metric_label(gender_key),
                    "viewer_percentage": viewer_percentage,
                    "views": demographic_weight,
                }
            )
        demographic_age_items.extend(
            [
                {
                    "value": age_key,
                    "label": _YOUTUBE_AGE_GROUP_LABELS.get(age_key) or _youtube_metric_label(age_key),
                    "viewer_percentage": round(value, 4),
                    "views": demographic_weight,
                }
                for age_key, value in account_age_percentages.items()
            ]
        )
        demographic_gender_items.extend(
            [
                {
                    "value": gender_key,
                    "label": _YOUTUBE_GENDER_LABELS.get(gender_key) or _youtube_metric_label(gender_key),
                    "viewer_percentage": round(value, 4),
                    "views": demographic_weight,
                }
                for gender_key, value in account_gender_percentages.items()
            ]
        )

        sharing_service_rows = await safe_query(
            access_token,
            ["shares", "views", "estimatedMinutesWatched"],
            dimensions=["sharingService"],
            sort=["-shares"],
            max_results=25,
            label="sharing_services",
            query_kind="dimension_breakdown",
        )
        if not sharing_service_rows:
            sharing_service_rows = await safe_query(
                access_token,
                ["shares"],
                dimensions=["sharingService"],
                sort=["-shares"],
                max_results=25,
                label="sharing_services",
                query_kind="dimension_breakdown",
            )
        sharing_service_items.extend(
            _youtube_named_breakdown(
                sharing_service_rows,
                "sharingService",
                ["shares", "views", "estimatedMinutesWatched"],
                _YOUTUBE_SHARING_SERVICE_LABELS,
            )
        )

        card_rows = await safe_query(
            access_token,
            ["cardImpressions", "cardTeaserImpressions", "cardClicks", "cardTeaserClicks"],
            label="cards",
            query_kind="totals",
        )
        if card_rows:
            for row in card_rows:
                cards_summary["card_impressions"] += _metric_int(row.get("cardImpressions"))
                cards_summary["card_teaser_impressions"] += _metric_int(row.get("cardTeaserImpressions"))
                cards_summary["card_clicks"] += _metric_int(row.get("cardClicks"))
                cards_summary["card_teaser_clicks"] += _metric_int(row.get("cardTeaserClicks"))
            previous_card_totals = await safe_previous_totals(
                access_token,
                ["cardImpressions", "cardTeaserImpressions", "cardClicks", "cardTeaserClicks"],
            )
            previous_totals["card_impressions"] += _metric_int(previous_card_totals.get("cardImpressions"))
            previous_totals["card_teaser_impressions"] += _metric_int(previous_card_totals.get("cardTeaserImpressions"))
            previous_totals["card_clicks"] += _metric_int(previous_card_totals.get("cardClicks"))
            previous_totals["card_teaser_clicks"] += _metric_int(previous_card_totals.get("cardTeaserClicks"))

    if not all_feed and not audience_summary["subscribers_count"] and errors:
        return {
            "supported": False,
            "message": message or "Unable to load YouTube analytics for the selected account.",
            "errors": errors,
            "days": days,
            "group_by": group_by,
        }

    if post_summary["engagement"] == 0 and all_feed:
        post_summary["engagement"] = sum(
            _youtube_total_engagement(post)
            for post in _youtube_posts_in_window(all_feed, start_date, end_date)
        )

    summary_top_video = max(
        [
            {
                **post,
                "engagement": _youtube_total_engagement(post),
                "thumbnail_url": post.get("media_url"),
                "title": post.get("content") or "",
            }
            for post in _youtube_posts_in_window(all_feed, start_date, end_date)
        ],
        key=lambda item: _metric_int(item.get("engagement")),
        default=None,
    )

    merged_subscriber_growth: dict[str, dict[str, Any]] = {}
    for series in subscriber_growth_series:
        for point in series:
            date_key = point.get("date")
            if not date_key:
                continue
            row = merged_subscriber_growth.setdefault(date_key, {"date": date_key, "gained": 0, "lost": 0, "net": 0})
            row["gained"] += _metric_int(point.get("gained"))
            row["lost"] += _metric_int(point.get("lost"))
            row["net"] += _metric_int(point.get("net"))
    subscriber_growth = [merged_subscriber_growth[key] for key in sorted(merged_subscriber_growth.keys())]

    merged_subscriber_geo = _merge_named_metrics(
        [
            {**item, "key": item.get("country_code"), "label": item.get("country_code")}
            for item in subscriber_geo_items
        ],
        "key",
        ["count"],
    )
    merged_views_geo_payload = merge_youtube_geography_payloads(
        views_geo_payloads,
        metric_label="Views",
    )
    merged_minutes_geo_payload = merge_youtube_geography_payloads(
        minutes_geo_payloads,
        metric_label="Minutes Watched",
    )
    merged_watch_quality_series = _merge_youtube_watch_quality_series(watch_quality_series)
    merged_views_series = _merge_youtube_series(views_series)
    merged_minutes_series = _merge_youtube_series(minutes_series)
    merged_age_groups = _merge_named_weighted_metrics(
        demographic_age_items,
        "value",
        [],
        ["viewer_percentage"],
    )
    merged_gender_distribution = _merge_named_weighted_metrics(
        demographic_gender_items,
        "value",
        [],
        ["viewer_percentage"],
    )
    merged_age_gender_matrix = _merge_named_weighted_metrics(
        demographic_matrix_items,
        "value",
        [],
        ["viewer_percentage"],
    )
    for row in merged_age_gender_matrix:
        if ":" in str(row.get("value") or ""):
            age_group, gender = str(row.get("value") or "").split(":", 1)
            row["age_group"] = age_group
            row["age_group_label"] = _YOUTUBE_AGE_GROUP_LABELS.get(age_group) or _youtube_metric_label(age_group)
            row["gender"] = gender
            row["gender_label"] = _YOUTUBE_GENDER_LABELS.get(gender) or _youtube_metric_label(gender)
    merged_operating_system = _merge_named_metrics(operating_system_items, "value", ["views", "estimatedMinutesWatched"])
    merged_creator_content_type = _merge_named_weighted_metrics(
        creator_content_type_items,
        "value",
        ["views", "estimatedMinutesWatched", "engagedViews"],
        ["averageViewDuration", "averageViewPercentage"],
    )
    merged_live_on_demand = _merge_named_weighted_metrics(
        live_on_demand_items,
        "value",
        ["views", "estimatedMinutesWatched", "engagedViews"],
        ["averageViewDuration", "averageViewPercentage"],
    )
    merged_sharing_services = _merge_named_metrics(sharing_service_items, "value", ["shares", "views", "estimatedMinutesWatched"])
    merged_search_terms = _merge_named_metrics(
        [{"key": item.get("term"), "label": item.get("term"), "views": item.get("views"), "estimated_minutes_watched": item.get("estimated_minutes_watched")} for item in search_term_items],
        "key",
        ["views", "estimated_minutes_watched"],
    )

    watch_quality_avg_duration = (
        round(watch_quality_summary["avg_duration_weighted"] / watch_quality_summary["views_weight"], 4)
        if watch_quality_summary["views_weight"] > 0 else 0.0
    )
    watch_quality_avg_percentage = (
        round(watch_quality_summary["avg_percentage_weighted"] / watch_quality_summary["views_weight"], 4)
        if watch_quality_summary["views_weight"] > 0 else 0.0
    )
    previous_watch_quality_avg_duration = (
        round(previous_watch_quality_summary["avg_duration_weighted"] / previous_watch_quality_summary["views_weight"], 4)
        if previous_watch_quality_summary["views_weight"] > 0 else 0.0
    )
    previous_watch_quality_avg_percentage = (
        round(previous_watch_quality_summary["avg_percentage_weighted"] / previous_watch_quality_summary["views_weight"], 4)
        if previous_watch_quality_summary["views_weight"] > 0 else 0.0
    )

    retention_available_videos: list[dict[str, Any]] = []
    seen_retention_ids: set[str] = set()
    for source_metric, videos in (
        ("views", top_videos_by_views[:5]),
        ("estimated_minutes_watched", top_videos_by_minutes[:5]),
    ):
        for video in videos:
            video_id = str(video.get("id") or "")
            if not video_id or video_id in seen_retention_ids:
                continue
            seen_retention_ids.add(video_id)
            retention_available_videos.append(
                {
                    **(_youtube_video_card(video) or {}),
                    "video_id": video_id,
                    "published_at": video.get("timestamp"),
                    "source_metric": source_metric,
                }
            )
    retention_default_video_id = next(
        (
            str(video.get("id") or "")
            for video in top_videos_by_views
            if str(video.get("id") or "") in retention_payloads and retention_payloads[str(video.get("id") or "")].get("series")
        ),
        next((video_id for video_id in retention_video_ids if retention_payloads.get(video_id, {}).get("series")), None),
    )

    summary_top_geography = (merged_views_geo_payload.get("rows") or [None])[0]

    report_has_primary_metrics = bool(
        audience_summary["subscribers_count"]
        or audience_summary["subscribers_gained"]
        or audience_summary["subscribers_lost"]
        or post_summary["videos"]
        or post_summary["engagement"]
        or views_series
        or minutes_series
        or top_videos_by_views
        or top_videos_by_minutes
    )
    if message and report_has_primary_metrics:
        message = None

    optional_support["watch_quality"] = bool(
        optional_support["watch_quality"]
        or watch_quality_summary["engaged_views"]
        or watch_quality_summary["views_weight"]
        or merged_watch_quality_series
    )
    optional_support["viewer_demographics"] = bool(
        optional_support["viewer_demographics"]
        or merged_age_groups
        or merged_gender_distribution
        or merged_age_gender_matrix
    )
    optional_support["operating_system"] = bool(optional_support["operating_system"] or merged_operating_system)
    optional_support["content_type_breakdown"] = bool(
        optional_support["content_type_breakdown"]
        or merged_creator_content_type
        or merged_live_on_demand
    )
    optional_support["sharing_services"] = bool(optional_support["sharing_services"] or merged_sharing_services)
    optional_support["retention"] = bool(optional_support["retention"] or retention_payloads)

    report = {
        "supported": True,
        "days": days,
        "group_by": group_by,
        "message": message,
        "errors": errors,
        "supports": {
            "cards": card_metrics_supported,
            "end_screen": False,
            "audience": True,
            "video_performance": analytics_enabled,
            **optional_support,
        },
        "account": {
            "count": len(accounts),
            "selected_account_id": account_id,
            "fallback_used": fallback_used,
        },
        "summary": {
            "audience_summary": {
                "subscribers_count": audience_summary["subscribers_count"],
                "subscribers_gained": audience_summary["subscribers_gained"],
                "subscribers_lost": audience_summary["subscribers_lost"],
                "avg_gained_per_day": round(audience_summary["subscribers_gained"] / max(days, 1), 2),
                "avg_lost_per_day": round(audience_summary["subscribers_lost"] / max(days, 1), 2),
                "gained_change_pct": _pct_change(audience_summary["subscribers_gained"], previous_totals["subscribers_gained"]),
                "lost_change_pct": _pct_change(audience_summary["subscribers_lost"], previous_totals["subscribers_lost"]),
            },
            "post_summary": {
                "videos": post_summary["videos"],
                "engagement": post_summary["engagement"],
                "avg_videos_per_day": round(post_summary["videos"] / max(days, 1), 2),
                "avg_engagement_per_day": round(post_summary["engagement"] / max(days, 1), 2),
                "videos_change_pct": _pct_change(post_summary["videos"], previous_totals["videos"]),
                "engagement_change_pct": _pct_change(post_summary["engagement"], previous_totals["engagement"]),
                "top_video": _youtube_video_card(summary_top_video),
                "top_geography_by_views": summary_top_geography,
            },
            "cards_summary": {
                "card_impressions": cards_summary["card_impressions"],
                "card_teaser_impressions": cards_summary["card_teaser_impressions"],
                "card_clicks": cards_summary["card_clicks"],
                "card_teaser_clicks": cards_summary["card_teaser_clicks"],
                "avg_card_impressions_per_day": round(cards_summary["card_impressions"] / max(days, 1), 2),
                "avg_card_clicks_per_day": round(cards_summary["card_clicks"] / max(days, 1), 2),
                "card_impressions_change_pct": _pct_change(cards_summary["card_impressions"], previous_totals["card_impressions"]),
                "card_teaser_impressions_change_pct": _pct_change(cards_summary["card_teaser_impressions"], previous_totals["card_teaser_impressions"]),
                "card_clicks_change_pct": _pct_change(cards_summary["card_clicks"], previous_totals["card_clicks"]),
                "card_teaser_clicks_change_pct": _pct_change(cards_summary["card_teaser_clicks"], previous_totals["card_teaser_clicks"]),
            },
            "watch_quality_summary": {
                "engaged_views": watch_quality_summary["engaged_views"],
                "average_view_duration_seconds": watch_quality_avg_duration,
                "average_view_percentage": watch_quality_avg_percentage,
                "engaged_views_change_pct": _pct_change(watch_quality_summary["engaged_views"], previous_watch_quality_summary["engaged_views"]),
                "average_view_duration_change_pct": _pct_change(watch_quality_avg_duration, previous_watch_quality_avg_duration),
                "average_view_percentage_change_pct": _pct_change(watch_quality_avg_percentage, previous_watch_quality_avg_percentage),
                "series": merged_watch_quality_series,
            },
        },
        "audience": {
            "subscriber_growth": subscriber_growth,
            "total_subscribers": audience_summary["subscribers_count"],
            "subscribers_gained": audience_summary["subscribers_gained"],
            "subscribers_lost": audience_summary["subscribers_lost"],
            "net_change": audience_summary["subscribers_gained"] - audience_summary["subscribers_lost"],
            "avg_new_subscribers_per_day": round(audience_summary["subscribers_gained"] / max(days, 1), 2),
            "subscriber_by_geography": [
                {
                    "country_code": row.get("key"),
                    "count": row.get("count"),
                }
                for row in merged_subscriber_geo[:20]
            ],
            "viewer_demographics": {
                "age_groups": [
                    {
                        "value": row.get("value"),
                        "label": row.get("label"),
                        "viewer_percentage": row.get("viewer_percentage"),
                    }
                    for row in merged_age_groups
                ],
                "gender_distribution": [
                    {
                        "value": row.get("value"),
                        "label": row.get("label"),
                        "viewer_percentage": row.get("viewer_percentage"),
                    }
                    for row in merged_gender_distribution
                ],
                "age_gender_matrix": [
                    {
                        "value": row.get("value"),
                        "label": row.get("label"),
                        "age_group": row.get("age_group"),
                        "age_group_label": row.get("age_group_label"),
                        "gender": row.get("gender"),
                        "gender_label": row.get("gender_label"),
                        "viewer_percentage": row.get("viewer_percentage"),
                    }
                    for row in merged_age_gender_matrix
                ],
            },
        },
        "video_performance": {
            "views_minutes_series": {
                "views": merged_views_series,
                "estimated_minutes_watched": merged_minutes_series,
            },
            "avg_views_per_day": round(sum(_metric_int(point.get("count")) for point in merged_views_series) / max(days, 1), 2),
            "avg_minutes_watched_per_day": round(sum(float(point.get("count") or 0) for point in merged_minutes_series) / max(days, 1), 4),
            "views_change_pct": _pct_change(sum(_metric_int(point.get("count")) for point in merged_views_series), previous_totals["views"]),
            "estimated_minutes_watched_change_pct": _pct_change(sum(float(point.get("count") or 0) for point in merged_minutes_series), previous_totals["estimated_minutes_watched"]),
            "top_videos": {
                "views": _youtube_video_card(max(top_videos_by_views, key=lambda item: _metric_int(item.get("views")), default=None)),
                "minutes_watched": _youtube_video_card(max(top_videos_by_minutes, key=lambda item: float(item.get("estimated_minutes_watched") or 0), default=None)),
                "top5_views": [_youtube_video_card(item) for item in top_videos_by_views[:5]],
                "top5_minutes_watched": [_youtube_video_card(item) for item in top_videos_by_minutes[:5]],
            },
            "views_by_geography": merged_views_geo_payload,
            "estimated_minutes_watched_by_geography": merged_minutes_geo_payload,
            "traffic_source": _merge_named_metrics(traffic_source_items, "value", ["views", "estimatedMinutesWatched"])[:10],
            "playback_location": _merge_named_metrics(playback_location_items, "value", ["views", "estimatedMinutesWatched"])[:10],
            "operating_system": merged_operating_system[:10],
            "content_type_breakdown": {
                "creator_content_type": [
                    {
                        "value": row.get("value"),
                        "label": row.get("label"),
                        "views": row.get("views"),
                        "estimated_minutes_watched": row.get("estimatedMinutesWatched"),
                        "engaged_views": row.get("engagedViews"),
                        "average_view_duration_seconds": row.get("averageViewDuration"),
                        "average_view_percentage": row.get("averageViewPercentage"),
                    }
                    for row in merged_creator_content_type
                ],
                "live_or_on_demand": [
                    {
                        "value": row.get("value"),
                        "label": row.get("label"),
                        "views": row.get("views"),
                        "estimated_minutes_watched": row.get("estimatedMinutesWatched"),
                        "engaged_views": row.get("engagedViews"),
                        "average_view_duration_seconds": row.get("averageViewDuration"),
                        "average_view_percentage": row.get("averageViewPercentage"),
                    }
                    for row in merged_live_on_demand
                ],
            },
            "sharing_services": [
                {
                    "value": row.get("value"),
                    "label": row.get("label"),
                    "shares": row.get("shares"),
                    "views": row.get("views"),
                    "estimated_minutes_watched": row.get("estimatedMinutesWatched"),
                }
                for row in merged_sharing_services[:10]
            ],
            "youtube_search_terms": [
                {
                    "term": row.get("key"),
                    "views": row.get("views"),
                    "estimated_minutes_watched": row.get("estimated_minutes_watched"),
                }
                for row in merged_search_terms[:10]
            ],
            "views_by_device_type": _merge_named_metrics(device_type_items, "value", ["views"]),
            "views_minutes_by_subscribed_status": _merge_named_metrics(subscribed_status_items, "value", ["views", "estimatedMinutesWatched"]),
            "retention": {
                "selected_video_id": retention_default_video_id,
                "videos": [
                    {
                        **video,
                        **(retention_payloads.get(video.get("video_id")) or {}),
                    }
                    for video in retention_available_videos
                    if retention_payloads.get(video.get("video_id"))
                ],
            },
        },
    }

    if summary_top_geography and not report["summary"]["post_summary"].get("top_geography_by_views"):
        report["summary"]["post_summary"]["top_geography_by_views"] = summary_top_geography

    report["supports"].update(
        {
            "watch_quality": optional_support["watch_quality"],
            "viewer_demographics": optional_support["viewer_demographics"],
            "operating_system": optional_support["operating_system"],
            "content_type_breakdown": optional_support["content_type_breakdown"],
            "sharing_services": optional_support["sharing_services"],
            "retention": optional_support["retention"],
        }
    )

    return report


@router.get("/analytics/bluesky-report")
async def analytics_bluesky_report(
    current_user: CurrentUser,
    db: DB,
    days: int = Query(30, ge=1, le=365),
    account_id: str | None = Query(None, alias="accountId"),
):
    accounts = await _load_social_accounts(db, current_user["user_id"], "bluesky", account_id)
    if not accounts:
        return {
            "supported": False,
            "message": "Connect a Bluesky account to view this report.",
        }

    from api.routes.accounts import _get_bluesky_access_token
    from backend.app.social.bluesky import BlueskyAuth

    auth = BlueskyAuth()
    current_since = datetime.now(timezone.utc) - timedelta(days=days)
    previous_since = current_since - timedelta(days=days)
    all_posts: list[dict[str, Any]] = []
    all_notifications: list[dict[str, Any]] = []
    summary_errors: list[dict[str, str]] = []
    message_errors: list[dict[str, str]] = []
    follower_series: list[list[dict[str, int]]] = []
    mention_series: list[list[dict[str, int]]] = []
    message_series: list[list[dict[str, int]]] = []
    total_followers = 0
    total_following = 0
    total_posts_count = 0
    current_new_followers = 0
    previous_new_followers = 0
    current_mentions = 0
    current_messages = 0

    for account in accounts:
        label = _account_error_label(account)
        platform_user_id = account.get("platform_user_id")
        encrypted_token = account.get("access_token")
        if not platform_user_id or not encrypted_token:
            _append_account_error(summary_errors, account, "Account is missing platform credentials.")
            continue

        try:
            access_token = decrypt(encrypted_token)
        except Exception:
            _append_account_error(summary_errors, account, "Stored token could not be decrypted.")
            continue

        try:
            profile = await auth.get_user_profile(
                access_token,
                platform_user_id,
                fallback_actor=account.get("platform_username"),
            )
        except Exception:
            try:
                access_token = await _get_bluesky_access_token(db, account, force_refresh=True)
                profile = await auth.get_user_profile(
                    access_token,
                    platform_user_id,
                    fallback_actor=account.get("platform_username"),
                )
            except Exception as exc:
                _append_account_error(summary_errors, account, _analytics_error_message("bluesky", exc))
                continue

        handle = profile.get("username") or account.get("platform_username") or platform_user_id
        own_did = str(profile.get("id") or platform_user_id or "")

        try:
            feed = await auth.fetch_posts(access_token, handle, limit=100)
        except Exception as exc:
            _append_account_error(summary_errors, account, f"Failed to fetch Bluesky feed: {exc}")
            feed = []
        feed = [_standardize_feed_post(post) for post in (feed or [])]

        if not feed:
            fallback_posts = await _fetch_db_published_posts(db, current_user["user_id"], account, limit=100)
            feed = [_standardize_feed_post(post) for post in fallback_posts]

        all_posts.extend(feed)
        total_followers += _metric_int(profile.get("followers_count"))
        total_following += _metric_int(profile.get("following_count"))
        total_posts_count += _metric_int(profile.get("posts_count"))

        notifications: list[dict[str, Any]] = []
        cursor: str | None = None
        oldest_seen: datetime | None = None
        for _ in range(5):
            page = await auth.list_notifications(access_token, limit=100, cursor=cursor)
            batch = page.get("notifications") or []
            if not batch:
                break
            notifications.extend(batch)
            parsed_batch = [
                _parse_platform_timestamp(item.get("indexedAt") or item.get("record", {}).get("createdAt"))
                for item in batch
            ]
            parsed_batch = [dt for dt in parsed_batch if dt]
            if parsed_batch:
                batch_oldest = min(parsed_batch)
                oldest_seen = batch_oldest if oldest_seen is None else min(oldest_seen, batch_oldest)
            cursor = page.get("cursor")
            if not cursor or (oldest_seen and oldest_seen < previous_since):
                break

        all_notifications.extend(notifications)

        follow_dates_current: list[datetime] = []
        mention_dates_current: list[datetime] = []
        for notification in notifications:
            reason = str(notification.get("reason") or "").lower()
            ts = _parse_platform_timestamp(notification.get("indexedAt") or notification.get("record", {}).get("createdAt"))
            if not ts:
                continue
            if current_since <= ts:
                if reason == "follow":
                    follow_dates_current.append(ts)
                if reason == "mention":
                    mention_dates_current.append(ts)
            elif previous_since <= ts < current_since:
                if reason == "follow":
                    previous_new_followers += 1

        current_new_followers += len(follow_dates_current)
        current_mentions += len(mention_dates_current)
        follower_series.append(_series_from_dates(follow_dates_current))
        mention_series.append(_series_from_dates(mention_dates_current))

        try:
            convo_page = await auth.list_conversations(access_token, limit=15)
            convos = convo_page.get("convos") or convo_page.get("conversations") or []
            received_current: list[datetime] = []
            for convo in convos[:10]:
                convo_id = convo.get("id") or convo.get("convoId")
                if not convo_id:
                    continue
                message_cursor: str | None = None
                for _ in range(2):
                    message_page = await auth.get_conversation_messages(access_token, convo_id, limit=50, cursor=message_cursor)
                    messages = message_page.get("messages") or message_page.get("items") or []
                    if not messages:
                        break
                    for message in messages:
                        sender = (message.get("sender") or {}).get("did")
                        if sender and own_did and sender == own_did:
                            continue
                        sent_at = _parse_platform_timestamp(message.get("sentAt") or message.get("createdAt"))
                        if not sent_at or sent_at < current_since:
                            continue
                        received_current.append(sent_at)
                    message_cursor = message_page.get("cursor")
                    if not message_cursor:
                        break
            current_messages += len(received_current)
            message_series.append(_series_from_dates(received_current))
        except Exception as exc:
            _append_account_error(message_errors, account, f"Messages are currently unavailable from Bluesky chat: {exc}")

    if not total_followers and not all_posts and summary_errors:
        return {
            "supported": False,
            "message": "Unable to load Bluesky analytics for the selected account.",
            "errors": summary_errors,
        }

    current_posts = []
    previous_posts = []
    for post in all_posts:
        ts = _parse_platform_timestamp(post.get("timestamp"))
        if not ts:
            current_posts.append(post)
            continue
        if ts >= current_since:
            current_posts.append(post)
        elif ts >= previous_since:
            previous_posts.append(post)

    current_total_engagement = sum(_bluesky_post_engagement(post) for post in current_posts)
    previous_total_engagement = sum(_bluesky_post_engagement(post) for post in previous_posts)

    type_order = ["image", "text", "video", "link", "quoted"]
    type_labels = {
        "image": "Image",
        "text": "Text",
        "video": "Video",
        "link": "Link",
        "quoted": "Quoted",
    }
    post_type_counts = {key: 0 for key in type_order}
    engagement_by_type_bucket = {key: 0 for key in type_order}
    posts_by_app: dict[str, dict[str, int]] = {}

    for post in current_posts:
        post_type = _bluesky_post_type(post)
        post_type_counts[post_type] += 1
        engagement_by_type_bucket[post_type] += _bluesky_post_engagement(post)
        app_bucket = posts_by_app.setdefault("Bluesky", {"posts": 0, "likes": 0, "replies": 0, "reposts": 0, "quotes": 0})
        app_bucket["posts"] += 1
        app_bucket["likes"] += _metric_int(post.get("likes"))
        app_bucket["replies"] += _metric_int(post.get("comments_count"))
        app_bucket["reposts"] += _metric_int(post.get("shares"))
        app_bucket["quotes"] += _metric_int(post.get("quotes"))

    def _normalize_top_post(post: dict[str, Any]) -> dict[str, Any]:
        likes = _metric_int(post.get("likes"))
        replies = _metric_int(post.get("comments_count"))
        reposts = _metric_int(post.get("shares"))
        quotes = _metric_int(post.get("quotes"))
        engagement = likes + replies + reposts + quotes
        return {
            "id": post.get("id"),
            "content": post.get("content", ""),
            "media_url": post.get("media_url"),
            "media_type": _bluesky_post_type(post),
            "timestamp": post.get("timestamp"),
            "permalink": post.get("permalink"),
            "likes": likes,
            "replies": replies,
            "reposts": reposts,
            "quotes": quotes,
            "engagement": engagement,
            "engagement_rate": _bluesky_post_engagement_rate(post, total_followers),
            "source_app": "Bluesky",
        }

    top_post = max(current_posts, key=_bluesky_post_engagement, default=None)
    top_posts = [_normalize_top_post(post) for post in current_posts]

    summary = {
        "followers_total": total_followers,
        "following_total": total_following,
        "posts_total": total_posts_count,
        "new_followers": current_new_followers,
        "new_followers_change_pct": _percentage_change(current_new_followers, previous_new_followers),
        "avg_new_followers_per_day": round(current_new_followers / max(days, 1), 2),
        "post_summary": {
            "total_posts": len(current_posts),
            "avg_posts_per_day": round(len(current_posts) / max(days, 1), 2),
            "total_engagement": current_total_engagement,
            "avg_engagement_per_day": round(current_total_engagement / max(days, 1), 2),
            "total_posts_change_pct": _percentage_change(len(current_posts), len(previous_posts)),
            "total_engagement_change_pct": _percentage_change(current_total_engagement, previous_total_engagement),
            "top_post": _normalize_top_post(top_post) if top_post else None,
            "engagement_by_type": [
                {
                    "type": key,
                    "label": type_labels[key],
                    "engagement": engagement_by_type_bucket[key],
                    "posts": post_type_counts[key],
                }
                for key in type_order
            ],
        },
    }

    audience = {
        "follower_growth": _merge_date_counts(follower_series),
        "mentions_received": _merge_date_counts(mention_series),
        "messages_received": _merge_date_counts(message_series),
        "mentions_total": current_mentions,
        "messages_total": current_messages,
        "messages_supported": not bool(message_errors),
        "messages_message": (
            None if not message_errors else "Bluesky mentions are shown, but direct-message analytics are currently unavailable for this account."
        ),
    }

    posts_and_engagement = {
        "posts_vs_engagement": {
            "posts": _merge_bluesky_metric_series([_bluesky_metric_series(current_posts, current_since, "posts")]),
            "engagement": _merge_bluesky_metric_series([_bluesky_metric_series(current_posts, current_since, "engagement")]),
        },
        "posts_by_type": [
            {
                "type": key,
                "label": type_labels[key],
                "posts": post_type_counts[key],
            }
            for key in type_order
        ],
        "top_posts": sorted(
            top_posts,
            key=lambda post: (post["engagement"], post["likes"], post["replies"], post["reposts"], post["quotes"]),
            reverse=True,
        )[:20],
        "posts_by_publishing_apps": [
            {"app": app_name, **metrics}
            for app_name, metrics in posts_by_app.items()
        ],
        "post_engagement": _merge_bluesky_metric_series([_bluesky_metric_series(current_posts, current_since, "engagement")]),
        "engagement_by_type": [
            {
                "type": key,
                "label": type_labels[key],
                "engagement": engagement_by_type_bucket[key],
            }
            for key in type_order
        ],
        "engagement_actions": {
            "likes": _merge_bluesky_metric_series([_bluesky_metric_series(current_posts, current_since, "likes")]),
            "replies": _merge_bluesky_metric_series([_bluesky_metric_series(current_posts, current_since, "replies")]),
            "reposts": _merge_bluesky_metric_series([_bluesky_metric_series(current_posts, current_since, "reposts")]),
            "quotes": _merge_bluesky_metric_series([_bluesky_metric_series(current_posts, current_since, "quotes")]),
        },
    }

    return {
        "supported": True,
        "days": days,
        "summary": summary,
        "audience": audience,
        "posts_engagement": posts_and_engagement,
        "errors": summary_errors,
        "message_errors": message_errors,
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
                event_log(
                    logger,
                    "warning",
                    "analytics.provider.fallback_failed",
                    exc_info=exc,
                    route="/analytics/overview",
                    platform=platform,
                    account_id=account_id,
                    failure_type="feed_fallback_failed",
                    provider_error=shorten_provider_error(exc),
                    fetch_mode="db_to_api_fallback",
                    outcome="failed",
                )
                capture_degraded_event(
                    "Analytics overview feed fallback failed",
                    route="/analytics/overview",
                    platform=platform,
                    account_id=account_id,
                    failure_type="feed_fallback_failed",
                )
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
                if media_type in {"VIDEO", "REELS"}:
                    fallback_type_counts["video"] += 1
                elif media_type in {"IMAGE", "CAROUSEL_ALBUM"}:
                    fallback_type_counts["image"] += 1
                else:
                    fallback_type_counts["text"] += 1

        if fallback_published_count:
            published_in_period = fallback_published_count
            platform_counts = fallback_platform_counts
            type_counts = fallback_type_counts

    accounts = await _load_social_accounts(db, current_user["user_id"], platform, account_id)
    connected_accounts: list[dict[str, Any]] = []
    overview_errors: list[dict[str, str]] = []
    if accounts:
        async def _build_account_summary(account: dict[str, Any]) -> dict[str, Any]:
            plat = account.get("platform")
            engagement: dict[str, Any] = {}
            if plat in _SUPPORTED_ENGAGEMENT_PLATFORMS:
                try:
                    _, engagement = await _fetch_account_feed_and_stats(db, account, days=days)
                    if engagement.get("error"):
                        _append_account_error(overview_errors, account, str(engagement["error"]))
                except Exception as exc:
                    _append_account_error(overview_errors, account, _analytics_error_message(plat, exc))
            return _normalize_connected_account(account, engagement)

        connected_accounts = await asyncio.gather(*[_build_account_summary(account) for account in accounts])

    audience_totals = _aggregate_account_overview(connected_accounts)

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
        "connected_accounts": connected_accounts,
        "audience_totals": audience_totals,
        "errors": overview_errors,
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
    timeline = [{"date": d["_id"], "count": d["count"]} for d in docs if d.get("_id")]

    if not timeline and account_id and platform in _SUPPORTED_ENGAGEMENT_PLATFORMS:
        accounts = await _load_social_accounts(db, current_user["user_id"], platform, account_id)
        if accounts:
            counts_by_date: dict[str, int] = {}
            since_dt = datetime.now(timezone.utc) - timedelta(days=days)
            for account in accounts:
                try:
                    feed, _ = await _fetch_account_feed_and_stats(db, account, days=days)
                except Exception as exc:
                    event_log(
                        logger,
                        "warning",
                        "analytics.provider.fallback_failed",
                        exc_info=exc,
                        route="/analytics/timeline",
                        platform=platform,
                        account_id=account_id,
                        failure_type="timeline_feed_fallback_failed",
                        provider_error=shorten_provider_error(exc),
                        fetch_mode="db_to_api_fallback",
                        outcome="failed",
                    )
                    continue

                for post in feed:
                    ts = _parse_platform_timestamp(post.get("timestamp"))
                    if ts and ts < since_dt:
                        continue
                    if ts:
                        date_key = ts.date().isoformat()
                    else:
                        date_key = str(post.get("timestamp") or "")[:10]
                    if not date_key:
                        continue
                    counts_by_date[date_key] = counts_by_date.get(date_key, 0) + 1

            timeline = [{"date": date_key, "count": counts_by_date[date_key]} for date_key in sorted(counts_by_date.keys())]

    return {"timeline": timeline}


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
            try:
                feed, engagement = await _fetch_account_feed_and_stats(db, account, days=days)
                if engagement.get("error"):
                    _append_account_error(errors, account, str(engagement["error"]))
            except Exception as exc:
                _append_account_error(errors, account, _analytics_error_message(plat, exc))
                feed, engagement = [], {}

        connected_accounts.append(_normalize_connected_account(account, engagement))

        if not feed:
            feed = await _fetch_db_published_posts(db, current_user["user_id"], account, limit=50)

        if not feed and not engagement:
            if plat in _SUPPORTED_ENGAGEMENT_PLATFORMS and not _has_account_error(errors, account):
                _append_account_error(errors, account, "Unable to fetch recent analytics from the platform API.")
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
    fallback_used = False
    if platform:
        accounts, fallback_used = await _load_social_accounts_for_report(
            db,
            current_user["user_id"],
            platform,
            account_id,
        )
    else:
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
            try:
                feed, _ = await _fetch_account_feed_and_stats(db, account)
            except Exception as exc:
                errors.append(
                    {
                        "account": account.get("platform_username") or account_identifier or plat or "unknown",
                        "error": str(exc),
                    }
                )
                feed = []

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
        "account_fallback_used": fallback_used,
    }
