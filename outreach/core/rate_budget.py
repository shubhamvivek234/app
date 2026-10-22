"""Legacy pacing facade backed by the shared MongoDB physical-request budget.

Working hours and sender pacing remain supported; storage failures deny requests.
Live adapters reserve at their transport boundary instead of using this facade.
"""
import logging
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)



def _to_utc(dt: Any) -> datetime:
    if isinstance(dt, datetime):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    if isinstance(dt, str):
        try:
            parsed = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except Exception as exc:
            logger.debug("Rate budget timestamp parse fallback to UTC now (%s)", type(exc).__name__)
    return datetime.now(timezone.utc)


def _get_tz(tz_name: str | None) -> ZoneInfo:
    if not tz_name:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, Exception):
        return ZoneInfo("UTC")


class RateBudget:
    """
    Evaluates whether an outbound action can be dispatched now or must be rescheduled.
    """

    @classmethod
    async def acquire_token(
        cls,
        sender_id: str,
        sender_config: dict[str, Any],
        action_type: str = "generic",
        redis_client: Any = None,
        now: Optional[datetime] = None,
        db: Any = None,
    ) -> tuple[bool, int, str]:
        """
        Requests an execution token for the sender.

        Returns:
            (allowed: bool, retry_after_seconds: int, reason: str)
            - If allowed is True: worker dispatches immediately.
            - If allowed is False: worker must reschedule using self.retry(countdown=retry_after_seconds).
        """
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        # 1. Circuit Breaker / Account Status Check
        status = sender_config.get("status", "active")
        if status in {"checkpoint_detected", "checkpoint", "reauth_required", "error"}:
            stop_reason = sender_config.get("stop_reason") or "checkpoint_detected"
            return False, 3600, f"sender_stopped_{stop_reason}"

        cooldown_until = sender_config.get("cooldown_until")
        if cooldown_until:
            cooldown_dt = _to_utc(cooldown_until)
            if cooldown_dt > now:
                remaining_sec = int((cooldown_dt - now).total_seconds()) + 1
                return False, remaining_sec, f"cooldown_active_{sender_config.get('stop_reason', 'cooldown')}"

        # 2. Timezone-Aware Working Hours Check
        # Daytime working hours check applies to outbound prospect actions; off-peak maintenance (e.g. withdraw) is exempt
        tz_name = sender_config.get("working_timezone") or "UTC"
        tz = _get_tz(tz_name)
        sender_now = now.astimezone(tz)

        if action_type != "withdraw":
            working_days = sender_config.get("working_days") or [0, 1, 2, 3, 4]  # Mon-Fri
            start_str = sender_config.get("working_hours_start") or "09:00"
            end_str = sender_config.get("working_hours_end") or "17:00"

            try:
                sh, sm = map(int, start_str.split(":"))
                eh, em = map(int, end_str.split(":"))
                start_time = dtime(sh, sm)
                end_time = dtime(eh, em)
            except Exception:
                start_time = dtime(9, 0)
                end_time = dtime(17, 0)

            # Check day of week
            if sender_now.weekday() not in working_days:
                # Calculate days until next working day
                days_ahead = 1
                while (sender_now.weekday() + days_ahead) % 7 not in working_days:
                    days_ahead += 1
                next_start_date = sender_now.date() + timedelta(days=days_ahead)
                next_start_dt = datetime.combine(next_start_date, start_time, tz)
                wait_sec = int((next_start_dt - sender_now).total_seconds()) + 1
                return False, max(wait_sec, 60), "outside_working_days"

            # Check time window
            current_time = sender_now.time()
            if current_time < start_time:
                today_start = datetime.combine(sender_now.date(), start_time, tz)
                wait_sec = int((today_start - sender_now).total_seconds()) + 1
                return False, max(wait_sec, 60), "before_working_hours"

            if current_time >= end_time:
                # Find next valid working day
                days_ahead = 1
                while (sender_now.weekday() + days_ahead) % 7 not in working_days:
                    days_ahead += 1
                next_start_date = sender_now.date() + timedelta(days=days_ahead)
                next_start_dt = datetime.combine(next_start_date, start_time, tz)
                wait_sec = int((next_start_dt - sender_now).total_seconds()) + 1
                return False, max(wait_sec, 60), "after_working_hours"

        # Compatibility facade: physical requests use RequestEnvelope directly.
        # There is no Redis/process-memory authority or silent offline grant.
        from outreach.core.request_guard import PhysicalBudget
        workspace_id = sender_config.get("workspace_id")
        if db is None or not workspace_id:
            return False, 30, "budget_authority_unavailable"
        if action_type == "withdraw":
            return False, 30, "withdrawal_unavailable"
        policy = dict(sender_config.get("request_budget") or {})
        policy.setdefault("hourly_cap", int(sender_config.get("hourly_action_cap") or 8))
        policy.setdefault("daily_cap", int(sender_config.get("daily_action_cap") or 50))
        policy.setdefault("reserved_hourly", 0)
        policy.setdefault("reserved_daily", 0)
        policy.setdefault("min_interval_seconds", int(sender_config.get("min_interval_seconds", 45)))
        allowed, wait, reason = await PhysicalBudget(db).reserve(workspace_id, sender_id, "search", "read",
            {"request_budget": policy}, now=now)
        reason = {"physical_hourly_cap": "hourly_cap_reached", "physical_daily_cap": "daily_cap_reached"}.get(reason, reason)
        return allowed, wait, reason

    @classmethod
    def reset_memory(cls) -> None:
        """Deprecated compatibility hook: execution has no process-local budget."""
