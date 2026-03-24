"""Calendar notes — CRUD + public calendar share."""
import logging
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from api.deps import CurrentUser, DB

logger = logging.getLogger(__name__)
router = APIRouter(tags=["calendar"])


class CalendarNoteCreate(BaseModel):
    date: str          # YYYY-MM-DD
    note: str
    color: str = "#4CAF50"


class CalendarShareCreate(BaseModel):
    expires_days: int = 30


@router.get("/calendar/notes")
async def list_calendar_notes(
    current_user: CurrentUser,
    db: DB,
    month: str = Query(None, description="YYYY-MM filter"),
):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    query: dict = {"workspace_id": workspace_id}
    if month:
        query["date"] = {"$regex": f"^{month}"}
    cursor = db.calendar_notes.find(query, {"_id": 0}).sort("date", 1)
    docs = await cursor.to_list(None)
    for d in docs:
        d.setdefault("id", d.get("note_id", ""))
    return docs


@router.post("/calendar/notes", status_code=status.HTTP_201_CREATED)
async def create_calendar_note(body: CalendarNoteCreate, current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    now = datetime.now(timezone.utc)
    note_id = str(uuid.uuid4())
    doc = {
        "note_id": note_id,
        "id": note_id,
        "workspace_id": workspace_id,
        "user_id": current_user["user_id"],
        "date": body.date,
        "note": body.note,
        "color": body.color,
        "created_at": now,
    }
    await db.calendar_notes.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/calendar/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_calendar_note(note_id: str, current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    result = await db.calendar_notes.delete_one(
        {"$or": [{"note_id": note_id}, {"id": note_id}], "workspace_id": workspace_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Note not found")


@router.post("/calendar/share")
async def create_calendar_share(body: CalendarShareCreate, current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(24)
    doc = {
        "token": token,
        "workspace_id": workspace_id,
        "created_by": current_user["user_id"],
        "expires_at": (now + timedelta(days=body.expires_days)).isoformat(),
        "created_at": now,
    }
    await db.calendar_shares.insert_one(doc)
    return {"token": token, "expires_at": doc["expires_at"]}
