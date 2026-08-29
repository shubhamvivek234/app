"""
Posts CRUD — schedule, list, update (optimistic lock), soft-delete.
All queries scope by workspace_id or user_id — never post_id alone.
Phase 5.5:  EC8 content policy + EC23 platform×content-type validation on create.
Phase 7.5:  Pre-publish content intelligence (7.5.3) + audit event logging.
Phase 10.1: Schedule density warning on post save.
"""
import hashlib
import io
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Annotated

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.deps import CurrentUser, DB, QueueRedis, VerifiedUser, require_permission
from api.limiter import limiter
from api.models.post import (
    BulkCreateRequest,
    BulkCreateResponse,
    CreatePostRequest,
    PostResponse,
    PostStatus,
    UpdatePostRequest,
    PlatformOverride,
)
from api.task_queue import enqueue_task, revoke_task
from utils.audit import log_audit_event
from utils.content_policy import check_content_policy, validate_platform_content_type
from utils.observability import event_log, shorten_provider_error
from utils.notifications import emit_notification
from utils.schedule_density import check_schedule_density
from utils.ssrf_guard import assert_safe_url
from utils.storage import public_url_for_key
from utils.timeslots import normalize_timeslot_category, resolve_next_timeslot_for_account
from utils.roles import has_permission

logger = logging.getLogger(__name__)
router = APIRouter(tags=["posts"])

_BLOCKED_STATUSES = {PostStatus.QUEUED, PostStatus.PROCESSING}
_SUBSCRIPTION_ALLOWED = {"active", "grace"}
_READY_MEDIA_STATUSES = {"ready", "archived"}
_POLL_RULES = {
    "twitter": {
        "question_max": 280,
        "option_max": 25,
        "durations": {"ONE_DAY", "THREE_DAYS", "SEVEN_DAYS"},
    },
    "linkedin": {
        "question_max": 140,
        "option_max": 30,
        "durations": {"ONE_DAY", "THREE_DAYS", "SEVEN_DAYS", "FOURTEEN_DAYS"},
    },
    "threads": {
        "question_max": 500,
        "option_max": 100,
        "durations": {"ONE_DAY"},
    },
}


class ApprovalDecisionBody(BaseModel):
    reason: str = ""


class ApprovalResubmitBody(BaseModel):
    content: str | None = None
    assigned_reviewer_id: str | None = None
    approval_due_at: datetime | None = None


class ApprovalBulkDecisionBody(BaseModel):
    post_ids: list[str]
    reason: str = ""


def _post_notification_preview(doc: dict) -> str:
    text = (doc.get("title") or doc.get("content") or "Untitled post").strip()
    if len(text) > 90:
        return f"{text[:87].rstrip()}..."
    return text or "Untitled post"


async def _emit_scheduled_post_notification(db, post: dict, *, now: datetime | None = None) -> None:
    scheduled_time = post.get("scheduled_time")
    if not scheduled_time:
        return

    post_id = str(post.get("id") or "")
    user_id = str(post.get("user_id") or "")
    if not post_id or not user_id:
        return

    platforms = list(post.get("platforms") or [])
    platform_copy = ", ".join(platform.capitalize() for platform in platforms[:3])
    if len(platforms) > 3:
        platform_copy = f"{platform_copy} +{len(platforms) - 3} more"
    if not platform_copy:
        platform_copy = "selected platforms"

    schedule_iso = scheduled_time.isoformat() if hasattr(scheduled_time, "isoformat") else str(scheduled_time)
    timezone_label = post.get("timezone") or "UTC"
    await emit_notification(
        db,
        user_id=user_id,
        event="post.scheduled",
        notification_type="post.scheduled",
        title="Post scheduled",
        message=(
            f"{_post_notification_preview(post)} is scheduled for {schedule_iso} "
            f"({timezone_label}) on {platform_copy}."
        ),
        severity="low",
        channels=("in_app",),
        metadata={
            "post_id": post_id,
            "platforms": platforms,
            "scheduled_time": schedule_iso,
            "timezone": timezone_label,
        },
        target_path="/content-library?status=scheduled",
        dedup_key=f"post:{post_id}:scheduled",
        created_at=now,
        update_existing=True,
    )


def _ensure_verified_email_for_publish_action(current_user: dict) -> None:
    if not current_user.get("email_verified", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required before connecting accounts, publishing, or inviting teammates.",
        )


def _subtract_months(reference: datetime, months: int) -> datetime:
    year = reference.year
    month = reference.month - months
    while month <= 0:
        month += 12
        year -= 1

    month_lengths = [
        31,
        29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ]
    day = min(reference.day, month_lengths[month - 1])
    return reference.replace(year=year, month=month, day=day)


def _infer_published_media_kind(doc: dict) -> str:
    explicit = (doc.get("published_media_kind") or "").strip().lower()
    if explicit in {"text", "image", "video", "mixed"}:
        return explicit

    media_types = [
        str(media_type).strip().lower()
        for media_type in (doc.get("media_types") or [])
        if str(media_type).strip()
    ]
    has_thumbnail = bool(doc.get("published_card_thumbnail_url") or (doc.get("thumbnail_urls") or []))
    has_media_url = bool(doc.get("media_urls") or doc.get("media_url"))
    post_type = str(doc.get("post_type") or "").strip().lower()

    if media_types:
        has_image = any(media_type == "image" for media_type in media_types)
        has_video = any(media_type == "video" for media_type in media_types)
        if has_image and has_video:
            return "mixed"
        if has_video:
            return "video"
        if has_image:
            return "image"

    if "mixed" in post_type:
        return "mixed"
    if post_type in {"video", "reel", "story"} or "video" in post_type:
        return "video"
    if has_thumbnail or has_media_url:
        return "image"
    return "text"


def _collect_dispatch_task_ids(doc: dict | None) -> list[str]:
    if not doc:
        return []
    task_ids: list[str] = []
    for result_group in (doc.get("account_results") or {}, doc.get("platform_results") or {}):
        if not isinstance(result_group, dict):
            continue
        for result in result_group.values():
            if not isinstance(result, dict):
                continue
            task_id = result.get("dispatch_task_id")
            if task_id:
                task_ids.append(str(task_id))
    # Preserve order but dedupe.
    return list(dict.fromkeys(task_ids))


def _needs_card_media_backfill(doc: dict) -> bool:
    return bool(doc.get("media_ids")) and (
        not doc.get("media_urls")
        or not doc.get("thumbnail_urls")
        or not doc.get("media_url")
    )


def _backfill_post_media_card_fields(doc: dict, media_assets_by_id: dict[str, dict]) -> dict:
    ordered_media_ids = [media_id for media_id in (doc.get("media_ids") or []) if media_id]
    if not ordered_media_ids:
        return doc

    ordered_assets = [
        media_assets_by_id[media_id]
        for media_id in ordered_media_ids
        if media_id in media_assets_by_id
    ]
    if not ordered_assets:
        return doc

    if not doc.get("media_urls"):
        doc["media_urls"] = [
            asset.get("media_url")
            for asset in ordered_assets
            if asset.get("media_url")
        ]
    if not doc.get("thumbnail_urls"):
        doc["thumbnail_urls"] = [
            asset.get("thumbnail_url") or asset.get("media_url")
            for asset in ordered_assets
            if asset.get("thumbnail_url") or asset.get("media_url")
        ]
    if not doc.get("media_url"):
        media_urls = doc.get("media_urls") or []
        doc["media_url"] = media_urls[0] if media_urls else None
    return doc


async def _hydrate_post_card_fields_for_docs(db, docs: list[dict]) -> list[dict]:
    hydrated_docs = [dict(doc) for doc in docs]

    media_ids_by_user: dict[str, set[str]] = {}
    for doc in hydrated_docs:
        thumbnail_key = doc.get("published_card_thumbnail_key")
        if thumbnail_key and not doc.get("published_card_thumbnail_url"):
            try:
                doc["published_card_thumbnail_url"] = public_url_for_key(str(thumbnail_key))
            except Exception:
                logger.warning("Could not derive public thumbnail URL for post %s", doc.get("id"))

        if not _needs_card_media_backfill(doc):
            continue
        user_id = str(doc.get("user_id") or "").strip()
        if not user_id:
            continue
        media_ids_by_user.setdefault(user_id, set()).update(
            str(media_id).strip()
            for media_id in (doc.get("media_ids") or [])
            if str(media_id).strip()
        )

    media_assets_by_user: dict[str, dict[str, dict]] = {}
    for user_id, media_ids in media_ids_by_user.items():
        media_docs = await db.media_assets.find(
            {
                "user_id": user_id,
                "media_id": {"$in": list(media_ids)},
            },
            {"_id": 0, "media_id": 1, "media_url": 1, "thumbnail_url": 1},
        ).to_list(len(media_ids))
        media_assets_by_user[user_id] = {
            doc["media_id"]: doc
            for doc in media_docs
            if doc.get("media_id")
        }

    for doc in hydrated_docs:
        if _needs_card_media_backfill(doc):
            user_id = str(doc.get("user_id") or "").strip()
            if user_id and user_id in media_assets_by_user:
                _backfill_post_media_card_fields(doc, media_assets_by_user[user_id])
        if doc.get("published_media_kind") not in {"text", "image", "video", "mixed"}:
            doc["published_media_kind"] = _infer_published_media_kind(doc)

    return hydrated_docs


async def _hydrate_post_card_fields(db, doc: dict) -> dict:
    hydrated_docs = await _hydrate_post_card_fields_for_docs(db, [doc])
    return hydrated_docs[0]


def _plan_post_limit(plan: str) -> int:
    return {"starter": 30, "pro": 200, "agency": 2000}.get(plan, 30)


def _normalize_post_datetime_value(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    if isinstance(value, list):
        return [_normalize_post_datetime_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_post_datetime_value(item) for key, item in value.items()}
    return value


def _doc_to_response(doc: dict) -> PostResponse:
    normalized_doc = _normalize_post_datetime_value(dict(doc))
    normalized_doc.setdefault("id", str(normalized_doc.get("_id", "")))
    normalized_doc.pop("_id", None)
    normalized_doc.pop("deleted_at", None)
    return PostResponse(**normalized_doc)


def _post_workspace_id(current_user: dict) -> str:
    return (
        current_user.get("default_workspace_id")
        or current_user.get("workspace_id")
        or current_user["user_id"]
    )


def _approval_permission_flags(role: str) -> dict[str, bool]:
    can_decide = has_permission(role, "approval:decide")
    can_update = has_permission(role, "post:update")
    return {
        "can_read": has_permission(role, "approval:read"),
        "can_review": can_decide,
        "can_resubmit": can_update,
        "can_return_to_draft": can_decide,
    }


def _default_approval_due_at(scheduled_time: datetime | None) -> datetime | None:
    if not scheduled_time:
        return None
    return scheduled_time - timedelta(hours=1)


def _normalize_approval_due_at(value, scheduled_time: datetime | None) -> datetime | None:
    parsed = _normalized_schedule_datetime(value)
    if parsed is not None:
        return parsed
    return _default_approval_due_at(scheduled_time)


def _parse_timestamp_utc(value) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def _approval_activity_response(doc: dict) -> dict:
    return {
        "activity_id": doc.get("activity_id") or doc.get("id"),
        "post_id": doc.get("post_id"),
        "actor_id": doc.get("actor_id"),
        "action": doc.get("action"),
        "old_status": doc.get("old_status"),
        "new_status": doc.get("new_status"),
        "reason": doc.get("reason"),
        "created_at": _parse_timestamp_utc(doc.get("created_at")),
    }


async def _record_approval_activity(
    db,
    *,
    post_doc: dict,
    actor_id: str,
    action: str,
    old_status: str | None,
    new_status: str | None,
    reason: str | None = None,
    created_at: datetime | None = None,
) -> None:
    now = created_at or datetime.now(timezone.utc)
    activity = {
        "activity_id": str(ObjectId()),
        "workspace_id": post_doc.get("workspace_id"),
        "post_id": str(post_doc.get("id") or ""),
        "actor_id": actor_id,
        "action": action,
        "old_status": old_status,
        "new_status": new_status,
        "reason": (reason or "").strip() or None,
        "created_at": now,
    }
    await db.approval_activity.insert_one(activity)


async def _latest_approval_activity_for_posts(db, workspace_id: str, post_ids: list[str]) -> dict[str, dict]:
    if not post_ids:
        return {}
    latest: dict[str, dict] = {}
    for post_id in post_ids:
        docs = await db.approval_activity.find(
            {"workspace_id": workspace_id, "post_id": post_id},
            {"_id": 0},
        ).sort([("created_at", -1)]).limit(1).to_list(length=1)
        if docs:
            latest[post_id] = _approval_activity_response(docs[0])
    return latest


async def _approval_reviewer_user_ids(
    db,
    workspace_id: str,
    *,
    exclude_user_id: str | None = None,
    assigned_reviewer_id: str | None = None,
) -> list[str]:
    if assigned_reviewer_id and assigned_reviewer_id != exclude_user_id:
        return [assigned_reviewer_id]
    docs = await db.workspace_members.find(
        {
            "workspace_id": workspace_id,
            "role": {"$in": ["owner", "admin", "editor", "client"]},
        },
        {"_id": 0, "user_id": 1},
    ).to_list(length=100)
    user_ids: list[str] = []
    for doc in docs:
        user_id = str(doc.get("user_id") or "")
        if user_id and user_id != exclude_user_id and user_id not in user_ids:
            user_ids.append(user_id)
    return user_ids


async def _emit_approval_notification(
    db,
    *,
    post_doc: dict,
    event: str,
    title: str,
    message: str,
    target_user_ids: list[str],
    severity: str = "medium",
    dedup_suffix: str,
    now: datetime | None = None,
) -> None:
    post_id = str(post_doc.get("id") or "")
    if not post_id:
        return
    for target_user_id in target_user_ids:
        try:
            await emit_notification(
                db,
                user_id=target_user_id,
                event=event,
                notification_type=event,
                title=title,
                message=message,
                severity=severity,
                channels=("in_app",),
                metadata={
                    "post_id": post_id,
                    "workspace_id": post_doc.get("workspace_id"),
                    "status": post_doc.get("status"),
                },
                target_path="/approvals",
                dedup_key=f"approval:{post_id}:{dedup_suffix}:{target_user_id}",
                created_at=now,
                update_existing=True,
            )

            # E-mail notification with Magic Login Link for submitted or overdue approvals
            if event in ("approval.submitted", "approval.overdue"):
                user = await db.users.find_one({"user_id": target_user_id}, {"_id": 0, "email": 1, "display_name": 1})
                if user and user.get("email"):
                    from utils.auth_emails import get_auth_email_config_status, send_approval_notification_email
                    config = get_auth_email_config_status()
                    if config["configured"]:
                        import secrets
                        from db.redis_client import get_cache_redis
                        token = secrets.token_hex(16)
                        cache_redis = get_cache_redis()
                        # TTL: 7 days (604800 seconds)
                        await cache_redis.setex(f"magic_link:{token}", 604800, user["email"])
                        
                        action_url = f"{config['frontend_url'].rstrip('/')}/magic-login/{token}?post_id={post_id}"
                        post_title = post_doc.get("title") or (post_doc.get("content") or "")[:50] or "Untitled Post"
                        
                        await send_approval_notification_email(
                            email=user["email"],
                            name=user.get("display_name"),
                            post_title=post_title,
                            action_url=action_url,
                        )
                        logger.info("Approval notification email sent to %s for post %s", user["email"], post_id)
        except Exception as exc:
            logger.warning(
                "Failed to store or send approval notification for post %s user %s event %s: %s",
                post_id,
                target_user_id,
                event,
                exc,
            )


def _post_review_title(post_doc: dict) -> str:
    return _post_notification_preview(post_doc)


async def _notify_reviewers_of_submission(db, post_doc: dict, *, actor_id: str, now: datetime) -> None:
    workspace_id = str(post_doc.get("workspace_id") or "")
    if not workspace_id:
        return
    reviewer_ids = await _approval_reviewer_user_ids(
        db,
        workspace_id,
        exclude_user_id=actor_id,
        assigned_reviewer_id=post_doc.get("assigned_reviewer_id"),
    )
    await _emit_approval_notification(
        db,
        post_doc=post_doc,
        event="approval.submitted",
        title="Post submitted for approval",
        message=f"{_post_review_title(post_doc)} is ready for review.",
        target_user_ids=reviewer_ids,
        severity="medium",
        dedup_suffix="submitted",
        now=now,
    )


async def _notify_creator_of_decision(
    db,
    post_doc: dict,
    *,
    event: str,
    title: str,
    message: str,
    severity: str,
    dedup_suffix: str,
    now: datetime,
) -> None:
    creator_id = str(post_doc.get("user_id") or "")
    if not creator_id:
        return
    await _emit_approval_notification(
        db,
        post_doc=post_doc,
        event=event,
        title=title,
        message=message,
        target_user_ids=[creator_id],
        severity=severity,
        dedup_suffix=dedup_suffix,
        now=now,
    )


def _normalized_schedule_datetime(value) -> datetime | None:
    normalized = _normalize_post_datetime_value(value)
    return normalized if isinstance(normalized, datetime) else None


async def _enrich_approval_docs(
    db,
    docs: list[dict],
    *,
    workspace_id: str,
    current_user_id: str,
    now: datetime,
) -> list[dict]:
    if not docs:
        return []

    hydrated_docs = await _hydrate_post_card_fields_for_docs(db, docs)
    latest_activity = await _latest_approval_activity_for_posts(
        db,
        workspace_id,
        [str(doc.get("id")) for doc in hydrated_docs if doc.get("id")],
    )
    for doc in hydrated_docs:
        creator = await db.users.find_one(
            {"user_id": doc.get("user_id")},
            {"_id": 0, "display_name": 1, "email": 1},
        )
        if creator:
            doc["creator_display_name"] = creator.get("display_name") or creator.get("email")
            doc["creator_email"] = creator.get("email")
        if doc.get("rejection_reason") and not doc.get("rejection_note"):
            doc["rejection_note"] = doc["rejection_reason"]
        scheduled_time = _normalized_schedule_datetime(doc.get("scheduled_time"))
        approval_due_at = _normalize_approval_due_at(doc.get("approval_due_at"), scheduled_time)
        doc["approval_due_at"] = approval_due_at
        doc["approval_overdue"] = bool(approval_due_at and approval_due_at <= now)
        doc["approval_expiring_soon"] = bool(
            approval_due_at and now < approval_due_at <= now + timedelta(hours=24)
        )
        assigned_reviewer_id = doc.get("assigned_reviewer_id")
        doc["approval_assigned_to_me"] = bool(assigned_reviewer_id and assigned_reviewer_id == current_user_id)
        doc["approval_latest_activity"] = latest_activity.get(str(doc.get("id")))
    return [_normalize_post_datetime_value(doc) for doc in hydrated_docs]


def _social_account_identifier(account_doc: dict) -> str | None:
    return account_doc.get("account_id") or account_doc.get("id")


async def _resolve_selected_accounts(db, user_id: str, body: CreatePostRequest) -> list[dict]:
    if body.account_ids:
        accounts = await db.social_accounts.find(
            {
                "user_id": user_id,
                "$or": [
                    {"account_id": {"$in": body.account_ids}},
                    {"id": {"$in": body.account_ids}},
                ],
                "is_active": True,
            },
            {"_id": 0, "id": 1, "account_id": 1, "platform": 1},
        ).to_list(len(body.account_ids))
        matched_ids: set[str] = set()
        normalized_ids: list[str] = []
        backfill_ops = []
        for acct in accounts:
            canonical_id = _social_account_identifier(acct)
            if not canonical_id:
                continue
            if canonical_id not in normalized_ids:
                normalized_ids.append(canonical_id)
            matched_ids.update(filter(None, [acct.get("account_id"), acct.get("id")]))
            if not acct.get("account_id"):
                backfill_ops.append(
                    db.social_accounts.update_one(
                        {
                            "user_id": user_id,
                            "platform": acct.get("platform"),
                            "id": canonical_id,
                        },
                        {"$set": {"account_id": canonical_id}},
                    )
                )
            if not acct.get("id"):
                backfill_ops.append(
                    db.social_accounts.update_one(
                        {
                            "user_id": user_id,
                            "platform": acct.get("platform"),
                            "account_id": canonical_id,
                        },
                        {"$set": {"id": canonical_id}},
                    )
                )
        if backfill_ops:
            await asyncio.gather(*backfill_ops)
        missing = [account_id for account_id in body.account_ids if account_id not in matched_ids]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"One or more account_ids are invalid or inactive: {missing}",
            )

        selected_platforms = {acct.get("platform") for acct in accounts}
        requested_platforms = set(body.platforms)
        if not requested_platforms.issubset(selected_platforms):
            missing_platforms = sorted(requested_platforms - selected_platforms)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Selected accounts do not cover requested platforms: {missing_platforms}",
            )
        ordered_accounts: list[dict] = []
        accounts_by_identifier: dict[str, dict] = {}
        for acct in accounts:
            canonical_id = _social_account_identifier(acct)
            if canonical_id:
                accounts_by_identifier[canonical_id] = {
                    "account_id": canonical_id,
                    "platform": (acct.get("platform") or "").lower(),
                }

        for requested_id in body.account_ids:
            normalized_account = accounts_by_identifier.get(requested_id)
            if normalized_account and normalized_account not in ordered_accounts:
                ordered_accounts.append(normalized_account)
                continue

            for acct in accounts:
                if requested_id not in {acct.get("account_id"), acct.get("id")}:
                    continue
                canonical_id = _social_account_identifier(acct)
                if not canonical_id:
                    continue
                candidate = {
                    "account_id": canonical_id,
                    "platform": (acct.get("platform") or "").lower(),
                }
                if candidate not in ordered_accounts:
                    ordered_accounts.append(candidate)
                break
        return ordered_accounts

    selected_accounts: list[dict] = []
    if body.platforms:
        account_cursor = db.social_accounts.find(
            {"user_id": user_id, "platform": {"$in": body.platforms}, "is_active": True},
            {"_id": 0, "id": 1, "account_id": 1, "platform": 1},
        )
        async for acct in account_cursor:
            account_identifier = _social_account_identifier(acct)
            if account_identifier:
                selected_accounts.append({
                    "account_id": account_identifier,
                    "platform": (acct.get("platform") or "").lower(),
                })
    return selected_accounts


def _effective_override_for_account(
    body: CreatePostRequest | UpdatePostRequest,
    account_id: str,
    platform: str,
) -> PlatformOverride:
    return (
        (body.account_overrides or {}).get(account_id)
        or (body.platform_overrides or {}).get(platform)
        or PlatformOverride()
    )


async def _resolve_media_payload(
    db,
    user_id: str,
    media_ids: list[str] | None,
    media_urls_input: list[str] | None,
) -> tuple[list[str], list[str], str | None, float | None]:
    media_ids = list(media_ids or [])
    media_urls = list(media_urls_input or [])
    thumbnail_urls: list[str] = []
    video_size_mb: float | None = None

    if not media_ids:
        return media_urls, thumbnail_urls, (media_urls[0] if media_urls else None), video_size_mb

    media_docs = await db.media_assets.find(
        {
            "media_id": {"$in": media_ids},
            "user_id": user_id,
        },
        {"_id": 0},
    ).to_list(len(media_ids))
    by_id = {doc.get("media_id"): doc for doc in media_docs}

    if len(by_id) != len(media_ids):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="One or more media_ids are invalid or do not belong to you",
        )

    ordered_docs = [by_id[media_id] for media_id in media_ids if media_id in by_id]
    not_ready = [
        doc.get("media_id")
        for doc in ordered_docs
        if (doc.get("status") or "").lower() not in _READY_MEDIA_STATUSES or not doc.get("media_url")
    ]
    if not_ready:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"One or more uploads are still processing or failed: {not_ready}",
        )

    media_urls = [doc["media_url"] for doc in ordered_docs if doc.get("media_url")]
    thumbnail_urls = [
        doc.get("thumbnail_url") or doc.get("media_url")
        for doc in ordered_docs
        if doc.get("thumbnail_url") or doc.get("media_url")
    ]
    if ordered_docs:
        first_size = ordered_docs[0].get("file_size_bytes")
        if first_size:
            video_size_mb = round(first_size / (1024 * 1024), 2)

    return media_urls, thumbnail_urls, (media_urls[0] if media_urls else None), video_size_mb


def _override_explicitly_sets_media(override: PlatformOverride) -> bool:
    """True only when media fields were explicitly sent by the client."""
    fields_set = getattr(override, "model_fields_set", set())
    return "media_ids" in fields_set or "media_urls" in fields_set


def _effective_media_count_for_account(body: CreatePostRequest, override: PlatformOverride) -> int:
    if _override_explicitly_sets_media(override):
        return len(override.media_ids or override.media_urls or [])
    return len(body.media_ids or body.media_urls or [])


def _validate_poll_for_account(
    *,
    platform: str,
    account_id: str,
    override: PlatformOverride,
    body: CreatePostRequest,
) -> None:
    poll = override.poll
    if poll is None:
        return

    rules = _POLL_RULES.get(platform)
    if not rules:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{platform} poll posts are not supported for account {account_id}",
        )

    question = (poll.question or "").strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{platform} poll question is required for account {account_id}",
        )
    if len(question) > rules["question_max"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{platform} poll question max is {rules['question_max']} characters for account {account_id}",
        )

    options = [str(option).strip() for option in (poll.options or []) if str(option).strip()]
    if len(options) < 2 or len(options) > 4:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{platform} poll must have between 2 and 4 options for account {account_id}",
        )

    for index, option in enumerate(options, start=1):
        if len(option) > rules["option_max"]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{platform} poll option {index} max is {rules['option_max']} characters for account {account_id}",
            )

    if (poll.duration or "ONE_DAY").upper() not in rules["durations"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{platform} poll duration is invalid for account {account_id}",
        )

    if _effective_media_count_for_account(body, override) > 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{platform} poll posts cannot include media for account {account_id}",
        )

    if platform == "linkedin" and override.linkedin_document_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"linkedin poll posts cannot include a document attachment for account {account_id}",
        )


# ── Create ───────────────────────────────────────────────────────────────────

@router.post("/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[require_permission("post:create")])
@limiter.limit("100/hour")
async def create_post(
    request: Request,
    body: CreatePostRequest,
    current_user: CurrentUser,
    db: DB,
    queue_redis: QueueRedis,
) -> PostResponse:
    if body.publish_now or body.scheduled_time or body.timeslot_category:
        _ensure_verified_email_for_publish_action(current_user)
    sub_status = current_user.get("subscription_status", "free")
    if sub_status not in _SUBSCRIPTION_ALLOWED:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Active subscription required to schedule posts",
        )

    workspace_id = body.workspace_id or current_user.get("default_workspace_id")
    user_id = current_user["user_id"]
    now = datetime.now(timezone.utc)
    selected_accounts = await _resolve_selected_accounts(db, user_id, body)
    social_account_ids = [account["account_id"] for account in selected_accounts]

    # EC23 — Validate platform × content-type compatibility
    for platform in body.platforms:
        try:
            validate_platform_content_type(platform, body.post_type)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    # EC8 — Content policy check (local, fast)
    policy_warnings: list[str] = []
    for account in selected_accounts:
        platform = account["platform"]
        effective_content = _effective_override_for_account(body, account["account_id"], platform).content
        if effective_content is None:
            effective_content = body.content or ""
        result = check_content_policy(effective_content, platform)
        if not result.approved:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "Content policy violation",
                    "platform": platform,
                    "account_id": account["account_id"],
                    "violations": result.violations,
                },
            )
        policy_warnings.extend(result.warnings)

    # Phase 7.5.3 — Pre-publish content intelligence (non-blocking warnings)
    intelligence_warnings: list[str] = []

    # Duplicate detection: SHA256 of content vs last 30 published posts
    if body.content:
        content_hash = hashlib.sha256(body.content.encode()).hexdigest()
        recent = await db.posts.count_documents({
            "workspace_id": workspace_id,
            "content_hash": content_hash,
            "status": "published",
        })
        if recent > 0:
            intelligence_warnings.append("Duplicate content detected — this post has been published before")

    # Platform/account character count enforcement (default content + overrides)
    _CHAR_LIMITS = {"twitter": 280, "linkedin": 3000, "instagram": 2200, "facebook": 63206, "tiktok": 2200, "youtube": 5000, "threads": 500}
    for account in selected_accounts:
        platform = account["platform"]
        limit = _CHAR_LIMITS.get(platform.lower())
        effective_override = _effective_override_for_account(body, account["account_id"], platform)
        override_content = effective_override.content
        effective = override_content if override_content is not None else body.content
        if limit and effective and len(effective) > limit:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{platform} character limit is {limit} (got {len(effective)}) for account {account['account_id']}",
            )
        _validate_poll_for_account(
            platform=platform,
            account_id=account["account_id"],
            override=effective_override,
            body=body,
        )

    # Hashtag limit warnings (platform best practices)
    _HASHTAG_LIMITS = {"instagram": 30, "twitter": 2, "linkedin": 5, "tiktok": 10, "threads": 5}
    if body.content:
        import re as _re
        hashtag_count = len(_re.findall(r"#\w+", body.content))
        for platform in body.platforms:
            rec = _HASHTAG_LIMITS.get(platform.lower())
            if rec and hashtag_count > rec:
                intelligence_warnings.append(
                    f"{platform}: {hashtag_count} hashtags detected — recommended max is {rec}"
                )

    all_warnings = policy_warnings + intelligence_warnings
    if all_warnings:
        event_log(
            logger,
            "info",
            "posts.pre_publish.warning",
            route="/posts",
            user_id=user_id,
            warnings=all_warnings,
            outcome="warning",
        )

    if body.workspace_id and body.workspace_id != current_user.get("default_workspace_id"):
        member = await db.workspace_members.find_one(
            {"workspace_id": body.workspace_id, "user_id": user_id}
        )
        if not member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of the specified workspace",
            )

    # SEC-2: SSRF guard on user-supplied media_urls
    for url in (body.media_urls or []):
        try:
            assert_safe_url(url)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    for override in (body.platform_overrides or {}).values():
        for url in (override.media_urls or []):
            try:
                assert_safe_url(url)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    for override in (body.account_overrides or {}).values():
        for url in (override.media_urls or []):
            try:
                assert_safe_url(url)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    media_urls, thumbnail_urls, primary_media_url, video_size_mb = await _resolve_media_payload(
        db, user_id, body.media_ids, body.media_urls
    )

    normalized_platform_overrides: dict[str, dict] = {}
    for platform, override in (body.platform_overrides or {}).items():
        normalized_override = override.model_dump(exclude_none=True)
        use_media_override = _override_explicitly_sets_media(override)
        normalized_override["use_media_override"] = use_media_override

        if use_media_override:
            override_media_urls, override_thumbnail_urls, override_primary_media_url, _ = await _resolve_media_payload(
                db, user_id, override.media_ids, override.media_urls
            )
            normalized_override["media_ids"] = list(override.media_ids or [])
            normalized_override["media_urls"] = override_media_urls
            normalized_override["media_url"] = override_primary_media_url
            normalized_override["thumbnail_urls"] = override_thumbnail_urls

        normalized_platform_overrides[platform] = normalized_override

    normalized_account_overrides: dict[str, dict] = {}
    for account in selected_accounts:
        account_id = account["account_id"]
        override = (body.account_overrides or {}).get(account_id)
        if override is None:
            continue

        normalized_override = override.model_dump(exclude_none=True)
        use_media_override = _override_explicitly_sets_media(override)
        normalized_override["use_media_override"] = use_media_override

        if use_media_override:
            override_media_urls, override_thumbnail_urls, override_primary_media_url, _ = await _resolve_media_payload(
                db, user_id, override.media_ids, override.media_urls
            )
            normalized_override["media_ids"] = list(override.media_ids or [])
            normalized_override["media_urls"] = override_media_urls
            normalized_override["media_url"] = override_primary_media_url
            normalized_override["thumbnail_urls"] = override_thumbnail_urls

        normalized_account_overrides[account_id] = normalized_override

    timeslot_category: str | None = None
    if body.timeslot_category:
        if body.publish_now:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="publish_now cannot be combined with timeslot scheduling",
            )
        if body.scheduled_time:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="scheduled_time cannot be combined with timeslot scheduling",
            )
        if len(selected_accounts) != 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Add to Timeslot currently supports exactly one selected account",
            )
        try:
            timeslot_category = normalize_timeslot_category(body.timeslot_category)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        user_tz = body.timezone or current_user.get("timezone") or "UTC"
        next_slot, message, _ = await resolve_next_timeslot_for_account(
            db,
            workspace_id,
            selected_accounts[0]["account_id"],
            timeslot_category,
            now=now,
            timezone_name=user_tz,
        )
        if next_slot is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=message or "No available timeslot found",
            )
        post_status = PostStatus.SCHEDULED
        scheduled_time = next_slot
    elif body.publish_now:
        post_status = PostStatus.QUEUED
        scheduled_time = now
    elif body.scheduled_time:
        post_status = PostStatus.SCHEDULED
        scheduled_time = body.scheduled_time
    else:
        post_status = PostStatus.DRAFT
        scheduled_time = None

    # Phase 10.1 — Schedule density warning (non-blocking)
    density_ws = body.workspace_id or current_user.get("default_workspace_id")
    density_warnings = []
    if scheduled_time is not None:
        density_warnings = await check_schedule_density(
            db, density_ws, body.platforms, scheduled_time
        )
    for dw in density_warnings:
        event_log(
            logger,
            "warning",
            "posts.schedule_density.warning",
            route="/posts",
            user_id=user_id,
            workspace_id=workspace_id,
            failure_type="schedule_density_warning",
            provider_error=dw.message,
            outcome="warning",
        )
        all_warnings.append(dw.message)

    doc: dict = {
        "id": str(ObjectId()),
        "user_id": user_id,
        "workspace_id": workspace_id,
        "content": body.content,
        "title": body.title,
        "platforms": body.platforms,
        "publish_targets": selected_accounts,
        "account_ids": social_account_ids,
        "social_account_ids": social_account_ids,
        "media_ids": list(body.media_ids or []),
        "media_urls": media_urls,
        "media_url": primary_media_url,
        "post_type": body.post_type,
        "tiktok_privacy": body.tiktok_privacy,
        "disable_duet": body.disable_duet,
        "disable_comment": body.disable_comment,
        "disable_stitch": body.disable_stitch,
        "timezone": body.timezone,
        "scheduled_timezone_explicit": bool(body.scheduled_time),
        "timeslot_category": timeslot_category,
        "scheduled_time": scheduled_time,
        "status": post_status,
        "platform_results": {
            platform: {"status": "pending"}
            for platform in body.platforms
        },
        "account_results": {
            account["account_id"]: {
                "status": "pending",
                "platform": account["platform"],
                "account_id": account["account_id"],
            }
            for account in selected_accounts
        },
        "platform_post_urls": {},
        "status_history": [
            {"status": post_status, "timestamp": now, "actor": user_id}
        ],
        "thumbnail_urls": thumbnail_urls,
        "pre_upload_status": None,
        "queue_job_id": None,
        "jitter_seconds": None,
        "video_size_mb": video_size_mb,
        "version": 1,
        "dlq_reason": None,
        "content_hash": hashlib.sha256((body.content or "").encode()).hexdigest(),
        "schedule_warnings": all_warnings,
        "platform_overrides": normalized_platform_overrides,
        "account_overrides": normalized_account_overrides,
        "created_at": now,
        "updated_at": now,
    }

    await db.posts.insert_one(doc)

    if post_status == PostStatus.SCHEDULED and scheduled_time is not None:
        try:
            await _emit_scheduled_post_notification(db, doc, now=now)
        except Exception as exc:
            logger.warning("Failed to store scheduled notification for post %s: %s", doc["id"], exc)

    if body.publish_now:
        try:
            async_result = enqueue_task(
                "celery_workers.tasks.publish.publish_post",
                kwargs={"post_id": doc["id"], "version": doc["version"]},
                queue="high_priority",
            )
            doc["queue_job_id"] = async_result.id
            await db.posts.update_one(
                {"id": doc["id"], "workspace_id": workspace_id, "user_id": user_id},
                {"$set": {"queue_job_id": async_result.id, "updated_at": now}},
            )
            event_log(
                logger,
                "info",
                "posts.publish.enqueued",
                route="/posts",
                user_id=user_id,
                workspace_id=workspace_id,
                post_id=doc["id"],
                queue_job_id=async_result.id,
                outcome="enqueued",
            )
        except Exception as exc:
            event_log(
                logger,
                "error",
                "posts.publish.enqueue_failed",
                exc_info=exc,
                route="/posts",
                user_id=user_id,
                workspace_id=workspace_id,
                post_id=doc["id"],
                failure_type="enqueue_failed",
                provider_error=shorten_provider_error(exc),
                outcome="failed",
            )
            failed_at = datetime.now(timezone.utc)
            await db.posts.update_one(
                {"id": doc["id"], "workspace_id": workspace_id, "user_id": user_id},
                {
                    "$set": {
                        "status": PostStatus.FAILED,
                        "updated_at": failed_at,
                        "dlq_reason": "Failed to enqueue immediate publish",
                    },
                    "$push": {
                        "status_history": {
                            "status": PostStatus.FAILED,
                            "timestamp": failed_at,
                            "actor": "api",
                            "message": "Failed to enqueue immediate publish",
                        }
                    },
                },
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to queue post for immediate publishing",
            )

    # Phase 7.5.1 — Audit event
    await log_audit_event(
        db,
        action="post.created",
        actor_id=user_id,
        workspace_id=workspace_id,
        resource_type="post",
        resource_id=doc["id"],
        details={
            "platforms": body.platforms,
            "scheduled_time": scheduled_time.isoformat() if scheduled_time else None,
            "status": post_status.value,
            "publish_now": body.publish_now,
        },
    )

    event_log(
        logger,
        "info",
        "posts.created",
        route="/posts",
        user_id=user_id,
        workspace_id=workspace_id,
        post_id=doc["id"],
        status=post_status.value,
        publish_now=body.publish_now,
        outcome="created",
    )
    return _doc_to_response(doc)


# ── Bulk Create ──────────────────────────────────────────────────────────────

@router.get("/posts/bulk/template", response_class=StreamingResponse)
async def download_bulk_template():
    """Download a CSV template for bulk uploading posts."""
    import csv
    import io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Text", "Image URL", "Tags", "Posting Time"])
    example_time = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    writer.writerow(["A post with text...", "", "#sample", example_time])
    writer.writerow(["A post with an image", "https://example.com/image.jpg", "", ""])
    output.seek(0)
    
    headers = {
        "Content-Disposition": 'attachment; filename="bulk_upload_template.csv"',
        "Content-Type": "text/csv"
    }
    return StreamingResponse(output, headers=headers)


@router.post("/posts/bulk", response_model=BulkCreateResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[require_permission("post:create")])
@limiter.limit("50/hour")
async def bulk_create_posts(
    request: Request,
    body: BulkCreateRequest,
    current_user: CurrentUser,
    db: DB,
    queue_redis: QueueRedis,
) -> BulkCreateResponse:
    if any(post_item.scheduled_time for post_item in body.posts):
        _ensure_verified_email_for_publish_action(current_user)
    sub_status = current_user.get("subscription_status", "free")
    if sub_status not in _SUBSCRIPTION_ALLOWED:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Active subscription required to schedule posts",
        )

    workspace_id = body.workspace_id or current_user.get("default_workspace_id")
    user_id = current_user["user_id"]
    now = datetime.now(timezone.utc)
    
    created_count = 0
    skipped_count = 0
    errors = []

    for index, post_item in enumerate(body.posts):
        try:
            for platform in body.platforms:
                result = check_content_policy(post_item.content or "", platform)
                if not result.approved:
                    raise ValueError(f"Policy violation for {platform}: {result.violations}")

            _CHAR_LIMITS = {"twitter": 280, "linkedin": 3000, "instagram": 2200, "facebook": 63206, "tiktok": 2200, "youtube": 5000}
            for platform in body.platforms:
                limit = _CHAR_LIMITS.get(platform.lower())
                if limit and len(post_item.content) > limit:
                    raise ValueError(f"{platform} character limit is {limit}")

            doc = {
                "id": str(ObjectId()),
                "user_id": user_id,
                "workspace_id": workspace_id,
                "content": post_item.content,
                "platforms": body.platforms,
                "media_ids": [],
                "post_type": "image" if post_item.media_urls else "text",
                "timezone": body.timezone,
                "scheduled_time": post_item.scheduled_time,
                "status": PostStatus.SCHEDULED if post_item.scheduled_time else PostStatus.DRAFT,
                "platform_results": {},
                "platform_post_urls": {},
                "status_history": [
                    {"status": PostStatus.SCHEDULED if post_item.scheduled_time else PostStatus.DRAFT, "timestamp": now, "actor": user_id}
                ],
                "thumbnail_urls": post_item.media_urls,
                "pre_upload_status": None,
                "queue_job_id": None,
                "jitter_seconds": None,
                "version": 1,
                "dlq_reason": None,
                "content_hash": hashlib.sha256((post_item.content or "").encode()).hexdigest(),
                "schedule_warnings": [],
                "created_at": now,
                "updated_at": now,
            }
            
            await db.posts.insert_one(doc)
            created_count += 1
            
            await log_audit_event(
                db,
                action="post.created.bulk",
                actor_id=user_id,
                workspace_id=workspace_id,
                resource_type="post",
                resource_id=doc["id"],
                details={"platforms": body.platforms},
            )

        except Exception as e:
            skipped_count += 1
            errors.append({"row": index + 1, "message": str(e)})

    return BulkCreateResponse(created=created_count, skipped=skipped_count, errors=errors)


# ── List ─────────────────────────────────────────────────────────────────────

@router.get("/posts", response_model=list[PostResponse],
            dependencies=[require_permission("post:read")])
async def list_posts(
    current_user: CurrentUser,
    db: DB,
    workspace_id: Annotated[str | None, Query(max_length=100)] = None,
    status_filter: Annotated[str | None, Query(alias="status", max_length=50)] = None,
    published_window: Annotated[str | None, Query(max_length=50)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[PostResponse]:
    user_id = current_user["user_id"]
    ws_id = workspace_id or _post_workspace_id(current_user)

    query: dict = {
        "workspace_id": ws_id,
        "user_id": user_id,
        "deleted_at": {"$exists": False},
    }
    if status_filter:
        query["status"] = status_filter
    if status_filter == PostStatus.PUBLISHED and published_window == "past_6_months":
        cutoff = _subtract_months(datetime.now(timezone.utc), 6)
        cutoff_iso = cutoff.isoformat()
        query["$or"] = [
            {"published_at": {"$gte": cutoff}},
            {"published_at": {"$gte": cutoff_iso}},
            {"published_at": None, "updated_at": {"$gte": cutoff}},
            {"published_at": None, "updated_at": {"$gte": cutoff_iso}},
            {"published_at": {"$exists": False}, "updated_at": {"$gte": cutoff}},
            {"published_at": {"$exists": False}, "updated_at": {"$gte": cutoff_iso}},
            {
                "published_at": None,
                "updated_at": None,
                "created_at": {"$gte": cutoff},
            },
            {
                "published_at": None,
                "updated_at": None,
                "created_at": {"$gte": cutoff_iso},
            },
            {
                "published_at": {"$exists": False},
                "updated_at": {"$exists": False},
                "created_at": {"$gte": cutoff},
            },
            {
                "published_at": {"$exists": False},
                "updated_at": {"$exists": False},
                "created_at": {"$gte": cutoff_iso},
            },
        ]

    skip = (page - 1) * limit
    sort_spec = [("created_at", -1)]
    if status_filter == PostStatus.PUBLISHED:
        sort_spec = [("published_at", -1), ("updated_at", -1), ("created_at", -1)]
    cursor = db.posts.find(query, {"_id": 0}).sort(sort_spec).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)
    hydrated_docs = await _hydrate_post_card_fields_for_docs(db, docs)
    return [_doc_to_response(d) for d in hydrated_docs]


@router.get("/posts/recent-published", response_model=list[PostResponse],
            dependencies=[require_permission("post:read")])
async def list_recent_published_posts(
    current_user: CurrentUser,
    db: DB,
    workspace_id: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=25)] = 25,
) -> list[PostResponse]:
    user_id = current_user["user_id"]
    ws_id = workspace_id or _post_workspace_id(current_user)

    query: dict = {
        "workspace_id": ws_id,
        "user_id": user_id,
        "status": PostStatus.PUBLISHED,
        "deleted_at": {"$exists": False},
    }

    cursor = db.posts.find(query, {"_id": 0}).sort(
        [("published_at", -1), ("updated_at", -1), ("created_at", -1)]
    ).limit(limit)
    docs = await cursor.to_list(length=limit)
    hydrated_docs = await _hydrate_post_card_fields_for_docs(db, docs)
    return [_doc_to_response(d) for d in hydrated_docs]


@router.get("/approvals", dependencies=[require_permission("approval:read")])
async def list_approval_queue(
    current_user: CurrentUser,
    db: DB,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
):
    workspace_id = _post_workspace_id(current_user)
    now = datetime.now(timezone.utc)
    membership = await db.workspace_members.find_one(
        {"workspace_id": workspace_id, "user_id": current_user["user_id"]},
        {"_id": 0, "role": 1},
    )
    current_role = (membership or {}).get("role") or current_user.get("workspace_role") or "viewer"
    permission_flags = _approval_permission_flags(current_role)
    base_query = {
        "workspace_id": workspace_id,
        "deleted_at": {"$exists": False},
    }
    awaiting_query = {
        **base_query,
        "status": PostStatus.PENDING_APPROVAL,
        "scheduled_time": {"$gt": now},
    }
    changes_requested_query = {
        **base_query,
        "status": PostStatus.DRAFT,
        "rejection_reason": {"$regex": r"\S"},
    }
    expired_query = {
        **base_query,
        "status": PostStatus.PENDING_APPROVAL,
        "scheduled_time": {"$lte": now},
    }

    awaiting_cursor = db.posts.find(
        awaiting_query,
        {"_id": 0},
    ).sort([("scheduled_time", 1), ("updated_at", -1), ("created_at", -1)]).limit(limit)
    changes_requested_cursor = db.posts.find(
        changes_requested_query,
        {"_id": 0},
    ).sort([("rejected_at", -1), ("updated_at", -1), ("created_at", -1)]).limit(limit)
    expired_cursor = db.posts.find(
        expired_query,
        {"_id": 0},
    ).sort([("scheduled_time", -1), ("updated_at", -1), ("created_at", -1)]).limit(limit)

    awaiting_docs = await awaiting_cursor.to_list(length=limit)
    changes_requested_docs = await changes_requested_cursor.to_list(length=limit)
    expired_docs = await expired_cursor.to_list(length=limit)

    awaiting = await _enrich_approval_docs(
        db,
        awaiting_docs,
        workspace_id=workspace_id,
        current_user_id=current_user["user_id"],
        now=now,
    )
    changes_requested = [
        doc for doc in await _enrich_approval_docs(
            db,
            changes_requested_docs,
            workspace_id=workspace_id,
            current_user_id=current_user["user_id"],
            now=now,
        )
        if str(doc.get("rejection_reason") or "").strip()
    ]
    expired = await _enrich_approval_docs(
        db,
        expired_docs,
        workspace_id=workspace_id,
        current_user_id=current_user["user_id"],
        now=now,
    )

    return {
        "current_user_role": current_role,
        "permissions": permission_flags,
        "awaiting": awaiting,
        "changes_requested": changes_requested,
        "expired": expired,
        "summary": {
            "awaiting": await db.posts.count_documents(awaiting_query),
            "changes_requested": await db.posts.count_documents(changes_requested_query),
            "expired": await db.posts.count_documents(expired_query),
        },
    }


@router.get("/approvals/{post_id}/activity", dependencies=[require_permission("approval:read")])
async def get_approval_activity(
    post_id: str,
    current_user: CurrentUser,
    db: DB,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    workspace_id = _post_workspace_id(current_user)
    post = await db.posts.find_one(
        {
            "id": post_id,
            "workspace_id": workspace_id,
            "deleted_at": {"$exists": False},
        },
        {"_id": 0, "id": 1},
    )
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    docs = await db.approval_activity.find(
        {"workspace_id": workspace_id, "post_id": post_id},
        {"_id": 0},
    ).sort([("created_at", -1)]).limit(limit).to_list(length=limit)
    return [_approval_activity_response(doc) for doc in docs]


# ── Get single ───────────────────────────────────────────────────────────────

@router.get("/posts/{post_id}", response_model=PostResponse,
            dependencies=[require_permission("post:read")])
async def get_post(
    post_id: str,
    current_user: CurrentUser,
    db: DB,
) -> PostResponse:
    user_id = current_user["user_id"]
    ws_id = _post_workspace_id(current_user)

    doc = await db.posts.find_one(
        {"id": post_id, "user_id": user_id, "deleted_at": {"$exists": False}},
        {"_id": 0},
    )
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    # Verify via workspace_id when present
    if doc.get("workspace_id") and doc["workspace_id"] != ws_id:
        member = await db.workspace_members.find_one(
            {"workspace_id": doc["workspace_id"], "user_id": user_id}
        )
        if not member:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return _doc_to_response(await _hydrate_post_card_fields(db, doc))


# ── Update (optimistic lock EC25) ────────────────────────────────────────────

@router.patch("/posts/{post_id}", response_model=PostResponse,
              dependencies=[require_permission("post:update")])
async def update_post(
    post_id: str,
    body: UpdatePostRequest,
    current_user: CurrentUser,
    db: DB,
) -> PostResponse:
    if body.scheduled_time is not None:
        _ensure_verified_email_for_publish_action(current_user)
    user_id = current_user["user_id"]

    existing = await db.posts.find_one(
        {"id": post_id, "user_id": user_id, "deleted_at": {"$exists": False}},
        {
            "_id": 0,
            "id": 1,
            "user_id": 1,
            "status": 1,
            "workspace_id": 1,
            "platforms": 1,
            "title": 1,
            "content": 1,
            "scheduled_time": 1,
            "timezone": 1,
            "account_ids": 1,
            "social_account_ids": 1,
            "platform_results": 1,
            "post_type": 1,
            "approved_by": 1,
            "approved_at": 1,
        },
    )
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    if existing.get("status") in _BLOCKED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Post is currently being published",
        )

    if existing.get("status") == PostStatus.PENDING_APPROVAL:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This post is pending approval. Return it to draft before editing.",
        )

    if (
        existing.get("status") == PostStatus.SCHEDULED
        and (existing.get("approved_by") or existing.get("approved_at"))
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This approved post is locked by the approval workflow. Return it to draft before editing.",
        )

    now = datetime.now(timezone.utc)
    updates: dict = {"updated_at": now}
    if body.content is not None:
        updates["content"] = body.content
    if "scheduled_time" in body.model_fields_set:
        updates["scheduled_time"] = body.scheduled_time

    next_platforms = list(body.platforms) if body.platforms is not None else list(existing.get("platforms") or [])
    next_account_ids = list(body.account_ids) if body.account_ids is not None else list(existing.get("account_ids") or existing.get("social_account_ids") or [])
    selected_accounts = None
    if body.platforms is not None or body.account_ids is not None or body.account_overrides is not None:
        selected_accounts = await _resolve_selected_accounts(
            db,
            user_id,
            SimpleNamespace(account_ids=next_account_ids, platforms=next_platforms),
        )
        social_account_ids = [account["account_id"] for account in selected_accounts]
        updates["platforms"] = next_platforms
        updates["publish_targets"] = selected_accounts
        updates["account_ids"] = social_account_ids
        updates["social_account_ids"] = social_account_ids
        updates["platform_results"] = {
            platform: {"status": "pending"}
            for platform in next_platforms
        }
        updates["account_results"] = {
            account["account_id"]: {
                "status": "pending",
                "platform": account["platform"],
                "account_id": account["account_id"],
            }
            for account in selected_accounts
        }

    next_post_type = body.post_type if body.post_type is not None else existing.get("post_type")
    if body.platforms is not None or body.post_type is not None:
        for platform in next_platforms:
            try:
                validate_platform_content_type(platform, next_post_type)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    if body.media_urls is not None:
        for url in body.media_urls:
            try:
                assert_safe_url(url)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if body.media_ids is not None or body.media_urls is not None:
        media_urls, thumbnail_urls, primary_media_url, _ = await _resolve_media_payload(
            db, user_id, body.media_ids or [], body.media_urls or []
        )
        updates["media_ids"] = list(body.media_ids or [])
        updates["media_urls"] = media_urls
        updates["media_url"] = primary_media_url
        updates["thumbnail_urls"] = thumbnail_urls
    if body.post_type is not None:
        updates["post_type"] = body.post_type
    if "title" in body.model_fields_set:
        updates["title"] = body.title
    if "timezone" in body.model_fields_set:
        updates["timezone"] = body.timezone
    if "scheduled_time" in body.model_fields_set:
        updates["scheduled_timezone_explicit"] = bool(body.scheduled_time)

    if "scheduled_time" in body.model_fields_set and body.scheduled_time is not None:
        density_ws = existing.get("workspace_id") or current_user.get("default_workspace_id")
        density_warnings = await check_schedule_density(
            db,
            density_ws,
            next_platforms,
            body.scheduled_time,
        )
        for dw in density_warnings:
            event_log(
                logger,
                "warning",
                "posts.schedule_density.warning",
                route="/posts/{post_id}",
                user_id=user_id,
                workspace_id=density_ws,
                failure_type="schedule_density_warning",
                provider_error=dw.message,
                outcome="warning",
            )

    if body.platform_overrides is not None:
        normalized_platform_overrides: dict[str, dict] = {}
        for platform, override in body.platform_overrides.items():
            for url in (override.media_urls or []):
                try:
                    assert_safe_url(url)
                except ValueError as exc:
                    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
            normalized_override = override.model_dump(exclude_none=True)
            use_media_override = _override_explicitly_sets_media(override)
            normalized_override["use_media_override"] = use_media_override

            if use_media_override:
                override_media_urls, override_thumbnail_urls, override_primary_media_url, _ = await _resolve_media_payload(
                    db, user_id, override.media_ids, override.media_urls
                )
                normalized_override["media_ids"] = list(override.media_ids or [])
                normalized_override["media_urls"] = override_media_urls
                normalized_override["media_url"] = override_primary_media_url
                normalized_override["thumbnail_urls"] = override_thumbnail_urls

            normalized_platform_overrides[platform] = normalized_override
        updates["platform_overrides"] = normalized_platform_overrides
    if body.account_overrides is not None:
        normalized_account_overrides: dict[str, dict] = {}
        selected_accounts = selected_accounts or await _resolve_selected_accounts(
            db,
            user_id,
            SimpleNamespace(account_ids=next_account_ids, platforms=next_platforms),
        )
        valid_account_ids = {account["account_id"] for account in selected_accounts}
        for account_id, override in body.account_overrides.items():
            if account_id not in valid_account_ids:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Account override is not valid for this post: {account_id}",
                )
            for url in (override.media_urls or []):
                try:
                    assert_safe_url(url)
                except ValueError as exc:
                    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
            normalized_override = override.model_dump(exclude_none=True)
            use_media_override = _override_explicitly_sets_media(override)
            normalized_override["use_media_override"] = use_media_override

            if use_media_override:
                override_media_urls, override_thumbnail_urls, override_primary_media_url, _ = await _resolve_media_payload(
                    db, user_id, override.media_ids, override.media_urls
                )
                normalized_override["media_ids"] = list(override.media_ids or [])
                normalized_override["media_urls"] = override_media_urls
                normalized_override["media_url"] = override_primary_media_url
                normalized_override["thumbnail_urls"] = override_thumbnail_urls

            normalized_account_overrides[account_id] = normalized_override
        updates["account_overrides"] = normalized_account_overrides

    result = await db.posts.update_one(
        {
            "id": post_id,
            "user_id": user_id,
            "version": body.version,
            "deleted_at": {"$exists": False},
        },
        {"$set": updates, "$inc": {"version": 1}},
    )

    if result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Version conflict — fetch the latest version and retry",
        )

    updated = await db.posts.find_one({"id": post_id, "user_id": user_id}, {"_id": 0})

    if (
        "scheduled_time" in body.model_fields_set
        and body.scheduled_time is not None
        and updated
        and updated.get("status") == PostStatus.SCHEDULED
    ):
        try:
            await _emit_scheduled_post_notification(db, updated, now=now)
        except Exception as exc:
            logger.warning("Failed to store rescheduled notification for post %s: %s", post_id, exc)

    # Phase 7.5.1 — Audit event
    await log_audit_event(
        db,
        action="post.updated",
        actor_id=user_id,
        workspace_id=existing["workspace_id"],
        resource_type="post",
        resource_id=post_id,
        details={"fields_changed": list(updates.keys())},
    )

    return _doc_to_response(await _hydrate_post_card_fields(db, updated))


# ── Soft-delete ───────────────────────────────────────────────────────────────

@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[require_permission("post:delete")])
async def delete_post(
    post_id: str,
    current_user: CurrentUser,
    db: DB,
) -> None:
    user_id = current_user["user_id"]

    existing = await db.posts.find_one(
        {"id": post_id, "user_id": user_id, "deleted_at": {"$exists": False}},
        {
            "_id": 0,
            "status": 1,
            "queue_job_id": 1,
            "media_ids": 1,
            "workspace_id": 1,
            "platform_results": 1,
            "account_results": 1,
        },
    )
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    now = datetime.now(timezone.utc)
    set_updates = {"deleted_at": now, "updated_at": now, "status": PostStatus.CANCELLED}
    if existing.get("status") in _BLOCKED_STATUSES:
        platform_results = existing.get("platform_results") or {}
        account_results = existing.get("account_results") or {}
        for platform, result in platform_results.items():
            if (result or {}).get("status") not in {"published", "failed", "permanently_failed", "cancelled"}:
                set_updates[f"platform_results.{platform}.status"] = "cancelled"
                set_updates[f"platform_results.{platform}.error"] = "Cancelled by user"
        for account_id, result in account_results.items():
            if (result or {}).get("status") not in {"published", "failed", "permanently_failed", "cancelled"}:
                set_updates[f"account_results.{account_id}.status"] = "cancelled"
                set_updates[f"account_results.{account_id}.error"] = "Cancelled by user"

    await db.posts.update_one(
        {"id": post_id, "user_id": user_id},
        {"$set": set_updates},
    )

    # Revoke Celery task if queued
    queue_job_id = existing.get("queue_job_id")
    if queue_job_id:
        try:
            revoke_task(queue_job_id, terminate=False)
        except Exception as exc:
            logger.warning("Failed to revoke Celery task %s: %s", queue_job_id, exc)

    for child_task_id in _collect_dispatch_task_ids(existing):
        try:
            revoke_task(child_task_id, terminate=False)
        except Exception as exc:
            logger.warning("Failed to revoke child Celery task %s: %s", child_task_id, exc)

    # Schedule near-immediate orphan cleanup for deleted post media.
    try:
        enqueue_task(
            "celery_workers.tasks.cleanup.cleanup_deleted_post_media",
            args=[post_id],
        )
    except Exception as exc:
        logger.warning("Failed to schedule media cleanup for %s: %s", post_id, exc)

    # Phase 7.5.1 — Audit event
    await log_audit_event(
        db,
        action="post.deleted",
        actor_id=user_id,
        workspace_id=existing["workspace_id"],
        resource_type="post",
        resource_id=post_id,
        details={},
    )


# ── Failed / DLQ ──────────────────────────────────────────────────────────────

@router.get("/posts/failed", dependencies=[require_permission("post:read")])
async def list_failed_posts(current_user: CurrentUser, db: DB):
    """Return posts with failed or partially failed publishing outcomes."""
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    cursor = db.posts.find(
        {
            "workspace_id": workspace_id,
            "status": {"$in": ["failed", "partial"]},
            "deleted_at": {"$exists": False},
        },
        {"_id": 0},
    ).sort("updated_at", -1).limit(100)
    docs = await cursor.to_list(None)
    hydrated_docs = await _hydrate_post_card_fields_for_docs(db, docs)
    return [_doc_to_response(d) for d in hydrated_docs]


@router.post("/posts/{post_id}/retry", dependencies=[require_permission("post:update")])
async def retry_failed_post(
    post_id: str,
    current_user: VerifiedUser,
    db: DB,
    platform: str | None = Query(None),
):
    """Re-queue failed publishing work, optionally for a single platform."""
    from celery_workers.tasks.publish import _aggregate_platform_results, _get_publish_targets

    user_id = current_user["user_id"]
    post = await db.posts.find_one(
        {"id": post_id, "user_id": user_id, "deleted_at": {"$exists": False}},
        {"_id": 0, "status": 1, "version": 1, "platforms": 1, "platform_results": 1, "account_results": 1, "publish_targets": 1},
    )
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.get("status") not in ("failed", "dlq", "partial"):
        raise HTTPException(
            status_code=409,
            detail="Only failed or partially failed posts can be retried",
        )

    platform_results = post.get("platform_results") or {}
    account_results = post.get("account_results") or {}
    retryable_statuses = {"failed", "permanently_failed", "paused"}
    retry_targets: list[dict]

    if account_results:
        publish_targets = _get_publish_targets(post)
        if platform:
            retry_targets = [
                target
                for target in publish_targets
                if target["platform"] == platform
                and (account_results.get(target["target_key"]) or {}).get("status") in retryable_statuses
            ]
            if not retry_targets:
                raise HTTPException(status_code=409, detail=f"Platform {platform} is not in a retryable state")
        else:
            retry_targets = [
                target
                for target in publish_targets
                if (account_results.get(target["target_key"]) or {}).get("status") in retryable_statuses
            ]
            if not retry_targets:
                if post.get("status") in ("failed", "dlq"):
                    retry_targets = publish_targets
                else:
                    raise HTTPException(status_code=409, detail="No failed accounts to retry")
    else:
        retry_platforms: list[str]
        if platform:
            if platform not in set(post.get("platforms") or []):
                raise HTTPException(status_code=404, detail="Platform not associated with this post")
            platform_status = (platform_results.get(platform) or {}).get("status")
            if platform_status not in retryable_statuses:
                raise HTTPException(
                    status_code=409,
                    detail=f"Platform {platform} is not in a retryable state",
                )
            retry_platforms = [platform]
        else:
            retry_platforms = [
                name
                for name, result in platform_results.items()
                if (result or {}).get("status") in retryable_statuses
            ]
            if not retry_platforms:
                if post.get("status") in ("failed", "dlq"):
                    retry_platforms = list(post.get("platforms") or [])
                else:
                    raise HTTPException(status_code=409, detail="No failed platforms to retry")
        retry_targets = [{"platform": retry_platform, "account_id": None, "target_key": retry_platform} for retry_platform in retry_platforms]

    now = datetime.now(timezone.utc)
    set_updates = {
        "status": PostStatus.PROCESSING,
        "updated_at": now,
    }
    unset_updates = {"dlq_reason": ""}
    for target in retry_targets:
        target_key = target["target_key"]
        if account_results:
            prefix = f"account_results.{target_key}"
            set_updates[f"{prefix}.status"] = "queued"
            set_updates[f"{prefix}.platform"] = target["platform"]
            set_updates[f"{prefix}.account_id"] = target["account_id"] or target_key
        else:
            prefix = f"platform_results.{target_key}"
            set_updates[f"{prefix}.status"] = "queued"
        set_updates[f"{prefix}.last_attempt_at"] = now
        set_updates[f"{prefix}.next_retry_at"] = None
        set_updates[f"{prefix}.error"] = None
        set_updates[f"{prefix}.dlq_reason"] = None
        set_updates[f"{prefix}.retry_count"] = 0

    if account_results:
        next_post = {
            **post,
            "account_results": {
                **account_results,
                **{
                    target["target_key"]: {
                        **(account_results.get(target["target_key"]) or {}),
                        "status": "queued",
                        "platform": target["platform"],
                        "account_id": target["account_id"] or target["target_key"],
                        "last_attempt_at": now,
                        "next_retry_at": None,
                        "error": None,
                        "dlq_reason": None,
                        "retry_count": 0,
                    }
                    for target in retry_targets
                },
            },
        }
        set_updates["platform_results"] = _aggregate_platform_results(next_post)

    await db.posts.update_one(
        {"id": post_id, "user_id": user_id, "deleted_at": {"$exists": False}},
        {
            "$set": set_updates,
            "$unset": unset_updates,
            "$inc": {"version": 1},
        },
    )

    enqueue_errors: list[str] = []
    for target in retry_targets:
        try:
            enqueue_task(
                "celery_workers.tasks.publish.publish_to_platform",
                kwargs={"post_id": post_id, "platform": target["platform"], "account_id": target["account_id"], "attempt": 0},
                queue="default",
            )
        except Exception as exc:
            enqueue_errors.append(f"{target['target_key']}: {exc}")
            logger.warning(
                "Failed to enqueue retry for post %s target %s: %s",
                post_id,
                target["target_key"],
                exc,
            )

    if enqueue_errors:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to enqueue retry for one or more platforms: {enqueue_errors}",
        )

    return {
        "retried": True,
        "post_id": post_id,
        "platforms": sorted({target["platform"] for target in retry_targets}),
        "account_ids": [target["account_id"] for target in retry_targets if target["account_id"]],
    }


# ── Approval workflow ─────────────────────────────────────────────────────────

async def _approve_post_action(
    post_id: str,
    current_user: dict,
    db,
    *,
    activity_action: str = "approved",
):
    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id
    now = datetime.now(timezone.utc)
    existing = await db.posts.find_one(
        {
            "id": post_id,
            "workspace_id": workspace_id,
            "status": PostStatus.PENDING_APPROVAL,
            "deleted_at": {"$exists": False},
        },
        {"_id": 0},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Post not found or not pending approval")
    scheduled_time = _normalized_schedule_datetime(existing.get("scheduled_time"))
    if scheduled_time is None or scheduled_time <= now:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Approval requires a future scheduled time. Move this post back to draft and reschedule it before approval.",
        )
    result = await db.posts.find_one_and_update(
        {
            "id": post_id,
            "workspace_id": workspace_id,
            "status": PostStatus.PENDING_APPROVAL,
            "deleted_at": {"$exists": False},
        },
        {"$set": {"status": PostStatus.SCHEDULED, "approved_by": user_id,
                  "approved_at": now, "updated_at": now},
         "$push": {"status_history": {"status": PostStatus.SCHEDULED,
                                      "timestamp": now, "actor": user_id}}},
        return_document=True,
        projection={"_id": 0},
    )
    if not result:
        raise HTTPException(status_code=404, detail="Post not found or not pending approval")
    await _record_approval_activity(
        db,
        post_doc=result,
        actor_id=user_id,
        action=activity_action,
        old_status=PostStatus.PENDING_APPROVAL,
        new_status=PostStatus.SCHEDULED,
        created_at=now,
    )
    await _notify_creator_of_decision(
        db,
        result,
        event="approval.approved",
        title="Post approved",
        message=f"{_post_review_title(result)} was approved and is back on the schedule.",
        severity="low",
        dedup_suffix="approved",
        now=now,
    )
    return {"approved": True, "post_id": post_id, "status": PostStatus.SCHEDULED}


async def _reject_post_action(
    post_id: str,
    body: ApprovalDecisionBody,
    current_user: dict,
    db,
    *,
    activity_action: str = "changes_requested",
):
    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id
    now = datetime.now(timezone.utc)
    reason = (body.reason or "").strip() or "Changes requested"
    existing = await db.posts.find_one(
        {
            "id": post_id,
            "workspace_id": workspace_id,
            "status": PostStatus.PENDING_APPROVAL,
            "deleted_at": {"$exists": False},
        },
        {"_id": 0},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Post not found or not pending approval")
    result = await db.posts.find_one_and_update(
        {
            "id": post_id,
            "workspace_id": workspace_id,
            "status": PostStatus.PENDING_APPROVAL,
            "deleted_at": {"$exists": False},
        },
        {"$set": {"status": PostStatus.DRAFT, "rejected_by": user_id,
                  "rejected_at": now, "rejection_reason": reason,
                  "updated_at": now},
         "$push": {"status_history": {"status": PostStatus.DRAFT,
                                      "timestamp": now, "actor": user_id,
                                      "reason": reason}}},
        return_document=True,
        projection={"_id": 0},
    )
    if not result:
        raise HTTPException(status_code=404, detail="Post not found or not pending approval")
    await _record_approval_activity(
        db,
        post_doc=result,
        actor_id=user_id,
        action=activity_action,
        old_status=PostStatus.PENDING_APPROVAL,
        new_status=PostStatus.DRAFT,
        reason=reason,
        created_at=now,
    )
    await _notify_creator_of_decision(
        db,
        result,
        event="approval.changes_requested",
        title="Changes requested",
        message=f"{_post_review_title(result)} needs changes before it can be approved.",
        severity="medium",
        dedup_suffix="changes",
        now=now,
    )
    return {"rejected": True, "post_id": post_id, "status": PostStatus.DRAFT, "rejection_reason": reason}


async def _resubmit_post_action(post_id: str, body: ApprovalResubmitBody, current_user: dict, db):
    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id
    now = datetime.now(timezone.utc)
    existing = await db.posts.find_one(
        {
            "id": post_id,
            "workspace_id": workspace_id,
            "status": PostStatus.DRAFT,
            "deleted_at": {"$exists": False},
        },
        {"_id": 0},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Post not found or not eligible for resubmission")
    if existing.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the draft creator can resubmit this post for review.",
        )
    scheduled_time = _normalized_schedule_datetime(existing.get("scheduled_time"))
    if scheduled_time is None or scheduled_time <= now:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Set a future scheduled time before submitting this draft for review.",
        )
    approval_due_at = body.approval_due_at or _default_approval_due_at(scheduled_time)
    updates: dict = {
        "status": PostStatus.PENDING_APPROVAL,
        "updated_at": now,
        "approval_due_at": approval_due_at,
    }
    if body.content:
        updates["content"] = body.content
    if body.assigned_reviewer_id:
        updates["assigned_reviewer_id"] = body.assigned_reviewer_id
    action = "resubmitted" if str(existing.get("rejection_reason") or "").strip() else "submitted"
    result = await db.posts.find_one_and_update(
        {
            "id": post_id,
            "user_id": user_id,
            "workspace_id": workspace_id,
            "status": PostStatus.DRAFT,
            "deleted_at": {"$exists": False},
        },
        {"$set": updates,
         "$unset": {
             "rejection_reason": "",
             "rejected_at": "",
             "rejected_by": "",
             "approval_overdue_notified_at": "",
         },
         "$push": {"status_history": {"status": PostStatus.PENDING_APPROVAL,
                                      "timestamp": now, "actor": user_id}}},
        return_document=True,
        projection={"_id": 0},
    )
    if not result:
        raise HTTPException(status_code=404, detail="Post not found or not eligible for resubmission")
    await _record_approval_activity(
        db,
        post_doc=result,
        actor_id=user_id,
        action=action,
        old_status=PostStatus.DRAFT,
        new_status=PostStatus.PENDING_APPROVAL,
        reason="Submitted for review",
        created_at=now,
    )
    await _notify_reviewers_of_submission(db, result, actor_id=user_id, now=now)
    return {"resubmitted": True, "post_id": post_id, "status": PostStatus.PENDING_APPROVAL}


async def _return_post_to_draft_action(post_id: str, current_user: dict, db):
    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id
    now = datetime.now(timezone.utc)
    existing = await db.posts.find_one(
        {
            "id": post_id,
            "workspace_id": workspace_id,
            "deleted_at": {"$exists": False},
            "$or": [
                {"status": PostStatus.PENDING_APPROVAL},
                {"status": PostStatus.SCHEDULED, "approved_by": {"$exists": True}},
            ],
        },
        {"_id": 0},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Post not found or not eligible to return to draft")
    result = await db.posts.find_one_and_update(
        {
            "id": post_id,
            "workspace_id": workspace_id,
            "deleted_at": {"$exists": False},
            "$or": [
                {"status": PostStatus.PENDING_APPROVAL},
                {"status": PostStatus.SCHEDULED, "approved_by": {"$exists": True}},
            ],
        },
        {
            "$set": {"status": PostStatus.DRAFT, "updated_at": now},
            "$unset": {"approved_by": "", "approved_at": ""},
            "$push": {
                "status_history": {
                    "status": PostStatus.DRAFT,
                    "timestamp": now,
                    "actor": user_id,
                    "reason": "Returned to draft after approval window expired",
                }
            },
        },
        return_document=True,
        projection={"_id": 0},
    )
    if not result:
        raise HTTPException(status_code=404, detail="Post not found or not eligible to return to draft")
    await _record_approval_activity(
        db,
        post_doc=result,
        actor_id=user_id,
        action="returned",
        old_status=existing.get("status"),
        new_status=PostStatus.DRAFT,
        reason="Returned to draft for rescheduling or edits",
        created_at=now,
    )
    await _notify_creator_of_decision(
        db,
        result,
        event="approval.returned",
        title="Post returned to draft",
        message=f"{_post_review_title(result)} was returned to draft for rescheduling or edits.",
        severity="medium",
        dedup_suffix="returned",
        now=now,
    )
    return {"returned_to_draft": True, "post_id": post_id, "status": PostStatus.DRAFT}


def _bulk_unique_post_ids(post_ids: list[str]) -> list[str]:
    unique: list[str] = []
    for post_id in post_ids or []:
        clean = str(post_id or "").strip()
        if clean and clean not in unique:
            unique.append(clean)
    return unique


@router.post("/posts/{post_id}/approve", dependencies=[require_permission("approval:decide")])
async def approve_post(post_id: str, current_user: CurrentUser, db: DB):
    """Approve a post in review status → scheduled."""
    return await _approve_post_action(post_id, current_user, db)


@router.post("/posts/{post_id}/reject", dependencies=[require_permission("approval:decide")])
async def reject_post(post_id: str, body: ApprovalDecisionBody, current_user: CurrentUser, db: DB):
    """Reject a post in review — moves to draft with rejection note."""
    return await _reject_post_action(post_id, body, current_user, db)


@router.post("/posts/{post_id}/resubmit", dependencies=[require_permission("post:update")])
async def resubmit_post(post_id: str, body: ApprovalResubmitBody, current_user: CurrentUser, db: DB):
    """Resubmit a rejected post for approval."""
    return await _resubmit_post_action(post_id, body, current_user, db)


@router.post("/posts/{post_id}/submit-review", dependencies=[require_permission("post:update")])
async def submit_post_for_review(post_id: str, body: ApprovalResubmitBody, current_user: CurrentUser, db: DB):
    return await _resubmit_post_action(post_id, body, current_user, db)


@router.post("/posts/{post_id}/return-to-draft", dependencies=[require_permission("approval:decide")])
async def return_post_to_draft(post_id: str, current_user: CurrentUser, db: DB):
    """Return an expired approval item back to draft for rescheduling."""
    return await _return_post_to_draft_action(post_id, current_user, db)


@router.post("/approvals/bulk/approve", dependencies=[require_permission("approval:decide")])
async def bulk_approve_posts(body: ApprovalBulkDecisionBody, current_user: CurrentUser, db: DB):
    approved: list[str] = []
    errors: list[dict] = []
    for post_id in _bulk_unique_post_ids(body.post_ids):
        try:
            await _approve_post_action(post_id, current_user, db, activity_action="bulk_approved")
            approved.append(post_id)
        except HTTPException as exc:
            errors.append({"post_id": post_id, "status_code": exc.status_code, "detail": exc.detail})
    return {"approved": approved, "errors": errors}


@router.post("/approvals/bulk/reject", dependencies=[require_permission("approval:decide")])
async def bulk_reject_posts(body: ApprovalBulkDecisionBody, current_user: CurrentUser, db: DB):
    rejected: list[str] = []
    errors: list[dict] = []
    reason = (body.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Rejection reason is required for bulk review")
    for post_id in _bulk_unique_post_ids(body.post_ids):
        try:
            await _reject_post_action(
                post_id,
                ApprovalDecisionBody(reason=reason),
                current_user,
                db,
                activity_action="bulk_changes_requested",
            )
            rejected.append(post_id)
        except HTTPException as exc:
            errors.append({"post_id": post_id, "status_code": exc.status_code, "detail": exc.detail})
    return {"rejected": rejected, "errors": errors}


# ── Duplicate ─────────────────────────────────────────────────────────────────

@router.post("/posts/{post_id}/duplicate", dependencies=[require_permission("post:create")])
async def duplicate_post(post_id: str, current_user: CurrentUser, db: DB):
    """Create a draft copy of an existing post."""
    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id

    original = await db.posts.find_one(
        {"id": post_id, "user_id": user_id, "deleted_at": {"$exists": False}},
        {"_id": 0},
    )
    if not original:
        raise HTTPException(status_code=404, detail="Post not found")

    now = datetime.now(timezone.utc)
    new_id = str(ObjectId())
    copy = {**original, "id": new_id, "status": PostStatus.DRAFT,
            "scheduled_time": None, "created_at": now, "updated_at": now,
            "platform_results": {}, "queue_job_id": None, "version": 1,
            "dlq_reason": None, "status_history": [
                {"status": PostStatus.DRAFT, "timestamp": now, "actor": user_id}
            ]}
    copy.pop("_id", None)
    await db.posts.insert_one(copy)
    copy.pop("_id", None)
    return _doc_to_response(copy)


# ── Onboarding complete ───────────────────────────────────────────────────────

@router.post("/onboarding/complete")
async def complete_onboarding(body: dict, current_user: CurrentUser, db: DB):
    """Mark user onboarding as completed."""
    user_id = current_user["user_id"]
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"onboarding_completed": True, "updated_at": datetime.now(timezone.utc)}},
    )
    return {"completed": True}


# ── Inline Draft Comments & Activity Threads (Feature 5) ─────────────────────

class AddCommentBody(BaseModel):
    text: str


@router.post("/posts/{post_id}/comments", dependencies=[require_permission("post:read")])
async def add_post_comment(
    post_id: str,
    body: AddCommentBody,
    current_user: CurrentUser,
    db: DB,
):
    """Add an inline review/revision comment to a post card."""
    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Comment text cannot be empty")

    post = await db.posts.find_one(
        {"id": post_id, "$or": [{"workspace_id": workspace_id}, {"user_id": user_id}], "deleted_at": {"$exists": False}}
    )
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    comment_id = str(ObjectId())
    now = datetime.now(timezone.utc)
    user_doc = await db.users.find_one({"user_id": user_id}) or {}
    author_name = user_doc.get("name") or user_doc.get("email") or "Team Member"
    author_avatar = user_doc.get("picture") or user_doc.get("avatar_url")

    comment_doc = {
        "id": comment_id,
        "user_id": user_id,
        "author_name": author_name,
        "author_avatar": author_avatar,
        "text": text,
        "created_at": now,
        "resolved": False,
    }

    await db.posts.update_one(
        {"id": post_id},
        {
            "$push": {"comments": comment_doc},
            "$set": {"updated_at": now},
        }
    )

    if hasattr(db, "approval_activity") and post.get("status") == PostStatus.PENDING_APPROVAL.value:
        try:
            await _record_approval_activity(
                db,
                post_doc=post,
                actor_id=user_id,
                action="comment_added",
                old_status=post.get("status", PostStatus.DRAFT.value),
                new_status=post.get("status", PostStatus.DRAFT.value),
                created_at=now,
                note=text[:80],
            )
        except Exception:
            pass

    return comment_doc


@router.patch("/posts/{post_id}/comments/{comment_id}/resolve", dependencies=[require_permission("post:read")])
async def toggle_post_comment_resolve(
    post_id: str,
    comment_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """Toggle resolved status of an inline comment."""
    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id

    post = await db.posts.find_one(
        {"id": post_id, "$or": [{"workspace_id": workspace_id}, {"user_id": user_id}], "deleted_at": {"$exists": False}}
    )
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    comments = post.get("comments") or []
    target_comment = next((c for c in comments if c.get("id") == comment_id), None)
    if not target_comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    new_resolved = not target_comment.get("resolved", False)
    await db.posts.update_one(
        {"id": post_id, "comments.id": comment_id},
        {"$set": {"comments.$.resolved": new_resolved, "updated_at": datetime.now(timezone.utc)}}
    )
    return {"resolved": new_resolved}


@router.delete("/posts/{post_id}/comments/{comment_id}", dependencies=[require_permission("post:read")])
async def delete_post_comment(
    post_id: str,
    comment_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """Delete an inline comment."""
    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id

    post = await db.posts.find_one(
        {"id": post_id, "$or": [{"workspace_id": workspace_id}, {"user_id": user_id}], "deleted_at": {"$exists": False}}
    )
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    await db.posts.update_one(
        {"id": post_id},
        {"$pull": {"comments": {"id": comment_id}}, "$set": {"updated_at": datetime.now(timezone.utc)}}
    )
    return {"deleted": True}


# ── Shareable Client Review Magic Links (Feature 2) ──────────────────────────

class ShareReviewLinkBody(BaseModel):
    expires_in_days: int = 7
    allow_comments: bool = True


class PublicDecisionBody(BaseModel):
    post_id: str
    decision: str  # "approve" | "changes_requested"
    feedback: str | None = None
    reviewer_name: str | None = "Client Reviewer"


@router.post("/approvals/share-link", dependencies=[require_permission("approval:read")])
async def generate_shareable_review_link(
    body: ShareReviewLinkBody,
    current_user: CurrentUser,
    db: DB,
):
    """Generate a signed public magic link for frictionless client reviews without login."""
    import secrets
    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id
    token = f"rev_{secrets.token_urlsafe(24)}"
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=max(1, min(body.expires_in_days, 30)))

    doc = {
        "token": token,
        "workspace_id": workspace_id,
        "created_by": user_id,
        "allow_comments": body.allow_comments,
        "expires_at": expires_at,
        "created_at": now,
    }
    await db.approval_links.insert_one(doc)

    return {
        "token": token,
        "share_url": f"https://www.unravler.com/review/{token}",
        "expires_at": expires_at.isoformat(),
        "allow_comments": body.allow_comments,
    }


@router.get("/approvals/public/{token}")
async def get_public_approval_feed(
    token: str,
    db: DB,
):
    """Public read-only feed of pending posts for client review."""
    link_doc = await db.approval_links.find_one({"token": token})
    if not link_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid or expired review link")

    now = datetime.now(timezone.utc)
    exp = link_doc.get("expires_at")
    if exp and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp and now > exp:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="This review link has expired")

    workspace_id = link_doc.get("workspace_id")
    posts_cursor = db.posts.find({
        "$or": [{"workspace_id": workspace_id}, {"user_id": workspace_id}],
        "status": PostStatus.PENDING_APPROVAL.value,
        "deleted_at": {"$exists": False},
    }).sort("scheduled_time", 1).limit(50)

    pending_posts = []
    async for p in posts_cursor:
        pending_posts.append({
            "id": p.get("id"),
            "content": p.get("content", ""),
            "platforms": p.get("platforms", []),
            "media_urls": p.get("media_urls", []),
            "post_type": p.get("post_type", "text"),
            "title": p.get("title"),
            "scheduled_time": p.get("scheduled_time").isoformat() if isinstance(p.get("scheduled_time"), datetime) else p.get("scheduled_time"),
            "timezone": p.get("timezone", "UTC"),
            "comments": [
                {
                    "id": c.get("id"),
                    "author_name": c.get("author_name", "Reviewer"),
                    "text": c.get("text", ""),
                    "created_at": c.get("created_at").isoformat() if isinstance(c.get("created_at"), datetime) else c.get("created_at"),
                    "resolved": c.get("resolved", False),
                }
                for c in (p.get("comments") or [])
            ],
        })

    return {
        "workspace_id": workspace_id,
        "allow_comments": link_doc.get("allow_comments", True),
        "posts": pending_posts,
    }


@router.post("/approvals/public/{token}/decision")
async def submit_public_client_decision(
    token: str,
    body: PublicDecisionBody,
    db: DB,
):
    """Submit client approval or change request via public magic link."""
    link_doc = await db.approval_links.find_one({"token": token})
    if not link_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid or expired review link")

    now = datetime.now(timezone.utc)
    exp = link_doc.get("expires_at")
    if exp and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp and now > exp:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="This review link has expired")

    workspace_id = link_doc.get("workspace_id")
    post = await db.posts.find_one({
        "id": body.post_id,
        "$or": [{"workspace_id": workspace_id}, {"user_id": workspace_id}],
        "status": PostStatus.PENDING_APPROVAL.value,
        "deleted_at": {"$exists": False},
    })
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found or already reviewed")

    reviewer = body.reviewer_name or "Client (Magic Link)"

    if body.decision == "approve":
        update_fields = {
            "status": PostStatus.SCHEDULED.value,
            "approved_at": now,
            "approved_by": reviewer,
            "rejection_reason": None,
            "updated_at": now,
        }
        await db.posts.update_one(
            {"id": body.post_id},
            {
                "$set": update_fields,
                "$inc": {"version": 1},
                "$push": {
                    "status_history": {
                        "status": PostStatus.SCHEDULED.value,
                        "timestamp": now,
                        "actor": reviewer,
                        "message": f"Approved via client magic link by {reviewer}",
                    }
                },
            },
        )
    else:
        reason = (body.feedback or "Changes requested by client").strip()
        update_fields = {
            "status": PostStatus.DRAFT.value,
            "rejected_at": now,
            "rejected_by": reviewer,
            "rejection_reason": reason,
            "updated_at": now,
        }
        comment_item = {
            "id": str(ObjectId()),
            "user_id": "client_guest",
            "author_name": reviewer,
            "author_avatar": None,
            "text": f"Change Request: {reason}",
            "created_at": now,
            "resolved": False,
        }
        await db.posts.update_one(
            {"id": body.post_id},
            {
                "$set": update_fields,
                "$inc": {"version": 1},
                "$push": {
                    "comments": comment_item,
                    "status_history": {
                        "status": PostStatus.DRAFT.value,
                        "timestamp": now,
                        "actor": reviewer,
                        "message": f"Changes requested: {reason}",
                    },
                },
            },
        )

    return {"ok": True, "post_id": body.post_id, "status": update_fields["status"]}

