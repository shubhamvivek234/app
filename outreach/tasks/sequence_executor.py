"""
Phase 5: Sequence Step Executor Engine.
Evaluates DAG state machines, checks rate limits, executes actions via Voyager/Playwright,
and transitions leads to subsequent steps with delay timers.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from outreach.models import LeadExecutionState, SequenceNodeType
from outreach.core.rate_limiter import OutboundRateLimiter
from outreach.core.proxy_manager import JITProxyManager
from outreach.core.paid_access import get_active_entitlement, sender_is_ready
from outreach.core.dag_compiler import contains_ai_prompt_token, interpolate_template
from outreach.core.voice_cloner import VoiceCloner
from outreach.core.safety_shield import SafetyShield
from outreach.core.sequence_capabilities import sequence_capability_map
from outreach.engine.voyager_client import VoyagerClient

logger = logging.getLogger(__name__)

_OUTBOUND_ACTIONS = {
    SequenceNodeType.VISIT_PROFILE.value: "profile_visits",
    SequenceNodeType.CONNECTION_REQUEST.value: "connection_invites",
    SequenceNodeType.SEND_MESSAGE.value: "messages",
    SequenceNodeType.VOICE_NOTE.value: "voice_notes",
    SequenceNodeType.LIKE_LAST_POST.value: "post_likes",
    SequenceNodeType.SEND_EMAIL.value: "email_sends",
}
_CONFIRMED_STATUSES = {
    "viewed", "invite_sent", "message_sent", "voice_note_sent", "liked", "sent",
    "accepted", "found", "not_found", "completed", "confirmed", "skipped",
}


async def _pause_uncertain(db, lead: dict, operation_id: str, reason: str) -> dict[str, Any]:
    """Quarantine an ambiguous action without scheduling an automatic retry."""
    now = datetime.now(timezone.utc)
    safe_reason = reason[:180]
    await db.outreach_tasks.update_one(
        {"id": operation_id, "workspace_id": lead["workspace_id"], "status": "dispatching"},
        {"$set": {"status": "uncertain", "reason": safe_reason, "updated_at": now}},
    )
    await db.outreach_leads.update_one(
        {"id": lead["id"], "workspace_id": lead["workspace_id"]},
        {"$set": {"execution_state": LeadExecutionState.WAITING_TRIGGER,
                  "failure_reason": safe_reason, "next_action_due_at": None, "updated_at": now}},
    )
    await db.outreach_campaigns.update_one(
        {"id": lead["campaign_id"], "workspace_id": lead["workspace_id"], "status": "active"},
        {"$set": {"status": "paused", "pause_reason": "An action outcome needs manual reconciliation before resuming.",
                  "updated_at": now}},
    )
    return {"status": "action_uncertain", "action": operation_id.split(":")[-1], "reason": safe_reason}


async def _claim_operation(db, lead: dict, account: dict, node_type: str, operation_id: str) -> str:
    """One atomic pre-send claim per lead/node; existing dispatches never resend."""
    now = datetime.now(timezone.utc)
    try:
        await db.outreach_tasks.insert_one({
            "id": operation_id, "workspace_id": lead["workspace_id"],
            "user_id": account.get("user_id"), "campaign_id": lead["campaign_id"],
            "lead_id": lead["id"], "account_id": account["id"],
            "task_type": node_type, "status": "dispatching",
            "created_at": now, "updated_at": now,
        })
        return "new"
    except DuplicateKeyError:
        existing = await db.outreach_tasks.find_one({"id": operation_id, "workspace_id": lead["workspace_id"]})
        if existing and existing.get("status") in {"completed", "accepted", "skipped"}:
            return str(existing["status"])
        return "uncertain"


async def _safe_action(awaitable) -> dict[str, Any]:
    try:
        result = await awaitable
        return result if isinstance(result, dict) else {"status": "uncertain"}
    except Exception as exc:
        logger.error("Outreach provider result uncertain (%s)", type(exc).__name__)
        return {"status": "uncertain"}


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
            LeadExecutionState.BOUNCED,
            LeadExecutionState.FAILED,
        ):
            return {"status": "terminal_state", "state": lead.get("execution_state")}
        if lead.get("execution_state") == LeadExecutionState.REPLIED and not lead.get("waiting_for_reply_at"):
            return {"status": "terminal_state", "state": lead.get("execution_state")}

        # 1. Fetch Campaign and verify active status
        workspace_id = lead.get("workspace_id")
        if not workspace_id:
            return {"status": "paid_access_required"}
        campaign = await db.outreach_campaigns.find_one({
            "id": lead["campaign_id"], "workspace_id": workspace_id,
            "is_deleted": {"$ne": True},
        })
        if not campaign or campaign.get("status") != "active":
            return {"status": "campaign_not_active"}

        # 2. Verify Working Hours
        schedule_data = campaign.get("schedule") or {}
        if not OutboundRateLimiter.is_within_working_hours(schedule_data):
            logger.info("Lead %s step skipped: currently outside working hours", lead_id)
            return {"status": "outside_working_hours"}

        # 3. Fetch Assigned Sender Account
        assigned_account_id = lead.get("assigned_account_id")
        if not assigned_account_id:
            return {"status": "no_account_assigned"}

        account = await db.outreach_accounts.find_one({
            "id": assigned_account_id, "workspace_id": workspace_id,
        })
        if not account or account.get("status") != "active":
            return {"status": "account_unavailable"}

        # 4. Fetch Sequence DAG
        sequence = await db.outreach_sequences.find_one({
            "campaign_id": lead["campaign_id"],
            "workspace_id": workspace_id,
            "is_deleted": {"$ne": True},
        })
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
                {"id": lead_id, "workspace_id": workspace_id},
                {"$set": {"execution_state": LeadExecutionState.FINISHED}}
            )
            return {"status": "finished", "reason": "no_more_nodes"}

        node = nodes_lookup[curr_node_id]
        node_type = node.get("type")
        capability = sequence_capability_map().get(node_type)
        if not capability or not capability["supported"]:
            return {"status": "unsupported_action", "action": node_type,
                    "reason": "This sequence step has no verified campaign runner."}
        if not capability["live_enabled"]:
            return {"status": "action_disabled", "action": node_type,
                    "reason": "This sequence capability is disabled for this deployment."}
        if capability["channel"] == "linkedin":
            if not await sender_is_ready(db, workspace_id, account):
                return {"status": "paid_access_required"}
        elif not await get_active_entitlement(db, workspace_id):
            return {"status": "paid_access_required"}
        if contains_ai_prompt_token(node.get("config", {})):
            reason = "AI prompt tokens are not generated by the live campaign runner. Replace this step with finished message copy."
            await db.outreach_leads.update_one(
                {"id": lead_id},
                {"$set": {
                    "execution_state": LeadExecutionState.FAILED,
                    "failure_reason": reason,
                    "updated_at": datetime.now(timezone.utc),
                }}
            )
            return {"status": "action_failed", "action": node_type, "reason": reason}

        if node_type == SequenceNodeType.IF_EMAIL_AVAILABLE:
            from outreach.core.email_finder import is_lead_email_available

            available = await is_lead_email_available(db, workspace_id, lead)
            branch = "positive" if available else "negative"
            next_node_id = node.get("branches", {}).get(branch)
            now = datetime.now(timezone.utc)
            await db.outreach_leads.update_one(
                {"id": lead_id, "workspace_id": workspace_id},
                {"$set": {"current_node_id": next_node_id,
                          "execution_state": LeadExecutionState.QUEUED if next_node_id else LeadExecutionState.FINISHED,
                          "next_action_due_at": now, "updated_at": now}},
            )
            return {"status": "branch_advanced", "next_node_id": next_node_id,
                    "condition_met": bool(available)}

        # Email-only sequences must not require (or decrypt) LinkedIn cookies.
        voyager = None
        if capability["channel"] == "linkedin":
            proxy_url = JITProxyManager.format_proxy_url(account["proxy"]) if account.get("proxy") else None
            voyager = VoyagerClient(
                session_cookie_enc=account.get("session_cookie_enc", ""),
                jsession_id=account.get("jsession_id", ""),
                proxy_url=proxy_url,
            )

        # Connection and reply branches are conditions to wait for, not an
        # immediate check after sending. Keep the lead on this node until the
        # signal arrives or the seven-day branch timeout expires.
        waiting_field = "waiting_for_connection_at" if node_type in (SequenceNodeType.CONNECTION_REQUEST, SequenceNodeType.IF_CONNECTED) else (
            "waiting_for_reply_at" if node_type in (SequenceNodeType.SEND_MESSAGE, SequenceNodeType.VOICE_NOTE) else None
        )
        if waiting_field and lead.get(waiting_field):
            wait_started = lead[waiting_field]
            if isinstance(wait_started, str):
                try:
                    wait_started = datetime.fromisoformat(wait_started)
                except ValueError:
                    wait_started = datetime.now(timezone.utc)
            if wait_started.tzinfo is None:
                wait_started = wait_started.replace(tzinfo=timezone.utc)

            branch_signal = (
                await voyager.check_connection_status_strict(lead.get("linkedin_urn") or lead["linkedin_url"])
                if node_type in (SequenceNodeType.CONNECTION_REQUEST, SequenceNodeType.IF_CONNECTED)
                else bool(lead.get("has_replied"))
            )
            branches = node.get("branches", {})
            try:
                default_timeout = 3 if node_type == SequenceNodeType.IF_CONNECTED else 7
                timeout_days = max(1, min(30, int(node.get("config", {}).get("timeout_days", default_timeout))))
            except (TypeError, ValueError):
                timeout_days = 7
            timeout_at = wait_started + timedelta(days=timeout_days)
            now = datetime.now(timezone.utc)
            if branch_signal is None:
                if now >= timeout_at:
                    reason = "Connection status could not be verified before the condition deadline. Review this lead manually."
                    await db.outreach_leads.update_one(
                        {"id": lead_id, "workspace_id": workspace_id},
                        {"$set": {"execution_state": LeadExecutionState.WAITING_TRIGGER,
                                  "next_action_due_at": None, "failure_reason": reason, "updated_at": now}},
                    )
                    return {"status": "condition_needs_review", "reason": reason}
                next_check = now + timedelta(hours=1)
                await db.outreach_leads.update_one(
                    {"id": lead_id, "workspace_id": workspace_id},
                    {"$set": {"execution_state": LeadExecutionState.WAITING_DELAY,
                              "next_action_due_at": next_check, "updated_at": now}},
                )
                return {"status": "condition_unknown", "next_check_at": next_check.isoformat()}
            if branch_signal or now >= timeout_at:
                next_node_id = branches.get("positive") if branch_signal else branches.get("negative")
                updates: dict[str, Any] = {
                    "current_node_id": next_node_id,
                    "execution_state": LeadExecutionState.QUEUED if next_node_id else LeadExecutionState.FINISHED,
                    "next_action_due_at": now,
                    "updated_at": now,
                }
                if node_type in (SequenceNodeType.CONNECTION_REQUEST, SequenceNodeType.IF_CONNECTED) and branch_signal:
                    updates["is_connected"] = True
                    updates["accepted_at"] = lead.get("accepted_at") or now
                await db.outreach_leads.update_one(
                    {"id": lead_id},
                    {"$set": updates, "$unset": {waiting_field: ""}},
                )
                return {"status": "branch_advanced", "next_node_id": next_node_id, "condition_met": bool(branch_signal)}

            next_check = min(now + timedelta(hours=24), timeout_at)
            await db.outreach_leads.update_one(
                {"id": lead_id},
                {"$set": {
                    "execution_state": LeadExecutionState.WAITING_DELAY,
                    "next_action_due_at": next_check,
                    "updated_at": datetime.now(timezone.utc),
                }},
            )
            return {"status": "waiting_for_condition", "next_check_at": next_check.isoformat()}

        # 6. Execute Action with Rate Limiting
        action_name = node_type
        campaign_limits = campaign.get("limits") or {}
        action_result: dict[str, Any] | None = None
        claim_state = "none"
        operation_id = f"{lead_id}:{curr_node_id}"
        if node_type not in (SequenceNodeType.IF_CONNECTED,):
            import inspect
            tasks_col = getattr(db, "outreach_tasks", None)
            find_one = getattr(tasks_col, "find_one", None) if tasks_col is not None else None
            existing = None
            if callable(find_one):
                res = find_one({"id": operation_id, "workspace_id": workspace_id}, {"status": 1})
                if inspect.isawaitable(res):
                    existing = await res
                elif isinstance(res, dict):
                    existing = res
            if isinstance(existing, dict):
                if existing.get("status") in {"completed", "accepted", "skipped"}:
                    claim_state = str(existing["status"])
                    action_result = {"status": "skipped" if claim_state == "skipped" else "confirmed"}
                else:
                    return await _pause_uncertain(
                        db, lead, operation_id, "An earlier attempt may already have sent this action. Review before resuming.",
                    )

        if action_result is None:
            if node_type == SequenceNodeType.SEND_EMAIL:
                from outreach.core.email_finder import is_lead_email_available
                from outreach.core.mailbox_connection import get_ready_mailbox

                if not await is_lead_email_available(db, workspace_id, lead):
                    return {"status": "action_failed", "action": node_type,
                            "reason": "This lead has no valid, unsuppressed email address."}
                if not await get_ready_mailbox(db, workspace_id, account["id"]):
                    return {"status": "mailbox_unavailable", "action": node_type}

            limit_field = _OUTBOUND_ACTIONS.get(node_type)
            if limit_field and not await OutboundRateLimiter.check_and_increment_daily_limit(
                account, limit_field, db, campaign_limits,
            ):
                return {"status": "rate_limited", "action": limit_field}

            if node_type not in (SequenceNodeType.IF_CONNECTED,):
                claim_state = await _claim_operation(db, lead, account, node_type, operation_id)
                if claim_state == "uncertain":
                    return await _pause_uncertain(
                        db, lead, operation_id, "An earlier attempt may already have sent this action. Review before resuming.",
                    )
                if claim_state in {"completed", "accepted", "skipped"}:
                    action_result = {"status": "skipped" if claim_state == "skipped" else "confirmed"}

        if node_type == SequenceNodeType.VISIT_PROFILE:
            if action_result is None:
                action_result = await _safe_action(voyager.visit_profile(lead["linkedin_url"]))

        elif node_type == SequenceNodeType.CONNECTION_REQUEST:
            if action_result is None:
                note_template = node.get("config", {}).get("note", "")
                custom_note = interpolate_template(note_template, lead) if note_template else ""
                action_result = await _safe_action(voyager.send_connection_invite(
                    lead.get("linkedin_urn") or lead["linkedin_url"], custom_note,
                ))

        elif node_type == SequenceNodeType.SEND_MESSAGE:
            if action_result is None:
                body_template = node.get("config", {}).get("body", "Hi {{first_name}}")
                msg_body = interpolate_template(body_template, lead)
                action_result = await _safe_action(voyager.send_direct_message(
                    lead.get("linkedin_urn") or lead["linkedin_url"], msg_body,
                ))

        elif node_type == SequenceNodeType.LIKE_LAST_POST:
            if action_result is None:
                action_config = node.get("config", {})
                action_result = await _safe_action(voyager.like_last_post(
                    lead.get("linkedin_urn") or lead["linkedin_url"],
                    max_age_days=action_config.get("max_post_age_days", 30),
                ))
                no_post_found = (action_result.get("error") or "").lower().startswith(("no post found", "no recent post found"))
                if action_result.get("status") == "failed" and no_post_found and action_config.get("skip_if_no_posts", True):
                    action_result = {"status": "skipped"}

        elif node_type == SequenceNodeType.VOICE_NOTE:
            if action_result is None:
                try:
                    voice = await db.outreach_voices.find_one({
                        "workspace_id": workspace_id, "assigned_account_ids": account.get("id"),
                    })
                    if not voice:
                        voice = await db.outreach_voices.find_one({"workspace_id": workspace_id})
                    script_template = node.get("config", {}).get(
                        "script", "Hey {{first_name}}, saw your work at {{company_name}} and wanted to send a quick voice note!"
                    )
                    voice_id = voice.get("elevenlabs_voice_id", "voice_mock_default") if voice else "voice_mock_default"
                    audio_bytes = await VoiceCloner().synthesize_voice_note(
                        voice_id=voice_id, template_text=script_template, lead=lead,
                    )
                    action_result = await _safe_action(voyager.send_voice_note(
                        recipient_urn=lead.get("linkedin_urn") or lead["linkedin_url"],
                        audio_bytes=audio_bytes,
                        transcript=interpolate_template(script_template, lead),
                    ))
                except Exception as exc:
                    logger.error("Voice step outcome uncertain (%s)", type(exc).__name__)
                    action_result = {"status": "uncertain"}

        elif node_type == SequenceNodeType.FIND_EMAIL:
            if action_result is None:
                from outreach.core.email_finder import find_lead_email

                action_result = await _safe_action(find_lead_email(db, workspace_id=workspace_id, lead_id=lead_id))

        elif node_type == SequenceNodeType.SEND_EMAIL:
            if action_result is None:
                from outreach.core.mailbox_delivery import send_outreach_email

                config = node.get("config") or {}
                subject = config.get("subject") or ""
                body = config.get("body") or ""
                if not isinstance(subject, str) or not subject.strip() or not isinstance(body, str) or not body.strip():
                    action_result = {"status": "failed"}
                else:
                    action_result = await _safe_action(send_outreach_email(
                        db, workspace_id=workspace_id, sender_account_id=account["id"],
                        lead_id=lead_id, to_email=lead["email"],
                        subject=interpolate_template(subject, lead),
                        body=interpolate_template(body, lead), operation_id=operation_id,
                    ))
        elif node_type == SequenceNodeType.IF_CONNECTED:
            # Branch evaluation below performs the connection check; this node
            # intentionally has no outbound action and consumes no daily quota.
            action_result = {"status": "condition_checked"}

        else:
            reason = f"Unsupported sequence step: {node_type}"
            await db.outreach_leads.update_one(
                {"id": lead_id},
                {"$set": {
                    "execution_state": LeadExecutionState.FAILED,
                    "failure_reason": reason,
                    "updated_at": datetime.now(timezone.utc),
                }}
            )
            return {"status": "unsupported_action", "action": node_type}

        result_status = (action_result or {}).get("status")
        if node_type != SequenceNodeType.IF_CONNECTED:
            status_code = action_result.get("status_code") or action_result.get("http_status")
            if (node_type not in (SequenceNodeType.FIND_EMAIL, SequenceNodeType.SEND_EMAIL)
                    and isinstance(status_code, int)
                    and SafetyShield.should_trip_circuit_breaker(status_code, str(action_result.get("text") or ""))):
                await SafetyShield.trip_circuit_breaker(
                    account["id"], f"LinkedIn returned HTTP {status_code}", db,
                    workspace_id=workspace_id,
                )
                return await _pause_uncertain(
                    db, lead, operation_id, "LinkedIn restricted this sender; review the account before resuming.",
                )
            if node_type == SequenceNodeType.SEND_EMAIL and result_status == "failed":
                # A rejected provider request is a known non-send, distinct
                # from a transport timeout or a 5xx with unknown acceptance.
                reason = str(action_result.get("reason") or "Email provider rejected the message")[:180]
                await db.outreach_tasks.update_one(
                    {"id": operation_id, "workspace_id": workspace_id, "status": "dispatching"},
                    {"$set": {"status": "failed", "reason": reason, "updated_at": datetime.now(timezone.utc)}},
                )
                await db.outreach_leads.update_one(
                    {"id": lead_id, "workspace_id": workspace_id},
                    {"$set": {"execution_state": LeadExecutionState.FAILED,
                              "failure_reason": reason, "next_action_due_at": None,
                              "updated_at": datetime.now(timezone.utc)}},
                )
                return {"status": "action_failed", "action": node_type, "reason": reason}
            if result_status not in _CONFIRMED_STATUSES:
                return await _pause_uncertain(
                    db, lead, operation_id, "The provider did not confirm this action. Review its outcome before resuming.",
                )
            if claim_state == "new":
                recorded_status = "accepted" if node_type == SequenceNodeType.SEND_EMAIL else (
                    "skipped" if result_status == "skipped" else "completed"
                )
                try:
                    await db.outreach_tasks.update_one(
                        {"id": operation_id, "workspace_id": workspace_id, "status": "dispatching"},
                        {"$set": {"status": recorded_status,
                                  "provider_message_id": action_result.get("provider_message_id"),
                                  "provider_thread_id": action_result.get("provider_thread_id"),
                                  "updated_at": datetime.now(timezone.utc)}},
                    )
                except Exception as exc:
                    logger.error("Outreach action confirmation could not be recorded (%s)", type(exc).__name__)
                    return await _pause_uncertain(
                        db, lead, operation_id, "The action may have completed, but confirmation was not saved.",
                    )

        if node_type == SequenceNodeType.CONNECTION_REQUEST and node.get("branches"):
            waiting_since = datetime.now(timezone.utc)
            await db.outreach_leads.update_one(
                {"id": lead_id},
                {"$set": {
                    "waiting_for_connection_at": waiting_since,
                    "execution_state": LeadExecutionState.WAITING_DELAY,
                    "next_action_due_at": waiting_since + timedelta(hours=24),
                    "last_action_taken": action_name,
                    "last_action_at": waiting_since,
                    "updated_at": waiting_since,
                }},
            )
            return {"status": "success", "action": action_name, "waiting_for": "connection"}

        if node_type in (SequenceNodeType.SEND_MESSAGE, SequenceNodeType.VOICE_NOTE) and node.get("branches"):
            waiting_since = datetime.now(timezone.utc)
            await db.outreach_leads.update_one(
                {"id": lead_id},
                {"$set": {
                    "waiting_for_reply_at": waiting_since,
                    "execution_state": LeadExecutionState.WAITING_DELAY,
                    "next_action_due_at": waiting_since + timedelta(hours=24),
                    "last_action_taken": action_name,
                    "last_action_at": waiting_since,
                    "updated_at": waiting_since,
                }},
            )
            return {"status": "success", "action": action_name, "waiting_for": "reply"}

        # 7. Advance Lead State to Next Node in DAG
        next_node_id = None
        branches = node.get("branches", {})

        if branches.get("positive") or (node_type == SequenceNodeType.IF_CONNECTED and branches.get("negative")):
            if node_type in (SequenceNodeType.IF_CONNECTED,):
                branch_signal = await voyager.check_connection_status_strict(lead.get("linkedin_urn") or lead["linkedin_url"])
                if branch_signal is None:
                    now = datetime.now(timezone.utc)
                    next_check = now + timedelta(hours=1)
                    await db.outreach_leads.update_one(
                        {"id": lead_id, "workspace_id": workspace_id},
                        {"$set": {"execution_state": LeadExecutionState.WAITING_DELAY,
                                  "waiting_for_connection_at": lead.get("waiting_for_connection_at") or now,
                                  "next_action_due_at": next_check, "updated_at": now}},
                    )
                    return {"status": "condition_unknown", "next_check_at": next_check.isoformat()}
            else:
                branch_signal = bool(lead.get("has_replied"))
            if branch_signal:
                next_node_id = branches["positive"]
                if node_type == SequenceNodeType.IF_CONNECTED:
                    await db.outreach_leads.update_one({"id": lead_id}, {"$set": {
                        "is_connected": True,
                        "accepted_at": lead.get("accepted_at") or datetime.now(timezone.utc),
                    }})
            else:
                if node_type == SequenceNodeType.IF_CONNECTED and not lead.get("waiting_for_connection_at"):
                    waiting_since = datetime.now(timezone.utc)
                    await db.outreach_leads.update_one(
                        {"id": lead_id},
                        {"$set": {
                            "waiting_for_connection_at": waiting_since,
                            "execution_state": LeadExecutionState.WAITING_DELAY,
                            "next_action_due_at": waiting_since + timedelta(hours=24),
                            "updated_at": waiting_since,
                        }},
                    )
                    return {"status": "waiting_for_condition", "next_check_at": (waiting_since + timedelta(hours=24)).isoformat()}
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
