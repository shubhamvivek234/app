"""Idempotent one-to-one provider-accepted email sends from outreach workers."""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timezone
from email.message import EmailMessage
from email.policy import SMTP

import httpx

from outreach.core.email_finder import is_lead_email_available, normalize_email
from outreach.core.mailbox_connection import get_mailbox_access_token, get_ready_mailbox
from outreach.core.provider_custody import MailboxAccess
from outreach.core.session_custody import custody_mode


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
    message.set_content(render_email_body(body))
    return message.as_bytes()


def render_email_body(body: str) -> str:
    """The review screen and MIME builder must show the same effective copy."""
    return body.rstrip() + "\n\nIf you do not want follow-ups, reply STOP.\n"


async def _post_provider_message(provider: str, token: str, mime: bytes, *, envelope) -> httpx.Response:
    envelope.assert_email(mime)
    envelope.assert_bearer(token)
    async with httpx.AsyncClient(timeout=25) as client:
        if provider == "gmail":
            return await envelope.call("POST", GMAIL_SEND_URL, lambda: client.post(
                GMAIL_SEND_URL, headers={"Authorization": f"Bearer {token}"},
                json={"raw": base64.urlsafe_b64encode(mime).rstrip(b"=").decode("ascii")}), action="email")
        if provider == "microsoft":
            return await envelope.call("POST", GRAPH_SEND_URL, lambda: client.post(
                GRAPH_SEND_URL, headers={"Authorization": f"Bearer {token}", "Content-Type": "text/plain"},
                content=base64.b64encode(mime).decode("ascii")), action="email")
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
    """Accepted is provider acceptance only. A possible send is never retried."""
    from outreach.core.provider_boundary import create_provider_envelope
    from outreach.core.provider_operations import ProviderOperations
    from outreach.core.request_guard import RequestDenied, current_request_parent

    if not operation_id or len(operation_id) > 200:
        return {"status": "failed", "reason": "A stable operation ID is required"}
    recipient = normalize_email(to_email)
    if not recipient or not subject.strip() or not body.strip() or len(subject) > 500 or len(body) > 20000:
        return {"status": "failed", "reason": "A valid recipient, subject and body are required"}
    operations = ProviderOperations(db, "outreach_email_operations")
    op_key = f"email:{workspace_id}:{operation_id}"
    prior = await operations.prior(workspace_id, op_key)
    if prior and prior.get("status") != "not_submitted":
        if prior.get("status") in {"dispatching", "uncertain"}:
            repaired = await operations.repair(prior)
            return _public_result(repaired) if repaired else {"status": "uncertain", "reason": "Previous send outcome requires reconciliation"}
        return _public_result(prior)
    mailbox = await get_ready_mailbox(db, workspace_id, sender_account_id)
    if not mailbox:
        raise RequestDenied("mailbox_unavailable")
    lead = await _eligible_lead(db, workspace_id, sender_account_id, lead_id, recipient)
    if not lead:
        raise RequestDenied("lead_changed")
    # Capture the identity before refresh. Reconnecting cannot authorize an old token.
    envelope = await create_provider_envelope(db, workspace_id, sender_account_id, "email_send", mailbox, operation_id, lead_id)
    mime = _mime_message(mailbox["email"], recipient, subject.strip(), body, _message_id(op_key))
    envelope.assert_email(mime)
    op = {"_id": op_key, "workspace_id": workspace_id, "sender_account_id": sender_account_id,
        "lead_id": lead_id, "campaign_id": lead["campaign_id"], "provider": mailbox["provider"],
        "recipient": recipient, "sender_email": mailbox["email"], "subject": subject.strip(),
        "message_id": _message_id(op_key), "source": "email_send", "logical_operation_id": operation_id,
        "credential_generation": envelope.generation, "account_generation": envelope.account_generation,
        "lead_snapshot": {name: lead.get(name) for name in ("enrollment_id", "current_node_id", "authorized_revision", "sequence_version")}}
    if not await operations.claim(op):
        return {"status": "uncertain", "reason": "Previous send outcome requires reconciliation"}
    try:
        token = await get_mailbox_access_token(db, mailbox)
        if isinstance(token, MailboxAccess):
            envelope.bind_mailbox(token.secret)
            token = token.secret.value
        if not await _eligible_lead(db, workspace_id, sender_account_id, lead_id, recipient):
            raise RequestDenied("lead_changed")
        response = await _post_provider_message(mailbox["provider"], token, mime, envelope=envelope)
        data = envelope.response_evidence(response, "email", True)["provider_outcome"]
        result = {**data, "status": "failed" if data["status"] == "rejected" else "accepted"}
        if result["status"] == "accepted":
            result["accepted_at"] = datetime.now(timezone.utc)
        else:
            result["reason"] = "Provider rejected the message"
        if not await operations.finish(workspace_id, op_key, result):
            return {"status": "uncertain", "reason": "Provider confirmation needs reconciliation"}
        if response.status_code in {401, 403}:
            await db.outreach_mailboxes.update_one({"workspace_id": workspace_id, "sender_account_id": sender_account_id,
                "connection_job_id": mailbox.get("connection_job_id"), "provider": mailbox["provider"],
                "provider_user_id": mailbox.get("provider_user_id")}, {"$set": {"status": "reauth_required"}})
        return _public_result(result)
    except RequestDenied as exc:
        parent = current_request_parent()
        if parent and not parent.mutation_attempted:
            await operations.finish(workspace_id, op_key, {"status": "not_submitted", "reason": exc.reason})
            raise
        await operations.finish(workspace_id, op_key, {"status": "uncertain", "reason": "Provider request outcome is unknown"})
        return {"status": "uncertain", "reason": "Provider request outcome is unknown"}
    except Exception:
        parent = current_request_parent()
        possible = bool(parent and parent.mutation_attempted)
        result = {"status": "uncertain" if possible else "not_submitted", "reason": "Provider request outcome is unknown" if possible else "mailbox_unavailable"}
        try:
            await operations.finish(workspace_id, op_key, result)
        except Exception:
            pass
        if not possible:
            raise RequestDenied("mailbox_unavailable") from None
        return result
