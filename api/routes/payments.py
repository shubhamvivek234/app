"""
Payments — Stripe checkout session creation and status polling.
Supports Stripe (primary). Razorpay + PayPal preserved as stubs (env-gated).
EC28: idempotent webhook processing via Redis dedup (handled in webhooks.py).
"""
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from api.deps import CurrentUser, DB
from api.limiter import limiter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["payments"])


# ── Plan pricing ──────────────────────────────────────────────────────────────

_PRICING: dict[str, dict] = {
    "pro": {
        "amount": 999,        # in paise / cents (₹999 or $9.99)
        "currency": "INR",
        "duration_days": 30,
        "label": "Pro Monthly",
    },
    "agency": {
        "amount": 2999,
        "currency": "INR",
        "duration_days": 30,
        "label": "Agency Monthly",
    },
}


# ── Request / response models ─────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan: str
    payment_method: Literal["stripe", "razorpay"] = "stripe"


class CheckoutSessionResponse(BaseModel):
    session_id: str
    url: str
    payment_method: str


class CheckoutStatusResponse(BaseModel):
    session_id: str
    payment_status: str          # pending | paid | failed
    plan: str | None = None
    amount: int | None = None
    currency: str | None = None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/payments/checkout", response_model=CheckoutSessionResponse,
             status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_checkout(
    request: Request,
    body: CheckoutRequest,
    current_user: CurrentUser,
    db: DB,
) -> CheckoutSessionResponse:
    """
    Create a Stripe or Razorpay checkout session.
    Records a pending transaction in payment_transactions.
    On success the webhook (webhooks.py) will activate the subscription.
    """
    if body.plan not in _PRICING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid plan '{body.plan}'. Valid plans: {list(_PRICING)}",
        )

    plan_info = _PRICING[body.plan]
    user_id = current_user["user_id"]
    origin = request.headers.get("origin", os.environ.get("FRONTEND_URL", "http://localhost:3000"))

    if body.payment_method == "stripe":
        return await _stripe_checkout(db, user_id, current_user.get("email", ""), body.plan, plan_info, origin)

    if body.payment_method == "razorpay":
        return await _razorpay_checkout(db, user_id, body.plan, plan_info)

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported payment method: {body.payment_method}",
    )


@router.get("/payments/status/{session_id}", response_model=CheckoutStatusResponse)
@limiter.limit("30/minute")
async def get_payment_status(
    request: Request,
    session_id: str,
    current_user: CurrentUser,
    db: DB,
) -> CheckoutStatusResponse:
    """
    Poll payment status for a given Stripe session / Razorpay order.
    For Stripe: re-checks session status live and activates subscription if paid.
    """
    user_id = current_user["user_id"]
    txn = await db.payment_transactions.find_one(
        {"session_id": session_id, "user_id": user_id},
        {"_id": 0},
    )
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    if txn["payment_method"] == "stripe":
        return await _stripe_status(db, session_id, user_id, txn)

    # Razorpay — return stored status (webhook activates on payment.captured)
    return CheckoutStatusResponse(
        session_id=session_id,
        payment_status=txn.get("payment_status", "pending"),
        plan=txn.get("plan"),
        amount=txn.get("amount"),
        currency=txn.get("currency"),
    )


# ── Payment provider helpers ──────────────────────────────────────────────────

async def _stripe_checkout(
    db, user_id: str, email: str, plan: str, plan_info: dict, origin: str
) -> CheckoutSessionResponse:
    stripe_key = os.environ.get("STRIPE_SECRET_KEY")
    if not stripe_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe is not configured",
        )

    try:
        from emergentintegrations.payments.stripe.checkout import (
            StripeCheckout, CheckoutSessionRequest,
        )

        webhook_url = f"{origin}/api/v1/webhooks/stripe"
        success_url = f"{origin}/billing?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{origin}/billing"

        checkout = StripeCheckout(api_key=stripe_key, webhook_url=webhook_url)
        req = CheckoutSessionRequest(
            amount=plan_info["amount"],
            currency=plan_info["currency"].lower(),
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"user_id": user_id, "plan": plan, "email": email},
        )
        session = await checkout.create_checkout_session(req)

    except Exception as exc:
        logger.error("Stripe checkout error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Checkout session creation failed",
        ) from exc

    await _record_transaction(db, user_id, session.session_id, plan, plan_info, "stripe")

    return CheckoutSessionResponse(
        session_id=session.session_id,
        url=session.url,
        payment_method="stripe",
    )


async def _razorpay_checkout(
    db, user_id: str, plan: str, plan_info: dict
) -> CheckoutSessionResponse:
    rp_key_id = os.environ.get("RAZORPAY_KEY_ID")
    rp_key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
    if not rp_key_id or not rp_key_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Razorpay is not configured",
        )

    try:
        import razorpay  # type: ignore

        client = razorpay.Client(auth=(rp_key_id, rp_key_secret))
        order = client.order.create({
            "amount": plan_info["amount"] * 100,  # Razorpay expects smallest unit
            "currency": plan_info["currency"],
            "payment_capture": 1,
        })
        order_id = order["id"]

    except Exception as exc:
        logger.error("Razorpay order error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Razorpay order creation failed",
        ) from exc

    await _record_transaction(db, user_id, order_id, plan, plan_info, "razorpay")

    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    return CheckoutSessionResponse(
        session_id=order_id,
        url=f"{frontend_url}/razorpay-checkout?order_id={order_id}",
        payment_method="razorpay",
    )


async def _stripe_status(
    db, session_id: str, user_id: str, txn: dict
) -> CheckoutStatusResponse:
    stripe_key = os.environ.get("STRIPE_SECRET_KEY")
    if not stripe_key:
        return CheckoutStatusResponse(
            session_id=session_id,
            payment_status=txn.get("payment_status", "pending"),
            plan=txn.get("plan"),
            amount=txn.get("amount"),
            currency=txn.get("currency"),
        )

    try:
        from emergentintegrations.payments.stripe.checkout import StripeCheckout

        checkout = StripeCheckout(api_key=stripe_key, webhook_url="")
        stripe_status = await checkout.get_checkout_status(session_id)

        if stripe_status.payment_status == "paid" and txn.get("payment_status") != "paid":
            await _activate_subscription(db, user_id, txn)

        return CheckoutStatusResponse(
            session_id=session_id,
            payment_status=stripe_status.payment_status,
            plan=txn.get("plan"),
            amount=int(stripe_status.amount_total or 0),
            currency=stripe_status.currency,
        )
    except Exception as exc:
        logger.error("Stripe status check error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment status check failed",
        ) from exc


async def _activate_subscription(db, user_id: str, txn: dict) -> None:
    """Activate subscription after confirmed payment (poll-based fallback)."""
    from datetime import timedelta

    plan = txn.get("plan", "pro")
    duration = _PRICING.get(plan, {}).get("duration_days", 30)
    end_date = datetime.now(timezone.utc) + timedelta(days=duration)

    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "subscription_status": "active",
            "plan": plan,
            "subscription_end_date": end_date,
        }},
    )
    await db.payment_transactions.update_one(
        {"session_id": txn["session_id"]},
        {"$set": {
            "payment_status": "paid",
            "updated_at": datetime.now(timezone.utc),
        }},
    )
    logger.info("Subscription activated (poll): user=%s plan=%s", user_id, plan)


async def _record_transaction(
    db, user_id: str, session_id: str, plan: str, plan_info: dict, method: str
) -> None:
    now = datetime.now(timezone.utc)
    await db.payment_transactions.update_one(
        {"session_id": session_id},
        {"$setOnInsert": {
            "transaction_id": f"txn_{uuid.uuid4().hex[:16]}",
            "user_id": user_id,
            "session_id": session_id,
            "plan": plan,
            "amount": plan_info["amount"],
            "currency": plan_info["currency"],
            "payment_method": method,
            "payment_status": "pending",
            "created_at": now,
            "updated_at": now,
        }},
        upsert=True,
    )
