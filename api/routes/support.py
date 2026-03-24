"""Support contact form."""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, status
from pydantic import BaseModel, EmailStr

from api.deps import CurrentUser, DB

logger = logging.getLogger(__name__)
router = APIRouter(tags=["support"])


class SupportRequest(BaseModel):
    subject: str
    message: str
    category: str = "general"
    email: EmailStr | None = None


@router.post("/support/contact", status_code=status.HTTP_201_CREATED)
async def submit_support_request(body: SupportRequest, current_user: CurrentUser, db: DB):
    now = datetime.now(timezone.utc)
    ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
    doc = {
        "ticket_id": ticket_id,
        "user_id": current_user["user_id"],
        "email": body.email or current_user.get("email"),
        "subject": body.subject,
        "message": body.message,
        "category": body.category,
        "status": "open",
        "created_at": now,
    }
    await db.support_tickets.insert_one(doc)
    doc.pop("_id", None)
    logger.info("Support ticket created: %s user=%s", ticket_id, current_user["user_id"])
    return {"ticket_id": ticket_id, "status": "open", "message": "Your request has been received. We'll respond within 24 hours."}
