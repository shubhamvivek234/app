"""Bounded Gmail-history and Microsoft-Inbox-delta reply monitoring.

Normal messages use metadata; delivery-status messages are read as MIME so a
failed recipient can be attributed. Stale or incomplete cursors block sends.
"""
from __future__ import annotations

import base64
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from urllib.parse import quote, urlparse

import httpx
import logging

from outreach.core.email_finder import normalize_email, suppress_email
from outreach.core.mailbox_connection import MailboxUnavailable, _paid_sender, get_mailbox_access_token, is_mailbox_pilot_allowed
from outreach.models import LeadExecutionState
from outreach.core.paid_access import _utc

logger = logging.getLogger(__name__)


GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
GRAPH_BASE = "https://graph.microsoft.com/v1.0/me"
MAX_SYNC_PAGES = 20
MAX_EVENTS = 500
_BOUNCE_SENDERS = {"mailer-daemon", "postmaster"}
_MAX_DSN_BYTES = 2_000_000
_MESSAGE_ID_PATTERN = re.compile(r"<[^<>\s]{1,998}>")


def _sync_enabled() -> bool:
    return os.getenv("OUTREACH_EMAIL_SYNC_ENABLED", "false").strip().lower() in {"true", "1"}


def is_mailbox_sync_pilot_allowed(workspace_id: str | None = None) -> bool:
    if not _sync_enabled():
        return False
    allowlist = os.getenv("OUTREACH_MAILBOX_PILOT_WORKSPACES", "").strip()
    if not allowlist or allowlist == "*":
        return True
    allowed_ids = {ws.strip() for ws in allowlist.split(",") if ws.strip()}
    return bool(workspace_id and workspace_id in allowed_ids)


def _safe_graph_delta_url(url: str) -> bool:
    parsed = urlparse(url)
    return (parsed.scheme == "https" and parsed.hostname == "graph.microsoft.com"
            and parsed.path.lower().startswith("/v1.0/me/mailfolders/")
            and "/messages/delta" in parsed.path.lower()
            and not parsed.username and not parsed.password)


async def _provider_get(url: str, token: str, *, params: dict | None = None) -> httpx.Response:
    if not (url.startswith(GMAIL_BASE + "/") or _safe_graph_delta_url(url)
            or url.startswith(GRAPH_BASE + "/messages/")):
        raise MailboxUnavailable("Invalid mailbox sync URL")
    async with httpx.AsyncClient(timeout=25) as client:
        return await client.get(url, params=params, headers={"Authorization": f"Bearer {token}"})


def _response_json(response: httpx.Response) -> dict:
    if response.status_code != 200:
        raise MailboxUnavailable("Mailbox reply cursor is unavailable")
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("error"):
        raise MailboxUnavailable("Mailbox reply cursor returned an error")
    return payload


def _mailbox_snapshot_filter(mailbox: dict) -> dict:
    """Never let an older sync mark a reconnected mailbox healthy."""
    query = {
        "workspace_id": mailbox["workspace_id"],
        "sender_account_id": mailbox["sender_account_id"],
        "status": "active", "provider": mailbox.get("provider"),
    }
    job_id = mailbox.get("connection_job_id")
    query["connection_job_id"] = job_id if job_id else {"$exists": False}
    cursor_field = "history_id" if mailbox.get("provider") == "gmail" else "delta_url"
    query[cursor_field] = mailbox.get(cursor_field)
    return query


async def bootstrap_mailbox_sync(db, workspace_id: str, sender_account_id: str, *,
                                 expected_connection_job_id: str | None = None,
                                 sync_lease_id: str | None = None) -> dict:
    """Establish a post-connection cursor; no historical email is attributed."""
    if not is_mailbox_sync_pilot_allowed(workspace_id):
        await db.outreach_mailboxes.update_one(
            {"workspace_id": workspace_id, "sender_account_id": sender_account_id},
            {"$set": {"sync_status": "disabled", "last_sync_at": None}},
        )
        return {"status": "disabled"}
    if not await _paid_sender(db, workspace_id, sender_account_id):
        raise MailboxUnavailable("Paid sender access is unavailable")
    mailbox = await db.outreach_mailboxes.find_one({
        "workspace_id": workspace_id, "sender_account_id": sender_account_id, "status": "active",
    })
    if not mailbox:
        raise MailboxUnavailable("Mailbox is not connected")
    if expected_connection_job_id is not None and mailbox.get("connection_job_id") != expected_connection_job_id:
        raise MailboxUnavailable("Mailbox connection changed during reply sync")
    token = await get_mailbox_access_token(db, mailbox)
    now = datetime.now(timezone.utc)
    if mailbox.get("provider") == "gmail":
        history_id = mailbox.get("history_id")
        if not history_id:
            profile = _response_json(await _provider_get(GMAIL_BASE + "/profile", token))
            history_id = profile.get("historyId")
        if not history_id:
            raise MailboxUnavailable("Gmail did not return a history cursor")
        updates = {"history_id": str(history_id), "sync_status": "healthy", "last_sync_at": now}
    elif mailbox.get("provider") == "microsoft":
        # Graph permits a receivedDateTime filter on initial delta. Consume
        # every page to obtain an actual deltaLink before enabling sends.
        initial_url = GRAPH_BASE + "/mailFolders/inbox/messages/delta"
        params = {"changeType": "created", "$select": "id,from,receivedDateTime,internetMessageId,internetMessageHeaders,subject",
                  "$filter": f"receivedDateTime ge {now.isoformat().replace('+00:00', 'Z')}", "$top": "100"}
        next_url = initial_url
        delta_url = None
        for page in range(MAX_SYNC_PAGES):
            if not await _paid_sender(db, workspace_id, sender_account_id):
                raise MailboxUnavailable("Paid sender access ended during mailbox sync")
            payload = _response_json(await _provider_get(next_url, token, params=params if page == 0 else None))
            next_url = payload.get("@odata.nextLink")
            delta_url = payload.get("@odata.deltaLink")
            if delta_url:
                break
            if not next_url or not _safe_graph_delta_url(next_url):
                raise MailboxUnavailable("Microsoft did not return a complete inbox cursor")
        if not delta_url or not _safe_graph_delta_url(delta_url):
            raise MailboxUnavailable("Microsoft inbox cursor could not be completed")
        updates = {"delta_url": delta_url, "sync_status": "healthy", "last_sync_at": now}
    else:
        raise MailboxUnavailable("Unsupported email provider")
    if not await _paid_sender(db, workspace_id, sender_account_id):
        raise MailboxUnavailable("Paid sender access ended during mailbox sync")
    query = _mailbox_snapshot_filter(mailbox)
    if sync_lease_id:
        query["sync_lease_id"] = sync_lease_id
    saved = await db.outreach_mailboxes.update_one(query, {"$set": updates})
    if not getattr(saved, "modified_count", 0):
        raise MailboxUnavailable("Mailbox connection changed during reply sync")
    return {"status": "healthy"}


def _header_map(headers: object) -> dict[str, str]:
    if not isinstance(headers, list):
        return {}
    return {str(item.get("name") or "").lower(): str(item.get("value") or "")
            for item in headers if isinstance(item, dict)}


def _sender_email(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    addresses = getaddresses([value])
    return normalize_email(addresses[0][1]) if addresses else None


def _is_bounce_sender(email: str | None) -> bool:
    return bool(email and email.split("@", 1)[0] in _BOUNCE_SENDERS)


def _dsn_failed_recipient(raw: bytes) -> str | None:
    """Read only structured RFC 3464 failed-recipient fields, never body prose."""
    if not raw or len(raw) > _MAX_DSN_BYTES:
        return None
    try:
        message = BytesParser(policy=policy.default).parsebytes(raw)
        for part in message.walk():
            if part.get_content_type() != "message/delivery-status":
                continue
            payload = part.get_payload()
            if not isinstance(payload, list):
                continue
            for block in payload:
                action = str(block.get("Action") or "").lower()
                status = str(block.get("Status") or "")
                if action != "failed" and not status.startswith("5."):
                    continue
                target = str(block.get("Final-Recipient") or block.get("Original-Recipient") or "")
                address = normalize_email(target.split(";", 1)[-1].strip())
                if address:
                    return address
    except Exception:
        return None
    return None


async def _gmail_dsn_recipient(message_id: str, token: str) -> str | None:
    payload = _response_json(await _provider_get(
        f"{GMAIL_BASE}/messages/{quote(message_id, safe='')}", token,
        params={"format": "raw"},
    ))
    encoded = payload.get("raw")
    if not isinstance(encoded, str) or len(encoded) > (_MAX_DSN_BYTES * 4 // 3 + 8):
        return None
    try:
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except (ValueError, TypeError):
        return None
    return _dsn_failed_recipient(raw)


async def _graph_dsn_recipient(message_id: str, token: str) -> str | None:
    url = f"{GRAPH_BASE}/messages/{quote(message_id, safe='')}/$value"
    response = await _provider_get(url, token)
    if response.status_code != 200:
        raise MailboxUnavailable("Microsoft delivery report could not be read")
    return _dsn_failed_recipient(response.content)


async def _mark_inbound(db, mailbox: dict, message: dict) -> dict:
    """Associate only post-send inbound messages; no historical attribution."""
    workspace_id = mailbox["workspace_id"]
    sender_id = mailbox["sender_account_id"]
    provider_id = str(message.get("id") or "")
    from_email = normalize_email(message.get("from"))
    received_at = _utc(message.get("received_at"))
    if not provider_id or not from_email or not received_at:
        return {"status": "ignored"}
    if from_email == mailbox.get("email"):
        return {"status": "ignored"}
    if _is_bounce_sender(from_email):
        failed_email = normalize_email(message.get("failed_recipient"))
        if not failed_email:
            # Unknown bounce target: keep the mailbox unavailable for more
            # automated sends until a human reviews the provider mailbox.
            raise MailboxUnavailable("A bounce could not be attributed to a lead")
        return await _apply_inbound(db, mailbox, provider_id, failed_email, received_at,
                                    message, kind="bounce")
    return await _apply_inbound(db, mailbox, provider_id, from_email, received_at, message, kind="reply")


async def _apply_inbound(db, mailbox: dict, provider_id: str, recipient: str,
                         received_at: datetime, message: dict, *, kind: str) -> dict:
    workspace_id, sender_id = mailbox["workspace_id"], mailbox["sender_account_id"]
    prior = await db.outreach_email_inbound_events.find_one({
        "workspace_id": workspace_id, "sender_account_id": sender_id,
        "provider_message_id": provider_id,
    }, {"_id": 1})
    if prior:
        return {"status": "duplicate"}
    scope = {"workspace_id": workspace_id, "sender_account_id": sender_id,
             "status": "accepted", "accepted_at": {"$lt": received_at}}
    references = " ".join(str(message.get(key) or "") for key in ("references", "in_reply_to"))
    message_ids = list(dict.fromkeys(_MESSAGE_ID_PATTERN.findall(references)))
    op = None
    if kind == "reply" and message_ids:
        # A reply may come from an alias. Match a specific sent Message-ID
        # before falling back to the less reliable sender-address heuristic.
        op = await db.outreach_email_operations.find_one(
            {**scope, "message_id": {"$in": message_ids}}, sort=[("accepted_at", -1)],
        )
    if not op:
        op = await db.outreach_email_operations.find_one(
            {**scope, "recipient": recipient}, sort=[("accepted_at", -1)],
        )
    if not op:
        return {"status": "ignored"}
    original_recipient = normalize_email(op.get("recipient")) or recipient
    matched_by_id = bool(op.get("message_id") and op["message_id"] in message_ids)
    matched_by_thread = bool(message.get("thread_id") and op.get("provider_thread_id")
                             and message["thread_id"] == op["provider_thread_id"])
    attribution = "message_reference" if matched_by_id else "provider_thread" if matched_by_thread else "sender_address_and_time"
    now = datetime.now(timezone.utc)
    if kind == "bounce":
        await suppress_email(db, workspace_id=workspace_id, email=recipient, reason="bounce", lead_id=op.get("lead_id"))
        changed = await db.outreach_leads.update_one(
            {"workspace_id": workspace_id, "id": op["lead_id"], "email_bounced_at": {"$exists": False}},
            {"$set": {"email_bounced_at": received_at, "execution_state": LeadExecutionState.BOUNCED,
                      "email_reply_attribution": attribution, "updated_at": now}},
        )
    else:
        # The same address sending a new message after our send is not proof
        # that it replied to *our* message. Stop follow-ups for review, but do
        # not invent a confirmed reply or claim that the person opted out.
        confirmed = attribution != "sender_address_and_time"
        await suppress_email(db, workspace_id=workspace_id, email=original_recipient,
                             reason="recipient_replied" if confirmed else "possible_reply_review",
                             lead_id=op.get("lead_id"))
        if confirmed:
            changed = await db.outreach_leads.update_one(
                {"workspace_id": workspace_id, "id": op["lead_id"], "has_replied": {"$ne": True}},
                {"$set": {"has_replied": True, "replied_at": received_at,
                          "execution_state": LeadExecutionState.REPLIED,
                          "pause_reason": "Lead replied via email",
                          "email_reply_attribution": attribution, "updated_at": now}},
            )
            if getattr(changed, "modified_count", 0):
                if hasattr(db, "outreach_tasks") and hasattr(db.outreach_tasks, "update_many"):
                    task_res = db.outreach_tasks.update_many(
                        {"lead_id": op["lead_id"], "workspace_id": workspace_id, "status": "pending"},
                        {"$set": {"status": "skipped", "skip_reason": "Lead replied: follow-up touches stopped", "resolved_at": now}},
                    )
                    if hasattr(task_res, "__await__"):
                        await task_res
                if op.get("campaign_id"):
                    await db.outreach_campaigns.update_one(
                        {"workspace_id": workspace_id, "id": op["campaign_id"]},
                        {"$inc": {"replies_count": 1}},
                    )
                lead_doc = None
                if hasattr(db, "outreach_leads") and hasattr(db.outreach_leads, "find_one"):
                    find_res = db.outreach_leads.find_one(
                        {"workspace_id": workspace_id, "id": op["lead_id"]},
                        {"first_name": 1, "last_name": 1, "name": 1, "email": 1, "linkedin_url": 1},
                    )
                    import inspect
                    if inspect.isawaitable(find_res):
                        lead_doc = await find_res
                    elif isinstance(find_res, dict):
                        lead_doc = find_res
                lead_doc = lead_doc or {}
                lead_display = (
                    f"{lead_doc.get('first_name', '')} {lead_doc.get('last_name', '')}".strip()
                    or lead_doc.get("name")
                    or original_recipient
                )

                # 1. Upsert into unified outreach inbox thread
                try:
                    from outreach.models import OutreachInboxThread, OutreachInboxMessage, MessageSenderType
                    thread_id = f"thread_email_{op['lead_id']}"
                    find_thread = None
                    if hasattr(db, "outreach_inbox_threads") and hasattr(db.outreach_inbox_threads, "find_one"):
                        t_res = db.outreach_inbox_threads.find_one({
                            "workspace_id": workspace_id,
                            "$or": [{"lead_id": op["lead_id"]}, {"id": thread_id}],
                        })
                        import inspect
                        if inspect.isawaitable(t_res):
                            find_thread = await t_res
                        elif isinstance(t_res, dict):
                            find_thread = t_res

                    new_msg = OutreachInboxMessage(
                        sender_type=MessageSenderType.LEAD,
                        sender_name=lead_display,
                        sender_urn=original_recipient,
                        body=f"Inbound reply received from {original_recipient}",
                        timestamp=received_at,
                    )
                    if find_thread:
                        await db.outreach_inbox_threads.update_one(
                            {"id": find_thread["id"], "workspace_id": workspace_id},
                            {
                                "$push": {"messages": new_msg.model_dump()},
                                "$set": {
                                    "last_message_snippet": f"Inbound reply from {original_recipient}",
                                    "last_message_at": received_at,
                                },
                                "$inc": {"unread_count": 1},
                            },
                        )
                    elif hasattr(db, "outreach_inbox_threads") and hasattr(db.outreach_inbox_threads, "insert_one"):
                        new_thread = OutreachInboxThread(
                            id=thread_id,
                            workspace_id=workspace_id,
                            account_id=sender_id,
                            lead_id=op["lead_id"],
                            lead_name=lead_display,
                            lead_urn=original_recipient,
                            campaign_id=op.get("campaign_id"),
                            is_outreach=True,
                            last_message_snippet=f"Inbound reply from {original_recipient}",
                            last_message_at=received_at,
                            unread_count=1,
                            messages=[new_msg],
                        )
                        await db.outreach_inbox_threads.insert_one(new_thread.model_dump())
                except Exception as thread_err:
                    logger.warning("Failed to sync inbox thread for email reply %s: %s", op.get("lead_id"), thread_err)

                # 2. Record Transactional Outbox Event for Slack notifications & Webhook subscribers
                try:
                    from outreach.core.event_outbox import record_outbox_event
                    from outreach.core.event_definitions import WebhookEvent

                    await record_outbox_event(
                        db=db,
                        workspace_id=workspace_id,
                        event_type=WebhookEvent.LEAD_REPLIED,
                        aggregate_id=op["lead_id"],
                        dedupe_key=f"lead.replied:email:{op['lead_id']}:{provider_id}",
                        data={
                            "lead_id": op["lead_id"],
                            "lead_name": lead_display,
                            "campaign_id": op.get("campaign_id"),
                            "channel": "email",
                            "email": original_recipient,
                            "sender_account_id": sender_id,
                        },
                    )
                except Exception as outbox_err:
                    logger.warning("Failed to record outbox event for email reply %s: %s", op.get("lead_id"), outbox_err)
        else:
            await db.outreach_leads.update_one(
                {"workspace_id": workspace_id, "id": op["lead_id"], "has_replied": {"$ne": True}},
                {"$set": {"execution_state": LeadExecutionState.WAITING_TRIGGER,
                          "email_review_required_at": received_at,
                          "email_reply_attribution": attribution, "updated_at": now}},
            )
            kind = "possible_reply"
    await db.outreach_email_inbound_events.update_one(
        {"workspace_id": workspace_id, "sender_account_id": sender_id,
         "provider_message_id": provider_id},
        {"$setOnInsert": {"lead_id": op.get("lead_id"), "operation_id": op.get("_id"),
                          "kind": kind, "recipient": original_recipient,
                          "inbound_sender": recipient, "received_at": received_at,
                          "attribution": attribution, "created_at": now}}, upsert=True,
    )
    return {"status": kind, "attribution": attribution}


async def _gmail_messages(mailbox: dict, token: str) -> tuple[list[dict], str]:
    history_id = mailbox.get("history_id")
    if not history_id:
        raise MailboxUnavailable("Gmail cursor is missing")
    messages: list[dict] = []
    next_page = None
    final_history_id = None
    for page in range(MAX_SYNC_PAGES):
        params = {"startHistoryId": str(history_id), "historyTypes": "messageAdded", "maxResults": 100}
        if next_page:
            params["pageToken"] = next_page
        payload = _response_json(await _provider_get(GMAIL_BASE + "/history", token, params=params))
        for item in payload.get("history") or []:
            for added in item.get("messagesAdded") or []:
                reference = added.get("message") or {}
                message_id = reference.get("id")
                if not message_id:
                    continue
                if len(messages) >= MAX_EVENTS:
                    raise MailboxUnavailable("Gmail sync backlog exceeds safe batch size")
                detail = _response_json(await _provider_get(
                    f"{GMAIL_BASE}/messages/{message_id}", token,
                    params={"format": "metadata", "metadataHeaders": [
                        "From", "To", "References", "In-Reply-To", "X-Failed-Recipients", "Final-Recipient", "Original-Recipient",
                    ]},
                ))
                if "SENT" in (detail.get("labelIds") or []):
                    continue
                headers = _header_map((detail.get("payload") or {}).get("headers"))
                timestamp = detail.get("internalDate")
                try:
                    received = datetime.fromtimestamp(int(timestamp) / 1000, timezone.utc)
                except (TypeError, ValueError, OverflowError):
                    continue
                failed_header = headers.get("x-failed-recipients") or headers.get("final-recipient") or headers.get("original-recipient")
                failed_recipient = _sender_email(failed_header.split(";", 1)[-1]) if failed_header else None
                sender = _sender_email(headers.get("from"))
                if _is_bounce_sender(sender) and not failed_recipient:
                    failed_recipient = await _gmail_dsn_recipient(str(message_id), token)
                messages.append({
                    "id": str(message_id), "thread_id": detail.get("threadId"),
                    "from": sender, "received_at": received,
                    "references": headers.get("references"), "in_reply_to": headers.get("in-reply-to"),
                    "failed_recipient": failed_recipient,
                })
        next_page = payload.get("nextPageToken")
        final_history_id = payload.get("historyId")
        if not next_page:
            break
    if next_page or not final_history_id:
        raise MailboxUnavailable("Gmail cursor is incomplete")
    return messages, str(final_history_id)


async def _graph_messages(mailbox: dict, token: str) -> tuple[list[dict], str]:
    next_url = mailbox.get("delta_url")
    if not next_url or not _safe_graph_delta_url(next_url):
        raise MailboxUnavailable("Microsoft inbox cursor is invalid")
    messages: list[dict] = []
    final_url = None
    for _ in range(MAX_SYNC_PAGES):
        payload = _response_json(await _provider_get(next_url, token))
        for item in payload.get("value") or []:
            if item.get("@removed"):
                continue
            if len(messages) >= MAX_EVENTS:
                raise MailboxUnavailable("Microsoft sync backlog exceeds safe batch size")
            address = ((item.get("from") or {}).get("emailAddress") or {}).get("address")
            headers = _header_map(item.get("internetMessageHeaders"))
            failed_recipient = _sender_email(headers.get("x-failed-recipients") or headers.get("final-recipient"))
            if _is_bounce_sender(normalize_email(address)) and not failed_recipient and item.get("id"):
                failed_recipient = await _graph_dsn_recipient(str(item["id"]), token)
            messages.append({
                "id": item.get("id"), "from": normalize_email(address),
                "received_at": item.get("receivedDateTime"),
                "references": headers.get("references"), "in_reply_to": headers.get("in-reply-to"),
                "failed_recipient": failed_recipient,
            })
        next_url = payload.get("@odata.nextLink")
        final_url = payload.get("@odata.deltaLink")
        if final_url:
            break
        if not next_url or not _safe_graph_delta_url(next_url):
            raise MailboxUnavailable("Microsoft inbox cursor is incomplete")
    if not final_url or not _safe_graph_delta_url(final_url):
        raise MailboxUnavailable("Microsoft inbox cursor is incomplete")
    return messages, final_url


async def sync_mailbox_replies(db, *, workspace_id: str, sender_account_id: str) -> dict:
    """Worker-only sync; failed or incomplete cycles immediately disable sends."""
    if not is_mailbox_sync_pilot_allowed(workspace_id) or not await _paid_sender(db, workspace_id, sender_account_id):
        return {"status": "unavailable"}
    mailbox = await db.outreach_mailboxes.find_one({
        "workspace_id": workspace_id, "sender_account_id": sender_account_id, "status": "active",
    })
    if not mailbox:
        return {"status": "unavailable"}
    now = datetime.now(timezone.utc)
    lease_id = uuid.uuid4().hex
    claimed = await db.outreach_mailboxes.update_one(
        {"workspace_id": workspace_id, "sender_account_id": sender_account_id, "status": "active",
         "$or": [{"sync_lease_until": {"$lt": now}}, {"sync_lease_until": {"$exists": False}}]},
        {"$set": {"sync_lease_until": now + timedelta(minutes=2), "sync_lease_id": lease_id}},
    )
    if not getattr(claimed, "modified_count", 0):
        return {"status": "already_running"}
    query = {**_mailbox_snapshot_filter(mailbox), "sync_lease_id": lease_id}
    try:
        if mailbox.get("sync_status") in {"initializing", "disabled"}:
            return await bootstrap_mailbox_sync(
                db, workspace_id, sender_account_id,
                expected_connection_job_id=mailbox.get("connection_job_id"),
                sync_lease_id=lease_id,
            )
        token = await get_mailbox_access_token(db, mailbox)
        if not await _paid_sender(db, workspace_id, sender_account_id):
            raise MailboxUnavailable("Paid sender access ended during mailbox sync")
        if mailbox.get("provider") == "gmail":
            messages, cursor = await _gmail_messages(mailbox, token)
            cursor_update = {"history_id": cursor}
        elif mailbox.get("provider") == "microsoft":
            messages, cursor = await _graph_messages(mailbox, token)
            cursor_update = {"delta_url": cursor}
        else:
            raise MailboxUnavailable("Unsupported email provider")
        results = []
        for message in messages:
            if not await _paid_sender(db, workspace_id, sender_account_id):
                raise MailboxUnavailable("Paid sender access ended during mailbox sync")
            results.append(await _mark_inbound(db, mailbox, message))
        saved = await db.outreach_mailboxes.update_one(
            query, {"$set": {**cursor_update, "sync_status": "healthy",
                             "last_sync_at": datetime.now(timezone.utc)}},
        )
        if not getattr(saved, "modified_count", 0):
            raise MailboxUnavailable("Mailbox connection changed during reply sync")
        return {"status": "healthy", "replies": sum(x.get("status") == "reply" for x in results),
                "bounces": sum(x.get("status") == "bounce" for x in results)}
    except Exception:
        await db.outreach_mailboxes.update_one(
            query, {"$set": {"sync_status": "stale", "sync_error": "Reply synchronization needs attention",
                             "updated_at": datetime.now(timezone.utc)}},
        )
        return {"status": "stale"}
    finally:
        await db.outreach_mailboxes.update_one(
            {"workspace_id": workspace_id, "sender_account_id": sender_account_id,
             "sync_lease_id": lease_id},
            {"$unset": {"sync_lease_until": "", "sync_lease_id": ""}},
        )
