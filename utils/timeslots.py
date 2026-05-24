from __future__ import annotations

from datetime import datetime, timedelta, timezone

DAY_ORDER = [
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
    "SUNDAY",
]
DAY_INDEX = {day: index for index, day in enumerate(DAY_ORDER)}
VALID_DAYS = set(DAY_ORDER)
VALID_MINUTES = {"00", "15", "30", "45"}
VALID_AMPM = {"AM", "PM"}
DEFAULT_TIMESLOT_CATEGORY = "Category 1"
VALID_TIMESLOT_CATEGORIES = {
    "Category 1",
    "Category 2",
    "Category 3",
    "Custom",
}


def normalize_timeslot_category(category: str | None) -> str:
    value = (category or DEFAULT_TIMESLOT_CATEGORY).strip() or DEFAULT_TIMESLOT_CATEGORY
    if value not in VALID_TIMESLOT_CATEGORIES:
        raise ValueError(
            f"Invalid timeslot category: {value}. Must be one of {sorted(VALID_TIMESLOT_CATEGORIES)}"
        )
    return value


def normalize_timeslot_clock(
    day_of_week: str,
    hour: str,
    minute: str,
    ampm: str,
) -> tuple[str, str, str, str]:
    normalized_day = str(day_of_week or "").strip().upper()
    normalized_hour = str(hour or "").strip().zfill(2)
    normalized_minute = str(minute or "").strip().zfill(2)
    normalized_ampm = str(ampm or "").strip().upper()

    if normalized_day not in VALID_DAYS:
        raise ValueError(
            f"Invalid day_of_week: {day_of_week}. Must be one of {sorted(VALID_DAYS)}"
        )
    if normalized_ampm not in VALID_AMPM:
        raise ValueError("ampm must be 'AM' or 'PM'")
    if normalized_minute not in VALID_MINUTES:
        raise ValueError("minute must be one of 00, 15, 30, 45")
    try:
        hour_int = int(normalized_hour)
    except (TypeError, ValueError) as exc:
        raise ValueError("hour must be a number between 01 and 12") from exc
    if hour_int < 1 or hour_int > 12:
        raise ValueError("hour must be between 01 and 12")

    return normalized_day, f"{hour_int:02d}", normalized_minute, normalized_ampm


def sort_timeslot_docs(docs: list[dict]) -> list[dict]:
    return sorted(
        docs,
        key=lambda doc: (
            DAY_INDEX.get(str(doc.get("day_of_week", "")).upper(), 99),
            to_24_hour(doc.get("hour", "12"), doc.get("ampm", "AM")),
            int(str(doc.get("minute", "00")).zfill(2)),
        ),
    )


def to_24_hour(hour: str, ampm: str) -> int:
    hour_value = int(str(hour).zfill(2))
    ampm_value = str(ampm).upper()
    if ampm_value == "PM" and hour_value != 12:
        hour_value += 12
    if ampm_value == "AM" and hour_value == 12:
        hour_value = 0
    return hour_value


def minute_key(dt: datetime) -> str:
    normalized = dt.astimezone(timezone.utc).replace(second=0, microsecond=0)
    return normalized.isoformat()


def build_day_map(timeslots: list[dict]) -> dict[str, list[tuple[int, int]]]:
    day_map: dict[str, list[tuple[int, int]]] = {}
    for slot in timeslots:
        hour_24 = to_24_hour(slot["hour"], slot["ampm"])
        minute = int(str(slot["minute"]).zfill(2))
        day = str(slot["day_of_week"]).upper()
        day_map.setdefault(day, []).append((hour_24, minute))
    for day in day_map:
        day_map[day].sort()
    return day_map


async def collect_occupied_slot_keys(
    db,
    workspace_id: str,
    account_id: str,
    *,
    now: datetime,
    horizon_days: int = 60,
) -> set[str]:
    future = now + timedelta(days=horizon_days)
    cursor = db.posts.find(
        {
            "workspace_id": workspace_id,
            "status": "scheduled",
            "scheduled_time": {"$gte": now.isoformat(), "$lte": future.isoformat()},
            "$or": [
                {"account_ids": account_id},
                {"social_account_ids": account_id},
                {"platform_account_ids": account_id},
                {"social_account_id": account_id},
                {"publish_targets": {"$elemMatch": {"account_id": account_id}}},
            ],
        },
        {"_id": 0, "scheduled_time": 1},
    )
    occupied: set[str] = set()
    for post in await cursor.to_list(None):
        scheduled = post.get("scheduled_time")
        if not scheduled:
            continue
        try:
            dt = (
                scheduled
                if isinstance(scheduled, datetime)
                else datetime.fromisoformat(str(scheduled).replace("Z", "+00:00"))
            )
        except ValueError:
            continue
        occupied.add(minute_key(dt))
    return occupied


def find_next_available_timeslot(
    timeslots: list[dict],
    occupied_keys: set[str],
    *,
    now: datetime,
    horizon_days: int = 60,
) -> datetime | None:
    if not timeslots:
        return None

    day_map = build_day_map(timeslots)
    check_date = now.date()
    for _ in range(horizon_days):
        day_name = check_date.strftime("%A").upper()
        for hour_24, minute in day_map.get(day_name, []):
            candidate = datetime(
                check_date.year,
                check_date.month,
                check_date.day,
                hour_24,
                minute,
                tzinfo=timezone.utc,
            )
            if candidate <= now:
                continue
            if minute_key(candidate) not in occupied_keys:
                return candidate
        check_date += timedelta(days=1)
    return None


async def resolve_next_timeslot_for_account(
    db,
    workspace_id: str,
    account_id: str,
    category: str | None,
    *,
    now: datetime | None = None,
    reserved_keys: set[str] | None = None,
    horizon_days: int = 60,
) -> tuple[datetime | None, str | None, str]:
    effective_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    normalized_category = normalize_timeslot_category(category)
    cursor = db.timeslots.find(
        {
            "workspace_id": workspace_id,
            "account_id": account_id,
            "category": normalized_category,
        },
        {"_id": 0},
    )
    timeslot_docs = sort_timeslot_docs(await cursor.to_list(None))
    if not timeslot_docs:
        return None, "No timeslots configured for this account", normalized_category

    occupied = await collect_occupied_slot_keys(
        db,
        workspace_id,
        account_id,
        now=effective_now,
        horizon_days=horizon_days,
    )
    if reserved_keys:
        occupied.update(reserved_keys)

    next_slot = find_next_available_timeslot(
        timeslot_docs,
        occupied,
        now=effective_now,
        horizon_days=horizon_days,
    )
    if next_slot is None:
        return None, "No available slot found in the next 60 days", normalized_category
    return next_slot, None, normalized_category
