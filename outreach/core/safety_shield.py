"""
Phase 8: LinkedIn Anti-Ban Safety Shield & Algorithmic Warm-up Governor.
Applies progressive quotas, stale invite withdrawal, and circuit-breaker
pauses upon detecting security checkpoints. It cannot guarantee account safety.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from outreach.models import AccountStatus, CampaignStatus, LeadExecutionState, WithdrawnInvite
from outreach.core.rate_budget import RateBudget

logger = logging.getLogger(__name__)


async def _fetch_cursor_docs(cursor_or_coro: Any, length: int = 1000) -> list[dict[str, Any]]:
    target = cursor_or_coro
    if hasattr(target, "__await__"):
        target = await target
    if hasattr(target, "to_list"):
        return await target.to_list(length=length)
    if isinstance(target, list):
        return target
    return []


class WarmUpGovernor:
    """
    Progressively ramps up daily LinkedIn invitation quotas to build sender trust score.
    Prevents sudden velocity spikes that trigger LinkedIn bot detection algorithms.
    """

    @staticmethod
    def get_recommended_invite_limit(connected_at: datetime, target_cap: int = 20) -> int:
        """
        Calculates safe daily invitation limit based on account maturity.
        - Days 0-7: 5 invites / day
        - Days 8-14: 10 invites / day
        - Days 15-21: 15 invites / day
        - Days 22+: Full target cap (e.g. 20-25 / day)
        """
        now = datetime.now(timezone.utc)
        if connected_at.tzinfo is None:
            connected_at = connected_at.replace(tzinfo=timezone.utc)

        age_days = (now - connected_at).days

        if age_days < 7:
            return min(5, target_cap)
        elif age_days < 14:
            return min(10, target_cap)
        elif age_days < 21:
            return min(15, target_cap)
        else:
            return target_cap


class SafetyShield:
    """
    Monitors account health and trips circuit breakers when anti-bot triggers occur.
    """

    SUSPICIOUS_KEYWORDS = [
        "checkpoint",
        "challenge",
        "captcha",
        "security-check",
        "unusual activity",
        "temporarily restricted",
        "action blocked",
    ]

    @classmethod
    def should_trip_circuit_breaker(cls, status_code: int, response_text: str = "") -> bool:
        """
        Inspects LinkedIn Voyager response for restriction signals or HTTP 429 / 999 / 403 / 401.
        """
        if status_code in (401, 403, 429, 999):
            return True

        lower_resp = response_text.lower()
        if any(keyword in lower_resp for keyword in cls.SUSPICIOUS_KEYWORDS):
            return True

        return False

    @classmethod
    async def trip_circuit_breaker(
        cls,
        account_id: str,
        reason: str,
        db: AsyncIOMotorDatabase,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Immediately marks account as restricted and pauses all campaigns relying on it.
        """
        logger.warning(
            "SAFETY SHIELD TRIPPED: Pausing account %s due to '%s'",
            account_id,
            reason,
        )

        query: dict[str, Any] = {"id": account_id}
        if workspace_id:
            query["workspace_id"] = workspace_id

        now = datetime.now(timezone.utc)
        await db.outreach_accounts.update_one(
            query,
            {
                "$set": {
                    "status": AccountStatus.CHECKPOINT_DETECTED.value,
                    "circuit_broken_at": now,
                    "circuit_break_reason": reason,
                    "stop_reason": reason,
                    "stopped_at": now,
                    "updated_at": now,
                }
            },
        )

        camp_query: dict[str, Any] = {
            "sender_account_ids": account_id,
            "status": CampaignStatus.ACTIVE.value,
        }
        if workspace_id:
            camp_query["workspace_id"] = workspace_id

        paused_campaigns = None
        if hasattr(db, "outreach_campaigns") and hasattr(db.outreach_campaigns, "update_many"):
            paused_campaigns = await db.outreach_campaigns.update_many(
                camp_query,
                {"$set": {"status": CampaignStatus.PAUSED.value, "pause_reason": f"Safety circuit breaker on sender {account_id}"},
                 "$inc": {"authorization_revision": 1}, "$addToSet": {"pause_reasons": "sender_stopped"}},
            )

        if hasattr(db, "outreach_tasks") and hasattr(db.outreach_tasks, "update_many"):
            await db.outreach_tasks.update_many(
                {"assigned_account_id": account_id, "status": "pending"},
                {"$set": {"status": "paused", "skip_reason": f"Safety circuit breaker on sender {account_id}", "resolved_at": now}},
            )

        paused_count = getattr(paused_campaigns, "modified_count", 0) if paused_campaigns else 0

        return {
            "account_id": account_id,
            "status": "circuit_breaker_tripped",
            "campaigns_paused": paused_count,
            "reason": reason,
        }

    @classmethod
    async def withdraw_stale_invitations(
        cls,
        account_id: str,
        db: AsyncIOMotorDatabase,
        max_age_days: int = 21,
        workspace_id: str | None = None,
        max_withdrawals: int = 25,
        redis_client: Any = None,
    ) -> int:
        """Withdrawal has no verified transport; never invent provider completion."""
        logger.info("Automatic withdrawal unavailable: provider execution is not implemented")
        return 0
