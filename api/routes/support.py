"""Support and public contact form endpoints."""
import html
import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from api.deps import CurrentUser, DB
from api.limiter import limiter
from utils.email_service import send_email_or_raise_async

logger = logging.getLogger(__name__)
router = APIRouter(tags=["support"])

CONTACT_RECIPIENT_EMAIL = (os.environ.get("CONTACT_RECIPIENT_EMAIL") or "contact@unravler.com").strip() or "contact@unravler.com"


class SupportRequest(BaseModel):
    subject: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=2, max_length=4000)
    category: str = Field(default="general", max_length=120)
    email: EmailStr | None = None


class PublicContactRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    company: str | None = Field(default=None, max_length=120)
    topic: str = Field(default="General Inquiry", max_length=120)
    seats: str | int | None = Field(default=None)
    country: str | None = Field(default=None, max_length=80)
    message: str = Field(..., min_length=2, max_length=4000)
    attachment_name: str | None = Field(default=None, max_length=255)
    acknowledged_terms: bool = Field(default=True)
    honeypot: str | None = Field(default=None, max_length=200)


async def _dispatch_contact_notification_email(
    *,
    ticket_id: str,
    sender_name: str,
    sender_email: str,
    topic: str,
    message: str,
    company: str | None = None,
    seats: str | int | None = None,
    country: str | None = None,
    attachment_name: str | None = None,
) -> bool:
    outbound_from = (os.environ.get("SENDER_EMAIL") or CONTACT_RECIPIENT_EMAIL).strip()
    subject = f"[Unravler Contact {ticket_id}] {topic} — {sender_name}"
    safe_name = html.escape(sender_name)
    safe_email = html.escape(sender_email)
    safe_topic = html.escape(topic)
    safe_company = html.escape(company or "Not specified")
    safe_seats = html.escape(str(seats) if seats is not None else "Not specified")
    safe_country = html.escape(country or "Not specified")
    safe_attachment = html.escape(attachment_name or "None")
    safe_message = html.escape(message).replace("\n", "<br>")

    html_body = f"""\
<!DOCTYPE html>
<html lang="en">
  <body style="margin:0;padding:24px;background:#f8fafc;color:#0f172a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;margin:0 auto;background:#ffffff;border:1px solid #e2e8f0;border-radius:16px;overflow:hidden;">
      <tr>
        <td style="padding:24px 28px;background:#0f172a;color:#ffffff;">
          <p style="margin:0 0 4px 0;font-size:12px;letter-spacing:0.08em;text-transform:uppercase;color:#94a3b8;">Unravler Contact Desk</p>
          <h1 style="margin:0;font-size:20px;font-weight:700;">New Inquiry · {ticket_id}</h1>
        </td>
      </tr>
      <tr>
        <td style="padding:24px 28px;font-size:14px;line-height:1.6;color:#334155;">
          <p style="margin:0 0 8px 0;"><strong>From:</strong> {safe_name} (<a href="mailto:{safe_email}" style="color:#0062ff;">{safe_email}</a>)</p>
          <p style="margin:0 0 8px 0;"><strong>Topic:</strong> {safe_topic}</p>
          <p style="margin:0 0 8px 0;"><strong>Company / Workspace:</strong> {safe_company}</p>
          <p style="margin:0 0 8px 0;"><strong>Requested Seats / Country:</strong> {safe_seats} · {safe_country}</p>
          <p style="margin:0 0 16px 0;"><strong>Attachment Reference:</strong> {safe_attachment}</p>
          <div style="padding:16px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;color:#0f172a;">
            {safe_message}
          </div>
        </td>
      </tr>
    </table>
  </body>
</html>
"""
    text_body = (
        f"New Unravler Contact Inquiry ({ticket_id})\n"
        f"To: {CONTACT_RECIPIENT_EMAIL}\n"
        f"From: {sender_name} <{sender_email}>\n"
        f"Topic: {topic}\n"
        f"Company: {company or 'Not specified'}\n"
        f"Requested Seats: {seats if seats is not None else 'Not specified'}\n"
        f"Country: {country or 'Not specified'}\n"
        f"Attachment: {attachment_name or 'None'}\n\n"
        f"Message:\n{message}\n"
    )
    try:
        await send_email_or_raise_async(
            to=CONTACT_RECIPIENT_EMAIL,
            subject=subject,
            html=html_body,
            text=text_body,
            reply_to=sender_email,
            sender_email=outbound_from,
            sender_name="Unravler Contact Desk",
        )
        return True
    except Exception as exc:
        logger.warning(
            "Contact notification email fallback (stored in DB): ticket_id=%s err=%s",
            ticket_id,
            type(exc).__name__,
        )
        return False


@router.post("/support/contact", status_code=status.HTTP_201_CREATED)
async def submit_support_request(body: SupportRequest, current_user: CurrentUser, db: DB):
    now = datetime.now(timezone.utc)
    ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
    sender_email = str(body.email or current_user.get("email") or "unknown@unravler.com")
    sender_name = str(current_user.get("display_name") or sender_email)
    doc = {
        "ticket_id": ticket_id,
        "user_id": current_user["user_id"],
        "name": sender_name,
        "email": sender_email,
        "recipient_email": CONTACT_RECIPIENT_EMAIL,
        "subject": body.subject.strip(),
        "message": body.message.strip(),
        "category": body.category.strip(),
        "source": "authenticated_support",
        "status": "open",
        "created_at": now,
    }
    await db.support_tickets.insert_one(doc)
    doc.pop("_id", None)
    await _dispatch_contact_notification_email(
        ticket_id=ticket_id,
        sender_name=sender_name,
        sender_email=sender_email,
        topic=body.subject.strip(),
        message=body.message.strip(),
    )
    logger.info("Support ticket created: %s user=%s", ticket_id, current_user["user_id"])
    return {
        "ticket_id": ticket_id,
        "recipient_email": CONTACT_RECIPIENT_EMAIL,
        "status": "open",
        "message": "Your request has been received. Our team at contact@unravler.com will respond within 24 hours.",
    }


@router.post("/support/public-contact", status_code=status.HTTP_201_CREATED)
@router.post("/contact", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def submit_public_contact_request(request: Request, body: PublicContactRequest, db: DB):
    now = datetime.now(timezone.utc)
    ticket_id = f"UNR-{uuid.uuid4().hex[:8].upper()}"

    # Honeypot check: silently succeed if automated bot filled the hidden field
    if body.honeypot and body.honeypot.strip():
        return {
            "ticket_id": ticket_id,
            "recipient_email": CONTACT_RECIPIENT_EMAIL,
            "status": "received",
            "message": "Thank you! Your message has been sent to contact@unravler.com. We will get back to you within 24 hours.",
        }

    if not body.acknowledged_terms:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Please acknowledge the Terms of Service and Privacy Policy before submitting.",
        )

    clean_name = body.name.strip()
    clean_email = str(body.email).strip()
    clean_topic = (body.topic or "General Inquiry").strip()
    clean_message = body.message.strip()
    clean_company = body.company.strip() if body.company else None
    clean_country = body.country.strip() if body.country else None
    clean_attachment = body.attachment_name.strip() if body.attachment_name else None

    email_dispatched = await _dispatch_contact_notification_email(
        ticket_id=ticket_id,
        sender_name=clean_name,
        sender_email=clean_email,
        topic=clean_topic,
        message=clean_message,
        company=clean_company,
        seats=body.seats,
        country=clean_country,
        attachment_name=clean_attachment,
    )

    doc = {
        "ticket_id": ticket_id,
        "user_id": None,
        "name": clean_name,
        "email": clean_email,
        "company": clean_company,
        "topic": clean_topic,
        "subject": clean_topic,
        "seats": body.seats,
        "country": clean_country,
        "message": clean_message,
        "attachment_name": clean_attachment,
        "acknowledged_terms": True,
        "recipient_email": CONTACT_RECIPIENT_EMAIL,
        "email_dispatched": email_dispatched,
        "source": "public_contact_form",
        "status": "open",
        "created_at": now,
    }
    await db.support_tickets.insert_one(doc)
    logger.info(
        "Public contact inquiry received: ticket_id=%s topic=%s email_dispatched=%s",
        ticket_id,
        clean_topic,
        email_dispatched,
    )
    return {
        "ticket_id": ticket_id,
        "recipient_email": CONTACT_RECIPIENT_EMAIL,
        "email_dispatched": email_dispatched,
        "status": "received",
        "message": "Thank you! Your message has been sent to contact@unravler.com. Our team will get back to you within 24 hours.",
    }
