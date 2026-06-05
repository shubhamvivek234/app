"""Dashboard overview — aggregated workspace control center payload."""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Query

from api.deps import CurrentUser, DB, require_permission
from api.routes.accounts import _hydrate_social_account_metadata
from api.routes.posts import _hydrate_post_card_fields_for_docs

router = APIRouter(tags=["dashboard"])

_ACTION_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_ACCOUNT_HEALTH_RANK = {"restricted": 0, "reconnect_required": 1, "expiring": 2, "healthy": 3}
_DASHBOARD_SECTIONS = ("core", "queue", "wins", "activity", "health", "performance")
_SECTION_FIELDS = {
    "core": ("summary", "operations", "action_items", "refreshed_at"),
    "queue": ("upcoming_posts",),
    "wins": ("recent_published",),
    "activity": ("activity",),
    "health": ("account_health",),
    "performance": ("performance_7d",),
}
_DEFAULT_TYPE_COUNTS = {"text": 0, "image": 0, "video": 0}


def _workspace_id_for(current_user: dict[str, Any]) -> str:
    return current_user.get("default_workspace_id") or current_user["user_id"]


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


def _notification_is_unread(notification: dict[str, Any]) -> bool:
    if "is_read" in notification:
        return not bool(notification.get("is_read"))
    if "read" in notification:
        return not bool(notification.get("read"))
    return True


def _account_label(account: dict[str, Any]) -> str:
    return (
        account.get("display_name")
        or account.get("platform_username")
        or account.get("account_id")
        or account.get("id")
        or "Unknown account"
    )


def _post_account_identifiers(doc: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("account_ids", "social_account_ids", "platform_account_ids"):
        for value in doc.get(key) or []:
            normalized = str(value or "").strip()
            if normalized and normalized not in values:
                values.append(normalized)
    single_value = str(doc.get("social_account_id") or "").strip()
    if single_value and single_value not in values:
        values.append(single_value)
    return values


def _build_account_label_map(accounts: list[dict[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for account in accounts:
        label = _account_label(account)
        identifiers = {
            str(account.get("id") or "").strip(),
            str(account.get("account_id") or "").strip(),
            str(account.get("platform_user_id") or "").strip(),
            str(account.get("platform_username") or "").strip(),
        }
        identifiers.discard("")
        for identifier in identifiers:
            lookup[identifier] = label
    return lookup


def _parse_sections_param(sections: str | None) -> list[str]:
    if not isinstance(sections, str) or not sections:
        return list(_DASHBOARD_SECTIONS)

    requested: list[str] = []
    for raw_section in sections.split(","):
        section = raw_section.strip().lower()
        if section and section in _SECTION_FIELDS and section not in requested:
            requested.append(section)
    return requested or list(_DASHBOARD_SECTIONS)


def _derive_account_labels(doc: dict[str, Any], account_lookup: dict[str, str]) -> list[str]:
    labels: list[str] = []
    for identifier in _post_account_identifiers(doc):
        label = account_lookup.get(identifier)
        if label and label not in labels:
            labels.append(label)
    return labels


def _compact_post_card(doc: dict[str, Any], account_lookup: dict[str, str]) -> dict[str, Any]:
    thumbnail_urls = [url for url in (doc.get("thumbnail_urls") or []) if url]
    published_card_thumbnail_url = doc.get("published_card_thumbnail_url")
    if published_card_thumbnail_url and published_card_thumbnail_url not in thumbnail_urls:
        thumbnail_urls = [published_card_thumbnail_url, *thumbnail_urls]

    media_count = max(
        len(doc.get("media_ids") or []),
        len(doc.get("media_urls") or []),
        len(thumbnail_urls),
        0,
    )

    return {
        "id": str(doc.get("id") or ""),
        "title": doc.get("title"),
        "content": doc.get("content") or "",
        "status": doc.get("status"),
        "post_type": doc.get("post_type") or "text",
        "platforms": list(doc.get("platforms") or []),
        "account_ids": _post_account_identifiers(doc),
        "account_labels": _derive_account_labels(doc, account_lookup),
        "scheduled_time": doc.get("scheduled_time"),
        "published_at": doc.get("published_at"),
        "thumbnail_urls": thumbnail_urls,
        "published_card_thumbnail_url": published_card_thumbnail_url,
        "media_count": media_count,
        "published_media_kind": doc.get("published_media_kind"),
    }


def _notification_target_path(notification_type: str, message: str, metadata: dict[str, Any]) -> str:
    lowered_type = (notification_type or "").lower()
    lowered_message = (message or "").lower()
    combined = f"{lowered_type} {lowered_message}"
    if "verify" in combined or "email" in combined:
        return "/verify-email?returnTo=/dashboard"
    if "subscription" in combined or metadata.get("billing") or metadata.get("subscription"):
        return "/billing"
    if "account" in combined or "reconnect" in combined or metadata.get("account_id"):
        return "/accounts"
    if any(token in combined for token in ("comment", "dm", "message", "inbox")):
        return "/publish"
    if any(token in combined for token in ("failed", "partial", "publish", "scheduled", "post")):
        return "/content-library"
    return "/dashboard"


def _notification_severity(notification_type: str, message: str) -> str:
    lowered = f"{notification_type or ''} {message or ''}".lower()
    if any(token in lowered for token in ("expired", "revoked", "failed", "cancelled", "restriction", "blocked")):
        return "high"
    if any(token in lowered for token in ("comment", "dm", "message", "subscription")):
        return "medium"
    return "low"


def _normalize_activity(notification: dict[str, Any]) -> dict[str, Any]:
    notification_type = str(notification.get("type") or "info")
    message = str(notification.get("message") or "")
    metadata = notification.get("metadata") or {}
    return {
        "id": str(notification.get("id") or notification.get("notification_id") or ""),
        "type": notification_type,
        "message": message,
        "severity": _notification_severity(notification_type, message),
        "created_at": notification.get("created_at"),
        "target_path": _notification_target_path(notification_type, message, metadata),
        "is_read": not _notification_is_unread(notification),
    }


def _normalize_account_health(account: dict[str, Any], now: datetime) -> dict[str, Any]:
    expires_at = _coerce_datetime(account.get("expires_at") or account.get("token_expiry"))
    token_error = account.get("token_error")
    publish_restriction_type = account.get("publish_restriction_type")
    publish_action_required = account.get("publish_action_required")
    publish_error_code = account.get("publish_error_code")

    health_state = "healthy"
    health_message = None

    if publish_restriction_type or publish_action_required or publish_error_code:
        health_state = "restricted"
        health_message = (
            publish_action_required
            or publish_restriction_type
            or publish_error_code
            or "This account has a publish restriction."
        )
    elif token_error or (expires_at and expires_at <= now):
        health_state = "reconnect_required"
        health_message = token_error or "Access token expired. Reconnect the account."
    elif expires_at and (expires_at - now).total_seconds() <= 7 * 24 * 3600:
        health_state = "expiring"
        health_message = "Access token expires soon. Reconnect proactively to avoid interruptions."

    return {
        "id": str(account.get("id") or account.get("account_id") or ""),
        "account_id": str(account.get("account_id") or account.get("id") or ""),
        "platform": account.get("platform"),
        "display_name": account.get("display_name"),
        "platform_username": account.get("platform_username"),
        "picture_url": account.get("picture_url"),
        "expires_at": expires_at,
        "token_error": token_error,
        "followers_count": account.get("followers_count"),
        "following_count": account.get("following_count"),
        "posts_count": account.get("posts_count"),
        "publish_error_code": publish_error_code,
        "publish_error_category": account.get("publish_error_category"),
        "publish_action_required": publish_action_required,
        "publish_restriction_type": publish_restriction_type,
        "publish_blocked_at": account.get("publish_blocked_at"),
        "health_state": health_state,
        "health_message": health_message,
    }


def _build_action_items(
    current_user: dict[str, Any],
    *,
    operations: dict[str, Any],
    summary: dict[str, Any],
    account_health: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    if operations["verification_required"]:
        items.append(
            {
                "id": "verify-email",
                "kind": "verification",
                "severity": "high",
                "title": "Verify your email before publishing",
                "message": "Connecting accounts, publishing, scheduling, and inviting teammates are blocked until the email address is verified.",
                "cta_label": "Verify Email",
                "cta_path": "/verify-email?returnTo=/dashboard",
            }
        )

    subscription_status = str(operations.get("subscription_status") or current_user.get("subscription_status") or "free")
    if subscription_status in {"expired", "cancelled"}:
        items.append(
            {
                "id": "subscription-status",
                "kind": "subscription",
                "severity": "critical",
                "title": "Subscription needs attention",
                "message": "Billing status is no longer active. Renew or reactivate the plan to keep production workflows running.",
                "cta_label": "Open Billing",
                "cta_path": "/billing",
            }
        )
    elif subscription_status == "grace":
        items.append(
            {
                "id": "subscription-grace",
                "kind": "subscription",
                "severity": "medium",
                "title": "Subscription is in grace period",
                "message": "Billing needs attention soon to avoid interruptions to scheduled publishing.",
                "cta_label": "Review Billing",
                "cta_path": "/billing",
            }
        )

    if summary["connected_accounts"] == 0:
        items.append(
            {
                "id": "connect-accounts",
                "kind": "accounts",
                "severity": "high",
                "title": "Connect your first social account",
                "message": "No active social accounts are connected to this workspace yet.",
                "cta_label": "Connect Accounts",
                "cta_path": "/accounts",
            }
        )

    reconnect_accounts = [account for account in account_health if account.get("health_state") == "reconnect_required"]
    if reconnect_accounts:
        items.append(
            {
                "id": "reconnect-accounts",
                "kind": "accounts",
                "severity": "high",
                "title": "Reconnect affected social accounts",
                "message": f"{len(reconnect_accounts)} connected account{'s' if len(reconnect_accounts) != 1 else ''} need refreshed access before publishing can continue reliably.",
                "cta_label": "Review Accounts",
                "cta_path": "/accounts",
            }
        )

    restricted_accounts = [account for account in account_health if account.get("health_state") == "restricted"]
    if restricted_accounts:
        items.append(
            {
                "id": "restricted-accounts",
                "kind": "publishing",
                "severity": "high",
                "title": "Platform restrictions need attention",
                "message": f"{len(restricted_accounts)} connected account{'s' if len(restricted_accounts) != 1 else ''} currently have publish restrictions or action-required errors.",
                "cta_label": "Review Restrictions",
                "cta_path": "/accounts",
            }
        )

    if operations["failed_posts"] > 0:
        items.append(
            {
                "id": "failed-posts",
                "kind": "publishing",
                "severity": "high",
                "title": "Failed or partial posts need retry",
                "message": f"{operations['failed_posts']} post{'s' if operations['failed_posts'] != 1 else ''} need attention in the content library.",
                "cta_label": "Open Content Library",
                "cta_path": "/content-library",
            }
        )

    if operations["unread_inbox"] > 0:
        items.append(
            {
                "id": "unread-inbox",
                "kind": "inbox",
                "severity": "medium",
                "title": "Inbox needs attention",
                "message": f"{operations['unread_inbox']} unread inbox item{'s' if operations['unread_inbox'] != 1 else ''} are waiting across comments and DMs.",
                "cta_label": "Open Publish Inbox",
                "cta_path": "/publish",
            }
        )

    items.sort(key=lambda item: (_ACTION_SEVERITY_RANK.get(item["severity"], 99), item["title"]))
    return items


async def _count_documents(collection, query: dict[str, Any]) -> int:
    return await collection.count_documents(query)


async def _load_raw_accounts(db: DB, user_id: str) -> list[dict[str, Any]]:
    return await db.social_accounts.find(
        {"user_id": user_id, "is_active": True},
        {"_id": 0, "refresh_token": 0},
    ).to_list(length=100)


def _dashboard_account_needs_hydration(account: dict[str, Any]) -> bool:
    return any(
        [
            not account.get("display_name"),
            not account.get("platform_username"),
            not account.get("picture_url"),
            account.get("followers_count") is None,
            account.get("posts_count") is None,
        ]
    )


async def _hydrate_dashboard_accounts(
    db: DB,
    accounts: list[dict[str, Any]],
    *,
    refresh: bool,
    concurrency: int = 4,
) -> list[dict[str, Any]]:
    if not refresh:
        return [dict(account) for account in accounts]

    semaphore = asyncio.Semaphore(max(concurrency, 1))

    async def _maybe_hydrate(account: dict[str, Any]) -> dict[str, Any]:
        cloned = dict(account)
        if not _dashboard_account_needs_hydration(cloned):
            return cloned
        async with semaphore:
            try:
                return await _hydrate_social_account_metadata(db, cloned)
            except Exception:
                return cloned

    return await asyncio.gather(*[_maybe_hydrate(account) for account in accounts])


def _build_summary_and_operations(
    current_user: dict[str, Any],
    *,
    total_posts: int,
    scheduled_posts: int,
    published_posts: int,
    draft_posts: int,
    failed_posts: int,
    unread_notifications: int,
    unread_inbox: int,
    unread_comments: int,
    unread_dms: int,
    connected_accounts: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    summary = {
        "total_posts": total_posts,
        "scheduled_posts": scheduled_posts,
        "published_posts": published_posts,
        "draft_posts": draft_posts,
        "failed_posts": failed_posts,
        "connected_accounts": connected_accounts,
    }
    operations = {
        "unread_notifications": unread_notifications,
        "unread_inbox": unread_inbox,
        "unread_comments": unread_comments,
        "unread_dms": unread_dms,
        "failed_posts": failed_posts,
        "verification_required": not bool(current_user.get("email_verified", False)),
        "subscription_status": current_user.get("subscription_status", "free"),
    }
    return summary, operations


async def _build_core_section(
    db: DB,
    *,
    current_user: dict[str, Any],
    workspace_id: str,
    user_id: str,
    now: datetime,
    raw_accounts: list[dict[str, Any]],
) -> dict[str, Any]:
    base_post_query = {
        "workspace_id": workspace_id,
        "user_id": user_id,
        "deleted_at": {"$exists": False},
    }
    failed_status_query = {
        **base_post_query,
        "status": {"$in": ["failed", "partial"]},
    }

    (
        total_posts,
        scheduled_posts,
        published_posts,
        draft_posts,
        failed_posts,
        unread_notifications,
        unread_inbox,
        unread_comments,
        unread_dms,
    ) = await asyncio.gather(
        _count_documents(db.posts, base_post_query),
        _count_documents(db.posts, {**base_post_query, "status": "scheduled"}),
        _count_documents(db.posts, {**base_post_query, "status": "published"}),
        _count_documents(db.posts, {**base_post_query, "status": "draft"}),
        _count_documents(db.posts, failed_status_query),
        _count_documents(
            db.notifications,
            {
                "user_id": user_id,
                "$or": [
                    {"is_read": False},
                    {"is_read": {"$exists": False}, "read": {"$ne": True}},
                ],
            },
        ),
        _count_documents(
            db.inbox_messages,
            {"workspace_id": workspace_id, "user_id": user_id, "status": "unread"},
        ),
        _count_documents(
            db.inbox_messages,
            {"workspace_id": workspace_id, "user_id": user_id, "status": "unread", "type": "comment"},
        ),
        _count_documents(
            db.inbox_messages,
            {"workspace_id": workspace_id, "user_id": user_id, "status": "unread", "type": "dm"},
        ),
    )

    raw_account_health = sorted(
        [_normalize_account_health(account, now) for account in raw_accounts],
        key=lambda account: (
            _ACCOUNT_HEALTH_RANK.get(account["health_state"], 99),
            account.get("platform") or "",
            account.get("display_name") or account.get("platform_username") or "",
        ),
    )
    summary, operations = _build_summary_and_operations(
        current_user,
        total_posts=total_posts,
        scheduled_posts=scheduled_posts,
        published_posts=published_posts,
        draft_posts=draft_posts,
        failed_posts=failed_posts,
        unread_notifications=unread_notifications,
        unread_inbox=unread_inbox,
        unread_comments=unread_comments,
        unread_dms=unread_dms,
        connected_accounts=len(raw_accounts),
    )
    return {
        "summary": summary,
        "operations": operations,
        "action_items": _build_action_items(
            current_user,
            operations=operations,
            summary=summary,
            account_health=raw_account_health,
        ),
        "refreshed_at": now,
    }


async def _build_queue_section(
    db: DB,
    *,
    workspace_id: str,
    user_id: str,
    account_lookup: dict[str, str],
) -> dict[str, Any]:
    base_post_query = {
        "workspace_id": workspace_id,
        "user_id": user_id,
        "deleted_at": {"$exists": False},
    }
    upcoming_docs = await db.posts.find(
        {**base_post_query, "status": "scheduled"},
        {"_id": 0},
    ).sort([("scheduled_time", 1), ("created_at", 1)]).limit(8).to_list(length=8)
    upcoming_hydrated = await _hydrate_post_card_fields_for_docs(db, upcoming_docs)
    return {
        "upcoming_posts": [_compact_post_card(doc, account_lookup) for doc in upcoming_hydrated],
    }


async def _build_recent_wins_section(
    db: DB,
    *,
    workspace_id: str,
    user_id: str,
    account_lookup: dict[str, str],
) -> dict[str, Any]:
    base_post_query = {
        "workspace_id": workspace_id,
        "user_id": user_id,
        "deleted_at": {"$exists": False},
    }
    recent_docs = await db.posts.find(
        {**base_post_query, "status": "published"},
        {"_id": 0},
    ).sort([("published_at", -1), ("updated_at", -1), ("created_at", -1)]).limit(5).to_list(length=5)
    recent_hydrated = await _hydrate_post_card_fields_for_docs(db, recent_docs)
    return {
        "recent_published": [_compact_post_card(doc, account_lookup) for doc in recent_hydrated],
    }


async def _build_activity_section(
    db: DB,
    *,
    user_id: str,
) -> dict[str, Any]:
    recent_notifications = await db.notifications.find(
        {"user_id": user_id},
        {"_id": 0},
    ).sort("created_at", -1).limit(5).to_list(length=5)
    return {
        "activity": [_normalize_activity(notification) for notification in recent_notifications],
    }


def _coerce_metric_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _build_health_section(
    db: DB,
    *,
    raw_accounts: list[dict[str, Any]],
    now: datetime,
    refresh: bool,
) -> dict[str, Any]:
    accounts = await _hydrate_dashboard_accounts(db, raw_accounts, refresh=refresh)
    account_health = sorted(
        [_normalize_account_health(account, now) for account in accounts],
        key=lambda account: (
            _ACCOUNT_HEALTH_RANK.get(account["health_state"], 99),
            account.get("platform") or "",
            account.get("display_name") or account.get("platform_username") or "",
        ),
    )
    return {"account_health": account_health}


async def _build_performance_section(
    db: DB,
    *,
    base_post_query: dict[str, Any],
    raw_accounts: list[dict[str, Any]],
    days: int,
    now: datetime,
) -> dict[str, Any]:
    window_start = now - timedelta(days=days)
    recent_docs = await db.posts.find(
        {
            **base_post_query,
            "status": "published",
            "published_at": {"$gte": window_start},
        },
        {"_id": 0, "platforms": 1, "post_type": 1, "published_at": 1},
    ).to_list(length=5000)

    platform_counts: dict[str, int] = {}
    type_counts = dict(_DEFAULT_TYPE_COUNTS)
    for doc in recent_docs:
        for platform in doc.get("platforms") or []:
            normalized_platform = str(platform or "").strip().lower()
            if normalized_platform:
                platform_counts[normalized_platform] = platform_counts.get(normalized_platform, 0) + 1
        post_type = str(doc.get("post_type") or "text").strip().lower()
        if post_type not in type_counts:
            type_counts[post_type] = 0
        type_counts[post_type] += 1

    totals = {
        "followers_total": 0,
        "reach": 0,
        "impressions": 0,
        "profile_views": 0,
    }
    supported_counts = {key: 0 for key in totals}
    for account in raw_accounts:
        if (followers := _coerce_metric_int(account.get("followers_count"))) is not None:
            totals["followers_total"] += followers
            supported_counts["followers_total"] += 1
        if (reach := _coerce_metric_int(account.get("reach"))) is not None:
            totals["reach"] += reach
            supported_counts["reach"] += 1
        if (impressions := _coerce_metric_int(account.get("impressions"))) is not None:
            totals["impressions"] += impressions
            supported_counts["impressions"] += 1
        if (profile_views := _coerce_metric_int(account.get("profile_views"))) is not None:
            totals["profile_views"] += profile_views
            supported_counts["profile_views"] += 1

    audience_totals = {
        metric: totals[metric] if supported_counts[metric] else None
        for metric in totals
    }
    errors = [
        {
            "metric": metric,
            "error": f"{label} totals are not available in the dashboard snapshot for the connected accounts.",
        }
        for metric, label in (
            ("followers_total", "Follower"),
            ("reach", "Reach"),
            ("impressions", "Impression"),
            ("profile_views", "Profile view"),
        )
        if not supported_counts[metric]
    ]

    return {
        "performance_7d": {
            "published_in_period": len(recent_docs),
            "platform_counts": platform_counts,
            "type_counts": type_counts,
            "audience_totals": audience_totals,
            "errors": errors,
        },
    }


@router.get(
    "/dashboard/overview",
    dependencies=[
        require_permission("analytics:read"),
        require_permission("post:read"),
        require_permission("account:read"),
    ],
)
async def dashboard_overview(
    current_user: CurrentUser,
    db: DB,
    days: int = Query(7, ge=1, le=365),
    refresh: bool = Query(False),
    sections: str | None = Query(None),
):
    workspace_id = _workspace_id_for(current_user)
    user_id = current_user["user_id"]
    now = datetime.now(timezone.utc)
    requested_sections = _parse_sections_param(sections)
    base_post_query = {
        "workspace_id": workspace_id,
        "user_id": user_id,
        "deleted_at": {"$exists": False},
    }
    response: dict[str, Any] = {
        "refreshed_at": now,
    }
    section_errors: dict[str, str] = {}
    successful_sections: set[str] = set()

    raw_accounts_task: asyncio.Task[list[dict[str, Any]]] | None = None

    async def _get_raw_accounts() -> list[dict[str, Any]]:
        nonlocal raw_accounts_task
        if raw_accounts_task is None:
            raw_accounts_task = asyncio.create_task(_load_raw_accounts(db, user_id))
        return await raw_accounts_task

    async def _run_section(section_name: str, builder) -> None:
        try:
            payload = await builder()
            response.update(payload)
            successful_sections.add(section_name)
        except Exception as exc:
            section_errors[section_name] = str(exc) or f"Unable to load {section_name}."

    async def _build_core() -> dict[str, Any]:
        return await _build_core_section(
            db,
            current_user=current_user,
            workspace_id=workspace_id,
            user_id=user_id,
            now=now,
            raw_accounts=await _get_raw_accounts(),
        )

    async def _build_queue() -> dict[str, Any]:
        account_lookup = _build_account_label_map(await _get_raw_accounts())
        return await _build_queue_section(
            db,
            workspace_id=workspace_id,
            user_id=user_id,
            account_lookup=account_lookup,
        )

    async def _build_wins() -> dict[str, Any]:
        account_lookup = _build_account_label_map(await _get_raw_accounts())
        return await _build_recent_wins_section(
            db,
            workspace_id=workspace_id,
            user_id=user_id,
            account_lookup=account_lookup,
        )

    async def _build_activity() -> dict[str, Any]:
        return await _build_activity_section(db, user_id=user_id)

    async def _build_health() -> dict[str, Any]:
        return await _build_health_section(
            db,
            raw_accounts=await _get_raw_accounts(),
            now=now,
            refresh=refresh,
        )

    async def _build_performance() -> dict[str, Any]:
        return await _build_performance_section(
            db,
            base_post_query=base_post_query,
            raw_accounts=await _get_raw_accounts(),
            days=days,
            now=now,
        )

    builders = {
        "core": _build_core,
        "queue": _build_queue,
        "wins": _build_wins,
        "activity": _build_activity,
        "health": _build_health,
        "performance": _build_performance,
    }

    await asyncio.gather(*[
        _run_section(section_name, builders[section_name])
        for section_name in requested_sections
    ])

    response["sections_returned"] = [
        section_name
        for section_name in requested_sections
        if section_name in successful_sections
    ]

    if section_errors:
        response["section_errors"] = section_errors

    return response
