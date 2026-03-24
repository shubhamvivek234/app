"""
Bulk Upload API — CSV schedule + template endpoints.
Handles server-side Layer 7 validation (account existence, conflict checks)
after the client completes Layers 1–6 client-side.
"""
import csv
import io
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.deps import CurrentUser, DB

logger = logging.getLogger(__name__)
router = APIRouter(tags=["bulk-upload"])

VALID_PLATFORMS = {"instagram", "youtube", "twitter", "tiktok", "linkedin", "facebook", "bluesky"}
VALID_POST_TYPES = {"text", "image", "video", "carousel", "reel", "story"}
CSV_TEMPLATE_COLUMNS = [
    "content", "platforms", "accounts", "scheduled_time", "timezone",
    "image_urls", "video_url", "title", "tags", "post_type",
]

# ── Pydantic models ───────────────────────────────────────────────────────────

class BulkPost(BaseModel):
    content: str = ""
    platforms: list[str] = []
    accounts: str = "all"          # display name(s) or "all"
    scheduled_time: str | None = None  # ISO string from client
    timezone: str = "UTC"
    image_urls: list[str] = []
    video_url: str | None = None
    title: str | None = None
    tags: list[str] = []
    post_type: str | None = None
    status: str = "scheduled"      # "scheduled" | "draft"


class BulkScheduleRequest(BaseModel):
    posts: list[BulkPost]


class BulkScheduleResponse(BaseModel):
    created: int
    skipped: int
    errors: list[dict]


# ── CSV template ──────────────────────────────────────────────────────────────

@router.get("/bulk/csv-template")
async def download_csv_template():
    """Return a downloadable CSV template file."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_TEMPLATE_COLUMNS)
    writer.writerow([
        "Hello world! First post via CSV",
        "instagram,twitter",
        "all",
        "2025-06-01 10:00",
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


# ── Server-side Layer 7 validation helper ─────────────────────────────────────

async def _layer7_validate(db, user_id: str, workspace_id: str, posts: list[BulkPost]) -> list[dict]:
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
    account_names = {
        (a.get("username") or a.get("display_name") or "").lower(): a
        for a in all_accounts
    }

    # Build a set of scheduled times per account to detect 30-min conflicts
    existing_cursor = db.posts.find(
        {"workspace_id": workspace_id, "status": "scheduled"},
        {"_id": 0, "account_ids": 1, "scheduled_time": 1},
    )
    existing = await existing_cursor.to_list(None)
    scheduled_index: dict[str, list[datetime]] = {}
    for post in existing:
        for acc_id in post.get("account_ids", []):
            st = post.get("scheduled_time")
            if st:
                dt = datetime.fromisoformat(st) if isinstance(st, str) else st
                scheduled_index.setdefault(acc_id, []).append(dt)

    errors = []
    for post in posts:
        post_errors = {}

        # Resolve account names → IDs
        if post.accounts and post.accounts.lower() != "all":
            for name in post.accounts.split(","):
                name = name.strip().lower()
                if name and name not in account_names:
                    post_errors["accounts"] = f"Account '{name}' not found in workspace"
                    break

        # Check 30-min scheduling conflict
        if post.scheduled_time:
            try:
                new_dt = datetime.fromisoformat(post.scheduled_time.replace("Z", "+00:00"))
                window = timedelta(minutes=30)
                acc_ids = (
                    [a["id"] for a in all_accounts]
                    if post.accounts.lower() == "all"
                    else [
                        account_names[n.strip().lower()]["id"]
                        for n in post.accounts.split(",")
                        if n.strip().lower() in account_names
                    ]
                )
                for acc_id in acc_ids:
                    for existing_dt in scheduled_index.get(acc_id, []):
                        if abs((new_dt - existing_dt).total_seconds()) < window.total_seconds():
                            post_errors["scheduled_time"] = (
                                f"Conflict: account already has a post within 30 min of {post.scheduled_time}"
                            )
                            break
                    if "scheduled_time" in post_errors:
                        break
            except ValueError:
                post_errors["scheduled_time"] = "Could not parse scheduled_time for conflict check"

        errors.append(post_errors)

    return errors


# ── Schedule endpoint ─────────────────────────────────────────────────────────

@router.post("/bulk/csv-schedule", response_model=BulkScheduleResponse)
async def bulk_csv_schedule(
    request: BulkScheduleRequest,
    current_user: CurrentUser,
    db: DB,
):
    """
    Server-side Layer 7 validation then batch-insert valid posts.
    Client is responsible for Layers 1–6 before calling this endpoint.
    """
    if not request.posts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No posts provided")

    max_per_request = 500
    if len(request.posts) > max_per_request:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {max_per_request} posts per bulk import",
        )

    user_id = current_user.user_id
    workspace_id = current_user.workspace_id or user_id

    # Layer 7 validation
    layer7_errors = await _layer7_validate(db, user_id, workspace_id, request.posts)

    # Fetch workspace accounts for ID resolution
    accounts_cursor = db.social_accounts.find(
        {"workspace_id": workspace_id, "status": {"$ne": "deleted"}},
        {"_id": 0, "id": 1, "username": 1, "display_name": 1, "platform": 1},
    )
    all_accounts = await accounts_cursor.to_list(None)
    account_name_map = {
        (a.get("username") or a.get("display_name") or "").lower(): a
        for a in all_accounts
    }

    docs_to_insert = []
    skipped = 0
    error_report = []

    for i, (post, l7_err) in enumerate(zip(request.posts, layer7_errors)):
        if l7_err:
            skipped += 1
            error_report.append({"row": i + 1, "errors": l7_err})
            continue

        # Resolve account IDs
        if post.accounts.lower() == "all":
            account_ids = [a["id"] for a in all_accounts]
        else:
            account_ids = [
                account_name_map[n.strip().lower()]["id"]
                for n in post.accounts.split(",")
                if n.strip().lower() in account_name_map
            ]

        # Parse scheduled_time
        scheduled_time = None
        if post.scheduled_time:
            try:
                scheduled_time = datetime.fromisoformat(
                    post.scheduled_time.replace("Z", "+00:00")
                ).isoformat()
            except ValueError:
                scheduled_time = None

        now = datetime.now(timezone.utc).isoformat()
        docs_to_insert.append({
            "post_id": str(uuid.uuid4()),
            "user_id": user_id,
            "workspace_id": workspace_id,
            "content": post.content,
            "platforms": [p.lower().strip() for p in post.platforms],
            "account_ids": account_ids,
            "scheduled_time": scheduled_time,
            "timezone": post.timezone or "UTC",
            "media_urls": post.image_urls,
            "video_url": post.video_url,
            "title": post.title,
            "tags": post.tags,
            "post_type": post.post_type,
            "status": post.status,
            "source": "csv_bulk_import",
            "created_at": now,
            "updated_at": now,
        })

    created = 0
    if docs_to_insert:
        result = await db.posts.insert_many(docs_to_insert, ordered=False)
        created = len(result.inserted_ids)

    logger.info(
        "Bulk CSV import: user=%s created=%d skipped=%d",
        user_id, created, skipped,
    )

    return BulkScheduleResponse(created=created, skipped=skipped, errors=error_report)
