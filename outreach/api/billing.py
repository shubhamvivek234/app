"""
Phase 8: Decoupled Outbound Billing, Stripe Rate Cards & JIT Proxy Lifecycle Orchestrator.
Matches Prosp rate cards (1-5, 6-30, >30 accounts; Annual, Quarterly, Monthly),
4-day free trials, and enforces Zero-Cost-When-Idle proxy teardown upon subscription cancellation.
"""
import logging
from typing import Any
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.deps import get_current_user
from db.mongo import get_db
from outreach.core.proxy_manager import JITProxyManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["LinkedIn Outreach Billing"])

RATE_CARDS = [
    {
        "tier": "1-5",
        "label": "1–5 accounts",
        "min_seats": 1,
        "max_seats": 5,
        "annual": 61.99,
        "quarterly": 69.99,
        "monthly": 79.99,
        "savings_annual": "save 23% • $240.79/yr back",
        "savings_quarterly": "save 13% • $133.77/yr back",
    },
    {
        "tier": "6-30",
        "label": "6–30 accounts",
        "min_seats": 6,
        "max_seats": 30,
        "annual": 45.99,
        "quarterly": 52.99,
        "monthly": 59.99,
        "savings_annual": "save 23% • $168.00/yr back",
        "savings_quarterly": "save 12% • $84.00/yr back",
    },
    {
        "tier": "30+",
        "label": "Over 30 accounts",
        "min_seats": 31,
        "max_seats": 1000,
        "annual": 30.99,
        "quarterly": 34.99,
        "monthly": 39.99,
        "savings_annual": "save 23% • $108.00/yr back",
        "savings_quarterly": "save 13% • $60.00/yr back",
    },
]

FEATURES_INCLUDED = [
    "Unlimited campaigns, contacts, and messages",
    "Every team member, free",
    "Voice cloning",
    "Unlimited LinkedIn accounts, each with a free proxy",
    "Unified inbox across every account",
    "Templates, analytics, API and webhooks",
]


class StartTrialRequest(BaseModel):
    seats: int = Field(default=1, ge=1, le=100)
    interval: str = Field(default="monthly", description="'annual', 'quarterly', or 'monthly'")


class UpdateSeatsRequest(BaseModel):
    seats: int = Field(..., ge=1, le=100)


def calculate_price_per_seat(seats: int, interval: str) -> float:
    selected_tier = RATE_CARDS[0]
    for tier in RATE_CARDS:
        if tier["min_seats"] <= seats <= tier["max_seats"]:
            selected_tier = tier
            break

    interval_key = interval.lower()
    if interval_key not in ("annual", "quarterly", "monthly"):
        interval_key = "monthly"

    return float(selected_tier[interval_key])


@router.get("/plans")
async def get_outreach_plans(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Returns rate cards, included features, and active trial/subscription status.
    """
    user_id = current_user.get("user_id")
    subscription = await db.outreach_subscriptions.find_one({"workspace_id": user_id})

    now = datetime.now(timezone.utc)
    trial_active = False
    trial_days_remaining = 0

    if subscription and subscription.get("trial_ends_at"):
        trial_end = subscription["trial_ends_at"]
        if isinstance(trial_end, str):
            trial_end = datetime.fromisoformat(trial_end)
        if trial_end.tzinfo is None:
            trial_end = trial_end.replace(tzinfo=timezone.utc)
        if trial_end > now:
            trial_active = True
            trial_days_remaining = max(1, (trial_end - now).days)

    return {
        "rate_cards": RATE_CARDS,
        "features_included": FEATURES_INCLUDED,
        "subscription": subscription or {
            "status": "none",
            "seats": 1,
            "interval": "monthly",
            "trial_active": False,
        },
        "trial_active": trial_active,
        "trial_days_remaining": trial_days_remaining,
    }


@router.post("/start-trial")
async def start_outreach_trial(
    req: StartTrialRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Activates the 4-day free trial matching Part 3, Image 4.
    """
    user_id = current_user.get("user_id")
    price_per_seat = calculate_price_per_seat(req.seats, req.interval)
    trial_end = datetime.now(timezone.utc) + timedelta(days=4)

    sub_doc = {
        "workspace_id": user_id,
        "seats": req.seats,
        "interval": req.interval.lower(),
        "price_per_seat": price_per_seat,
        "status": "trialing",
        "trial_started_at": datetime.now(timezone.utc),
        "trial_ends_at": trial_end,
        "created_at": datetime.now(timezone.utc),
    }

    await db.outreach_subscriptions.update_one(
        {"workspace_id": user_id},
        {"$set": sub_doc},
        upsert=True,
    )

    return {
        "status": "trial_activated",
        "seats": req.seats,
        "interval": req.interval,
        "price_per_seat": price_per_seat,
        "trial_ends_at": trial_end.isoformat(),
        "trial_days_remaining": 4,
    }


@router.post("/update-seats")
async def update_seats(
    req: UpdateSeatsRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Dynamically adjusts seat count and recalculates tier price.
    """
    user_id = current_user.get("user_id")
    sub = await db.outreach_subscriptions.find_one({"workspace_id": user_id})
    interval = sub.get("interval", "monthly") if sub else "monthly"

    new_price = calculate_price_per_seat(req.seats, interval)
    await db.outreach_subscriptions.update_one(
        {"workspace_id": user_id},
        {"$set": {"seats": req.seats, "price_per_seat": new_price}},
        upsert=True,
    )

    return {"status": "success", "seats": req.seats, "price_per_seat": new_price}


@router.post("/cancel")
async def cancel_subscription(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Cancels subscription and executes JIT Zero-Cost Proxy Teardown across all connected senders.
    """
    user_id = current_user.get("user_id")

    # Update subscription
    await db.outreach_subscriptions.update_one(
        {"workspace_id": user_id},
        {"$set": {"status": "canceled", "canceled_at": datetime.now(timezone.utc)}},
    )

    # Teardown residential proxies immediately (Zero Cost When Idle)
    accounts = await db.outreach_accounts.find({"workspace_id": user_id}).to_list(100)
    released_proxies = 0

    proxy_manager = JITProxyManager()
    for acc in accounts:
        proxy_config = acc.get("proxy_config")
        if proxy_config and proxy_config.get("proxy_id"):
            await proxy_manager.release_proxy(proxy_config["proxy_id"])
            await db.outreach_accounts.update_one(
                {"id": acc["id"]},
                {"$unset": {"proxy_config": ""}},
            )
            released_proxies += 1

    return {
        "status": "canceled",
        "released_proxies_count": released_proxies,
        "message": "Subscription canceled. Proxies released to prevent idle infrastructure costs.",
    }
