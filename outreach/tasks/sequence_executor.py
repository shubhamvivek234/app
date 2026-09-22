"""
Phase 5: Sequence Step Executor Engine.
Evaluates DAG state machines, checks rate limits, executes actions via Voyager/Playwright,
and transitions leads to subsequent steps with delay timers.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from outreach.models import LeadExecutionState, SequenceNodeType, WorkingSchedule
from outreach.core.rate_limiter import OutboundRateLimiter
from outreach.core.proxy_manager import JITProxyManager
from outreach.core.dag_compiler import interpolate_template
from outreach.core.voice_cloner import VoiceCloner
from outreach.engine.voyager_client import VoyagerClient

logger = logging.getLogger(__name__)


class SequenceExecutor:
    """
    Executes a single step in a lead's outreach sequence.
    """

    @staticmethod
    async def execute_lead_step(lead_id: str, db: AsyncIOMotorDatabase) -> dict[str, Any]:
        lead = await db.outreach_leads.find_one({"id": lead_id})
        if not lead:
            return {"status": "lead_not_found"}

        if lead.get("execution_state") in (
            LeadExecutionState.FINISHED,
            LeadExecutionState.REPLIED,
            LeadExecutionState.BOUNCED,
            LeadExecutionState.FAILED,
        ):
            return {"status": "terminal_state", "state": lead.get("execution_state")}

        # 1. Fetch Campaign and verify active status
        campaign = await db.outreach_campaigns.find_one({"id": lead["campaign_id"]})
        if not campaign or campaign.get("status") != "active":
            return {"status": "campaign_not_active"}

        # 2. Verify Working Hours
        schedule_data = campaign.get("schedule") or {}
        schedule = WorkingSchedule(**schedule_data) if isinstance(schedule_data, dict) else schedule_data
        if not OutboundRateLimiter.is_within_working_hours(schedule):
            logger.info("Lead %s step skipped: currently outside working hours", lead_id)
            return {"status": "outside_working_hours"}

        # 3. Fetch Assigned Sender Account
        assigned_account_id = lead.get("assigned_account_id")
        if not assigned_account_id:
            return {"status": "no_account_assigned"}

        account = await db.outreach_accounts.find_one({"id": assigned_account_id})
        if not account or account.get("status") != "active":
            return {"status": "account_unavailable"}

        # 4. Fetch Sequence DAG
        sequence = await db.outreach_sequences.find_one({"campaign_id": lead["campaign_id"]})
        if not sequence or "compiled_dag" not in sequence:
            return {"status": "sequence_not_configured"}

        compiled = sequence["compiled_dag"]
        nodes_lookup = compiled.get("nodes", {})
        root_node_ids = compiled.get("root_node_ids", [])

        # Determine current node
        curr_node_id = lead.get("current_node_id")
        if not curr_node_id:
            curr_node_id = root_node_ids[0] if root_node_ids else None

        if not curr_node_id or curr_node_id not in nodes_lookup:
            await db.outreach_leads.update_one(
                {"id": lead_id},
                {"$set": {"execution_state": LeadExecutionState.FINISHED}}
            )
            return {"status": "finished", "reason": "no_more_nodes"}

        node = nodes_lookup[curr_node_id]
        node_type = node.get("type")

        # 5. Initialize Voyager Client with proxy
        proxy_url = None
        if account.get("proxy"):
            proxy_url = JITProxyManager.format_proxy_url(account["proxy"])

        voyager = VoyagerClient(
            session_cookie_enc=account.get("session_cookie_enc", ""),
            jsession_id=account.get("jsession_id", ""),
            proxy_url=proxy_url,
        )

        # 6. Execute Action with Rate Limiting
        action_success = False
        action_name = node_type

        if node_type == SequenceNodeType.VISIT_PROFILE:
            if not await OutboundRateLimiter.check_and_increment_daily_limit(account, "profile_visits", db):
                return {"status": "rate_limited", "action": "profile_visits"}
            await voyager.visit_profile(lead["linkedin_url"])
            action_success = True

        elif node_type == SequenceNodeType.CONNECTION_REQUEST:
            if not await OutboundRateLimiter.check_and_increment_daily_limit(account, "connection_invites", db):
                return {"status": "rate_limited", "action": "connection_invites"}
            note_template = node.get("config", {}).get("note", "")
            custom_note = interpolate_template(note_template, lead) if note_template else ""
            await voyager.send_connection_invite(lead.get("linkedin_urn") or lead["linkedin_url"], custom_note)
            action_success = True

        elif node_type == SequenceNodeType.SEND_MESSAGE:
            if not await OutboundRateLimiter.check_and_increment_daily_limit(account, "messages", db):
                return {"status": "rate_limited", "action": "messages"}
            body_template = node.get("config", {}).get("body", "Hi {{first_name}}")
            msg_body = interpolate_template(body_template, lead)
            await voyager.send_direct_message(lead.get("linkedin_urn") or lead["linkedin_url"], msg_body)
            action_success = True

        elif node_type == SequenceNodeType.LIKE_LAST_POST:
            if not await OutboundRateLimiter.check_and_increment_daily_limit(account, "post_likes", db):
                return {"status": "rate_limited", "action": "post_likes"}
            await voyager.like_last_post(lead.get("linkedin_urn") or lead["linkedin_url"])
            action_success = True

        elif node_type == SequenceNodeType.VOICE_NOTE:
            if not await OutboundRateLimiter.check_and_increment_daily_limit(account, "voice_notes", db):
                return {"status": "rate_limited", "action": "voice_notes"}

            # Resolve voice assigned to this account or workspace default
            voice = await db.outreach_voices.find_one({
                "workspace_id": account.get("workspace_id"),
                "assigned_account_ids": account.get("id"),
            })
            if not voice:
                voice = await db.outreach_voices.find_one({"workspace_id": account.get("workspace_id")})

            script_template = node.get("config", {}).get(
                "script", "Hey {{first_name}}, saw your work at {{company_name}} and wanted to send a quick voice note!"
            )
            voice_id = voice.get("elevenlabs_voice_id", "voice_mock_default") if voice else "voice_mock_default"

            cloner = VoiceCloner()
            audio_bytes = await cloner.synthesize_voice_note(
                voice_id=voice_id,
                template_text=script_template,
                lead=lead,
            )

            await voyager.send_voice_note(
                recipient_urn=lead.get("linkedin_urn") or lead["linkedin_url"],
                audio_bytes=audio_bytes,
                transcript=interpolate_template(script_template, lead),
            )
            action_success = True

        else:
            # Fallback pass-through for other node types
            action_success = True

        # 7. Advance Lead State to Next Node in DAG
        next_node_id = None
        branches = node.get("branches", {})

        if branches.get("positive"):
            # If lead has positive branch (e.g. accepted invite), check status
            is_connected = await voyager.check_connection_status(lead.get("linkedin_urn") or lead["linkedin_url"])
            if is_connected:
                next_node_id = branches["positive"]
                await db.outreach_leads.update_one({"id": lead_id}, {"$set": {"is_connected": True}})
            else:
                next_node_id = branches.get("negative")
        else:
            next_node_id = node.get("next_default")

        # Determine delay for next step
        next_node = nodes_lookup.get(next_node_id) if next_node_id else None
        delay_hours = next_node.get("delay_hours", 24) if next_node else 0
        next_due = datetime.now(timezone.utc) + timedelta(hours=delay_hours)

        update_fields: dict[str, Any] = {
            "last_action_taken": action_name,
            "last_action_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        if next_node_id:
            update_fields["current_node_id"] = next_node_id
            update_fields["execution_state"] = LeadExecutionState.WAITING_DELAY if delay_hours > 0 else LeadExecutionState.QUEUED
            update_fields["next_action_due_at"] = next_due
        else:
            update_fields["execution_state"] = LeadExecutionState.FINISHED

        await db.outreach_leads.update_one({"id": lead_id}, {"$set": update_fields})
        return {
            "status": "success",
            "action": action_name,
            "next_node_id": next_node_id,
            "next_action_due_at": next_due.isoformat(),
        }
