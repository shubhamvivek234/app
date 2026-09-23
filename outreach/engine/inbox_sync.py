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
from outreach.engine.voyager_client import VoyagerClient
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
            "$or": [{"workspace_id": self.workspace_id}, {"user_id": self.user_id}],
        })
        if not account:
            return {"status": "error", "error": f"Account {account_id} not found"}

        proxy_url = None
        if account.get("proxy_config"):
            proxy_url = JITProxyManager.format_proxy_url(account["proxy_config"])
        elif account.get("proxy"):
            proxy_url = JITProxyManager.format_proxy_url(account["proxy"])

        cookie_enc = account.get("encrypted_session_cookie") or account.get("session_cookie_enc", "")
        jsession_id = account.get("jsession_id", "")
        client = VoyagerClient(session_cookie_enc=cookie_enc, jsession_id=jsession_id, proxy_url=proxy_url)

        conversations = await client.fetch_conversations(count=25)
        synced_count = 0
        new_replies_detected = 0

        for conv in conversations:
            lead_urn = conv.get("lead_urn", "")
            lead_name = conv.get("lead_name", "LinkedIn Member")
            raw_msgs = conv.get("messages", [])
            last_snippet = conv.get("last_message_snippet") or ""
            if not last_snippet and raw_msgs:
                last_snippet = raw_msgs[-1].get("body") or raw_msgs[-1].get("text", "")

            last_time = conv.get("last_message_at") or datetime.now(timezone.utc)
            if isinstance(last_time, str):
                try:
                    last_time = datetime.fromisoformat(last_time)
                except Exception:
                    last_time = datetime.now(timezone.utc)

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

            intent_tag = conv.get("intent_tag")
            if not intent_tag:
                # Basic keyword intent inference
                lower_body = last_snippet.lower()
                if any(w in lower_body for w in ["yes", "interested", "call", "chat", "love to", "tuesday", "tomorrow"]):
                    intent_tag = "interested"
                elif any(w in lower_body for w in ["no thanks", "not interested", "unsubscribe", "remove"]):
                    intent_tag = "not_interested"

            # Look up if this lead belongs to an existing campaign lead
            matched_lead = await self.db.outreach_leads.find_one({
                "$or": [
                    {"workspace_id": self.workspace_id},
                    {"user_id": self.user_id},
                ],
                "$or": [
                    {"linkedin_url": {"$regex": lead_name.replace(" ", ".*"), "$options": "i"}},
                    {"first_name": lead_name.split()[0] if lead_name else ""},
                ],
            })
            campaign_id = matched_lead.get("campaign_id") if isinstance(matched_lead, dict) else None
            if not isinstance(campaign_id, str):
                campaign_id = None
            is_outreach = True if campaign_id or intent_tag or has_lead_reply else conv.get("is_outreach", False)

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
                "last_message_snippet": last_snippet,
                "last_message_at": last_time,
                "unread_count": conv.get("unread_count", 0),
                "intent_tag": intent_tag,
                "messages": parsed_msgs,
            }

            if existing:
                await self.db.outreach_inbox_threads.update_one(
                    {"id": existing["id"]},
                    {"$set": thread_doc},
                )
            else:
                new_thread = OutreachInboxThread(**thread_doc)
                await self.db.outreach_inbox_threads.insert_one(new_thread.model_dump())

            synced_count += 1

            # If lead replied, flag lead in CRM, update campaign reply counter, and stop sequence
            if has_lead_reply:
                lead_update = await self.db.outreach_leads.update_many(
                    {
                        "workspace_id": self.workspace_id,
                        "$or": [
                            {"profile_url": {"$regex": lead_name.replace(" ", ".*"), "$options": "i"}},
                            {"linkedin_url": {"$regex": lead_name.replace(" ", ".*"), "$options": "i"}},
                            {"first_name": lead_name.split()[0] if lead_name else ""},
                        ],
                        "has_replied": False,
                    },
                    {
                        "$set": {
                            "has_replied": True,
                            "execution_state": LeadExecutionState.REPLIED,
                            "replied_at": datetime.now(timezone.utc),
                        }
                    },
                )
                if hasattr(lead_update, "modified_count") and lead_update.modified_count > 0:
                    new_replies_detected += lead_update.modified_count

                # Increment campaign reply KPIs if lead has campaign_id
                if campaign_id:
                    inc_dict = {"replies_count": 1}
                    if intent_tag == "interested":
                        inc_dict["interested_count"] = 1
                    await self.db.outreach_campaigns.update_one(
                        {"id": campaign_id},
                        {"$inc": inc_dict},
                    )

        return {
            "account_id": account_id,
            "synced_threads": synced_count,
            "new_replies_detected": new_replies_detected,
        }

    async def sync_all_accounts(self) -> dict[str, Any]:
        """
        Synchronizes all connected active accounts in the workspace.
        """
        accounts = await _fetch_cursor_docs(
            self.db.outreach_accounts.find({
                "$or": [
                    {"workspace_id": self.workspace_id},
                    {"user_id": self.user_id},
                    {"workspace_id": self.user_id},
                ]
            }),
            length=100,
        )

        total_synced = 0
        total_replies = 0
        for acc in accounts:
            res = await self.sync_account_inbox(acc["id"])
            total_synced += res.get("synced_threads", 0)
            total_replies += res.get("new_replies_detected", 0)

        return {
            "accounts_synced": len(accounts),
            "total_threads_synced": total_synced,
            "total_replies_detected": total_replies,
        }
