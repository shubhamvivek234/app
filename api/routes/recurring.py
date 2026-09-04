"""Recurring post rules — CRUD."""
import logging
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from api.deps import CurrentUser, DB, VerifiedUser

logger = logging.getLogger(__name__)
router = APIRouter(tags=["recurring"])

VALID_FREQUENCIES = {"daily", "weekly", "monthly", "custom"}


class RecurringRuleCreate(BaseModel):
    name: str = ""
    content: str = ""
    platforms: list[str] = []
    accounts: list[str] = []
    post_type: str = "text"
    media_urls: list[str] = []
    frequency: str = "weekly"
    interval: int = 1
    days_of_week: list[int | str] = []
    day_of_month: int = 1
    time_of_day: str = "09:00"
    timezone: str = "UTC"
    start_date: str | None = None
    end_date: str | None = None
    is_active: bool = True
    status: str | None = None
    ai_remix: bool = False


class RecurringRuleUpdate(BaseModel):
    name: str | None = None
    content: str | None = None
    platforms: list[str] | None = None
    accounts: list[str] | None = None
    post_type: str | None = None
    media_urls: list[str] | None = None
    frequency: str | None = None
    interval: int | None = None
    days_of_week: list[int | str] | None = None
    day_of_month: int | None = None
    time_of_day: str | None = None
    timezone: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    is_active: bool | None = None
    status: str | None = None
    ai_remix: bool | None = None


def compute_first_scheduled_time(
    frequency: str,
    time_of_day: str,
    days_of_week: list[int | str] | None = None,
    day_of_month: int = 1,
) -> datetime:
    now = datetime.now(timezone.utc)
    try:
        hour, minute = map(int, (time_of_day or "09:00").split(":"))
    except Exception:
        hour, minute = 9, 0

    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)

    if frequency == "daily":
        return candidate
    elif frequency == "weekly":
        target_days = []
        for d in (days_of_week or []):
            try:
                target_days.append(int(d))
            except (ValueError, TypeError):
                pass
        if not target_days:
            target_days = [1]  # Monday default

        for _ in range(14):
            if int(candidate.strftime("%w")) in target_days:
                return candidate
            candidate += timedelta(days=1)
        return candidate
    elif frequency == "monthly":
        target_dom = max(1, min(day_of_month or 1, 28))
        candidate = candidate.replace(day=target_dom)
        if candidate <= now:
            month = candidate.month + 1
            year = candidate.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            candidate = candidate.replace(year=year, month=month, day=target_dom)
        return candidate
    return candidate


@router.get("/recurring-rules")
async def list_recurring_rules(current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    cursor = db.recurring_rules.find({"workspace_id": workspace_id}, {"_id": 0}).sort("created_at", -1)
    docs = await cursor.to_list(None)
    for d in docs:
        rule_id = d.get("rule_id") or d.get("id") or ""
        d.setdefault("id", rule_id)
        if "status" not in d:
            d["status"] = "active" if d.get("is_active", True) else "paused"
        d["is_active"] = (d["status"] == "active")

        template_id = f"tmpl_rule_{rule_id}"
        count = await db.posts.count_documents({
            "$or": [
                {"recurrence_template_id": template_id},
                {"recurrence_template_id": rule_id},
                {"recurrence_rule_id": rule_id},
            ],
            "status": "scheduled",
        })
        d["upcoming_count"] = count
    return docs


@router.post("/recurring-rules", status_code=status.HTTP_201_CREATED)
async def create_recurring_rule(body: RecurringRuleCreate, current_user: VerifiedUser, db: DB):
    if body.frequency not in VALID_FREQUENCIES:
        raise HTTPException(status_code=422, detail=f"frequency must be one of {sorted(VALID_FREQUENCIES)}")

    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    now = datetime.now(timezone.utc)
    rule_id = str(uuid.uuid4())

    name = (body.name or "").strip()
    if not name:
        clean_content = (body.content or "").strip()
        name = (clean_content[:40] + ("..." if len(clean_content) > 40 else "")) or "Recurring Rule"

    if body.status:
        is_active = (body.status.lower() == "active")
        rule_status = "active" if is_active else "paused"
    else:
        is_active = bool(body.is_active)
        rule_status = "active" if is_active else "paused"

    first_run = compute_first_scheduled_time(
        frequency=body.frequency,
        time_of_day=body.time_of_day,
        days_of_week=body.days_of_week,
        day_of_month=body.day_of_month,
    )

    rule_doc = {
        "rule_id": rule_id,
        "id": rule_id,
        "name": name,
        "content": body.content,
        "platforms": body.platforms,
        "accounts": body.accounts,
        "post_type": body.post_type,
        "media_urls": body.media_urls,
        "frequency": body.frequency,
        "interval": body.interval,
        "days_of_week": body.days_of_week,
        "day_of_month": body.day_of_month,
        "time_of_day": body.time_of_day,
        "timezone": body.timezone,
        "start_date": body.start_date,
        "end_date": body.end_date,
        "is_active": is_active,
        "status": rule_status,
        "ai_remix": body.ai_remix,
        "workspace_id": workspace_id,
        "user_id": current_user["user_id"],
        "created_at": now,
        "updated_at": now,
    }
    await db.recurring_rules.insert_one(rule_doc)

    template_id = f"tmpl_rule_{rule_id}"
    template_post = {
        "_id": template_id,
        "id": template_id,
        "recurrence_rule_id": rule_id,
        "user_id": current_user["user_id"],
        "workspace_id": workspace_id,
        "content": body.content,
        "platforms": body.platforms,
        "account_ids": body.accounts,
        "post_type": body.post_type,
        "media_urls": body.media_urls,
        "status": "template",
        "scheduled_time": first_run,
        "recurrence": {
            "enabled": is_active,
            "frequency": body.frequency,
            "interval": body.interval,
            "ai_remix": body.ai_remix,
            "anchor_day": body.day_of_month,
            "days_of_week": body.days_of_week,
            "time_of_day": body.time_of_day,
        },
        "created_at": now,
        "updated_at": now,
    }
    await db.posts.insert_one(template_post)

    if is_active:
        try:
            from celery_workers.tasks.recurring import _async_spawn
            await _async_spawn(db)
        except Exception as spawn_err:
            logger.warning("Spawning instances for new rule %s warning: %s", rule_id, spawn_err)

    upcoming_count = await db.posts.count_documents({
        "$or": [
            {"recurrence_template_id": template_id},
            {"recurrence_rule_id": rule_id},
        ],
        "status": "scheduled",
    })
    rule_doc["upcoming_count"] = upcoming_count
    await db.recurring_rules.update_one({"rule_id": rule_id}, {"$set": {"upcoming_count": upcoming_count}})

    rule_doc.pop("_id", None)
    return rule_doc


@router.patch("/recurring-rules/{rule_id}")
async def update_recurring_rule(rule_id: str, body: RecurringRuleUpdate, current_user: VerifiedUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    now = datetime.now(timezone.utc)

    update_data = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if not update_data:
        rule = await db.recurring_rules.find_one(
            {"$or": [{"rule_id": rule_id}, {"id": rule_id}], "workspace_id": workspace_id},
            {"_id": 0},
        )
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")
        return rule

    if "frequency" in update_data and update_data["frequency"] not in VALID_FREQUENCIES:
        raise HTTPException(status_code=422, detail=f"frequency must be one of {sorted(VALID_FREQUENCIES)}")

    if "status" in update_data and "is_active" not in update_data:
        update_data["is_active"] = (update_data["status"] == "active")
    elif "is_active" in update_data and "status" not in update_data:
        update_data["status"] = "active" if update_data["is_active"] else "paused"

    update_data["updated_at"] = now

    result = await db.recurring_rules.find_one_and_update(
        {"$or": [{"rule_id": rule_id}, {"id": rule_id}], "workspace_id": workspace_id},
        {"$set": update_data},
        return_document=True,
        projection={"_id": 0},
    )
    if not result:
        raise HTTPException(status_code=404, detail="Rule not found")

    result.setdefault("id", result.get("rule_id", rule_id))
    is_active = result.get("is_active", True)
    result["status"] = "active" if is_active else "paused"

    # Sync template post in db.posts
    template_id = f"tmpl_rule_{rule_id}"
    recurrence_update = {}
    if "is_active" in update_data:
        recurrence_update["recurrence.enabled"] = update_data["is_active"]
    if "frequency" in update_data:
        recurrence_update["recurrence.frequency"] = update_data["frequency"]
    if "ai_remix" in update_data:
        recurrence_update["recurrence.ai_remix"] = update_data["ai_remix"]
    if "day_of_month" in update_data:
        recurrence_update["recurrence.anchor_day"] = update_data["day_of_month"]
    if "days_of_week" in update_data:
        recurrence_update["recurrence.days_of_week"] = update_data["days_of_week"]
    if "time_of_day" in update_data:
        recurrence_update["recurrence.time_of_day"] = update_data["time_of_day"]

    post_updates = {**recurrence_update, "updated_at": now}
    if "content" in update_data:
        post_updates["content"] = update_data["content"]
    if "platforms" in update_data:
        post_updates["platforms"] = update_data["platforms"]
    if "accounts" in update_data:
        post_updates["account_ids"] = update_data["accounts"]

    await db.posts.update_one(
        {"$or": [{"_id": template_id}, {"id": template_id}, {"recurrence_rule_id": rule_id}], "status": "template"},
        {"$set": post_updates},
    )

    if not is_active:
        # Pause: delete future scheduled instances
        await db.posts.delete_many({
            "$or": [{"recurrence_template_id": template_id}, {"recurrence_rule_id": rule_id}],
            "status": "scheduled",
        })
    else:
        # Resumed: spawn instances
        try:
            from celery_workers.tasks.recurring import _async_spawn
            await _async_spawn(db)
        except Exception as spawn_err:
            logger.warning("Spawning instances for resumed rule %s warning: %s", rule_id, spawn_err)

    count = await db.posts.count_documents({
        "$or": [
            {"recurrence_template_id": template_id},
            {"recurrence_rule_id": rule_id},
        ],
        "status": "scheduled",
    })
    result["upcoming_count"] = count

    return result


@router.delete("/recurring-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recurring_rule(rule_id: str, current_user: CurrentUser, db: DB):
    workspace_id = current_user.get("default_workspace_id") or current_user["user_id"]
    template_id = f"tmpl_rule_{rule_id}"

    result = await db.recurring_rules.delete_one(
        {"$or": [{"rule_id": rule_id}, {"id": rule_id}], "workspace_id": workspace_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Rule not found")

    await db.posts.delete_many({
        "$or": [{"_id": template_id}, {"id": template_id}, {"recurrence_rule_id": rule_id}],
        "status": "template",
    })
    await db.posts.delete_many({
        "$or": [{"recurrence_template_id": template_id}, {"recurrence_rule_id": rule_id}],
        "status": "scheduled",
    })

