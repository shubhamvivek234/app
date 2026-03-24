"""
Timeslots API — CRUD for predetermined posting time slots.
When a user creates a post with "Add to Timeslot", the scheduler
queries the next unfilled slot for the account and assigns scheduled_time.
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from api.deps import CurrentUser, DB

logger = logging.getLogger(__name__)
router = APIRouter(tags=["timeslots"])

VALID_DAYS = {"MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"}

# ── Models ────────────────────────────────────────────────────────────────────

class TimeslotCreate(BaseModel):
    account_id: str
    category: str = "Category 1"
    day_of_week: str         # MONDAY … SUNDAY
    hour: str                # "01"–"12"
    minute: str              # "00", "15", "30", "45"
    ampm: str                # "AM" | "PM"


class TimeslotResponse(BaseModel):
    id: str
    account_id: str
    category: str
    day_of_week: str
    hour: str
    minute: str
    ampm: str
    created_at: str


class TimeslotsListResponse(BaseModel):
    timeslots: list[TimeslotResponse]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _doc_to_response(doc: dict) -> TimeslotResponse:
    return TimeslotResponse(
        id=doc["timeslot_id"],
        account_id=doc["account_id"],
        category=doc.get("category", "Category 1"),
        day_of_week=doc["day_of_week"],
        hour=doc["hour"],
        minute=doc["minute"],
        ampm=doc["ampm"],
        created_at=doc.get("created_at", ""),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/timeslots", response_model=TimeslotsListResponse)
async def list_timeslots(
    current_user: CurrentUser,
    db: DB,
    account_id: str = Query(..., description="Social account ID"),
    category: str = Query("Category 1"),
):
    """Return all timeslots for a given account + category."""
    user_id = current_user.user_id
    workspace_id = current_user.workspace_id or user_id

    cursor = db.timeslots.find(
        {
            "workspace_id": workspace_id,
            "account_id": account_id,
            "category": category,
        },
        {"_id": 0},
    ).sort("day_of_week", 1)
    docs = await cursor.to_list(None)
    return TimeslotsListResponse(timeslots=[_doc_to_response(d) for d in docs])


@router.post("/timeslots", response_model=TimeslotResponse, status_code=status.HTTP_201_CREATED)
async def create_timeslot(
    body: TimeslotCreate,
    current_user: CurrentUser,
    db: DB,
):
    """Create a single timeslot."""
    user_id = current_user.user_id
    workspace_id = current_user.workspace_id or user_id

    if body.day_of_week.upper() not in VALID_DAYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid day_of_week: {body.day_of_week}. Must be one of {sorted(VALID_DAYS)}",
        )
    if body.ampm not in ("AM", "PM"):
        raise HTTPException(status_code=422, detail="ampm must be 'AM' or 'PM'")

    # Prevent exact duplicate
    existing = await db.timeslots.find_one({
        "workspace_id": workspace_id,
        "account_id": body.account_id,
        "category": body.category,
        "day_of_week": body.day_of_week.upper(),
        "hour": body.hour,
        "minute": body.minute,
        "ampm": body.ampm,
    })
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An identical timeslot already exists for this account",
        )

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "timeslot_id": str(uuid.uuid4()),
        "user_id": user_id,
        "workspace_id": workspace_id,
        "account_id": body.account_id,
        "category": body.category,
        "day_of_week": body.day_of_week.upper(),
        "hour": body.hour,
        "minute": body.minute,
        "ampm": body.ampm,
        "created_at": now,
        "updated_at": now,
    }
    await db.timeslots.insert_one(doc)
    logger.info("Timeslot created: user=%s account=%s day=%s time=%s:%s%s",
                user_id, body.account_id, body.day_of_week, body.hour, body.minute, body.ampm)
    return _doc_to_response(doc)


@router.delete("/timeslots/{timeslot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_timeslot(
    timeslot_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """Delete a single timeslot by ID."""
    user_id = current_user.user_id
    workspace_id = current_user.workspace_id or user_id

    result = await db.timeslots.delete_one({
        "timeslot_id": timeslot_id,
        "workspace_id": workspace_id,
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Timeslot not found")


@router.delete("/timeslots", status_code=status.HTTP_204_NO_CONTENT)
async def clear_timeslots(
    current_user: CurrentUser,
    db: DB,
    account_id: str = Query(...),
    category: str = Query("Category 1"),
):
    """Delete all timeslots for an account + category."""
    workspace_id = current_user.workspace_id or current_user.user_id
    await db.timeslots.delete_many({
        "workspace_id": workspace_id,
        "account_id": account_id,
        "category": category,
    })


@router.get("/timeslots/next-slot")
async def get_next_slot(
    current_user: CurrentUser,
    db: DB,
    account_id: str = Query(...),
    category: str = Query("Category 1"),
):
    """
    Return the next unfilled timeslot datetime for 'Add to Timeslot' post creation.
    Scans forward from now through the weekly schedule until an empty slot is found.
    """
    from datetime import date
    import calendar

    workspace_id = current_user.workspace_id or current_user.user_id
    cursor = db.timeslots.find(
        {"workspace_id": workspace_id, "account_id": account_id, "category": category},
        {"_id": 0},
    )
    all_slots = await cursor.to_list(None)
    if not all_slots:
        return {"next_slot": None, "message": "No timeslots configured for this account"}

    # Build a dict: day_of_week → sorted list of (hour24, minute)
    day_map: dict[str, list[tuple[int, int]]] = {}
    for s in all_slots:
        h = int(s["hour"])
        m = int(s["minute"])
        if s["ampm"] == "PM" and h != 12:
            h += 12
        if s["ampm"] == "AM" and h == 12:
            h = 0
        day_map.setdefault(s["day_of_week"], []).append((h, m))
    for day in day_map:
        day_map[day].sort()

    # Fetch scheduled posts for this account in the next 60 days
    now = datetime.now(timezone.utc)
    future = (now + timedelta(days=60)).isoformat()
    taken_cursor = db.posts.find(
        {
            "workspace_id": workspace_id,
            "account_ids": account_id,
            "status": "scheduled",
            "scheduled_time": {"$gte": now.isoformat(), "$lte": future},
        },
        {"_id": 0, "scheduled_time": 1},
    )
    taken_posts = await taken_cursor.to_list(None)
    taken_minutes = set()
    for p in taken_posts:
        if p.get("scheduled_time"):
            try:
                dt = datetime.fromisoformat(p["scheduled_time"].replace("Z", "+00:00"))
                # Round to nearest minute for comparison
                taken_minutes.add(dt.replace(second=0, microsecond=0).isoformat())
            except ValueError:
                pass

    # Scan forward
    from datetime import timedelta
    check_date = now.date()
    for _ in range(60):
        day_name = check_date.strftime("%A").upper()
        times = day_map.get(day_name, [])
        for (h, m) in times:
            candidate = datetime(
                check_date.year, check_date.month, check_date.day, h, m,
                tzinfo=timezone.utc,
            )
            if candidate <= now:
                continue
            key = candidate.replace(second=0, microsecond=0).isoformat()
            if key not in taken_minutes:
                return {"next_slot": candidate.isoformat(), "day": day_name, "time": f"{h:02d}:{m:02d}"}
        check_date = date.fromordinal(check_date.toordinal() + 1)

    return {"next_slot": None, "message": "No available slot found in the next 60 days"}
