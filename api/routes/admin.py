"""
Phase 9 — Admin Panel API Routes.
Restricted to users with role="admin" or role="owner" in the users collection.
All actions are logged to the admin_audit_log collection.
"""
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from api.deps import CurrentUser, DB, CacheRedis, QueueRedis
from api.main import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

_ADMIN_ROLES = {"admin", "owner"}


# ── Auth guard ───────────────────────────────────────────────────────────────

def _require_admin(current_user: dict) -> None:
    """Raise 403 if the current user is not an admin or owner."""
    role = current_user.get("role", "")
    if role not in _ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or owner role required",
        )


async def _audit_log(db, admin_user_id: str, action: str, target: str, details: dict | None = None) -> None:
    """Write an entry to the admin audit trail."""
    await db.admin_audit_log.insert_one({
        "admin_user_id": admin_user_id,
        "action": action,
        "target": target,
        "details": details or {},
        "timestamp": datetime.now(timezone.utc),
    })


# ── Response models ──────────────────────────────────────────────────────────

class AdminUserSummary(BaseModel):
    user_id: str
    email: str
    display_name: str | None = None
    plan: str = "starter"
    subscription_status: str = "free"
    role: str = ""
    created_at: datetime
    is_suspended: bool = False


class AdminUserListResponse(BaseModel):
    data: list[AdminUserSummary]
    total: int
    page: int
    limit: int


class AdminUserDetail(BaseModel):
    user_id: str
    email: str
    display_name: str | None = None
    avatar_url: str | None = None
    plan: str = "starter"
    subscription_status: str = "free"
    role: str = ""
    created_at: datetime
    is_suspended: bool = False
    suspended_at: datetime | None = None
    suspend_reason: str | None = None
    accounts_count: int = 0
    posts_count: int = 0
    stripe_customer_id: str | None = None
    razorpay_customer_id: str | None = None
    workspace_ids: list[str] = Field(default_factory=list)


class SuspendRequest(BaseModel):
    suspend: bool = True
    reason: str = ""


class SuspendResponse(BaseModel):
    user_id: str
    is_suspended: bool
    suspended_at: datetime | None = None
    reason: str = ""


class AdminPostSummary(BaseModel):
    id: str
    user_id: str
    workspace_id: str | None = None
    platforms: list[str] = Field(default_factory=list)
    status: str
    created_at: datetime
    scheduled_time: datetime | None = None


class AdminPostListResponse(BaseModel):
    data: list[AdminPostSummary]
    total: int
    page: int
    limit: int


class DLQItem(BaseModel):
    task_id: str
    post_id: str | None = None
    user_id: str | None = None
    reason: str = ""
    failed_at: datetime | None = None
    retry_count: int = 0
    payload: dict = Field(default_factory=dict)


class DLQListResponse(BaseModel):
    data: list[DLQItem]
    total: int


class DLQRetryResponse(BaseModel):
    task_id: str
    retried: bool = True


class SystemMetrics(BaseModel):
    active_users_24h: int = 0
    total_users: int = 0
    posts_today: int = 0
    posts_published_today: int = 0
    posts_failed_today: int = 0
    success_rate_percent: float = 0.0
    queue_depth: int = 0
    dlq_size: int = 0


class BillingSummary(BaseModel):
    total_paying_users: int = 0
    mrr_estimate_cents: int = 0
    churn_last_30d: int = 0
    plan_distribution: dict[str, int] = Field(default_factory=dict)
    active_subscriptions: int = 0
    grace_subscriptions: int = 0
    cancelled_subscriptions: int = 0


# ── GET /admin/users ─────────────────────────────────────────────────────────

@router.get("/users", response_model=AdminUserListResponse)
@limiter.limit("60/minute")
async def list_users(
    request: Request,
    current_user: CurrentUser,
    db: DB,
    status_filter: Annotated[str | None, Query(alias="status", max_length=50)] = None,
    plan: Annotated[str | None, Query(max_length=20)] = None,
    created_after: Annotated[datetime | None, Query()] = None,
    created_before: Annotated[datetime | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminUserListResponse:
    _require_admin(current_user)

    query: dict = {}
    if status_filter:
        query["subscription_status"] = status_filter
    if plan:
        query["plan"] = plan
    if created_after or created_before:
        date_filter: dict = {}
        if created_after:
            date_filter["$gte"] = created_after
        if created_before:
            date_filter["$lte"] = created_before
        query["created_at"] = date_filter

    total = await db.users.count_documents(query)
    skip = (page - 1) * limit
    cursor = db.users.find(
        query,
        {"_id": 0, "user_id": 1, "email": 1, "display_name": 1, "plan": 1,
         "subscription_status": 1, "role": 1, "created_at": 1,
         "is_suspended": 1},
    ).sort("created_at", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)

    await _audit_log(db, current_user["user_id"], "list_users", "users", {"page": page})

    return AdminUserListResponse(
        data=[AdminUserSummary(**d) for d in docs],
        total=total,
        page=page,
        limit=limit,
    )


# ── GET /admin/users/{user_id} ───────────────────────────────────────────────

@router.get("/users/{user_id}", response_model=AdminUserDetail)
@limiter.limit("60/minute")
async def get_user_detail(
    request: Request,
    user_id: str,
    current_user: CurrentUser,
    db: DB,
) -> AdminUserDetail:
    _require_admin(current_user)

    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    accounts_count = await db.social_accounts.count_documents(
        {"user_id": user_id, "is_active": True}
    )
    posts_count = await db.posts.count_documents(
        {"user_id": user_id, "deleted_at": {"$exists": False}}
    )

    await _audit_log(db, current_user["user_id"], "view_user", user_id)

    return AdminUserDetail(
        user_id=user["user_id"],
        email=user.get("email", ""),
        display_name=user.get("display_name"),
        avatar_url=user.get("avatar_url"),
        plan=user.get("plan", "starter"),
        subscription_status=user.get("subscription_status", "free"),
        role=user.get("role", ""),
        created_at=user["created_at"],
        is_suspended=user.get("is_suspended", False),
        suspended_at=user.get("suspended_at"),
        suspend_reason=user.get("suspend_reason"),
        accounts_count=accounts_count,
        posts_count=posts_count,
        stripe_customer_id=user.get("stripe_customer_id"),
        razorpay_customer_id=user.get("razorpay_customer_id"),
        workspace_ids=user.get("workspace_ids", []),
    )


# ── PATCH /admin/users/{user_id}/suspend ─────────────────────────────────────

@router.patch("/users/{user_id}/suspend", response_model=SuspendResponse)
@limiter.limit("30/minute")
async def suspend_user(
    request: Request,
    user_id: str,
    body: SuspendRequest,
    current_user: CurrentUser,
    db: DB,
) -> SuspendResponse:
    _require_admin(current_user)

    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "role": 1})
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Prevent suspending other admins/owners unless you are owner
    target_role = user.get("role", "")
    if target_role in _ADMIN_ROLES and current_user.get("role") != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners can suspend admin users",
        )

    now = datetime.now(timezone.utc)

    if body.suspend:
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "is_suspended": True,
                "suspended_at": now,
                "suspend_reason": body.reason,
                "updated_at": now,
            }},
        )
        logger.info("User suspended: %s by admin=%s reason=%s", user_id, current_user["user_id"], body.reason)
    else:
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "is_suspended": False,
                "suspended_at": None,
                "suspend_reason": None,
                "updated_at": now,
            }},
        )
        logger.info("User unsuspended: %s by admin=%s", user_id, current_user["user_id"])

    await _audit_log(
        db, current_user["user_id"],
        "suspend_user" if body.suspend else "unsuspend_user",
        user_id,
        {"reason": body.reason},
    )

    return SuspendResponse(
        user_id=user_id,
        is_suspended=body.suspend,
        suspended_at=now if body.suspend else None,
        reason=body.reason if body.suspend else "",
    )


# ── GET /admin/posts ─────────────────────────────────────────────────────────

@router.get("/posts", response_model=AdminPostListResponse)
@limiter.limit("60/minute")
async def list_all_posts(
    request: Request,
    current_user: CurrentUser,
    db: DB,
    status_filter: Annotated[str | None, Query(alias="status", max_length=50)] = None,
    platform: Annotated[str | None, Query(max_length=30)] = None,
    created_after: Annotated[datetime | None, Query()] = None,
    created_before: Annotated[datetime | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminPostListResponse:
    _require_admin(current_user)

    query: dict = {"deleted_at": {"$exists": False}}
    if status_filter:
        query["status"] = status_filter
    if platform:
        query["platforms"] = platform
    if created_after or created_before:
        date_filter: dict = {}
        if created_after:
            date_filter["$gte"] = created_after
        if created_before:
            date_filter["$lte"] = created_before
        query["created_at"] = date_filter

    total = await db.posts.count_documents(query)
    skip = (page - 1) * limit
    cursor = db.posts.find(
        query,
        {"_id": 0, "id": 1, "user_id": 1, "workspace_id": 1, "platforms": 1,
         "status": 1, "created_at": 1, "scheduled_time": 1},
    ).sort("created_at", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)

    await _audit_log(db, current_user["user_id"], "list_posts", "posts", {"page": page})

    return AdminPostListResponse(
        data=[AdminPostSummary(**d) for d in docs],
        total=total,
        page=page,
        limit=limit,
    )


# ── GET /admin/dlq ───────────────────────────────────────────────────────────

@router.get("/dlq", response_model=DLQListResponse)
@limiter.limit("60/minute")
async def list_dlq(
    request: Request,
    current_user: CurrentUser,
    db: DB,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> DLQListResponse:
    _require_admin(current_user)

    total = await db.dead_letter_queue.count_documents({})
    skip = (page - 1) * limit
    cursor = db.dead_letter_queue.find(
        {},
        {"_id": 0},
    ).sort("failed_at", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)

    await _audit_log(db, current_user["user_id"], "view_dlq", "dlq", {"page": page})

    return DLQListResponse(
        data=[DLQItem(**d) for d in docs],
        total=total,
    )


# ── POST /admin/dlq/{task_id}/retry ──────────────────────────────────────────

@router.post("/dlq/{task_id}/retry", response_model=DLQRetryResponse)
@limiter.limit("30/minute")
async def retry_dlq_item(
    request: Request,
    task_id: str,
    current_user: CurrentUser,
    db: DB,
    queue_redis: QueueRedis,
) -> DLQRetryResponse:
    _require_admin(current_user)

    dlq_item = await db.dead_letter_queue.find_one({"task_id": task_id})
    if dlq_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DLQ item not found")

    now = datetime.now(timezone.utc)

    # Re-enqueue the task via Celery
    payload = dlq_item.get("payload", {})
    post_id = dlq_item.get("post_id")

    try:
        from celery_workers.celery_app import celery_app
        task_name = payload.get("task_name", "celery_workers.tasks.publish.publish_post")
        task_args = payload.get("args", [post_id] if post_id else [])
        celery_app.send_task(task_name, args=task_args)
    except Exception as exc:
        logger.error("Failed to retry DLQ item %s: %s", task_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to re-enqueue task: {exc}",
        )

    # Update the DLQ record
    await db.dead_letter_queue.update_one(
        {"task_id": task_id},
        {"$set": {"retried_at": now, "retried_by": current_user["user_id"]},
         "$inc": {"retry_count": 1}},
    )

    # Update the post status if applicable
    if post_id:
        await db.posts.update_one(
            {"id": post_id},
            {"$set": {"status": "queued", "updated_at": now, "dlq_reason": None}},
        )

    await _audit_log(
        db, current_user["user_id"], "retry_dlq", task_id,
        {"post_id": post_id},
    )

    logger.info("DLQ item retried: %s by admin=%s", task_id, current_user["user_id"])
    return DLQRetryResponse(task_id=task_id, retried=True)


# ── GET /admin/metrics ───────────────────────────────────────────────────────

@router.get("/metrics", response_model=SystemMetrics)
@limiter.limit("30/minute")
async def get_system_metrics(
    request: Request,
    current_user: CurrentUser,
    db: DB,
    queue_redis: QueueRedis,
) -> SystemMetrics:
    _require_admin(current_user)

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = now.replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta
    day_ago = now - timedelta(hours=24)

    # Active users in last 24h (users who created/updated posts)
    active_users_pipeline = [
        {"$match": {"updated_at": {"$gte": day_ago}}},
        {"$group": {"_id": "$user_id"}},
        {"$count": "count"},
    ]
    active_result = await db.posts.aggregate(active_users_pipeline).to_list(length=1)
    active_users_24h = active_result[0]["count"] if active_result else 0

    total_users = await db.users.count_documents({})

    posts_today = await db.posts.count_documents(
        {"created_at": {"$gte": today_start}, "deleted_at": {"$exists": False}}
    )
    posts_published_today = await db.posts.count_documents(
        {"status": "published", "updated_at": {"$gte": today_start}}
    )
    posts_failed_today = await db.posts.count_documents(
        {"status": "failed", "updated_at": {"$gte": today_start}}
    )

    total_attempted = posts_published_today + posts_failed_today
    success_rate = (
        round((posts_published_today / total_attempted) * 100, 1)
        if total_attempted > 0
        else 0.0
    )

    queue_depth = await queue_redis.llen("media_processing") or 0
    dlq_size = await db.dead_letter_queue.count_documents({})

    await _audit_log(db, current_user["user_id"], "view_metrics", "system")

    return SystemMetrics(
        active_users_24h=active_users_24h,
        total_users=total_users,
        posts_today=posts_today,
        posts_published_today=posts_published_today,
        posts_failed_today=posts_failed_today,
        success_rate_percent=success_rate,
        queue_depth=queue_depth,
        dlq_size=dlq_size,
    )


# ── GET /admin/billing ───────────────────────────────────────────────────────

@router.get("/billing", response_model=BillingSummary)
@limiter.limit("30/minute")
async def get_billing_summary(
    request: Request,
    current_user: CurrentUser,
    db: DB,
) -> BillingSummary:
    _require_admin(current_user)

    # Plan distribution
    plan_pipeline = [
        {"$group": {"_id": "$plan", "count": {"$sum": 1}}},
    ]
    plan_results = await db.users.aggregate(plan_pipeline).to_list(length=10)
    plan_distribution = {r["_id"]: r["count"] for r in plan_results if r["_id"]}

    # Subscription status counts
    active_subs = await db.users.count_documents({"subscription_status": "active"})
    grace_subs = await db.users.count_documents({"subscription_status": "grace"})
    cancelled_subs = await db.users.count_documents({"subscription_status": "cancelled"})

    total_paying = active_subs + grace_subs

    # MRR estimate (price in cents): starter=0, pro=2900, agency=9900
    plan_prices = {"starter": 0, "pro": 2900, "agency": 9900}
    mrr = 0
    for plan_name, count in plan_distribution.items():
        if plan_name in plan_prices:
            # Only count active/grace subscribers
            paying_in_plan = await db.users.count_documents({
                "plan": plan_name,
                "subscription_status": {"$in": ["active", "grace"]},
            })
            mrr += plan_prices[plan_name] * paying_in_plan

    # Churn: users who cancelled in the last 30 days
    from datetime import timedelta
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    churn_count = await db.users.count_documents({
        "subscription_status": "cancelled",
        "updated_at": {"$gte": thirty_days_ago},
    })

    await _audit_log(db, current_user["user_id"], "view_billing", "billing")

    return BillingSummary(
        total_paying_users=total_paying,
        mrr_estimate_cents=mrr,
        churn_last_30d=churn_count,
        plan_distribution=plan_distribution,
        active_subscriptions=active_subs,
        grace_subscriptions=grace_subs,
        cancelled_subscriptions=cancelled_subs,
    )
