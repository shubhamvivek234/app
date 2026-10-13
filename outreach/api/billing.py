"""Invite-only paid outreach pilot billing.

There is no public checkout or trial. An operator verifies an external invoice
and records a paid entitlement using the private operations command. Customer
endpoints can request access or schedule cancellation, never grant access.
"""
from datetime import datetime, timezone
import re

from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import PyMongoError
from outreach.core.workspace_scope import workspace_scope
from pydantic import BaseModel, Field

from db.mongo import get_db
from outreach.api.dependencies import get_outreach_user, require_outreach_permission
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
    current_user: dict = Depends(get_outreach_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace_id = _workspace_id(current_user)
    entitlement = await db.outreach_entitlements.find_one(workspace_scope(workspace_id))
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


@router.post("/request-access")
async def request_pilot_access(
    req: AccessRequest,
    current_user: dict = require_outreach_permission('billing:manage'),
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


@router.post("/billing-email")
async def update_billing_email(
    req: UpdateBillingEmailRequest,
    current_user: dict = require_outreach_permission('billing:manage'),
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


@router.post("/start-trial")
async def start_outreach_trial(
    req: StartTrialRequest,
    current_user: dict = require_outreach_permission('billing:manage'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    raise HTTPException(status_code=410, detail="The free trial is retired. Request managed pilot access instead.")


@router.post("/update-seats")
async def update_seats(
    req: UpdateSeatsRequest,
    current_user: dict = require_outreach_permission('billing:manage'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    raise HTTPException(status_code=410, detail="Seat changes require a verified invoice and operator approval.")


@router.post("/cancel")
async def cancel_subscription(
    current_user: dict = require_outreach_permission('billing:manage'),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    workspace_id = _workspace_id(current_user)
    entitlement = await db.outreach_entitlements.find_one(workspace_scope(workspace_id))
    if not entitlement_is_active(entitlement):
        raise HTTPException(status_code=409, detail="No active paid outreach period to cancel")
    paid_through = entitlement["paid_through"]
    if isinstance(paid_through, str):
        paid_through = datetime.fromisoformat(paid_through.replace("Z", "+00:00"))
    # Bind the decision to the captured invoice/term, including legacy absence.
    fields = ('_id', 'status', 'paid_through', 'last_invoice_id', 'seats', 'payment_source', 'is_revoked')
    basis = {field: entitlement[field] if field in entitlement else {'$exists': False} for field in fields}
    prior = {field: entitlement[field] if field in entitlement else {'$exists': False}
             for field in ('cancel_at_period_end', 'cancellation_requested_at')}
    requested_at = entitlement.get('cancellation_requested_at') if entitlement.get('cancel_at_period_end') is True else None
    try:
        result = await db.outreach_entitlements.update_one(
            {**workspace_scope(workspace_id), **basis, **prior},
            {'$set': {'cancel_at_period_end': True,
                      'cancellation_requested_at': requested_at or datetime.now(timezone.utc)}},
        )
        if result.matched_count != 1:
            current = await db.outreach_entitlements.find_one(workspace_scope(workspace_id))
            same_term = current and all((field in current) == (field in entitlement)
                                       and current.get(field) == entitlement.get(field) for field in fields)
            if not (same_term and entitlement_is_active(current) and current.get('cancel_at_period_end') is True):
                raise HTTPException(status_code=409, detail='Paid outreach period changed. Reload billing before cancelling.')
    except PyMongoError:
        raise HTTPException(status_code=503, detail='Could not confirm cancellation. Reload billing before retrying.') from None
    return {
        "status": "cancellation_scheduled", "paid_through": paid_through.isoformat(),
        "message": "Outreach stays available until the paid period ends. The sender IP remains reserved through its already-paid provider term. Our operator must disable provider auto-renewal separately.",
    }
