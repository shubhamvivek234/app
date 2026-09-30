"""
Sender-Scoped Circuit Breaker for LinkedIn Outreach Protection.
Monitors platform responses, traps challenges (429, 999, CAPTCHA, proxy failure),
atomically trips sender accounts to 'checkpoint_detected', pauses all pending tasks,
and enforces a mandatory cooldown before manual resumption.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from outreach.models import AccountStatus, CampaignStatus, StopReason

logger = logging.getLogger(__name__)

# Keywords in response bodies indicating security challenges
_CHALLENGE_KEYWORDS = [
    "checkpoint",
    "challenge",
    "captcha",
    "security-check",
    "unusual activity",
    "temporarily restricted",
    "action blocked",
    "verification code",
    "puzzle",
]

_COMMERCIAL_KEYWORDS = [
    "commercial use limit",
    "search limit reached",
    "monthly limit",
]


def parse_stop_reason(status_code: int | None = None, response_text: str = "") -> Optional[StopReason]:
    """
    Translates HTTP status codes or platform response text into a machine-readable StopReason.
    Returns None if response is healthy or does not warrant tripping the circuit breaker.
    """
    if status_code == 429:
        return StopReason.RATE_LIMITED_429
    if status_code == 999:
        return StopReason.SECURITY_CHALLENGE_999
    if status_code in (401, 403):
        return StopReason.SESSION_EXPIRED

    lower_text = (response_text or "").lower()
    if any(k in lower_text for k in _COMMERCIAL_KEYWORDS):
        return StopReason.COMMERCIAL_LIMIT
    if any(k in lower_text for k in _CHALLENGE_KEYWORDS):
        return StopReason.CHECKPOINT_CAPTCHA

    return None


def get_default_cooldown_hours(reason: StopReason | str) -> int:
    """Returns dynamic mandatory cooldown window based on platform severity."""
    r_str = reason.value if isinstance(reason, StopReason) else str(reason)
    if "429" in r_str or "rate_limited" in r_str:
        return 24
    if "999" in r_str or "security_challenge" in r_str:
        return 48
    if "captcha" in r_str or "checkpoint" in r_str:
        return 72
    if "commercial" in r_str:
        return 720  # 30 days
    if "proxy" in r_str:
        return 2
    if "session" in r_str:
        return 0  # Reauth required immediately
    return 24


class CircuitBreaker:
    """
    Manages circuit breaker lifecycle for LinkedIn sender accounts.
    """

    @classmethod
    async def trip_circuit_breaker(
        cls,
        sender_id: str,
        reason: StopReason | str,
        db: AsyncIOMotorDatabase,
        workspace_id: str | None = None,
        error_details: str | None = None,
        cooldown_hours: int | None = None,
    ) -> dict[str, Any]:
        """
        Immediately marks account as 'checkpoint_detected', freezes all pending tasks,
        pauses active campaigns with no healthy senders, and enforces a cooldown window.
        """
        reason_enum = reason if isinstance(reason, StopReason) else None
        if not reason_enum:
            try:
                reason_enum = StopReason(str(reason))
            except ValueError:
                reason_enum = StopReason.CHECKPOINT_CAPTCHA

        if cooldown_hours is None:
            cooldown_hours = get_default_cooldown_hours(reason_enum)

        now = datetime.now(timezone.utc)
        cooldown_until = now + timedelta(hours=cooldown_hours)

        logger.warning(
            "CIRCUIT BREAKER TRIPPED on sender %s: reason=%s, cooldown=%dh (until %s)",
            sender_id, reason_enum.value, cooldown_hours, cooldown_until.isoformat()
        )

        query: dict[str, Any] = {"id": sender_id}
        if workspace_id:
            query["workspace_id"] = workspace_id

        # 1. Update sender document
        account_update = {
            "status": AccountStatus.CHECKPOINT_DETECTED.value,
            "stop_reason": reason_enum.value,
            "stopped_at": now,
            "cooldown_until": cooldown_until,
            "error_details": error_details or f"Circuit breaker tripped: {reason_enum.value}",
            "updated_at": now,
        }
        await db.outreach_accounts.update_one(query, {"$set": account_update})

        # 2. Pause all pending queued tasks for this sender across the workspace
        task_query: dict[str, Any] = {
            "assigned_account_id": sender_id,
            "status": "pending",
        }
        if workspace_id:
            task_query["workspace_id"] = workspace_id

        paused_tasks_res = await db.outreach_tasks.update_many(
            task_query,
            {
                "$set": {
                    "status": "paused",
                    "skip_reason": f"Sender circuit breaker tripped ({reason_enum.value})",
                    "resolved_at": now,
                }
            },
        )

        # 3. Check campaigns using this sender: pause if no other active senders exist
        camp_query: dict[str, Any] = {
            "sender_account_ids": sender_id,
            "status": CampaignStatus.ACTIVE.value,
        }
        if workspace_id:
            camp_query["workspace_id"] = workspace_id

        affected_campaigns = await db.outreach_campaigns.find(camp_query).to_list(length=100)
        paused_campaigns_count = 0

        for camp in affected_campaigns:
            configured_senders = list(camp.get("sender_account_ids", []))
            # Check if any OTHER senders are active
            other_active = await db.outreach_accounts.count_documents({
                "id": {"$in": [s for s in configured_senders if s != sender_id]},
                "status": "active",
            })
            if other_active == 0:
                await db.outreach_campaigns.update_one(
                    {"id": camp["id"]},
                    {
                        "$set": {
                            "status": CampaignStatus.PAUSED.value,
                            "pause_reason": f"Sender {sender_id} stopped ({reason_enum.value}) and no alternative senders active",
                            "updated_at": now,
                        }
                    },
                )
                paused_campaigns_count += 1

        # 4. Emit outbox event for integrations
        if hasattr(db, "outreach_event_outbox"):
            event_doc = {
                "workspace_id": workspace_id or "global",
                "dedupe_key": f"circuit_breaker:{sender_id}:{int(now.timestamp())}",
                "event_type": "outreach.circuit_breaker_tripped",
                "payload": {
                    "sender_id": sender_id,
                    "stop_reason": reason_enum.value,
                    "cooldown_until": cooldown_until.isoformat(),
                    "tasks_paused": paused_tasks_res.modified_count,
                    "campaigns_paused": paused_campaigns_count,
                },
                "status": "pending",
                "occurred_at": now,
                "created_at": now,
            }
            try:
                await db.outreach_event_outbox.update_one(
                    {"dedupe_key": event_doc["dedupe_key"]},
                    {"$set": event_doc},
                    upsert=True,
                )
            except Exception as e:
                logger.debug("Could not record outbox event: %s", e)

        return {
            "sender_id": sender_id,
            "status": AccountStatus.CHECKPOINT_DETECTED.value,
            "stop_reason": reason_enum.value,
            "cooldown_until": cooldown_until.isoformat(),
            "tasks_paused": paused_tasks_res.modified_count,
            "campaigns_paused": paused_campaigns_count,
        }

    @classmethod
    def is_sender_available(cls, sender: dict[str, Any], now: Optional[datetime] = None) -> tuple[bool, Optional[str]]:
        """
        Determines whether a sender is available for outbound work.
        Returns (True, None) or (False, reason).
        """
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        status = sender.get("status")
        if status in {"checkpoint_detected", "checkpoint", "reauth_required", "error", "paused", "disconnected"}:
            reason = sender.get("stop_reason") or status
            return False, f"sender_status_{reason}"

        cooldown_until = sender.get("cooldown_until")
        if cooldown_until:
            cooldown_dt = cooldown_until if isinstance(cooldown_until, datetime) else None
            if not cooldown_dt and isinstance(cooldown_until, str):
                try:
                    cooldown_dt = datetime.fromisoformat(cooldown_until.replace("Z", "+00:00"))
                except Exception:
                    pass
            if cooldown_dt:
                if cooldown_dt.tzinfo is None:
                    cooldown_dt = cooldown_dt.replace(tzinfo=timezone.utc)
                if cooldown_dt > now:
                    remaining_hours = (cooldown_dt - now).total_seconds() / 3600.0
                    return False, f"cooldown_active_{remaining_hours:.1f}h_remaining"

        return True, None

    @classmethod
    async def resume_sender(
        cls,
        sender_id: str,
        workspace_id: str,
        db: AsyncIOMotorDatabase,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Resumes a stopped sender account after verifying cooldown period has passed
        or if force=True is explicitly supplied by an operator.
        """
        now = datetime.now(timezone.utc)
        sender = await db.outreach_accounts.find_one({"id": sender_id, "workspace_id": workspace_id})
        if not sender:
            raise ValueError(f"Sender account {sender_id} not found")

        cooldown_until = sender.get("cooldown_until")
        if not force and cooldown_until:
            cooldown_dt = cooldown_until if isinstance(cooldown_until, datetime) else None
            if not cooldown_dt and isinstance(cooldown_until, str):
                try:
                    cooldown_dt = datetime.fromisoformat(cooldown_until.replace("Z", "+00:00"))
                except Exception:
                    pass
            if cooldown_dt:
                if cooldown_dt.tzinfo is None:
                    cooldown_dt = cooldown_dt.replace(tzinfo=timezone.utc)
                if cooldown_dt > now:
                    remaining = (cooldown_dt - now).total_seconds() / 3600.0
                    raise ValueError(
                        f"Sender is under mandatory platform cooldown for another {remaining:.1f} hours (until {cooldown_dt.isoformat()}). Pass force=True to override."
                    )

        # Reactivate sender
        await db.outreach_accounts.update_one(
            {"id": sender_id, "workspace_id": workspace_id},
            {
                "$set": {
                    "status": AccountStatus.ACTIVE.value,
                    "stop_reason": None,
                    "stopped_at": None,
                    "cooldown_until": None,
                    "error_details": None,
                    "updated_at": now,
                }
            },
        )

        # Unpause paused tasks for this sender
        resumed_tasks = await db.outreach_tasks.update_many(
            {"assigned_account_id": sender_id, "workspace_id": workspace_id, "status": "paused"},
            {"$set": {"status": "pending", "skip_reason": None, "updated_at": now}},
        )

        return {
            "sender_id": sender_id,
            "status": "active",
            "tasks_resumed": resumed_tasks.modified_count,
        }
