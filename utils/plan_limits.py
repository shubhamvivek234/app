"""
Plan Limits & Quota Enforcement.
Enforces social account quotas, post caps, video clipping limits,
and dedicated Twitter / X API rate limits (including URL link-post detection).
"""
import logging
import re
from datetime import datetime, timezone
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)

PLAN_LIMITS: dict[str, dict] = {
    "starter": {
        "label": "Starter",
        "accounts": 6,
        "posts_monthly": 150,
        "twitter_total": 60,
        "twitter_links": 15,
        "twitter_daily": 5,
        "clipping_minutes": 30,
        "ai_text": 100,
        "ai_images": 30,
        "storage_mb": 10240,  # 10 GB
    },
    "pro": {
        "label": "Pro",
        "accounts": 18,
        "posts_monthly": -1,  # Unlimited
        "twitter_total": 180,
        "twitter_links": 40,
        "twitter_daily": 12,
        "clipping_minutes": 120,
        "ai_text": 500,
        "ai_images": 150,
        "storage_mb": 51200,  # 50 GB
    },
    "agency": {
        "label": "Agency",
        "accounts": 50,
        "posts_monthly": -1,  # Unlimited
        "twitter_total": 500,
        "twitter_links": 120,
        "twitter_daily": 30,
        "clipping_minutes": 400,
        "ai_text": 2000,
        "ai_images": 500,
        "storage_mb": 256000,  # 250 GB
    },
}


def has_link(content: str) -> bool:
    """Check if content contains a web URL / link."""
    return bool(URL_PATTERN.search(content or ""))


def get_plan_limits(plan_name: str | None) -> dict:
    """Resolve limits for a given plan (with aliases and default fallback)."""
    norm = (plan_name or "starter").lower().strip()
    if norm in ("creator",):
        norm = "pro"
    elif norm in ("business",):
        norm = "agency"
    elif norm not in PLAN_LIMITS:
        norm = "starter"
    return PLAN_LIMITS[norm]


async def check_twitter_post_limits(
    db,
    user_id: str,
    plan: str | None,
    content: str,
    byok_enabled: bool = False,
) -> None:
    """
    Enforce Twitter/X rate limits and URL link-post quotas.
    If byok_enabled is True, custom Twitter Developer keys are used (no limits applied).
    """
    if byok_enabled:
        return

    limits = get_plan_limits(plan)
    plan_label = limits["label"]
    is_link_post = has_link(content)

    now = datetime.now(timezone.utc)
    start_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    start_of_day = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

    # 1. Check daily throttle (anti-ban safeguard)
    daily_count = await db.posts.count_documents({
        "user_id": user_id,
        "platforms": {"$in": ["twitter", "x"]},
        "status": {"$in": ["scheduled", "published", "publishing"]},
        "created_at": {"$gte": start_of_day},
    })
    if daily_count >= limits["twitter_daily"]:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Daily Twitter/X post limit reached ({daily_count}/{limits['twitter_daily']} posts today) "
                f"on the {plan_label} plan. To avoid platform spam flags, please schedule for tomorrow or upgrade your plan."
            ),
        )

    # 2. Check total monthly Twitter posts
    monthly_total = await db.posts.count_documents({
        "user_id": user_id,
        "platforms": {"$in": ["twitter", "x"]},
        "status": {"$in": ["scheduled", "published", "publishing"]},
        "created_at": {"$gte": start_of_month},
    })
    if monthly_total >= limits["twitter_total"]:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Monthly Twitter/X limit reached ({monthly_total}/{limits['twitter_total']} tweets) on the {plan_label} plan. "
                "Upgrade to Pro or Agency, or connect your own Twitter Developer Keys (BYOK) for unlimited tweets."
            ),
        )

    # 3. Check monthly link-containing tweets
    if is_link_post:
        user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "extra_twitter_links": 1, "twitter_byok_enabled": 1})
        if user and user.get("twitter_byok_enabled"):
            return

        extra_links = (user or {}).get("extra_twitter_links", 0)
        allowed_links = limits["twitter_links"] + extra_links

        link_count = await db.posts.count_documents({
            "user_id": user_id,
            "platforms": {"$in": ["twitter", "x"]},
            "has_link": True,
            "status": {"$in": ["scheduled", "published", "publishing"]},
            "created_at": {"$gte": start_of_month},
        })
        if link_count >= allowed_links:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Monthly Twitter/X link post limit reached ({link_count}/{allowed_links} link tweets) on the {plan_label} plan. "
                    "Due to X API charges on links, purchase a Twitter Link Booster pack ($15 for 50 link posts) or connect your own Twitter Keys (BYOK) to continue."
                ),
            )
