"""
Dynamic Redis Token-Bucket Rate Budget for Outreach Pacing.
Eliminates arbitrary time.sleep() loops.
Driven dynamically by sender account settings:
- Daily action cap
- Hourly action cap
- Timezone-aware working hours & days
- Min / Max interval bounds
"""
import logging
import random
import time
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

# Fallback in-memory storage for test suites or offline Redis
_MEMORY_COUNTERS: dict[str, int] = {}
_MEMORY_TIMESTAMPS: dict[str, float] = {}


def _to_utc(dt: Any) -> datetime:
    if isinstance(dt, datetime):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    if isinstance(dt, str):
        try:
            parsed = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except Exception:
            pass
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
        now_ts = now.timestamp()

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

        # 3. Minimum Interval / Pacing Cooldown Check
        min_sec = sender_config.get("min_interval_seconds")
        min_interval = int(min_sec) if min_sec is not None else 45
        max_sec = sender_config.get("max_interval_seconds")
        max_interval = int(max_sec) if max_sec is not None else 180
        ts_key = f"outreach:budget:{sender_id}:last_action_ts"

        last_action_ts = await cls._get_timestamp(redis_client, ts_key)
        if last_action_ts and min_interval > 0:
            elapsed = now_ts - last_action_ts
            if elapsed < min_interval:
                retry_countdown = int(min_interval - elapsed) + 1
                return False, max(retry_countdown, 5), "min_interval_cooldown"

        # 4. Hourly Action Cap Check
        hourly_cap = int(sender_config.get("hourly_action_cap") or 8)
        hour_key = f"outreach:budget:{sender_id}:hourly:{sender_now.strftime('%Y%m%d%H')}"
        hourly_count = await cls._get_counter(redis_client, hour_key)
        if hourly_count >= hourly_cap:
            sec_until_next_hour = (60 - sender_now.minute) * 60 - sender_now.second + 5
            return False, max(sec_until_next_hour, 60), "hourly_cap_reached"

        # 5. Daily Action Cap Check
        daily_cap = int(sender_config.get("daily_action_cap") or 50)
        day_key = f"outreach:budget:{sender_id}:daily:{sender_now.strftime('%Y%m%d')}"
        daily_count = await cls._get_counter(redis_client, day_key)
        if daily_count >= daily_cap:
            # Time until midnight in sender's timezone
            sec_until_midnight = ((23 - sender_now.hour) * 3600) + ((59 - sender_now.minute) * 60) + (60 - sender_now.second) + 5
            return False, max(sec_until_midnight, 300), "daily_cap_reached"

        # 6. Action-Specific Limit Check (e.g. connection_invites, messages)
        limits = sender_config.get("limits") or {}
        if isinstance(limits, dict) and action_type in limits:
            action_cap = int(limits[action_type])
            action_day_key = f"outreach:budget:{sender_id}:{action_type}:daily:{sender_now.strftime('%Y%m%d')}"
            action_count = await cls._get_counter(redis_client, action_day_key)
            if action_count >= action_cap:
                sec_until_midnight = ((23 - sender_now.hour) * 3600) + ((59 - sender_now.minute) * 60) + (60 - sender_now.second) + 5
                return False, max(sec_until_midnight, 300), f"{action_type}_daily_cap_reached"

        # 7. Grant Token: Increment counters and record timestamp
        await cls._incr_counter(redis_client, hour_key, ttl=7200)
        await cls._incr_counter(redis_client, day_key, ttl=172800)
        if isinstance(limits, dict) and action_type in limits:
            await cls._incr_counter(redis_client, f"outreach:budget:{sender_id}:{action_type}:daily:{sender_now.strftime('%Y%m%d')}", ttl=172800)

        await cls._set_timestamp(redis_client, ts_key, now_ts, ttl=86400)
        return True, 0, "ok"

    # ── Helpers for Redis / In-Memory Fallback ───────────────────────────────

    @classmethod
    async def _get_counter(cls, redis_client: Any, key: str) -> int:
        if redis_client is not None:
            try:
                val = await redis_client.get(key)
                return int(val) if val else 0
            except Exception as e:
                logger.debug("Redis error reading counter %s, falling back to memory: %s", key, e)
        return _MEMORY_COUNTERS.get(key, 0)

    @classmethod
    async def _incr_counter(cls, redis_client: Any, key: str, ttl: int = 86400) -> int:
        if redis_client is not None:
            try:
                pipe = redis_client.pipeline()
                pipe.incr(key)
                pipe.expire(key, ttl)
                res = await pipe.execute()
                return int(res[0])
            except Exception as e:
                logger.debug("Redis error incrementing %s, falling back to memory: %s", key, e)
        _MEMORY_COUNTERS[key] = _MEMORY_COUNTERS.get(key, 0) + 1
        return _MEMORY_COUNTERS[key]

    @classmethod
    async def _get_timestamp(cls, redis_client: Any, key: str) -> Optional[float]:
        if redis_client is not None:
            try:
                val = await redis_client.get(key)
                return float(val) if val else None
            except Exception as e:
                logger.debug("Redis error reading ts %s, falling back to memory: %s", key, e)
        return _MEMORY_TIMESTAMPS.get(key)

    @classmethod
    async def _set_timestamp(cls, redis_client: Any, key: str, val: float, ttl: int = 86400) -> None:
        if redis_client is not None:
            try:
                await redis_client.set(key, str(val), ex=ttl)
                return
            except Exception as e:
                logger.debug("Redis error writing ts %s, falling back to memory: %s", key, e)
        _MEMORY_TIMESTAMPS[key] = val

    @classmethod
    def reset_memory(cls) -> None:
        """Utility for test suites to clear in-memory state."""
        _MEMORY_COUNTERS.clear()
        _MEMORY_TIMESTAMPS.clear()
