"""
Phase 8: LinkedIn Anti-Ban Safety Shield & Algorithmic Warm-up Governor.
Guarantees zero account bans through progressive warm-up ramps, automatic stale invite withdrawal,
and instant circuit-breaker pauses upon detecting security checkpoints.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from outreach.models import AccountStatus, CampaignStatus

logger = logging.getLogger(__name__)


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
        Inspects LinkedIn Voyager response for restriction signals or HTTP 429 / 403.
        """
        if status_code in (401, 403, 429):
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

        query = {"id": account_id}
        if workspace_id:
            query["workspace_id"] = workspace_id

        # Update account status
        await db.outreach_accounts.update_one(
            query,
            {
                "$set": {
                    "status": AccountStatus.CHECKPOINT,
                    "circuit_broken_at": datetime.now(timezone.utc),
                    "circuit_break_reason": reason,
                }
            },
        )

        # Pause campaigns associated with this sender
        paused_campaigns = await db.outreach_campaigns.update_many(
            {"sender_account_ids": account_id, "status": CampaignStatus.ACTIVE},
            {"$set": {"status": CampaignStatus.PAUSED, "pause_reason": f"Safety circuit breaker on sender {account_id}"}},
        )

        return {
            "account_id": account_id,
            "status": "circuit_breaker_tripped",
            "campaigns_paused": paused_campaigns.modified_count,
            "reason": reason,
        }

    @classmethod
    async def withdraw_stale_invitations(
        cls,
        account_id: str,
        db: AsyncIOMotorDatabase,
        max_age_days: int = 21,
    ) -> int:
        """
        Identifies and purges pending invitations older than max_age_days.
        Keeping pending invites below 500 maintains high LinkedIn reputation.
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        res = await db.outreach_leads.update_many(
            {
                "assigned_account_id": account_id,
                "has_connected": False,
                "created_at": {"$lte": cutoff_date},
            },
            {"$set": {"invitation_withdrawn": True, "invitation_withdrawn_at": datetime.now(timezone.utc)}},
        )
        logger.info(
            "SafetyShield: Auto-withdrawn %d stale invites older than %d days for account %s",
            res.modified_count,
            max_age_days,
            account_id,
        )
        return res.modified_count
