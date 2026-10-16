"""
Phase 7: Multi-Account Inbox Synchronization Engine.
Polls conversations across all connected LinkedIn accounts via private Voyager endpoints,
indexes unified threads into MongoDB, detects prospect replies, and marks sequence leads as replied.
"""
import logging
import uuid
from typing import Any
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import TypeAdapter, ValidationError

from outreach.core.proxy_manager import JITProxyManager
from outreach.core.paid_access import sender_is_ready, _utc
from outreach.core.inbox_freshness import PARSER_VERSION, credential_generation, session_filter
from outreach.core.lead_importer import normalize_linkedin_url
from outreach.core.safety_shield import SafetyShield
from outreach.engine.voyager_client import VoyagerClient, VoyagerRestrictionError
from outreach.core.request_guard import RequestEnvelope
from outreach.models import (
    OutreachInboxThread,
    OutreachInboxMessage,
    MessageSenderType,
    LeadExecutionState,
)

logger = logging.getLogger(__name__)
_TIMESTAMP_ADAPTER = TypeAdapter(datetime)


def _merge_observed_messages(existing: list[dict], incoming: list[dict], raw: list[dict]) -> list[dict]:
    """Keep saved evidence and deduplicate enrichment without inventing events."""
    def content(message):
        return (message.get("sender_type"), message.get("sender_urn"), message.get("body"), message.get("audio_url"))
    def timestamp(value):
        parsed = _utc(value)
        return parsed.replace(microsecond=parsed.microsecond // 1000 * 1000) if parsed else None
    messages = list(existing)
    identities = {(*content(message), timestamp(message.get("timestamp"))) for message in existing}
    bodies = {content(message) for message in existing}
    for message, source in zip(incoming, raw):
        # Pydantic has normalized message epochs/ISO times already. A thread
        # timestamp alone cannot distinguish two identical individual messages.
        stamp = timestamp(message.get("timestamp")) if source.get("timestamp") is not None else None
        identity = (*content(message), stamp)
        # Without a source timestamp, identical content is one observation;
        # its later ingestion time cannot establish another provider message.
        if identity in identities or (stamp is None and content(message) in bodies):
            continue
        messages.append(message)
        identities.add(identity)
        bodies.add(content(message))
    return sorted(messages, key=lambda message: timestamp(message.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc))


async def _fetch_cursor_docs(cursor_or_coro: Any, length: int = 1000) -> list[dict[str, Any]]:
    target = cursor_or_coro
    if hasattr(target, "__await__"):
        target = await target
    if hasattr(target, "to_list"):
        return await target.to_list(length=length)
    if isinstance(target, list):
        return target
    return []


class InboxSynchronizer:
    """
    Coordinates multi-account synchronization into a single unified conversation stream.
    """

    def __init__(self, db: AsyncIOMotorDatabase, workspace_id: str, user_id: str | None = None):
        self.db = db
        self.workspace_id = workspace_id
        self.user_id = user_id or workspace_id

    async def sync_account_inbox(self, account_id: str) -> dict[str, Any]:
        """
        Fetches and synchronizes inbox threads for a specific LinkedIn sender account.
        """
        account = await self.db.outreach_accounts.find_one({
            "id": account_id,
            "workspace_id": self.workspace_id,
        })
        if not account:
            return {"status": "error", "error": f"Account {account_id} not found"}
        if account.get("status") != "active":
            return {"status": "error", "error": "Sender account is not active"}
        if not await sender_is_ready(self.db, self.workspace_id, account):
            return {"status": "error", "error": "Paid sender access or provider IP is unavailable"}

        from outreach.core.proxy_custody import prepare_proxy
        proxy = account.get("proxy_config") or account.get("proxy")
        prepared = await prepare_proxy(proxy, self.workspace_id) if proxy else None
        proxy_url = prepared.url if prepared else None

        cookie_enc = account.get("encrypted_session_cookie") or account.get("session_cookie_enc", "")
        if not cookie_enc:
            return {"status": "error", "error": "Sender account has no LinkedIn session"}
        from outreach.core.session_custody import account_session
        client = VoyagerClient(**(await account_session(account)), proxy_url=proxy_url,
            request_envelope=RequestEnvelope(self.db, self.workspace_id, account_id, credential_generation(account), "sync", proxy_url, prepared_proxy=prepared))

        coverage_started = datetime.now(timezone.utc)
        sync_token = str(uuid.uuid4())
        snapshot_filter = session_filter(account)
        started = await self.db.outreach_accounts.update_one(snapshot_filter, {"$set": {"inbox_sync": {
            "status": "running", "owner_token": sync_token, "parser_version": PARSER_VERSION,
            "credential_generation": credential_generation(account), "coverage_started_at": coverage_started,
        }}})
        if getattr(started, "matched_count", 0) == 0:
            return {"status": "error", "error": "Sender changed before inbox sync", "coverage_complete": False}

        conversations = []
        exhausted = False
        try:
            for start in range(0, 500, 25):
                if not await sender_is_ready(self.db, self.workspace_id, account):
                    return {"status": "error", "error": "Paid sender access or provider IP is unavailable"}
                page = await client.fetch_conversations(count=25, start=start)
                if not isinstance(page, list):
                    raise ValueError("Invalid inbox page")
                conversations.extend(page)
                if len(page) < 25:
                    exhausted = True
                    break
        except VoyagerRestrictionError as exc:
            if SafetyShield.should_trip_circuit_breaker(exc.status_code):
                await SafetyShield.trip_circuit_breaker(account_id, f"Inbox sync triggered HTTP {exc.status_code}", self.db, self.workspace_id)
            return {"status": "error", "error": f"LinkedIn rejected inbox sync (HTTP {exc.status_code})", "coverage_complete": False}
        except Exception as exc:
            logger.error("Inbox coverage failed (%s)", type(exc).__name__)
            return {"status": "error", "error": "Inbox coverage could not be verified", "coverage_complete": False}
        synced_count = 0
        new_replies_detected = 0
        skipped_count = 0

        for conv in conversations:
            try:
                result = await self.persist_conversation(account_id, conv)
            except Exception as exc:
                logger.error("Inbox reply persistence failed (%s)", type(exc).__name__)
                return {"status": "error", "error": "Reply state could not be saved",
                        "coverage_complete": False}
            synced_count += result["synced_threads"]
            new_replies_detected += result["new_replies_detected"]
            skipped_count += result["skipped_threads"]

        coverage_complete = exhausted and skipped_count == 0
        finished = await self.db.outreach_accounts.update_one(
            {**snapshot_filter, "inbox_sync.owner_token": sync_token},
            {"$set": {"inbox_sync.status": "complete" if coverage_complete else "partial",
                      "inbox_sync.completed_at": datetime.now(timezone.utc),
                      "inbox_sync.synced_threads": synced_count}},
        )
        coverage_complete = coverage_complete and getattr(finished, "matched_count", 0) == 1
        if coverage_complete:
            await self.db.outreach_accounts.update_one(
                {**snapshot_filter, "inbox_sync.owner_token": sync_token,
                 "priority_sync_requested_at": {"$lte": coverage_started}},
                {"$unset": {"priority_sync_requested_at": "", "priority_sync_due_at": ""}},
            )
        if conversations and not synced_count:
            return {"status": "error", "error": "LinkedIn returned conversations without usable IDs",
                    "skipped_threads": skipped_count, "coverage_complete": False}
        return {
            "account_id": account_id,
            "synced_threads": synced_count,
            "new_replies_detected": new_replies_detected,
            "skipped_threads": skipped_count,
            "coverage_complete": coverage_complete,
        }

    async def persist_conversation(self, account_id: str, conv: dict) -> dict[str, int]:
        """Database-only reply/thread commit under the shared workspace guard."""
        from outreach.core.suppression import mutate_suppression
        async def save(current):
            synchronizer = InboxSynchronizer(current, self.workspace_id, self.user_id)
            return await synchronizer._store_conversation(account_id, conv)
        return await mutate_suppression(self.db, self.workspace_id, save)

    async def _store_conversation(self, account_id: str, conv: dict) -> dict[str, int]:
        synced_count = new_replies_detected = skipped_count = 0
        if (not isinstance(conv, dict) or not isinstance(conv.get("messages"), list)
                or any(not isinstance(m, dict) or m.get("sender_type") not in {"user", "lead"}
                       for m in conv.get("messages", []))):
            return {"synced_threads": 0, "new_replies_detected": 0, "skipped_threads": 1}
        lead_urn = conv.get("lead_urn", "")
        conversation_urn = conv.get("thread_urn") or conv.get("conversation_urn")
        if not lead_urn or not conversation_urn:
            logger.warning("Skipping LinkedIn conversation without a member and conversation URN")
            return {"synced_threads": 0, "new_replies_detected": 0, "skipped_threads": 1}
        lead_name = conv.get("lead_name", "LinkedIn Member")
        raw_msgs = conv.get("messages", [])
        incoming_at = None
        if conv.get("last_message_at") is not None:
            try:
                incoming_at = _utc(_TIMESTAMP_ADAPTER.validate_python(conv["last_message_at"]))
                incoming_at = incoming_at.replace(microsecond=incoming_at.microsecond // 1000 * 1000)
            except ValidationError:
                pass
        last_snippet = conv.get("last_message_snippet") or ""
        if not last_snippet and raw_msgs:
            last_snippet = raw_msgs[-1].get("body") or raw_msgs[-1].get("text", "")

        # Build messages list
        parsed_msgs = []
        has_lead_reply = False
        for m in raw_msgs:
            s_type = MessageSenderType.LEAD if m.get("sender_type") == "lead" else MessageSenderType.USER
            if s_type == MessageSenderType.LEAD:
                has_lead_reply = True
            parsed_msgs.append(
                OutreachInboxMessage(
                    sender_type=s_type,
                    sender_name=m.get("sender_name", lead_name if s_type == MessageSenderType.LEAD else "You"),
                    body=m.get("body") or m.get("text", ""),
                    timestamp=m["timestamp"] if m.get("timestamp") is not None else incoming_at or datetime.now(timezone.utc),
                ).model_dump()
            )

        # Check if this thread already exists
        filter_query = {
            "workspace_id": self.workspace_id,
            "account_id": account_id,
            "lead_urn": lead_urn,
        }
        existing = await self.db.outreach_inbox_threads.find_one(filter_query)
        last_time = incoming_at or (existing or {}).get("last_message_at") or datetime.now(timezone.utc)
        if not last_snippet:
            last_snippet = (existing or {}).get("last_message_snippet", "")

        intent_tag = existing.get("intent_tag") if existing else conv.get("intent_tag")
        if not intent_tag:
            # Basic keyword intent inference
            lead_messages = [m for m in raw_msgs if m.get("sender_type") == "lead"]
            lower_body = (lead_messages[-1].get("body") or lead_messages[-1].get("text", "")).lower() if lead_messages else ""
            if any(w in lower_body for w in ["no thanks", "not interested", "unsubscribe", "remove"]):
                intent_tag = "not_interested"
            elif any(w in lower_body for w in ["yes", "interested", "call", "chat", "love to", "tuesday", "tomorrow"]):
                intent_tag = "interested"

        # Look up if this lead belongs to an existing campaign lead
        profile_url = normalize_linkedin_url(conv.get("lead_profile_url") or conv.get("profile_url") or "")
        exact_identities = [{"linkedin_urn": lead_urn}]
        if profile_url:
            bare_url = profile_url.replace("https://www.linkedin.com/", "https://linkedin.com/")
            exact_identities.append({"linkedin_url": {"$in": [bare_url, bare_url.replace("https://linkedin.com/", "https://www.linkedin.com/")]}})
        matched_lead = await self.db.outreach_leads.find_one({
            "workspace_id": self.workspace_id,
            "assigned_account_id": account_id,
            "$or": exact_identities,
        })
        has_lead_reply = has_lead_reply or bool((existing or {}).get("has_lead_reply")) or any(
            isinstance(message, dict) and message.get("sender_type") == "lead"
            for message in (existing or {}).get("messages", [])
        )
        campaign_id = matched_lead.get("campaign_id") if isinstance(matched_lead, dict) else (existing or {}).get("campaign_id")
        if not isinstance(campaign_id, str):
            campaign_id = None
        is_outreach = bool(campaign_id or (existing or {}).get("is_outreach") or conv.get("is_outreach", False))

        thread_doc = {
            "workspace_id": self.workspace_id,
            "user_id": self.user_id,
            "account_id": account_id,
            "campaign_id": campaign_id,
            "is_outreach": is_outreach,
            "has_lead_reply": has_lead_reply,
            "lead_name": lead_name,
            "lead_headline": conv.get("lead_headline", ""),
            "lead_avatar": conv.get("lead_avatar", ""),
            "lead_urn": lead_urn,
            "lead_profile_url": profile_url or (existing or {}).get("lead_profile_url", ""),
            "conversation_urn": conversation_urn,
            "lead_id": matched_lead.get("id") if isinstance(matched_lead, dict) else (existing or {}).get("lead_id"),
            "last_message_snippet": last_snippet,
            "last_message_at": last_time,
            "unread_count": conv.get("unread_count", (existing or {}).get("unread_count", 0)),
            "intent_tag": intent_tag,
            "messages": parsed_msgs,
        }

        if existing:
            # Reply authority is monotonic. An older overlapping sync
            # cannot clear a reply observed by a newer one.
            thread_doc.pop("has_lead_reply", None)
            if has_lead_reply:
                thread_doc["has_lead_reply"] = True
            if not raw_msgs:
                thread_doc["messages"] = existing.get("messages", [])
            existing_at = _utc(existing.get("last_message_at"))
            if existing_at and (not incoming_at or incoming_at <= existing_at):
                # A retry re-reads current state, but the fetched page stays old.
                # Preserve newer saved content while monotonically recording replies.
                thread_doc["messages"] = _merge_observed_messages(existing.get("messages", []), parsed_msgs, raw_msgs)
                for field in ("last_message_at", "last_message_snippet", "unread_count"):
                    if field in existing:
                        thread_doc[field] = existing[field]
            thread_write = await self.db.outreach_inbox_threads.update_one(
                {"id": existing["id"], "workspace_id": self.workspace_id,
                 "thread_revision": existing["thread_revision"] if "thread_revision" in existing else {"$exists": False}},
                {"$set": thread_doc, "$inc": {"thread_revision": 1}},
            )
            if getattr(thread_write, "matched_count", 0) == 0:
                skipped_count += 1
                if has_lead_reply:
                    await self.db.outreach_inbox_threads.update_one(
                        {"id": existing["id"], "workspace_id": self.workspace_id},
                        {"$set": {"has_lead_reply": True}, "$inc": {"thread_revision": 1}},
                    )
        else:
            new_thread = OutreachInboxThread(**thread_doc)
            await self.db.outreach_inbox_threads.insert_one(new_thread.model_dump())

        synced_count += 1

        # The sender/recipient thread is suppression authority for future
        # imports too. Every other enrollment for this same sender stops;
        # thread attribution and its primary lead KPI remain separate.
        if has_lead_reply:
            from outreach.core.search_sources import retain_search_source_hold
            other_targets = {"workspace_id": self.workspace_id, "assigned_account_id": account_id,
                "$or": exact_identities, "has_replied": {"$ne": True},
                **({"id": {"$ne": matched_lead["id"]}} if isinstance(matched_lead, dict) else {})}
            await retain_search_source_hold(self.db, self.workspace_id, other_targets)
            await self.db.outreach_leads.update_many(
                other_targets,
                {"$set": {"has_replied": True, "execution_state": LeadExecutionState.REPLIED,
                          "replied_at": datetime.now(timezone.utc), "pause_reason": "Lead replied to this sender",
                          "next_action_due_at": None}},
            )

        # If lead replied, flag lead in CRM, update campaign reply counter, and stop sequence
        if has_lead_reply and isinstance(matched_lead, dict):
            await retain_search_source_hold(self.db, self.workspace_id,
                {"id": matched_lead["id"], "workspace_id": self.workspace_id, "has_replied": {"$ne": True}})
            lead_update = await self.db.outreach_leads.update_one(
                {
                    "id": matched_lead["id"],
                    "workspace_id": self.workspace_id,
                    "has_replied": {"$ne": True},
                },
                {
                    "$set": {
                        "has_replied": True,
                        "execution_state": LeadExecutionState.REPLIED,
                        "replied_at": datetime.now(timezone.utc),
                        "pause_reason": "Lead replied to outreach",
                        "next_action_due_at": None,
                    }
                },
            )
            newly_replied = getattr(lead_update, "modified_count", 0) == 1
            if newly_replied:
                new_replies_detected += 1
                if hasattr(self.db, "outreach_tasks") and hasattr(self.db.outreach_tasks, "update_many"):
                    task_update_res = self.db.outreach_tasks.update_many(
                        {
                            "lead_id": matched_lead["id"],
                            "workspace_id": self.workspace_id,
                            "status": "pending",
                        },
                        {
                            "$set": {
                                "status": "skipped",
                                "skip_reason": "Lead replied: follow-up touches stopped",
                                "resolved_at": datetime.now(timezone.utc),
                            }
                        },
                    )
                    if hasattr(task_update_res, "__await__"):
                        await task_update_res

            # Increment campaign reply KPIs if lead has campaign_id
            if campaign_id and newly_replied:
                await self.db.outreach_campaigns.update_one(
                    {"id": campaign_id, "workspace_id": self.workspace_id},
                    {"$inc": {"replies_count": 1}},
                )
                interested_count = await self.db.outreach_inbox_threads.count_documents({
                    "workspace_id": self.workspace_id,
                    "campaign_id": campaign_id,
                    "intent_tag": "interested",
                })
                await self.db.outreach_campaigns.update_one(
                    {"id": campaign_id, "workspace_id": self.workspace_id},
                    {"$set": {"interested_count": interested_count}},
                )

            if newly_replied:
                from outreach.core.event_outbox import record_outbox_event
                from outreach.core.event_definitions import WebhookEvent

                lead_display_name = (
                    f"{matched_lead.get('first_name', '')} {matched_lead.get('last_name', '')}".strip()
                    or matched_lead.get("name")
                    or lead_name
                    or "Prospect"
                )
                await record_outbox_event(
                    db=self.db,
                    workspace_id=self.workspace_id,
                    event_type=WebhookEvent.LEAD_REPLIED,
                    aggregate_id=matched_lead["id"],
                    dedupe_key=f"lead.replied:linkedin:{matched_lead['id']}",
                    data={
                        "lead_id": matched_lead["id"],
                        "lead_name": lead_display_name,
                        "campaign_id": campaign_id,
                        "channel": "linkedin",
                        "linkedin_url": matched_lead.get("linkedin_url") or profile_url,
                        "sender_account_id": account_id,
                    },
                )

        return {"synced_threads": synced_count, "new_replies_detected": new_replies_detected,
                "skipped_threads": skipped_count}

    async def sync_all_accounts(self) -> dict[str, Any]:
        """
        Synchronizes all connected active accounts in the workspace.
        """
        accounts = await _fetch_cursor_docs(
            self.db.outreach_accounts.find({
                "workspace_id": self.workspace_id,
                "status": "active",
            }),
            length=100,
        )
        if not accounts:
            return {"status": "error", "error": "No active sender accounts are available"}

        total_synced = 0
        total_replies = 0
        errors = []
        for acc in accounts:
            res = await self.sync_account_inbox(acc["id"])
            if res.get("status") == "error":
                errors.append({"account_id": acc["id"], "error": res["error"]})
            total_synced += res.get("synced_threads", 0)
            total_replies += res.get("new_replies_detected", 0)

        return {
            "accounts_synced": len(accounts),
            "total_threads_synced": total_synced,
            "total_replies_detected": total_replies,
            "errors": errors,
        }
