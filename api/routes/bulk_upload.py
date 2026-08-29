"""
Bulk Upload API — CSV schedule, URL validation + template endpoints.
Handles server-side Layer 7 validation (account existence, conflict checks)
after the client completes Layers 1–6 client-side.
"""
import asyncio
import csv
import hashlib
import io
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.deps import CurrentUser, DB, VerifiedUser
from utils.ssrf_guard import assert_safe_url, is_safe_url
from utils.timeslots import DEFAULT_TIMESLOT_CATEGORY, normalize_timeslot_category, resolve_next_timeslot_for_account

logger = logging.getLogger(__name__)
router = APIRouter(tags=["bulk-upload"])

VALID_PLATFORMS = {"instagram", "youtube", "twitter", "tiktok", "linkedin", "facebook", "bluesky", "threads", "pinterest", "discord"}
VALID_POST_TYPES = {"text", "image", "video", "carousel", "reel", "story"}
CSV_TEMPLATE_COLUMNS = [
    "content", "platforms", "accounts", "scheduled_time", "timeslot_category", "timezone",
    "image_urls", "video_url", "title", "tags", "post_type",
]

# ── Pydantic models ───────────────────────────────────────────────────────────

class BulkPost(BaseModel):
    content: str = ""
    platforms: list[str] = []
    accounts: str | list[str] = "all"      # display name(s) or "all"
    scheduled_time: str | None = None      # ISO string or wall-clock date string
    timeslot_category: str | None = DEFAULT_TIMESLOT_CATEGORY
    timezone: str = "UTC"
    image_urls: list[str] = []
    video_url: str | None = None
    title: str | None = None
    tags: list[str] = []
    post_type: str | None = None
    status: str = "scheduled"              # "scheduled" | "draft"
    row: int | None = None


class BulkScheduleRequest(BaseModel):
    posts: list[BulkPost]
    selected_account_ids: list[str] | None = None
    fallback_timezone: str | None = None


class BulkScheduleResponse(BaseModel):
    created: int
    skipped: int
    errors: list[dict]


class ValidateUrlsRequest(BaseModel):
    urls: list[str] = Field(default_factory=list, max_length=100)


class UrlValidationResult(BaseModel):
    url: str
    ok: bool
    status: int | None = None
    error: str | None = None
    content_type: str | None = None


# ── CSV template ──────────────────────────────────────────────────────────────

@router.get("/bulk/csv-template")
async def download_csv_template():
    """Return a downloadable CSV template file."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_TEMPLATE_COLUMNS)
    future = datetime.now(timezone.utc) + timedelta(days=7)
    future_str = future.strftime("%d/%b/%Y 10:00")
    writer.writerow([
        "Hello world! First post via CSV",
        "instagram,twitter",
        "all",
        future_str,
        "Category 1",
        "Asia/Kolkata",
        "",
        "",
        "",
        "social,marketing",
        "text",
    ])
    content = output.getvalue()
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=socialentangler_bulk_template.csv"},
    )


# ── URL Pre-Flight Validation ─────────────────────────────────────────────────

@router.post("/bulk/validate-urls", response_model=list[UrlValidationResult])
async def validate_bulk_urls(
    request: ValidateUrlsRequest,
    current_user: CurrentUser,
):
    """
    Fast pre-flight check for external media URLs in bulk CSV rows.
    Applies SSRF safety checks and performs async HEAD/GET checks.
    """
    if not request.urls:
        return []

    unique_urls = list(dict.fromkeys(u.strip() for u in request.urls if u and u.strip()))
    results: list[UrlValidationResult] = []

    async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
        for url in unique_urls[:100]:
            try:
                assert_safe_url(url)
            except ValueError as exc:
                results.append(UrlValidationResult(url=url, ok=False, error=str(exc)))
                continue

            try:
                # First attempt fast HEAD request
                head_resp = await client.head(url)
                if head_resp.status_code < 400:
                    ct = head_resp.headers.get("content-type", "")
                    results.append(UrlValidationResult(url=url, ok=True, status=head_resp.status_code, content_type=ct))
                    continue
                # If HEAD returned 405 Method Not Allowed, fallback to streaming GET
                if head_resp.status_code in (403, 405):
                    async with client.stream("GET", url) as stream_resp:
                        if stream_resp.status_code < 400:
                            ct = stream_resp.headers.get("content-type", "")
                            results.append(UrlValidationResult(url=url, ok=True, status=stream_resp.status_code, content_type=ct))
                            continue
                results.append(UrlValidationResult(url=url, ok=False, status=head_resp.status_code, error=f"HTTP {head_resp.status_code}"))
            except httpx.TimeoutException:
                results.append(UrlValidationResult(url=url, ok=False, error="URL check timed out after 5 seconds"))
            except Exception as exc:
                results.append(UrlValidationResult(url=url, ok=False, error=f"Failed to connect: {str(exc)}"))

    return results


# ── Server-side Layer 7 validation helper ─────────────────────────────────────

async def _layer7_validate(
    db: DB,
    user_id: str,
    workspace_id: str,
    posts: list[BulkPost],
    selected_account_ids: list[str] | None = None,
    fallback_timezone: str | None = None,
) -> list[dict]:
    """
    Layer 7: verify account names exist and check for scheduling conflicts.
    Returns list of per-post error dicts (empty dict = valid).
    """
    # Fetch all workspace accounts once
    accounts_cursor = db.social_accounts.find(
        {"workspace_id": workspace_id, "status": {"$ne": "deleted"}},
        {"_id": 0, "id": 1, "username": 1, "display_name": 1, "platform": 1},
    )
    all_accounts = await accounts_cursor.to_list(None)
    account_names: dict[str, dict] = {}
    for a in all_accounts:
        if a.get("username"):
            account_names[a["username"].lower()] = a
        if a.get("display_name"):
            account_names[a["display_name"].lower()] = a
        if a.get("id"):
            account_names[a["id"].lower()] = a

    # Build a set of scheduled times per account to detect 30-min conflicts
    existing_cursor = db.posts.find(
        {"workspace_id": workspace_id, "status": "scheduled", "deleted_at": {"$exists": False}},
        {"_id": 0, "account_ids": 1, "scheduled_time": 1},
    )
    existing = await existing_cursor.to_list(None)
    scheduled_index: dict[str, list[datetime]] = {}
    for post in existing:
        for acc_id in post.get("account_ids", []):
            st = post.get("scheduled_time")
            if st:
                dt = datetime.fromisoformat(st.replace("Z", "+00:00")) if isinstance(st, str) else st
                scheduled_index.setdefault(acc_id, []).append(dt)

    reserved_keys: dict[tuple[str, str], set[str]] = {}
    errors = []

    for post in posts:
        post_errors = {}

        # Resolve target account IDs
        acc_ids: list[str] = []
        if isinstance(post.accounts, list) and post.accounts:
            acc_ids = [str(a) for a in post.accounts]
        elif post.accounts and str(post.accounts).lower() != "all":
            for name in str(post.accounts).split(","):
                name = name.strip().lower()
                if name and name in account_names:
                    acc_ids.append(account_names[name]["id"])
                elif name:
                    post_errors["accounts"] = f"Account '{name}' not found in workspace"
                    break
        elif selected_account_ids:
            acc_ids = list(selected_account_ids)
        else:
            acc_ids = [a["id"] for a in all_accounts]

        # Check 30-min scheduling conflict
        if post.scheduled_time:
            try:
                new_dt = datetime.fromisoformat(post.scheduled_time.replace("Z", "+00:00"))
                if new_dt.tzinfo is None:
                    new_dt = new_dt.replace(tzinfo=timezone.utc)
                window = timedelta(minutes=30)
                for acc_id in acc_ids:
                    for existing_dt in scheduled_index.get(acc_id, []):
                        if existing_dt.tzinfo is None:
                            existing_dt = existing_dt.replace(tzinfo=timezone.utc)
                        if abs((new_dt - existing_dt).total_seconds()) < window.total_seconds():
                            post_errors["scheduled_time"] = (
                                f"Conflict: account already has a post within 30 min of {post.scheduled_time}"
                            )
                            break
                    if "scheduled_time" in post_errors:
                        break
                if "scheduled_time" not in post_errors:
                    # Reserve in batch index
                    for acc_id in acc_ids:
                        scheduled_index.setdefault(acc_id, []).append(new_dt)
            except ValueError:
                post_errors["scheduled_time"] = "Could not parse scheduled_time for conflict check"
        elif post.status == "scheduled":
            if len(acc_ids) != 1:
                post_errors["scheduled_time"] = (
                    "Leave scheduled_time blank only when the row targets exactly one account with timeslots configured"
                )
            else:
                try:
                    category = normalize_timeslot_category(post.timeslot_category)
                except ValueError as exc:
                    post_errors["timeslot_category"] = str(exc)
                else:
                    reserved = reserved_keys.setdefault((acc_ids[0], category), set())
                    row_tz = post.timezone or fallback_timezone or "UTC"
                    next_slot, message, normalized_category = await resolve_next_timeslot_for_account(
                        db,
                        workspace_id,
                        acc_ids[0],
                        category,
                        now=datetime.now(timezone.utc),
                        reserved_keys=reserved,
                        timezone_name=row_tz,
                    )
                    if next_slot is None:
                        post_errors["scheduled_time"] = message or "No available timeslot found"
                    else:
                        reserved.add(next_slot.replace(second=0, microsecond=0, tzinfo=timezone.utc).isoformat())
                        post.scheduled_time = next_slot.isoformat()
                        post.timeslot_category = normalized_category
                        scheduled_index.setdefault(acc_ids[0], []).append(next_slot)

        errors.append(post_errors)

    return errors


# ── Schedule endpoints ────────────────────────────────────────────────────────

@router.post("/bulk/csv-schedule", response_model=BulkScheduleResponse)
@router.post("/bulk/csv-upload", response_model=BulkScheduleResponse)
async def bulk_csv_schedule(
    request: BulkScheduleRequest,
    current_user: VerifiedUser,
    db: DB,
):
    """
    Server-side Layer 7 validation then batch-insert valid posts with full document schema.
    """
    if not request.posts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No posts provided")

    max_per_request = 500
    if len(request.posts) > max_per_request:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {max_per_request} posts per bulk import",
        )

    user_id = current_user["user_id"]
    workspace_id = current_user.get("default_workspace_id") or user_id

    # Layer 7 validation
    layer7_errors = await _layer7_validate(
        db,
        user_id,
        workspace_id,
        request.posts,
        selected_account_ids=request.selected_account_ids,
        fallback_timezone=request.fallback_timezone,
    )

    # Fetch workspace accounts for ID resolution
    accounts_cursor = db.social_accounts.find(
        {"workspace_id": workspace_id, "status": {"$ne": "deleted"}},
        {"_id": 0, "id": 1, "username": 1, "display_name": 1, "platform": 1},
    )
    all_accounts = await accounts_cursor.to_list(None)
    account_name_map: dict[str, dict] = {}
    for a in all_accounts:
        if a.get("username"):
            account_name_map[a["username"].lower()] = a
        if a.get("display_name"):
            account_name_map[a["display_name"].lower()] = a
        if a.get("id"):
            account_name_map[a["id"].lower()] = a
    account_id_map = {a["id"]: a for a in all_accounts}

    docs_to_insert = []
    skipped = 0
    error_report = []

    now = datetime.now(timezone.utc)

    for i, (post, l7_err) in enumerate(zip(request.posts, layer7_errors)):
        row_num = post.row if post.row is not None else (i + 1)
        if l7_err:
            skipped += 1
            error_report.append({"row": row_num, "errors": l7_err})
            continue

        # Resolve account IDs
        account_ids: list[str] = []
        if isinstance(post.accounts, list) and post.accounts:
            account_ids = [str(a) for a in post.accounts if str(a) in account_id_map]
        elif post.accounts and str(post.accounts).lower() != "all":
            account_ids = [
                account_name_map[n.strip().lower()]["id"]
                for n in str(post.accounts).split(",")
                if n.strip().lower() in account_name_map
            ]
        elif request.selected_account_ids:
            account_ids = [a_id for a_id in request.selected_account_ids if a_id in account_id_map]
        else:
            account_ids = [a["id"] for a in all_accounts]

        # Parse scheduled_time
        scheduled_time_dt: datetime | None = None
        if post.scheduled_time:
            try:
                scheduled_time_dt = datetime.fromisoformat(post.scheduled_time.replace("Z", "+00:00"))
                if scheduled_time_dt.tzinfo is None:
                    scheduled_time_dt = scheduled_time_dt.replace(tzinfo=timezone.utc)
            except ValueError:
                scheduled_time_dt = None

        platforms = [p.lower().strip() for p in post.platforms if p.strip()]
        media_urls = list(post.image_urls or [])
        if post.video_url and post.video_url.strip() and post.video_url.strip() not in media_urls:
            media_urls.append(post.video_url.strip())

        primary_media_url = media_urls[0] if media_urls else None

        # Infer post type if omitted
        inferred_post_type = post.post_type
        if not inferred_post_type:
            if post.video_url:
                inferred_post_type = "video"
            elif len(media_urls) > 1:
                inferred_post_type = "carousel"
            elif len(media_urls) == 1:
                inferred_post_type = "image"
            else:
                inferred_post_type = "text"

        post_id = str(uuid.uuid4())
        post_status = post.status or "scheduled"

        docs_to_insert.append({
            "id": post_id,
            "post_id": post_id,
            "user_id": user_id,
            "workspace_id": workspace_id,
            "content": post.content or "",
            "title": post.title,
            "platforms": platforms,
            "account_ids": account_ids,
            "social_account_ids": account_ids,
            "media_urls": media_urls,
            "media_url": primary_media_url,
            "video_url": post.video_url,
            "thumbnail_urls": [],
            "post_type": inferred_post_type,
            "timezone": post.timezone or request.fallback_timezone or "UTC",
            "timeslot_category": post.timeslot_category if post_status == "scheduled" else None,
            "scheduled_time": scheduled_time_dt,
            "tags": post.tags or [],
            "status": post_status,
            "platform_results": {p: {"status": "pending"} for p in platforms},
            "account_results": {
                acc_id: {
                    "status": "pending",
                    "platform": account_id_map.get(acc_id, {}).get("platform", ""),
                    "account_id": acc_id,
                }
                for acc_id in account_ids
            },
            "platform_post_urls": {},
            "status_history": [
                {"status": post_status, "timestamp": now, "actor": user_id}
            ],
            "version": 1,
            "content_hash": hashlib.sha256((post.content or "").encode()).hexdigest(),
            "source": "csv_bulk_import",
            "created_at": now,
            "updated_at": now,
        })

    created = 0
    if docs_to_insert:
        result = await db.posts.insert_many(docs_to_insert, ordered=False)
        created = len(result.inserted_ids)

    logger.info(
        f"Bulk CSV import: user={user_id} created={int(created)} skipped={int(skipped)}"
    )

    return BulkScheduleResponse(created=int(created), skipped=int(skipped), errors=error_report)
