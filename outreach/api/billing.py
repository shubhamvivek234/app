"""Invite-only paid outreach pilot billing.

There is no public checkout or trial. An operator verifies an external invoice
and records a paid entitlement using the private operations command. Customer
endpoints can request access or schedule cancellation, never grant access.
"""
from datetime import datetime, timezone
import re

from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from api.deps import get_current_user, require_permission
from db.mongo import get_db
from outreach.core.paid_access import (
    PILOT_MAX_SENDERS, PRICE_USD_PER_SENDER_MONTH, entitlement_is_active,
)


router = APIRouter(prefix="/billing", tags=["LinkedIn Outreach Billing"])


def _workspace_id(user: dict) -> str:
    return str(user.get("default_workspace_id") or user.get("user_id") or "")


class StartTrialRequest(BaseModel):
    seats: int = Field(default=1, ge=1, le=100)
    interval: str = "monthly"


class UpdateSeatsRequest(BaseModel):
    seats: int = Field(..., ge=1, le=100)


class UpdateBillingEmailRequest(BaseModel):
    billing_email: str


class AccessRequest(BaseModel):
    seats: int = Field(default=1, ge=1, le=PILOT_MAX_SENDERS)
    country_code: str = Field(..., min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")


def calculate_price_per_seat(seats: int, interval: str = "monthly") -> float:
    if not 1 <= seats <= PILOT_MAX_SENDERS or interval != "monthly":
        raise ValueError("Only 1–5 monthly pilot sender seats are offered")
    return float(PRICE_USD_PER_SENDER_MONTH)


@router.get("/plans")
async def get_outreach_plans(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace_id = _workspace_id(current_user)
    entitlement = await db.outreach_entitlements.find_one({"workspace_id": workspace_id})
    request = await db.outreach_access_requests.find_one({"workspace_id": workspace_id})
    public_entitlement = {
        key: entitlement.get(key) for key in (
            "status", "seats", "paid_through", "cancel_at_period_end",
            "price_usd_per_sender_month", "billing_email",
        )
    } if entitlement else {"status": "none", "seats": 0}
    return {
        "price_usd_per_sender_month": PRICE_USD_PER_SENDER_MONTH,
        "currency": "USD", "interval": "monthly", "max_pilot_seats": PILOT_MAX_SENDERS,
        "checkout_available": False, "trial_available": False,
        "activation_mode": "managed_after_verified_payment",
        "subscription": public_entitlement,
        "access_active": entitlement_is_active(entitlement),
        "access_request": {key: request.get(key) for key in ("seats", "country_code", "status")}
        if request else None,
        "billing_email": (entitlement or {}).get("billing_email") or current_user.get("email") or "",
    }


@router.post("/request-access", dependencies=[require_permission("billing:manage")])
async def request_pilot_access(
    req: AccessRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace_id = _workspace_id(current_user)
    now = datetime.now(timezone.utc)
    await db.outreach_access_requests.update_one(
        {"workspace_id": workspace_id},
        {"$set": {"user_id": current_user.get("user_id"), "seats": req.seats,
                  "country_code": req.country_code.upper(), "status": "pending_quote",
                  "updated_at": now},
         "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return {"status": "pending_quote", "message": "Request received. We will confirm country availability and cost before payment."}


@router.post("/billing-email", dependencies=[require_permission("billing:manage")])
async def update_billing_email(
    req: UpdateBillingEmailRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    email = req.billing_email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(status_code=400, detail="A valid billing email is required")
    await db.outreach_entitlements.update_one(
        {"workspace_id": _workspace_id(current_user)},
        {"$set": {"billing_email": email, "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return {"status": "success", "billing_email": email}


@router.post("/start-trial", dependencies=[require_permission("billing:manage")])
async def start_outreach_trial(
    req: StartTrialRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    raise HTTPException(status_code=410, detail="The free trial is retired. Request managed pilot access instead.")


@router.post("/update-seats", dependencies=[require_permission("billing:manage")])
async def update_seats(
    req: UpdateSeatsRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    raise HTTPException(status_code=410, detail="Seat changes require a verified invoice and operator approval.")


@router.post("/cancel", dependencies=[require_permission("billing:manage")])
async def cancel_subscription(
    current_user: dict = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace_id = _workspace_id(current_user)
    entitlement = await db.outreach_entitlements.find_one({"workspace_id": workspace_id})
    if not entitlement_is_active(entitlement):
        raise HTTPException(status_code=409, detail="No active paid outreach period to cancel")
    paid_through = entitlement["paid_through"]
    if isinstance(paid_through, str):
        paid_through = datetime.fromisoformat(paid_through.replace("Z", "+00:00"))
    await db.outreach_entitlements.update_one(
        {"workspace_id": workspace_id, "status": "active", "paid_through": entitlement["paid_through"]},
        {"$set": {"cancel_at_period_end": True, "cancellation_requested_at": datetime.now(timezone.utc)}},
    )
    return {
        "status": "cancellation_scheduled", "paid_through": paid_through.isoformat(),
        "message": "Outreach stays available until the paid period ends. The sender IP remains reserved through its already-paid provider term. Our operator must disable provider auto-renewal separately.",
    }
