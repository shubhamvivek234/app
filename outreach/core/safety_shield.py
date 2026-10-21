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
from outreach.core.workspace_scope import workspace_scope

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
    Progressively ramps up daily LinkedIn invitation and action quotas ("Activity Control")
    based on account maturity, existing LinkedIn network size (connections_count), and
    subscription tier (classic vs Sales Navigator / Recruiter).
    """

    HARD_CEILINGS = {
        "connection_invites": 75,
        "messages": 150,
        "profile_visits": 150,
        "inmails": 50,
        "voice_notes": 50,
        "follows": 100,
        "post_likes": 100,
        "comments": 50,
        "email_sends": 150,
    }

    WEEKLY_INVITE_CEILINGS = {
        "classic": 100,
        "sales_navigator": 200,
        "recruiter": 200,
    }

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

    @classmethod
    def get_activity_control_limits(
        cls,
        account: dict[str, Any],
        now: datetime | None = None,
    ) -> dict[str, int]:
        """
        Computes dynamic daily limits across all LinkedIn actions factoring in:
        1. Account warm-up age (`warmup_started_at` / `created_at`) or explicit `warmup_level`.
        2. Existing LinkedIn connections count (`connections_count`).
        3. Account tier (`premium_product`: classic, sales_navigator, recruiter).
        """
        now = now or datetime.now(timezone.utc)
        configured = account.get("limits") or {}

        # 1. Determine warm-up maturity factor (0.25 -> 0.50 -> 0.75 -> 1.0)
        started_raw = account.get("warmup_started_at") or account.get("created_at")
        started_dt: datetime | None = None
        if isinstance(started_raw, datetime):
            started_dt = started_raw if started_raw.tzinfo else started_raw.replace(tzinfo=timezone.utc)
        elif isinstance(started_raw, str):
            try:
                started_dt = datetime.fromisoformat(started_raw.replace("Z", "+00:00"))
                if started_dt.tzinfo is None:
                    started_dt = started_dt.replace(tzinfo=timezone.utc)
            except ValueError:
                started_dt = None

        if started_dt is not None:
            age_days = max(0, (now - started_dt).days)
            if age_days < 7:
                ramp_factor = 0.25
            elif age_days < 14:
                ramp_factor = 0.50
            elif age_days < 21:
                ramp_factor = 0.75
            else:
                ramp_factor = 1.0
        else:
            level = account.get("warmup_level")
            if isinstance(level, int) and 1 <= level <= 4:
                ramp_factor = {1: 0.25, 2: 0.50, 3: 0.75, 4: 1.0}[level]
            else:
                ramp_factor = 1.0

        # 2. Tier multiplier (Sales Navigator / Recruiter warm up 25% faster within target cap)
        tier = str(account.get("premium_product") or "classic").lower()
        tier_multiplier = 1.25 if tier in {"sales_navigator", "recruiter"} else 1.0

        # 3. Network size ceilings based on existing LinkedIn connections count
        connections_count = account.get("connections_count")
        network_ceilings: dict[str, int] = dict(cls.HARD_CEILINGS)
        if isinstance(connections_count, int) and not isinstance(connections_count, bool) and connections_count >= 0:
            if connections_count < 100:
                network_ceilings.update({"connection_invites": 10, "messages": 25, "profile_visits": 30})
            elif connections_count < 300:
                network_ceilings.update({"connection_invites": 20, "messages": 50, "profile_visits": 60})
            elif connections_count < 500:
                network_ceilings.update({"connection_invites": 35, "messages": 75, "profile_visits": 90})

        effective: dict[str, int] = {}
        for field, hard_max in cls.HARD_CEILINGS.items():
            raw_target = configured.get(field, 20)
            target = raw_target if isinstance(raw_target, int) and not isinstance(raw_target, bool) else 20
            target = max(0, min(target, hard_max))
            if target == 0:
                effective[field] = 0
                continue
            ramped = int(round(target * min(1.0, ramp_factor * tier_multiplier)))
            floor_val = 5 if field == "connection_invites" else 8
            ramped = max(min(floor_val, target), ramped)
            effective[field] = min(target, network_ceilings.get(field, hard_max), ramped)

        return effective

    @classmethod
    def compute_activity_control_summary(
        cls,
        account: dict[str, Any],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or datetime.now(timezone.utc)
        enabled = bool(account.get("activity_control_enabled") or account.get("status") == "warming")
        effective = cls.get_activity_control_limits(account, now=now)
        configured = account.get("limits") or {}
        tier = str(account.get("premium_product") or "classic").lower()
        weekly_ceiling = cls.WEEKLY_INVITE_CEILINGS.get(tier, 100)
        reset_at = account.get("weekly_invite_reset_at")
        if isinstance(reset_at, datetime) and reset_at.tzinfo is None:
            reset_at = reset_at.replace(tzinfo=timezone.utc)
        weekly_capped = bool(
            account.get("weekly_invite_limit_reached")
            and (reset_at is None or reset_at > now)
        )
        if weekly_capped:
            effective = {**effective, "connection_invites": 0}
        return {
            "activity_control_enabled": enabled,
            "warmup_level": account.get("warmup_level", 1),
            "connections_count": account.get("connections_count"),
            "premium_product": account.get("premium_product", "classic"),
            "weekly_invite_limit_reached": weekly_capped,
            "weekly_invite_reset_at": reset_at.isoformat() if isinstance(reset_at, datetime) else reset_at,
            "weekly_invites_sent": int(account.get("weekly_invites_sent") or 0),
            "weekly_invite_ceiling": weekly_ceiling,
            "effective_limits": effective if enabled else {
                k: (0 if weekly_capped and k == "connection_invites" else min(int(configured.get(k, 20)), v))
                for k, v in cls.HARD_CEILINGS.items()
                if isinstance(configured.get(k, 20), int)
            },
            "hard_ceilings": dict(cls.HARD_CEILINGS),
        }


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

    WEEKLY_INVITE_KEYWORDS = [
        "weekly invitation limit",
        "reached the weekly invitation",
        "fuse_limit_exceeded",
        "cant_resend_yet",
        "invitation limit",
    ]

    @classmethod
    def is_weekly_invite_limit_error(cls, status_code_or_text: int | str = 429, response_text: str = "") -> bool:
        """
        Detects when a 429/400/403 from LinkedIn (or an error message string) is specifically
        a weekly connection invitation quota warning rather than an account-wide security checkpoint.
        """
        if isinstance(status_code_or_text, str):
            lower_resp = status_code_or_text.lower()
            return any(kw in lower_resp for kw in cls.WEEKLY_INVITE_KEYWORDS)
        if status_code_or_text not in (400, 403, 429):
            return False
        lower_resp = (response_text or "").lower()
        return any(kw in lower_resp for kw in cls.WEEKLY_INVITE_KEYWORDS)

    @classmethod
    async def record_weekly_invite_limit(
        cls,
        account_id: str,
        reason: str,
        db: AsyncIOMotorDatabase,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Pauses ONLY connection invitations on the sender until the weekly reset window,
        allowing messages, profile visits, likes, and follows to continue uninterrupted.
        """
        scope = workspace_scope(workspace_id)
        now = datetime.now(timezone.utc)
        days_until_monday = (7 - now.weekday()) or 7
        reset_at = (now + timedelta(days=days_until_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
        await db.outreach_accounts.update_one(
            {"id": account_id, **scope},
            {
                "$set": {
                    "weekly_invite_limit_reached": True,
                    "weekly_invite_reset_at": reset_at,
                    "weekly_invite_limit_reason": reason[:200],
                    "updated_at": now,
                }
            },
        )
        return {
            "account_id": account_id,
            "status": "weekly_invite_limit_isolated",
            "weekly_invite_limit_reached": True,
            "weekly_invite_reset_at": reset_at.isoformat(),
            "reason": reason[:200],
        }

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
        scope = workspace_scope(workspace_id)
        logger.warning(
            "SAFETY SHIELD TRIPPED: Pausing account %s due to '%s'",
            account_id,
            reason,
        )

        query: dict[str, Any] = {"id": account_id, **scope}

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
            **scope,
        }

        paused_campaigns = None
        if hasattr(db, "outreach_campaigns") and hasattr(db.outreach_campaigns, "update_many"):
            paused_campaigns = await db.outreach_campaigns.update_many(
                camp_query,
                {"$set": {"status": CampaignStatus.PAUSED.value, "pause_reason": f"Safety circuit breaker on sender {account_id}"},
                 "$inc": {"authorization_revision": 1}, "$addToSet": {"pause_reasons": "sender_stopped"}},
            )

        if hasattr(db, "outreach_tasks") and hasattr(db.outreach_tasks, "update_many"):
            await db.outreach_tasks.update_many(
                {**scope, "$or": [{"assigned_account_id": account_id}, {"account_id": account_id}],
                 "status": {"$in": ["pending", "queued", "scheduled"]}},
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
