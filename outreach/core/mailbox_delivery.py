"""Idempotent one-to-one provider-accepted email sends from outreach workers."""
from __future__ import annotations

import base64
import hashlib
import os
from datetime import datetime, timezone
from email.message import EmailMessage
from email.policy import SMTP

import httpx
from pymongo.errors import DuplicateKeyError

from outreach.core.email_finder import is_lead_email_available, normalize_email
from outreach.core.mailbox_connection import get_mailbox_access_token, get_ready_mailbox


GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
GRAPH_SEND_URL = "https://graph.microsoft.com/v1.0/me/sendMail"


def _message_id(operation_id: str) -> str:
    digest = hashlib.sha256(operation_id.encode("utf-8")).hexdigest()[:40]
    return f"<{digest}@mail.unravler.com>"


def _mime_message(sender: str, recipient: str, subject: str, body: str, message_id: str) -> bytes:
    message = EmailMessage(policy=SMTP)
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message["Message-ID"] = message_id
    message["X-Unravler-Operation"] = message_id.strip("<>").split("@")[0]
    message.set_content(body.rstrip() + "\n\nIf you do not want follow-ups, reply STOP.\n")
    return message.as_bytes()


async def _post_provider_message(provider: str, token: str, mime: bytes) -> httpx.Response:
    async with httpx.AsyncClient(timeout=25) as client:
        if provider == "gmail":
            return await client.post(
                GMAIL_SEND_URL,
                headers={"Authorization": f"Bearer {token}"},
                json={"raw": base64.urlsafe_b64encode(mime).rstrip(b"=").decode("ascii")},
            )
        if provider == "microsoft":
            # Graph accepts base64-encoded MIME and replies with 202 but no ID.
            return await client.post(
                GRAPH_SEND_URL,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "text/plain"},
                content=base64.b64encode(mime).decode("ascii"),
            )
    raise ValueError("Unsupported mailbox provider")


def _public_result(operation: dict) -> dict:
    result = {"status": operation.get("status", "uncertain")}
    if operation.get("provider_message_id"):
        result["provider_message_id"] = operation["provider_message_id"]
    if operation.get("provider_thread_id"):
        result["provider_thread_id"] = operation["provider_thread_id"]
    if operation.get("reason"):
        result["reason"] = operation["reason"]
    return result


async def _record_result(db, query: dict, updates: dict) -> bool:
    try:
        result = await db.outreach_email_operations.update_one(query, {"$set": updates})
        return bool(getattr(result, "modified_count", 1))
    except Exception:
        return False


async def _eligible_lead(db, workspace_id: str, sender_account_id: str,
                         lead_id: str, recipient: str) -> dict | None:
    lead = await db.outreach_leads.find_one({
        "workspace_id": workspace_id, "id": lead_id, "assigned_account_id": sender_account_id,
    })
    if (not lead or lead.get("execution_state") not in {"queued", "waiting_delay"}
            or normalize_email(lead.get("email")) != recipient
            or not await is_lead_email_available(db, workspace_id, lead)):
        return None
    campaign_id = lead.get("campaign_id")
    if not campaign_id:
        return None
    campaign = await db.outreach_campaigns.find_one({
        "workspace_id": workspace_id, "id": campaign_id,
        "status": "active", "is_deleted": {"$ne": True},
    }, {"_id": 0, "id": 1, "status": 1, "is_deleted": 1})
    return lead if campaign and campaign.get("status") == "active" and not campaign.get("is_deleted") else None


async def send_outreach_email(
    db, *, workspace_id: str, sender_account_id: str, lead_id: str,
    to_email: str, subject: str, body: str, operation_id: str,
) -> dict:
    """Returns accepted, failed or uncertain; never claims delivery.

    The operation is inserted BEFORE contacting a provider. Any duplicate or
    ambiguous transport outcome is not blindly resent by a retrying worker.
    """
    if not operation_id or len(operation_id) > 200:
        return {"status": "failed", "reason": "A stable operation ID is required"}
    recipient = normalize_email(to_email)
    if not recipient or not subject.strip() or not body.strip() or len(subject) > 500 or len(body) > 20000:
        return {"status": "failed", "reason": "A valid recipient, subject and body are required"}
    op_key = f"email:{workspace_id}:{operation_id}"
    prior = await db.outreach_email_operations.find_one({"_id": op_key, "workspace_id": workspace_id})
    if prior:
        if prior.get("status") == "dispatching":
            return {"status": "uncertain", "reason": "Previous send outcome requires reconciliation"}
        return _public_result(prior)
    mailbox = await get_ready_mailbox(db, workspace_id, sender_account_id)
    if not mailbox:
        return {"status": "failed", "reason": "Paid mailbox access or reply sync is unavailable"}
    lead = await _eligible_lead(db, workspace_id, sender_account_id, lead_id, recipient)
    if not lead:
        return {"status": "failed", "reason": "Campaign or lead is no longer eligible to send"}
    now = datetime.now(timezone.utc)
    op = {
        "_id": op_key, "workspace_id": workspace_id, "sender_account_id": sender_account_id,
        "lead_id": lead_id, "campaign_id": lead.get("campaign_id"), "provider": mailbox["provider"],
        "recipient": recipient, "sender_email": mailbox["email"], "subject": subject.strip(),
        "message_id": _message_id(op_key), "status": "dispatching", "created_at": now,
    }
    try:
        await db.outreach_email_operations.insert_one(op)
    except DuplicateKeyError:
        prior = await db.outreach_email_operations.find_one({"_id": op_key, "workspace_id": workspace_id})
        if not prior:
            return {"status": "uncertain", "reason": "Existing send requires reconciliation"}
        if prior.get("status") == "dispatching":
            return {"status": "uncertain", "reason": "Previous send outcome requires reconciliation"}
        return _public_result(prior)
    except Exception:
        return {"status": "failed", "reason": "Send could not be recorded safely"}

    query = {"_id": op_key, "workspace_id": workspace_id, "status": "dispatching"}
    try:
        token = await get_mailbox_access_token(db, mailbox)
        # Paid period, reply sync, suppression or lead state could change during
        # token refresh. Perform every gate again immediately before POST.
        mailbox = await get_ready_mailbox(db, workspace_id, sender_account_id)
        lead = await _eligible_lead(db, workspace_id, sender_account_id, lead_id, recipient)
        if not mailbox or not lead:
            await _record_result(db, query, {"status": "failed", "reason": "Sender or lead became unavailable before send"})
            return {"status": "failed", "reason": "Sender or lead became unavailable before send"}
        mime = _mime_message(mailbox["email"], recipient, subject.strip(), body, op["message_id"])
        response = await _post_provider_message(mailbox["provider"], token, mime)
    except (httpx.TransportError, httpx.TimeoutException):
        await _record_result(db, query, {"status": "uncertain", "reason": "Provider request outcome is unknown"})
        return {"status": "uncertain", "reason": "Provider request outcome is unknown"}
    except Exception:
        await _record_result(db, query, {"status": "failed", "reason": "Mailbox is unavailable"})
        return {"status": "failed", "reason": "Mailbox is unavailable"}

    accepted = response.status_code == (200 if mailbox["provider"] == "gmail" else 202)
    provider_data: dict = {}
    if mailbox["provider"] == "gmail" and accepted:
        try:
            provider_data = response.json()
        except ValueError:
            provider_data = {}
        accepted = isinstance(provider_data, dict) and not provider_data.get("error") and bool(provider_data.get("id"))
    if not accepted:
        if response.status_code in {401, 403}:
            await db.outreach_mailboxes.update_one(
                {"workspace_id": workspace_id, "sender_account_id": sender_account_id},
                {"$set": {"status": "reauth_required", "updated_at": datetime.now(timezone.utc)}},
            )
        # A successful HTTP response with a malformed/missing provider ID may
        # still represent a sent message. Never classify it as a safe retry.
        status = "uncertain" if (response.status_code >= 500 or response.status_code == 429
                                 or 200 <= response.status_code < 300) else "failed"
        reason = "Provider acceptance was not confirmed" if status == "uncertain" else "Provider rejected the message"
        await _record_result(db, query, {"status": status, "reason": reason})
        return {"status": status, "reason": reason}
    updates = {"status": "accepted", "accepted_at": datetime.now(timezone.utc),
               "provider_message_id": provider_data.get("id") if mailbox["provider"] == "gmail" else None,
               "provider_thread_id": provider_data.get("threadId") if mailbox["provider"] == "gmail" else None}
    if not await _record_result(db, query, updates):
        return {"status": "uncertain", "reason": "Provider accepted message but confirmation needs reconciliation"}
    return _public_result(updates)
