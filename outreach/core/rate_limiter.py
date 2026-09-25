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
    def is_within_working_hours(schedule: WorkingSchedule | dict | None, now_dt: datetime | None = None) -> bool:
        """
        Determines whether a moment falls inside the campaign's active working hours.
        Supports both the API model (24-hour window + numeric weekdays) and the
        wizard format (weekday objects with one or more 12-hour ranges).
        """
        schedule_data = schedule.model_dump() if isinstance(schedule, WorkingSchedule) else schedule or {}
        if not isinstance(schedule_data, dict):
            return False

        tz_name = schedule_data.get("timezone") or "UTC"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("UTC")

        current_time = (now_dt or datetime.now(timezone.utc)).astimezone(tz)

        days = schedule_data.get("days", [0, 1, 2, 3, 4])
        if days and isinstance(days[0], dict):
            day_by_name = {
                "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                "friday": 4, "saturday": 5, "sunday": 6,
            }
            for day in days:
                if not isinstance(day, dict) or not day.get("enabled"):
                    continue
                if day_by_name.get(str(day.get("day", "")).lower()) != current_time.weekday():
                    continue
                for window in day.get("ranges") or []:
                    start_t = OutboundRateLimiter._parse_time(window.get("start"))
                    end_t = OutboundRateLimiter._parse_time(window.get("end"))
                    if start_t and end_t and start_t <= current_time.time().replace(tzinfo=None) <= end_t:
                        return True
            return False

        try:
            if current_time.weekday() not in days:
                return False
        except (TypeError, ValueError):
            return False
        start_t = OutboundRateLimiter._parse_time(schedule_data.get("start_time", "09:00"))
        end_t = OutboundRateLimiter._parse_time(schedule_data.get("end_time", "17:00"))
        if not start_t or not end_t:
            return False
        return start_t <= current_time.time().replace(tzinfo=None) <= end_t

    @staticmethod
    def has_valid_working_window(schedule: WorkingSchedule | dict | None) -> bool:
        schedule_data = schedule.model_dump() if isinstance(schedule, WorkingSchedule) else schedule or {}
        if not isinstance(schedule_data, dict):
            return False
        try:
            ZoneInfo(schedule_data.get("timezone") or "UTC")
        except Exception:
            return False
        days = schedule_data.get("days", [0, 1, 2, 3, 4])
        if not days:
            return False
        if isinstance(days[0], dict):
            for day in days:
                if not isinstance(day, dict) or not day.get("enabled"):
                    continue
                for window in day.get("ranges") or []:
                    start_t = OutboundRateLimiter._parse_time(window.get("start"))
                    end_t = OutboundRateLimiter._parse_time(window.get("end"))
                    if start_t and end_t and start_t < end_t:
                        return True
            return False
        start_t = OutboundRateLimiter._parse_time(schedule_data.get("start_time", "09:00"))
        end_t = OutboundRateLimiter._parse_time(schedule_data.get("end_time", "17:00"))
        has_valid_day = isinstance(days, list) and any(isinstance(day, int) and 0 <= day <= 6 for day in days)
        return bool(has_valid_day and start_t and end_t and start_t < end_t)

    @staticmethod
    def _parse_time(value: str | None) -> time | None:
        if not value or not isinstance(value, str):
            return None
        try:
            normalized = value.strip().upper()
            for fmt in ("%I:%M %p", "%H:%M"):
                try:
                    return datetime.strptime(normalized, fmt).time()
                except ValueError:
                    continue
        except (TypeError, ValueError):
            pass
        return None

    @staticmethod
    async def check_and_increment_daily_limit(
        account: dict,
        action_field: str,
        db: AsyncIOMotorDatabase,
        campaign_limits: dict | None = None,
    ) -> bool:
        """
        Checks if the account has remaining quota for the specific action today.
        If under limit, increments counter and returns True. Otherwise returns False.
        """
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Fetch limits (default to 20 if unset)
        limits = account.get("limits") or {}
        account_max = limits.get(action_field, 20)
        campaign_max = (campaign_limits or {}).get(action_field, account_max)
        max_allowed = min(account_max, campaign_max)
        if max_allowed <= 0:
            return False

        counter_expression = {
            "$cond": [
                {"$eq": ["$counters.date", today_str]},
                {"$ifNull": [f"$counters.{action_field}", 0]},
                0,
            ]
        }
        result = await db.outreach_accounts.update_one(
            {
                "id": account["id"],
                "$expr": {"$lt": [counter_expression, max_allowed]},
            },
            [{"$set": {
                "counters.date": today_str,
                f"counters.{action_field}": {"$add": [counter_expression, 1]},
                "last_active_at": datetime.now(timezone.utc),
            }}],
        )
        if result.matched_count == 0:
            logger.warning("Account %s reached daily limit for %s (%s)", account["id"], action_field, max_allowed)
            return False
        return True

    @staticmethod
    def calculate_human_jitter(base_seconds: float = 6.0) -> float:
        """
        Generates realistic Gaussian random micro-delays between consecutive actions.
        """
        delay = random.gauss(base_seconds, 2.0)
        return max(2.5, min(delay, 20.0))
