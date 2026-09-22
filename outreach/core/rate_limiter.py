"""
Phase 5: Outbound Rate Limiter, Working Hours Gatekeeper & Human Jitter Engine.
Protects accounts from bans by enforcing daily caps and human schedule emulation.
"""
import random
import logging
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
from motor.motor_asyncio import AsyncIOMotorDatabase
from outreach.models import WorkingSchedule, DailyLimits, DailyCounters

logger = logging.getLogger(__name__)


class OutboundRateLimiter:
    """
    Enforces human schedule emulation and daily safety limits per account.
    """

    @staticmethod
    def is_within_working_hours(schedule: WorkingSchedule, now_dt: datetime | None = None) -> bool:
        """
        Determines if the current moment falls inside the campaign's active working hours.
        """
        tz_name = schedule.timezone or "UTC"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("UTC")

        current_time = (now_dt or datetime.now(timezone.utc)).astimezone(tz)

        # 1. Check day of week (0 = Monday, 6 = Sunday)
        if current_time.weekday() not in schedule.days:
            return False

        # 2. Parse start and end times (HH:MM)
        try:
            start_parts = [int(p) for p in schedule.start_time.split(":")]
            end_parts = [int(p) for p in schedule.end_time.split(":")]
            start_t = time(start_parts[0], start_parts[1])
            end_t = time(end_parts[0], end_parts[1])
        except Exception:
            start_t = time(9, 0)
            end_t = time(17, 0)

        current_t = current_time.time()
        return start_t <= current_t <= end_t

    @staticmethod
    async def check_and_increment_daily_limit(
        account: dict,
        action_field: str,
        db: AsyncIOMotorDatabase,
    ) -> bool:
        """
        Checks if the account has remaining quota for the specific action today.
        If under limit, increments counter and returns True. Otherwise returns False.
        """
        account_id = account["id"]
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        counters = account.get("counters") or {}
        counter_date = counters.get("date", "")
        current_count = counters.get(action_field, 0) if counter_date == today_str else 0

        # Fetch limits (default to 20 if unset)
        limits = account.get("limits") or {}
        max_allowed = limits.get(action_field, 20)

        if current_count >= max_allowed:
            logger.warning(
                "Account %s reached daily limit for %s (%s/%s)",
                account_id, action_field, current_count, max_allowed,
            )
            return False

        # Reset counters if new day, otherwise increment
        update_query = {
            f"counters.{action_field}": current_count + 1,
            "counters.date": today_str,
            "last_active_at": datetime.now(timezone.utc),
        }

        await db.outreach_accounts.update_one(
            {"id": account_id},
            {"$set": update_query}
        )

        return True

    @staticmethod
    def calculate_human_jitter(base_seconds: float = 6.0) -> float:
        """
        Generates realistic Gaussian random micro-delays between consecutive actions.
        """
        delay = random.gauss(base_seconds, 2.0)
        return max(2.5, min(delay, 20.0))
