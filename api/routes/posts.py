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
from typing import Annotated

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from api.deps import CurrentUser, DB, QueueRedis, require_permission
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
from utils.schedule_density import check_schedule_density
from utils.ssrf_guard import assert_safe_url

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


def _hydrate_post_card_fields(doc: dict) -> dict:
    if doc.get("published_media_kind") not in {"text", "image", "video", "mixed"}:
        doc["published_media_kind"] = _infer_published_media_kind(doc)
    return doc


def _plan_post_limit(plan: str) -> int:
    return {"starter": 30, "pro": 200, "agency": 2000}.get(plan, 30)


def _doc_to_response(doc: dict) -> PostResponse:
    doc.setdefault("id", str(doc.get("_id", "")))
    doc.pop("_id", None)
    doc.pop("deleted_at", None)
    return PostResponse(**doc)


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
        logger.info("Post pre-publish warnings user=%s: %s", user_id, all_warnings)

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

    if body.publish_now:
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
        logger.warning("Schedule density warning: %s", dw.message)
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
            logger.info("Enqueued immediate publish for post %s task=%s", doc["id"], async_result.id)
        except Exception:
            logger.exception("Failed to enqueue immediate publish for post %s", doc["id"])
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

    logger.info("Post created: %s user=%s workspace=%s", doc["id"], user_id, workspace_id)
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
    ws_id = workspace_id or current_user.get("default_workspace_id")

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
            {"published_at": {"$exists": False}, "updated_at": {"$gte": cutoff}},
            {"published_at": {"$exists": False}, "updated_at": {"$gte": cutoff_iso}},
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
    return [_doc_to_response(_hydrate_post_card_fields(d)) for d in docs]


@router.get("/posts/recent-published", response_model=list[PostResponse],
            dependencies=[require_permission("post:read")])
async def list_recent_published_posts(
    current_user: CurrentUser,
    db: DB,
    workspace_id: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=25)] = 25,
) -> list[PostResponse]:
    user_id = current_user["user_id"]
    ws_id = workspace_id or current_user.get("default_workspace_id")

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
    return [_doc_to_response(_hydrate_post_card_fields(d)) for d in docs]


# ── Get single ───────────────────────────────────────────────────────────────

@router.get("/posts/{post_id}", response_model=PostResponse,
            dependencies=[require_permission("post:read")])
async def get_post(
    post_id: str,
    current_user: CurrentUser,
    db: DB,
) -> PostResponse:
    user_id = current_user["user_id"]
    ws_id = current_user.get("default_workspace_id")

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

    return _doc_to_response(_hydrate_post_card_fields(doc))


# ── Update (optimistic lock EC25) ────────────────────────────────────────────

@router.patch("/posts/{post_id}", response_model=PostResponse,
              dependencies=[require_permission("post:update")])
async def update_post(
    post_id: str,
    body: UpdatePostRequest,
    current_user: CurrentUser,
    db: DB,
) -> PostResponse:
    user_id = current_user["user_id"]

    existing = await db.posts.find_one(
        {"id": post_id, "user_id": user_id, "deleted_at": {"$exists": False}},
        {"_id": 0, "status": 1, "workspace_id": 1},
    )
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    if existing.get("status") in _BLOCKED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Post is currently being published",
        )

    now = datetime.now(timezone.utc)
    updates: dict = {"updated_at": now}
    if body.content is not None:
        updates["content"] = body.content
    if body.scheduled_time is not None:
        updates["scheduled_time"] = body.scheduled_time
    if body.platforms is not None:
        updates["platforms"] = body.platforms
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
        for account_id, override in body.account_overrides.items():
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

    return _doc_to_response(_hydrate_post_card_fields(updated))


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
        {"_id": 0, "status": 1, "queue_job_id": 1, "media_ids": 1, "workspace_id": 1},
    )
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    if existing.get("status") in _BLOCKED_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Post is currently being published",
        )

    now = datetime.now(timezone.utc)
    await db.posts.update_one(
        {"id": post_id, "user_id": user_id},
        {"$set": {"deleted_at": now, "updated_at": now, "status": PostStatus.CANCELLED}},
    )

    # Revoke Celery task if queued
    queue_job_id = existing.get("queue_job_id")
    if queue_job_id:
        try:
            revoke_task(queue_job_id, terminate=False)
        except Exception as exc:
            logger.warning("Failed to revoke Celery task %s: %s", queue_job_id, exc)

    # Schedule media cleanup with 5-minute delay
    try:
        enqueue_task(
            "celery_workers.tasks.cleanup.schedule_media_cleanup",
            args=[post_id],
            countdown=300,
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

@router.get("/posts/failed")
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
    return [_doc_to_response(d) for d in docs]


@router.post("/posts/{post_id}/retry")
async def retry_failed_post(
    post_id: str,
    current_user: CurrentUser,
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
        {"id": post_id},
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

@router.post("/posts/{post_id}/approve")
async def approve_post(post_id: str, current_user: CurrentUser, db: DB):
    """Approve a post in review status → scheduled."""
    user_id = current_user["user_id"]
    now = datetime.now(timezone.utc)
    result = await db.posts.find_one_and_update(
        {"id": post_id, "status": "pending_approval", "deleted_at": {"$exists": False}},
        {"$set": {"status": PostStatus.SCHEDULED, "approved_by": user_id,
                  "approved_at": now, "updated_at": now},
         "$push": {"status_history": {"status": PostStatus.SCHEDULED,
                                      "timestamp": now, "actor": user_id}}},
        return_document=True,
        projection={"_id": 0},
    )
    if not result:
        raise HTTPException(status_code=404, detail="Post not found or not pending approval")
    return {"approved": True, "post_id": post_id}


@router.post("/posts/{post_id}/reject")
async def reject_post(post_id: str, body: dict, current_user: CurrentUser, db: DB):
    """Reject a post in review — moves to draft with rejection note."""
    user_id = current_user["user_id"]
    now = datetime.now(timezone.utc)
    result = await db.posts.find_one_and_update(
        {"id": post_id, "status": "pending_approval", "deleted_at": {"$exists": False}},
        {"$set": {"status": PostStatus.DRAFT, "rejected_by": user_id,
                  "rejected_at": now, "rejection_reason": body.get("reason", ""),
                  "updated_at": now},
         "$push": {"status_history": {"status": PostStatus.DRAFT,
                                      "timestamp": now, "actor": user_id,
                                      "reason": body.get("reason", "")}}},
        return_document=True,
        projection={"_id": 0},
    )
    if not result:
        raise HTTPException(status_code=404, detail="Post not found or not pending approval")
    return {"rejected": True, "post_id": post_id}


@router.post("/posts/{post_id}/resubmit")
async def resubmit_post(post_id: str, body: dict, current_user: CurrentUser, db: DB):
    """Resubmit a rejected post for approval."""
    user_id = current_user["user_id"]
    now = datetime.now(timezone.utc)
    updates: dict = {"status": "pending_approval", "updated_at": now}
    if body.get("content"):
        updates["content"] = body["content"]
    result = await db.posts.find_one_and_update(
        {"id": post_id, "user_id": user_id, "deleted_at": {"$exists": False}},
        {"$set": updates,
         "$push": {"status_history": {"status": "pending_approval",
                                      "timestamp": now, "actor": user_id}}},
        return_document=True,
        projection={"_id": 0},
    )
    if not result:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"resubmitted": True, "post_id": post_id}


@router.post("/posts/{post_id}/submit-review")
async def submit_post_for_review(post_id: str, body: dict, current_user: CurrentUser, db: DB):
    return await resubmit_post(post_id, body, current_user, db)


# ── Duplicate ─────────────────────────────────────────────────────────────────

@router.post("/posts/{post_id}/duplicate")
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
