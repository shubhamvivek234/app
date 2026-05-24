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
from utils.timeslots import (
    normalize_timeslot_category,
    normalize_timeslot_clock,
    resolve_next_timeslot_for_account,
    sort_timeslot_docs,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["timeslots"])

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


async def _ensure_owned_account(db, current_user: CurrentUser, account_id: str) -> str:
    user_id = current_user.user_id
    workspace_id = current_user.workspace_id or user_id
    account = await db.social_accounts.find_one(
        {
            "workspace_id": workspace_id,
            "is_active": True,
            "$or": [
                {"account_id": account_id},
                {"id": account_id},
            ],
        },
        {"_id": 0, "account_id": 1, "id": 1},
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Social account not found")
    return account.get("account_id") or account.get("id") or account_id


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/timeslots", response_model=TimeslotsListResponse)
async def list_timeslots(
    current_user: CurrentUser,
    db: DB,
    account_id: str = Query(..., description="Social account ID"),
    category: str = Query("Category 1"),
):
    """Return all timeslots for a given account + category."""
    workspace_id = current_user.workspace_id or current_user.user_id
    canonical_account_id = await _ensure_owned_account(db, current_user, account_id)
    try:
        normalized_category = normalize_timeslot_category(category)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    cursor = db.timeslots.find(
        {
            "workspace_id": workspace_id,
            "account_id": canonical_account_id,
            "category": normalized_category,
        },
        {"_id": 0},
    )
    docs = sort_timeslot_docs(await cursor.to_list(None))
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
    canonical_account_id = await _ensure_owned_account(db, current_user, body.account_id)
    try:
        normalized_day, normalized_hour, normalized_minute, normalized_ampm = normalize_timeslot_clock(
            body.day_of_week,
            body.hour,
            body.minute,
            body.ampm,
        )
        normalized_category = normalize_timeslot_category(body.category)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    # Prevent exact duplicate
    existing = await db.timeslots.find_one({
        "workspace_id": workspace_id,
        "account_id": canonical_account_id,
        "category": normalized_category,
        "day_of_week": normalized_day,
        "hour": normalized_hour,
        "minute": normalized_minute,
        "ampm": normalized_ampm,
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
        "account_id": canonical_account_id,
        "category": normalized_category,
        "day_of_week": normalized_day,
        "hour": normalized_hour,
        "minute": normalized_minute,
        "ampm": normalized_ampm,
        "created_at": now,
        "updated_at": now,
    }
    await db.timeslots.insert_one(doc)
    logger.info("Timeslot created: user=%s account=%s day=%s time=%s:%s%s",
                user_id, canonical_account_id, normalized_day, normalized_hour, normalized_minute, normalized_ampm)
    return _doc_to_response(doc)


@router.delete("/timeslots/{timeslot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_timeslot(
    timeslot_id: str,
    current_user: CurrentUser,
    db: DB,
):
    """Delete a single timeslot by ID."""
    workspace_id = current_user.workspace_id or current_user.user_id

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
    canonical_account_id = await _ensure_owned_account(db, current_user, account_id)
    try:
        normalized_category = normalize_timeslot_category(category)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    await db.timeslots.delete_many({
        "workspace_id": workspace_id,
        "account_id": canonical_account_id,
        "category": normalized_category,
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
    workspace_id = current_user.workspace_id or current_user.user_id
    canonical_account_id = await _ensure_owned_account(db, current_user, account_id)
    try:
        next_slot, message, normalized_category = await resolve_next_timeslot_for_account(
            db,
            workspace_id,
            canonical_account_id,
            category,
            now=datetime.now(timezone.utc),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if next_slot is None:
        return {
            "next_slot": None,
            "message": message,
            "category": normalized_category,
        }

    day_name = next_slot.strftime("%A").upper()
    return {
        "next_slot": next_slot.isoformat(),
        "day": day_name,
        "time": next_slot.strftime("%H:%M"),
        "category": normalized_category,
    }
