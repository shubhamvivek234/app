"""
Phase 5.5 — Recurring post instance spawning.
Each occurrence is an independent document with status="scheduled".
Recurrence rules follow iCalendar RRULE semantics.
Leap year + end-of-month clamping: EC31.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from calendar import monthrange

from celery_workers.celery_app import celery_app
from db.mongo import get_client

logger = logging.getLogger(__name__)

# How far ahead to spawn instances
_SPAWN_HORIZON_DAYS = 14
_MAX_INSTANCES_PER_CYCLE = 200  # safety cap

# Beat registration
celery_app.conf.beat_schedule["spawn-recurring-instances"] = {
    "task": "celery_workers.tasks.recurring.spawn_recurring_instances",
    "schedule": 3600,  # every hour
    "options": {"queue": "default"},
}


# ── EC31 — End-of-month clamping ──────────────────────────────────────────────

def clamp_to_month_end(year: int, month: int, day: int) -> int:
    """
    Return the last valid day for the month if day exceeds it.
    e.g. Jan 31 → Feb 28/29 on a recurring monthly post.
    """
    _, max_day = monthrange(year, month)
    return min(day, max_day)


def next_occurrence(
    base_time: datetime,
    frequency: str,   # "daily" | "weekly" | "monthly" | "yearly"
    interval: int,    # every N frequency units
    anchor_day: int | None = None,  # for monthly: original day-of-month
) -> datetime:
    """
    Compute the next occurrence after base_time.
    anchor_day is the original day-of-month for monthly recurrences
    to handle EC31 (e.g. monthly on the 31st clamps to 28/29/30 in short months).
    """
    if frequency == "daily":
        return base_time + timedelta(days=interval)
    if frequency == "weekly":
        return base_time + timedelta(weeks=interval)
    if frequency == "monthly":
        month = base_time.month + interval
        year = base_time.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        day = clamp_to_month_end(year, month, anchor_day or base_time.day)
        return base_time.replace(year=year, month=month, day=day)
    if frequency == "yearly":
        try:
            return base_time.replace(year=base_time.year + interval)
        except ValueError:
            # Feb 29 → Feb 28 in non-leap year
            return base_time.replace(year=base_time.year + interval, day=28)
    raise ValueError(f"Unknown recurrence frequency: {frequency}")


# ── Task ──────────────────────────────────────────────────────────────────────

@celery_app.task(name="celery_workers.tasks.recurring.spawn_recurring_instances")
def spawn_recurring_instances() -> dict:
    """Spawn scheduled post instances for active recurrence templates."""
    return asyncio.get_event_loop().run_until_complete(_async_spawn())


async def _async_spawn() -> dict:
    import uuid

    client = await get_client()
    db = client[os.environ["DB_NAME"]]

    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=_SPAWN_HORIZON_DAYS)
    spawned = 0

    # Recurrence templates: posts with recurrence config and status="template"
    cursor = db.posts.find(
        {"status": "template", "recurrence.enabled": True},
        limit=500,
    )

    async for template in cursor:
        if spawned >= _MAX_INSTANCES_PER_CYCLE:
            break

        recurrence = template.get("recurrence", {})
        frequency: str = recurrence.get("frequency", "weekly")
        interval: int = recurrence.get("interval", 1)
        end_date = recurrence.get("end_date")  # None = no end
        anchor_day: int | None = recurrence.get("anchor_day")

        # Find last spawned instance for this template
        last = await db.posts.find_one(
            {"recurrence_template_id": str(template["_id"]), "status": {"$ne": "template"}},
            sort=[("scheduled_time", -1)],
        )
        next_time = next_occurrence(
            last["scheduled_time"] if last else template.get("scheduled_time", now),
            frequency,
            interval,
            anchor_day,
        )

        # Spawn all occurrences within the look-ahead window
        while next_time <= horizon:
            if end_date and next_time > end_date:
                break

            # Check if instance already exists (idempotent re-runs)
            existing = await db.posts.find_one({
                "recurrence_template_id": str(template["_id"]),
                "scheduled_time": next_time,
            })
            if not existing:
                instance = {
                    **{k: v for k, v in template.items() if k not in ("_id", "status", "recurrence")},
                    "id": str(uuid.uuid4()),
                    "status": "scheduled",
                    "recurrence_template_id": str(template["_id"]),
                    "scheduled_time": next_time,
                    "created_at": now,
                    "updated_at": now,
                    "version": 1,
                    "platform_results": {},
                }
                await db.posts.insert_one(instance)
                spawned += 1
                logger.info(
                    "Spawned recurring instance %s from template %s at %s",
                    instance["id"], template["_id"], next_time.isoformat(),
                )

            next_time = next_occurrence(next_time, frequency, interval, anchor_day)

    logger.info("recurring: spawned %d instances", spawned)
    return {"spawned": spawned}
