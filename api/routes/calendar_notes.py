"""Calendar notes — CRUD + public calendar share."""
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, model_validator

from api.deps import CurrentUser, DB

logger = logging.getLogger(__name__)
router = APIRouter(tags=["calendar"])


_CALENDAR_NOTE_COLOR_ALIASES = {
    "#4caf50": "green",
    "#2196f3": "blue",
    "#ffc107": "yellow",
    "#f44336": "red",
    "green": "green",
    "emerald": "green",
    "blue": "blue",
    "sky": "blue",
    "yellow": "yellow",
    "amber": "yellow",
    "red": "red",
    "rose": "red",
}


def _normalize_calendar_note_color(color: str | None) -> str:
    value = str(color or "").strip().lower()
    return _CALENDAR_NOTE_COLOR_ALIASES.get(value, "green")


def _serialize_calendar_note(doc: dict) -> dict:
    note_value = str(doc.get("note") or doc.get("text") or "").strip()
    serialized = dict(doc)
    serialized.setdefault("id", serialized.get("note_id", ""))
    serialized["note"] = note_value
    serialized["text"] = note_value
    serialized["color"] = _normalize_calendar_note_color(serialized.get("color"))
    return serialized


class CalendarNoteCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    date: str          # YYYY-MM-DD
    note: str | None = None
    text: str | None = None
    color: str = "green"

    @model_validator(mode="after")
    def _normalize_fields(self):
        note_value = str(self.note or self.text or "").strip()
        if not note_value:
            raise ValueError("note is required")
        self.note = note_value
        self.text = note_value
        self.color = _normalize_calendar_note_color(self.color)
        return self


class CalendarShareCreate(BaseModel):
    expires_days: int = 30
    regenerate: bool = False


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
    return [_serialize_calendar_note(doc) for doc in docs]


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
    return _serialize_calendar_note(doc)


@router.delete("/calendar/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_calendar_note(note_id: str, current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    result = await db.calendar_notes.delete_one(
        {"$or": [{"note_id": note_id}, {"id": note_id}], "workspace_id": workspace_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Note not found")


@router.get("/calendar/share")
async def get_calendar_share(current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    now = datetime.now(timezone.utc)
    existing = await db.calendar_shares.find_one(
        {"workspace_id": workspace_id, "expires_at": {"$gt": now.isoformat()}},
        {"_id": 0},
    )
    if existing:
        return {"token": existing["token"], "expires_at": existing["expires_at"]}
    return {"token": None, "expires_at": None}


@router.post("/calendar/share")
async def create_calendar_share(
    current_user: CurrentUser,
    db: DB,
    body: CalendarShareCreate | None = None,
):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    req = body or CalendarShareCreate()
    expires_days = req.expires_days if req.expires_days > 0 else 30
    now = datetime.now(timezone.utc)

    # Return existing unexpired token if regeneration not requested
    if not req.regenerate:
        existing = await db.calendar_shares.find_one(
            {"workspace_id": workspace_id, "expires_at": {"$gt": now.isoformat()}},
            {"_id": 0},
        )
        if existing:
            return {"token": existing["token"], "expires_at": existing["expires_at"]}

    token = secrets.token_urlsafe(24)
    doc = {
        "token": token,
        "workspace_id": workspace_id,
        "created_by": current_user["user_id"],
        "expires_at": (now + timedelta(days=expires_days)).isoformat(),
        "created_at": now,
    }
    await db.calendar_shares.insert_one(doc)
    return {"token": token, "expires_at": doc["expires_at"]}


@router.delete("/calendar/share", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_calendar_share(current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    await db.calendar_shares.delete_many({"workspace_id": workspace_id})


@router.get("/calendar/public/{token}")
async def get_public_calendar(token: str, db: DB):
    now = datetime.now(timezone.utc)
    share = await db.calendar_shares.find_one({"token": token}, {"_id": 0})
    if not share:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This calendar link is invalid or has been revoked.",
        )

    expires_at = share.get("expires_at")
    if expires_at:
        try:
            exp_dt = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if exp_dt < now:
                raise HTTPException(
                    status_code=status.HTTP_410_GONE,
                    detail="This calendar link has expired.",
                )
        except (ValueError, TypeError):
            pass

    workspace_id = share["workspace_id"]

    # Scheduled and published posts for this workspace (excluding soft-deleted)
    query = {
        "workspace_id": workspace_id,
        "deleted_at": {"$exists": False},
        "status": {"$in": ["scheduled", "published"]},
    }
    cursor = db.posts.find(query, {"_id": 0}).sort("scheduled_time", 1)
    posts_docs = await cursor.to_list(None)

    serialized_posts = []
    for doc in posts_docs:
        p = dict(doc)
        p["id"] = str(p.get("id") or p.get("post_id") or "")
        p.pop("deleted_at", None)
        for dt_key in ["scheduled_time", "published_at", "created_at", "updated_at"]:
            val = p.get(dt_key)
            if isinstance(val, datetime):
                p[dt_key] = val.isoformat()
        serialized_posts.append(p)

    # Calendar notes for this workspace
    notes_cursor = db.calendar_notes.find({"workspace_id": workspace_id}, {"_id": 0}).sort("date", 1)
    notes_docs = await notes_cursor.to_list(None)
    serialized_notes = [_serialize_calendar_note(n) for n in notes_docs]

    # Resolve workspace title/branding
    workspace_name = "Content Calendar"
    ws = await db.workspaces.find_one(
        {"$or": [{"_id": workspace_id}, {"workspace_id": workspace_id}]},
        {"_id": 0, "name": 1, "title": 1},
    )
    if ws:
        workspace_name = ws.get("name") or ws.get("title") or workspace_name
    else:
        user = await db.users.find_one(
            {"$or": [{"user_id": share.get("created_by")}, {"_id": share.get("created_by")}]},
            {"_id": 0, "display_name": 1, "name": 1, "workspace_name": 1},
        )
        if user:
            workspace_name = (
                user.get("workspace_name")
                or user.get("display_name")
                or user.get("name")
                or workspace_name
            )

    return {
        "posts": serialized_posts,
        "notes": serialized_notes,
        "workspace_name": workspace_name,
        "expires_at": expires_at,
    }
