"""Recurring post rules — CRUD."""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from api.deps import CurrentUser, DB

logger = logging.getLogger(__name__)
router = APIRouter(tags=["recurring"])

VALID_FREQUENCIES = {"daily", "weekly", "monthly", "custom"}


class RecurringRuleCreate(BaseModel):
    name: str
    content: str = ""
    platforms: list[str] = []
    frequency: str = "weekly"
    interval: int = 1
    days_of_week: list[str] = []
    time_of_day: str = "09:00"
    timezone: str = "UTC"
    start_date: str | None = None
    end_date: str | None = None
    is_active: bool = True


@router.get("/recurring-rules")
async def list_recurring_rules(current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    cursor = db.recurring_rules.find({"workspace_id": workspace_id}, {"_id": 0}).sort("created_at", -1)
    docs = await cursor.to_list(None)
    for d in docs:
        d.setdefault("id", d.get("rule_id", ""))
    return docs


@router.post("/recurring-rules", status_code=status.HTTP_201_CREATED)
async def create_recurring_rule(body: RecurringRuleCreate, current_user: CurrentUser, db: DB):
    if body.frequency not in VALID_FREQUENCIES:
        raise HTTPException(status_code=422, detail=f"frequency must be one of {sorted(VALID_FREQUENCIES)}")
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    now = datetime.now(timezone.utc)
    rule_id = str(uuid.uuid4())
    doc = {
        "rule_id": rule_id,
        "id": rule_id,
        **body.model_dump(),
        "workspace_id": workspace_id,
        "user_id": current_user["user_id"],
        "created_at": now,
        "updated_at": now,
    }
    await db.recurring_rules.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/recurring-rules/{rule_id}")
async def update_recurring_rule(rule_id: str, body: RecurringRuleCreate, current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    now = datetime.now(timezone.utc)
    result = await db.recurring_rules.find_one_and_update(
        {"$or": [{"rule_id": rule_id}, {"id": rule_id}], "workspace_id": workspace_id},
        {"$set": {**body.model_dump(), "updated_at": now}},
        return_document=True,
        projection={"_id": 0},
    )
    if not result:
        raise HTTPException(status_code=404, detail="Rule not found")
    result.setdefault("id", result.get("rule_id", rule_id))
    return result


@router.delete("/recurring-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recurring_rule(rule_id: str, current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    result = await db.recurring_rules.delete_one(
        {"$or": [{"rule_id": rule_id}, {"id": rule_id}], "workspace_id": workspace_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Rule not found")
