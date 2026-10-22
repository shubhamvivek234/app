"""Invite-only paid outreach pilot billing.

There is no public checkout or trial. An operator verifies an external invoice
and records a paid entitlement using the private operations command. Customer
endpoints can request access or schedule cancellation, never grant access.
"""
from datetime import datetime, timedelta, timezone
import logging
import os
import re

from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import PyMongoError
from outreach.core.workspace_scope import workspace_scope
from pydantic import BaseModel, Field

from db.mongo import get_db
from outreach.api.dependencies import get_outreach_user, require_outreach_permission
from outreach.core.paid_access import (
    PILOT_MAX_SENDERS, PRICE_USD_PER_SENDER_MONTH, _utc, entitlement_is_active,
)
from outreach.core.voice_policy import VOICE_POLICY


logger = logging.getLogger(__name__)
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
    except PyMongoError as exc:
        logger.warning("Billing cancellation confirmation failed for workspace=%s (%s)", workspace_id, type(exc).__name__)
        raise HTTPException(status_code=503, detail='Could not confirm cancellation. Reload billing before retrying.') from None
    logger.info("Outreach subscription cancellation scheduled for workspace=%s", workspace_id)
    return {
        "status": "cancellation_scheduled", "paid_through": paid_through.isoformat(),
        "message": "Outreach stays available until the paid period ends. The sender IP remains reserved through its already-paid provider term. Our operator must disable provider auto-renewal separately.",
    }


def _configured_operator_emails() -> set[str]:
    raw = ",".join(
        filter(
            None,
            (
                os.getenv("OUTREACH_OPERATOR_EMAILS", ""),
                os.getenv("ADMIN_EMAILS", ""),
            ),
        )
    )
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _is_platform_operator(user: dict) -> bool:
    if not isinstance(user, dict):
        return False
    role = str(user.get("role") or "").strip().lower()
    if role in {"admin", "owner", "superadmin"} or user.get("is_superadmin") is True:
        return True
    email = str(user.get("email") or "").strip().lower()
    if email and email in _configured_operator_emails():
        return True
    return False


async def _safe_to_list(collection, query: dict, limit: int = 200) -> list[dict]:
    if collection is None or not hasattr(collection, "find"):
        return []
    try:
        cursor = collection.find(query)
        if hasattr(cursor, "limit"):
            cursor = cursor.limit(limit)
        if hasattr(cursor, "to_list"):
            rows = await cursor.to_list(length=limit)
            return [r for r in (rows or []) if isinstance(r, dict)]
    except Exception as exc:
        logger.debug("Subscription monitor query skipped (%s)", type(exc).__name__)
    return []


def _summarize_workspace_subscription(
    ws_id: str,
    *,
    entitlement: dict | None,
    access_req: dict | None,
    accounts_list: list[dict],
    active_campaigns_count: int,
    voice_prep_budget: dict | None,
    voices_count: int,
    now: datetime,
    workspace_name: str = "",
    owner_email: str = "",
    owner_name: str = "",
    last_active_at: str | None = None,
) -> dict:
    today_iso = now.date().isoformat()
    is_active = entitlement_is_active(entitlement, now)
    paid_through_dt = _utc((entitlement or {}).get("paid_through"))
    paid_through_iso = paid_through_dt.isoformat() if paid_through_dt else None

    days_remaining: int | None = None
    hours_remaining: float | None = None
    if paid_through_dt is not None:
        delta_seconds = (paid_through_dt - now).total_seconds()
        if delta_seconds > 0:
            days_remaining = int((delta_seconds + 86399) // 86400)
            hours_remaining = round(delta_seconds / 3600.0, 1)
        else:
            days_remaining = 0
            hours_remaining = 0.0

    cancel_at_period_end = bool((entitlement or {}).get("cancel_at_period_end"))
    seats_granted = int((entitlement or {}).get("seats") or 0) if is_active else 0
    requested_seats = int((access_req or {}).get("seats") or 0) if isinstance(access_req, dict) else 0
    price_per_seat = int((entitlement or {}).get("price_usd_per_sender_month") or PRICE_USD_PER_SENDER_MONTH)
    monthly_recurring_usd = seats_granted * price_per_seat if is_active else 0

    has_expired_term = bool(
        isinstance(entitlement, dict)
        and (
            (paid_through_dt is not None and paid_through_dt <= now)
            or entitlement.get("status") == "expired"
        )
    )
    has_pending_quote = bool(isinstance(access_req, dict) and access_req.get("status") == "pending_quote")

    if is_active and cancel_at_period_end:
        lifecycle_state = "cancel_scheduled"
        plan_label = f"Paid Pilot ({seats_granted} {'seat' if seats_granted == 1 else 'seats'} · Cancels at period end)"
    elif is_active and days_remaining is not None and days_remaining <= 7:
        lifecycle_state = "expiring_soon"
        plan_label = f"Paid Pilot ({seats_granted} {'seat' if seats_granted == 1 else 'seats'} · Expiring in {days_remaining}d)"
    elif is_active:
        lifecycle_state = "active"
        plan_label = f"Paid Pilot ({seats_granted} {'seat' if seats_granted == 1 else 'seats'} · ${monthly_recurring_usd}/mo)"
    elif has_expired_term:
        lifecycle_state = "expired"
        plan_label = "Expired Pilot"
    elif has_pending_quote:
        lifecycle_state = "pending_quote"
        req_country = str((access_req or {}).get("country_code") or "").upper()
        plan_label = f"Quote Requested ({requested_seats} {'seat' if requested_seats == 1 else 'seats'}{f' · {req_country}' if req_country else ''})"
    else:
        lifecycle_state = "unpaid"
        plan_label = "Unpaid Draft Mode"

    connected_senders_count = len(accounts_list)
    active_senders_count = sum(1 for a in accounts_list if a.get("status") == "active")

    country_code = (
        str((access_req or {}).get("country_code") or "").upper()
        or next(
            (
                str((a.get("proxy") or {}).get("country_code") or "").upper()
                for a in accounts_list
                if isinstance(a.get("proxy"), dict) and (a.get("proxy") or {}).get("country_code")
            ),
            "",
        )
    )

    senders_breakdown = []
    for acc in accounts_list:
        limits = acc.get("limits") if isinstance(acc.get("limits"), dict) else {}
        counters = acc.get("counters") if isinstance(acc.get("counters"), dict) else {}
        is_today = counters.get("date") == today_iso
        proxy = acc.get("proxy") if isinstance(acc.get("proxy"), dict) else {}
        senders_breakdown.append({
            "id": acc.get("id"),
            "account_name": acc.get("account_name") or acc.get("vanity_name") or "LinkedIn Sender",
            "vanity_name": acc.get("vanity_name") or "",
            "status": acc.get("status") or "unknown",
            "premium_product": acc.get("premium_product") or "classic",
            "proxy_country": proxy.get("country_code") or "",
            "proxy_status": proxy.get("status") or "unassigned",
            "activity_control_enabled": bool(acc.get("activity_control_enabled")),
            "daily_voice_notes_limit": int(limits.get("voice_notes", 20)),
            "daily_voice_notes_used": int(counters.get("voice_notes", 0)) if is_today else 0,
            "daily_invites_limit": int(limits.get("connection_invites", 20)),
            "daily_invites_used": int(counters.get("connection_invites", 0)) if is_today else 0,
            "daily_messages_limit": int(limits.get("messages", 20)),
            "daily_messages_used": int(counters.get("messages", 0)) if is_today else 0,
        })

    voice_clips_today = int((voice_prep_budget or {}).get("clips") or 0)
    voice_chars_today = int((voice_prep_budget or {}).get("chars") or 0)
    daily_clips_limit = int(VOICE_POLICY.get("daily_clips", 20))
    daily_chars_limit = int(VOICE_POLICY.get("daily_chars", 20000))

    return {
        "workspace_id": ws_id,
        "workspace_name": workspace_name or ws_id,
        "owner_email": owner_email,
        "owner_name": owner_name,
        "last_active_at": last_active_at,
        "access_active": is_active,
        "lifecycle_state": lifecycle_state,
        "plan_label": plan_label,
        "seats_granted": seats_granted,
        "seats_used": connected_senders_count,
        "seats_remaining": max(0, seats_granted - connected_senders_count),
        "requested_seats": requested_seats,
        "active_senders_count": active_senders_count,
        "connected_senders_count": connected_senders_count,
        "active_campaigns_count": active_campaigns_count,
        "paid_through": paid_through_iso,
        "days_remaining": days_remaining,
        "hours_remaining": hours_remaining,
        "expiring_soon": bool(is_active and days_remaining is not None and days_remaining <= 7),
        "cancel_at_period_end": cancel_at_period_end,
        "price_usd_per_sender_month": price_per_seat,
        "monthly_recurring_usd": monthly_recurring_usd,
        "billing_email": (entitlement or {}).get("billing_email") or owner_email or "",
        "country_code": country_code,
        "voice_usage": {
            "voices_cloned_count": voices_count,
            "max_voices": 5,
            "today_clips_used": voice_clips_today,
            "daily_clips_limit": daily_clips_limit,
            "today_chars_used": voice_chars_today,
            "daily_chars_limit": daily_chars_limit,
        },
        "senders": senders_breakdown,
    }


def _extract_last_active_iso(user_doc: dict | None) -> str | None:
    if not isinstance(user_doc, dict):
        return None
    for field in ("last_login_at", "last_active_at", "updated_at", "created_at"):
        dt = _utc(user_doc.get(field))
        if dt is not None:
            return dt.isoformat()
    return None


@router.get("/subscription-monitor")
async def get_subscription_monitor(
    current_user: dict = Depends(get_outreach_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Live subscription, active user, sender seat, expiry countdown, and ElevenLabs
    voice quota telemetry for the current workspace (plus platform-wide overview
    when the authenticated user is a platform operator/admin).
    """
    now = datetime.now(timezone.utc)
    today_iso = now.date().isoformat()
    ws_id = _workspace_id(current_user)
    scope = workspace_scope(ws_id)

    entitlement = await db.outreach_entitlements.find_one(scope) if hasattr(db, "outreach_entitlements") else None
    access_req = await db.outreach_access_requests.find_one({"workspace_id": ws_id}) if hasattr(db, "outreach_access_requests") else None
    accounts_list = await _safe_to_list(
        getattr(db, "outreach_accounts", None),
        {**scope, "is_deleted": {"$ne": True}},
        limit=50,
    )
    campaigns_list = await _safe_to_list(
        getattr(db, "outreach_campaigns", None),
        {**scope, "is_deleted": {"$ne": True}, "status": "active"},
        limit=100,
    )
    voice_budget = (
        await db.outreach_voice_preparation_budgets.find_one({"_id": f"{ws_id}:{today_iso}", "workspace_id": ws_id})
        if hasattr(db, "outreach_voice_preparation_budgets")
        else None
    )
    voices_list = await _safe_to_list(getattr(db, "outreach_voices", None), scope, limit=10)
    ws_doc = (
        await db.workspaces.find_one({"workspace_id": ws_id})
        if hasattr(db, "workspaces") and hasattr(db.workspaces, "find_one")
        else None
    )

    # Workspace members & active user activity
    member_rows = await _safe_to_list(
        getattr(db, "workspace_members", None),
        {"workspace_id": ws_id},
        limit=100,
    )
    member_user_ids = [str(m.get("user_id")) for m in member_rows if m.get("user_id")]
    if current_user.get("user_id") and str(current_user["user_id"]) not in member_user_ids:
        member_user_ids.append(str(current_user["user_id"]))

    user_docs_by_id: dict[str, dict] = {}
    if member_user_ids and hasattr(db, "users"):
        user_rows = await _safe_to_list(db.users, {"user_id": {"$in": member_user_ids}}, limit=100)
        for u in user_rows:
            if u.get("user_id"):
                user_docs_by_id[str(u["user_id"])] = u

    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)
    workspace_members_summary = []
    ws_active_24h = 0
    ws_active_7d = 0

    for m in member_rows:
        uid = str(m.get("user_id") or "")
        u_doc = user_docs_by_id.get(uid) or (current_user if uid == str(current_user.get("user_id")) else {})
        last_iso = _extract_last_active_iso(u_doc) or _extract_last_active_iso(m)
        last_dt = _utc(last_iso)
        is_24h = bool(last_dt and last_dt >= cutoff_24h)
        is_7d = bool(last_dt and last_dt >= cutoff_7d)
        if is_24h:
            ws_active_24h += 1
        if is_7d:
            ws_active_7d += 1
        workspace_members_summary.append({
            "user_id": uid,
            "email": u_doc.get("email") or m.get("email") or "",
            "display_name": u_doc.get("display_name") or u_doc.get("name") or m.get("display_name") or "",
            "role": m.get("role") or "viewer",
            "last_active_at": last_iso,
            "active_24h": is_24h,
            "active_7d": is_7d,
        })

    if not workspace_members_summary and current_user.get("user_id"):
        last_iso = _extract_last_active_iso(current_user) or now.isoformat()
        ws_active_24h = 1
        ws_active_7d = 1
        workspace_members_summary.append({
            "user_id": str(current_user.get("user_id")),
            "email": current_user.get("email") or "",
            "display_name": current_user.get("display_name") or current_user.get("name") or "",
            "role": current_user.get("workspace_role") or "owner",
            "last_active_at": last_iso,
            "active_24h": True,
            "active_7d": True,
        })

    workspace_summary = _summarize_workspace_subscription(
        ws_id,
        entitlement=entitlement,
        access_req=access_req,
        accounts_list=accounts_list,
        active_campaigns_count=len(campaigns_list),
        voice_prep_budget=voice_budget,
        voices_count=len(voices_list),
        now=now,
        workspace_name=(ws_doc or {}).get("name") or (ws_doc or {}).get("workspace_name") or "Workspace",
        owner_email=current_user.get("email") or "",
        owner_name=current_user.get("display_name") or current_user.get("name") or "",
        last_active_at=_extract_last_active_iso(current_user),
    )
    workspace_summary["members_count"] = len(workspace_members_summary)
    workspace_summary["active_members_24h"] = ws_active_24h
    workspace_summary["active_members_7d"] = ws_active_7d
    workspace_summary["members"] = workspace_members_summary

    is_operator = _is_platform_operator(current_user)
    platform_overview = None

    if is_operator:
        all_users = await _safe_to_list(getattr(db, "users", None), {}, limit=500)
        all_workspaces = await _safe_to_list(getattr(db, "workspaces", None), {}, limit=500)
        all_entitlements = await _safe_to_list(getattr(db, "outreach_entitlements", None), {}, limit=500)
        all_requests = await _safe_to_list(getattr(db, "outreach_access_requests", None), {}, limit=500)
        all_accounts = await _safe_to_list(
            getattr(db, "outreach_accounts", None),
            {"is_deleted": {"$ne": True}},
            limit=500,
        )
        all_active_campaigns = await _safe_to_list(
            getattr(db, "outreach_campaigns", None),
            {"is_deleted": {"$ne": True}, "status": "active"},
            limit=500,
        )
        all_voice_budgets = await _safe_to_list(
            getattr(db, "outreach_voice_preparation_budgets", None),
            {"day": today_iso},
            limit=500,
        )
        all_voices = await _safe_to_list(getattr(db, "outreach_voices", None), {}, limit=500)

        users_by_id = {str(u.get("user_id")): u for u in all_users if u.get("user_id")}
        ent_by_ws = {str(e.get("workspace_id")): e for e in all_entitlements if e.get("workspace_id")}
        req_by_ws = {str(r.get("workspace_id")): r for r in all_requests if r.get("workspace_id")}
        vb_by_ws = {str(b.get("workspace_id")): b for b in all_voice_budgets if b.get("workspace_id")}

        acc_by_ws: dict[str, list[dict]] = {}
        for a in all_accounts:
            w = str(a.get("workspace_id") or "")
            if w:
                acc_by_ws.setdefault(w, []).append(a)

        camp_count_by_ws: dict[str, int] = {}
        for c in all_active_campaigns:
            w = str(c.get("workspace_id") or "")
            if w:
                camp_count_by_ws[w] = camp_count_by_ws.get(w, 0) + 1

        voices_count_by_ws: dict[str, int] = {}
        for v in all_voices:
            w = str(v.get("workspace_id") or "")
            if w:
                voices_count_by_ws[w] = voices_count_by_ws.get(w, 0) + 1

        ws_by_id = {str(w.get("workspace_id")): w for w in all_workspaces if w.get("workspace_id")}
        all_ws_ids = set(ws_by_id.keys()) | set(ent_by_ws.keys()) | set(req_by_ws.keys()) | set(acc_by_ws.keys()) | {ws_id}

        subscribers = []
        for target_ws_id in all_ws_ids:
            w_doc = ws_by_id.get(target_ws_id) or {}
            owner_id = str(w_doc.get("owner_id") or "")
            owner_doc = users_by_id.get(owner_id) or {}
            row_summary = _summarize_workspace_subscription(
                target_ws_id,
                entitlement=ent_by_ws.get(target_ws_id),
                access_req=req_by_ws.get(target_ws_id),
                accounts_list=acc_by_ws.get(target_ws_id, []),
                active_campaigns_count=camp_count_by_ws.get(target_ws_id, 0),
                voice_prep_budget=vb_by_ws.get(target_ws_id),
                voices_count=voices_count_by_ws.get(target_ws_id, 0),
                now=now,
                workspace_name=w_doc.get("name") or w_doc.get("workspace_name") or target_ws_id,
                owner_email=owner_doc.get("email") or (ent_by_ws.get(target_ws_id) or {}).get("billing_email") or "",
                owner_name=owner_doc.get("display_name") or owner_doc.get("name") or "",
                last_active_at=_extract_last_active_iso(owner_doc),
            )
            subscribers.append(row_summary)

        state_priority = {
            "expiring_soon": 0,
            "cancel_scheduled": 1,
            "active": 2,
            "pending_quote": 3,
            "expired": 4,
            "unpaid": 5,
        }
        subscribers.sort(
            key=lambda s: (
                state_priority.get(s["lifecycle_state"], 9),
                s["days_remaining"] if s["days_remaining"] is not None else 9999,
                s["workspace_name"],
            )
        )

        platform_active_24h = 0
        platform_active_7d = 0
        for u in all_users:
            dt = _utc(_extract_last_active_iso(u))
            if dt and dt >= cutoff_24h:
                platform_active_24h += 1
            if dt and dt >= cutoff_7d:
                platform_active_7d += 1

        platform_overview = {
            "kpis": {
                "total_users": len(all_users),
                "active_users_24h": platform_active_24h,
                "active_users_7d": platform_active_7d,
                "total_workspaces": len(subscribers),
                "active_paid_workspaces": sum(1 for s in subscribers if s["access_active"]),
                "expiring_soon_workspaces": sum(1 for s in subscribers if s["expiring_soon"]),
                "pending_quote_workspaces": sum(1 for s in subscribers if s["lifecycle_state"] == "pending_quote"),
                "expired_workspaces": sum(1 for s in subscribers if s["lifecycle_state"] == "expired"),
                "total_granted_seats": sum(s["seats_granted"] for s in subscribers),
                "total_connected_senders": sum(s["connected_senders_count"] for s in subscribers),
                "mrr_usd": sum(s["monthly_recurring_usd"] for s in subscribers),
                "voice_clips_today": sum(s["voice_usage"]["today_clips_used"] for s in subscribers),
                "voice_chars_today": sum(s["voice_usage"]["today_chars_used"] for s in subscribers),
            },
            "subscribers": subscribers,
        }

    posthog_key = (os.getenv("POSTHOG_API_KEY") or os.getenv("REACT_APP_POSTHOG_KEY") or "").strip()
    posthog_configured = bool(posthog_key and posthog_key != "YOUR_POSTHOG_KEY")

    return {
        "generated_at": now.isoformat(),
        "is_platform_operator": is_operator,
        "workspace": workspace_summary,
        "platform_overview": platform_overview,
        "posthog": {
            "configured": posthog_configured,
            "host": os.getenv("POSTHOG_HOST") or os.getenv("REACT_APP_POSTHOG_HOST") or "https://us.i.posthog.com",
        },
        "elevenlabs": {
            "configured": bool((os.getenv("ELEVENLABS_API_KEY") or "").strip() and os.getenv("ELEVENLABS_API_KEY") != "mock"),
            "voice_studio_enabled": os.getenv("OUTREACH_VOICE_STUDIO_ENABLED", "false").strip().lower() in {"1", "true", "yes"},
            "voice_preparation_enabled": os.getenv("OUTREACH_VOICE_PREPARATION_ENABLED", "false").strip().lower() in {"1", "true", "yes"},
            "model_id": VOICE_POLICY.get("model_id", "eleven_turbo_v2_5"),
            "daily_clips_per_workspace": int(VOICE_POLICY.get("daily_clips", 20)),
            "daily_chars_per_workspace": int(VOICE_POLICY.get("daily_chars", 20000)),
        },
    }
