"""
Phase 7: Multi-Account Inbox Synchronization Engine.
Polls conversations across all connected LinkedIn accounts via private Voyager endpoints,
indexes unified threads into MongoDB, detects prospect replies, and marks sequence leads as replied.
"""
import logging
from typing import Any
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase

from outreach.core.proxy_manager import JITProxyManager
from outreach.core.lead_importer import normalize_linkedin_url
from outreach.core.safety_shield import SafetyShield
from outreach.engine.voyager_client import VoyagerClient, VoyagerRestrictionError
from outreach.models import (
    OutreachInboxThread,
    OutreachInboxMessage,
    MessageSenderType,
    LeadExecutionState,
)

logger = logging.getLogger(__name__)


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

        proxy_url = None
        if account.get("proxy_config"):
            proxy_url = JITProxyManager.format_proxy_url(account["proxy_config"])
        elif account.get("proxy"):
            proxy_url = JITProxyManager.format_proxy_url(account["proxy"])

        cookie_enc = account.get("encrypted_session_cookie") or account.get("session_cookie_enc", "")
        if not cookie_enc:
            return {"status": "error", "error": "Sender account has no LinkedIn session"}
        jsession_id = account.get("jsession_id", "")
        client = VoyagerClient(session_cookie_enc=cookie_enc, jsession_id=jsession_id, proxy_url=proxy_url)

        conversations = []
        try:
            for start in range(0, 500, 25):
                page = await client.fetch_conversations(count=25, start=start)
                conversations.extend(page)
                if len(page) < 25:
                    break
        except VoyagerRestrictionError as exc:
            if SafetyShield.should_trip_circuit_breaker(exc.status_code):
                await SafetyShield.trip_circuit_breaker(account_id, f"Inbox sync triggered HTTP {exc.status_code}", self.db, self.workspace_id)
            return {"status": "error", "error": f"LinkedIn rejected inbox sync (HTTP {exc.status_code})"}
        synced_count = 0
        new_replies_detected = 0
        skipped_count = 0

        for conv in conversations:
            lead_urn = conv.get("lead_urn", "")
            conversation_urn = conv.get("thread_urn") or conv.get("conversation_urn")
            if not lead_urn or not conversation_urn:
                logger.warning("Skipping LinkedIn conversation without a member and conversation URN")
                skipped_count += 1
                continue
            lead_name = conv.get("lead_name", "LinkedIn Member")
            raw_msgs = conv.get("messages", [])
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
                        timestamp=m.get("timestamp") or datetime.now(timezone.utc),
                    ).model_dump()
                )

            # Check if this thread already exists
            filter_query = {
                "workspace_id": self.workspace_id,
                "account_id": account_id,
                "lead_urn": lead_urn,
            }
            existing = await self.db.outreach_inbox_threads.find_one(filter_query)
            last_time = conv.get("last_message_at") or (existing or {}).get("last_message_at") or datetime.now(timezone.utc)
            if isinstance(last_time, str):
                try:
                    last_time = datetime.fromisoformat(last_time)
                except ValueError:
                    last_time = (existing or {}).get("last_message_at") or datetime.now(timezone.utc)
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
                "$or": exact_identities,
            })
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
                if not raw_msgs:
                    thread_doc["messages"] = existing.get("messages", [])
                await self.db.outreach_inbox_threads.update_one(
                    {"id": existing["id"], "workspace_id": self.workspace_id},
                    {"$set": thread_doc},
                )
            else:
                new_thread = OutreachInboxThread(**thread_doc)
                await self.db.outreach_inbox_threads.insert_one(new_thread.model_dump())

            synced_count += 1

            # If lead replied, flag lead in CRM, update campaign reply counter, and stop sequence
            if has_lead_reply and isinstance(matched_lead, dict):
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
                        }
                    },
                )
                newly_replied = getattr(lead_update, "modified_count", 0) == 1
                if newly_replied:
                    new_replies_detected += 1

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

        if conversations and not synced_count:
            return {"status": "error", "error": "LinkedIn returned conversations without usable IDs", "skipped_threads": skipped_count}
        return {
            "account_id": account_id,
            "synced_threads": synced_count,
            "new_replies_detected": new_replies_detected,
            "skipped_threads": skipped_count,
        }

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
