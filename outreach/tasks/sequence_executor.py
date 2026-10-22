"""
Phase 5: Sequence Step Executor Engine.
Evaluates DAG state machines, checks rate limits, executes actions via Voyager/Playwright,
and transitions leads to subsequent steps with delay timers.
"""
import logging
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from outreach.models import LeadExecutionState, SequenceNodeType
from outreach.core.rate_limiter import OutboundRateLimiter
from outreach.core.proxy_manager import JITProxyManager
from outreach.core.paid_access import get_active_entitlement, sender_is_ready
from outreach.core.dag_compiler import (
    contains_ai_prompt_token,
    interpolate_template,
    select_step_variant,
    resolve_step_message_with_alternative,
)
from outreach.core.safety_shield import SafetyShield
from outreach.core.sequence_capabilities import sequence_capability_map
from outreach.core.authorization import authorization_snapshot, canonical_hash, dispatch_block_reason
from outreach.core.inbox_freshness import require_fresh_inbox
from outreach.core.execution_outbox import CLAIM_SECONDS, ExecutionOutbox
from outreach.core.sequence_versions import load_sequence
from outreach.core.sequence_preview import validate_pinned_sequence, checked_compiled, successor_fields, content_templates, due_block_reason, waiting_start
from outreach.core.sequence_contract import DAGValidationError

from outreach.core.sender_execution import SenderExecution
from outreach.engine.voyager_client import VoyagerClient
from outreach.core.request_guard import RequestEnvelope, RequestDenied, request_parent, unresolved_physical
from outreach.core.inbox_freshness import credential_generation
from outreach.core.content_approval import ContentApproval, CONTENT_ACTIONS, sequence_binding
from outreach.core.voice_artifacts import VoiceArtifacts
from outreach.core.session_custody import account_session
from outreach.core.proxy_custody import prepare_proxy
from outreach.tasks.sequence_dispatch import validate_dispatch_context, dispatch_intent_id

logger = logging.getLogger(__name__)

_OUTBOUND_ACTIONS = {
    SequenceNodeType.VISIT_PROFILE.value: "profile_visits",
    SequenceNodeType.CONNECTION_REQUEST.value: "connection_invites",
    SequenceNodeType.SEND_MESSAGE.value: "messages",
    SequenceNodeType.VOICE_NOTE.value: "voice_notes",
    SequenceNodeType.LIKE_LAST_POST.value: "post_likes",
    SequenceNodeType.FOLLOW.value: "follows",
    SequenceNodeType.COMMENT_LAST_POST.value: "comments",
    SequenceNodeType.ENDORSE_SKILLS.value: "profile_visits",
    SequenceNodeType.WITHDRAW_INVITE.value: "profile_visits",
    SequenceNodeType.INMAIL.value: "inmails",
    SequenceNodeType.SEND_EMAIL.value: "email_sends",
}
_CONFIRMED_STATUSES = {
    "viewed", "invite_sent", "message_sent", "voice_note_sent", "liked", "sent",
    "followed", "commented", "endorsed", "inmail_sent", "withdrawn",
    "accepted", "found", "not_found", "completed", "confirmed", "skipped",
}


async def _preflight_dispatch(db, lead: dict, expected: dict, node_type: str, *, authorizing: bool = False,
                              observing_connection: bool = False) -> str | None:
    """Re-read authority after preparation; old snapshots cannot authorize a send."""
    job_reason = await validate_dispatch_context(db, authorize_submission=authorizing)
    if job_reason:
        return job_reason
    workspace_id = expected["workspace_id"]
    current_lead = await db.outreach_leads.find_one({"id": lead["id"], "workspace_id": workspace_id})
    campaign = await db.outreach_campaigns.find_one({"id": expected["campaign_id"], "workspace_id": workspace_id})
    account = await db.outreach_accounts.find_one({"id": expected["sender_id"], "workspace_id": workspace_id})
    sequence = await load_sequence(db, workspace_id, expected["campaign_id"], campaign=campaign)
    if not all(isinstance(doc, dict) for doc in (current_lead, campaign, account, sequence)):
        return "dispatch_context_missing"
    reason = dispatch_block_reason(current_lead, campaign, account, sequence, expected)
    if reason:
        return reason
    due_reason = due_block_reason(current_lead, datetime.now(timezone.utc))
    if due_reason:
        return due_reason
    try:
        pinned = validate_pinned_sequence(sequence)
        current_node = pinned['nodes'].get(current_lead.get('current_node_id'))
        if not current_node or current_node['type'] != node_type:
            return 'sequence_review_required'
        if node_type == 'connection_request' and current_lead.get('is_connected') is True:
            return 'already_connected'
        if node_type == 'connection_request' and current_lead.get('withdrawn_at'):
            from outreach.core.paid_access import _utc
            withdrawn_dt = _utc(current_lead.get('withdrawn_at'))
            if withdrawn_dt and (datetime.now(timezone.utc) - withdrawn_dt) < timedelta(days=21):
                return 'reconnect_cooldown_21_days'
        if node_type == 'connection_request' and account.get('weekly_invite_limit_reached') is True:
            from outreach.core.paid_access import _utc
            reset_dt = _utc(account.get('weekly_invite_reset_at'))
            if reset_dt is None or reset_dt > datetime.now(timezone.utc):
                return 'weekly_invite_limit_reached'
        for text in content_templates({"id": current_lead.get('current_node_id'), **current_node}, lead=current_lead).values():
            rendered = interpolate_template(text, current_lead)
            if '{{' in rendered or '}}' in rendered:
                return 'sequence_variables_missing'
    except (DAGValidationError, TypeError, AttributeError):
        return 'sequence_review_required'
    if current_lead.get("current_node_id") != lead.get("current_node_id"):
        return "lead_changed"
    from outreach.core.connection_waits import scope_guard
    reason = await scope_guard(db, current_lead, campaign, sequence, account, for_observation=observing_connection)
    if reason:
        return reason
    if not OutboundRateLimiter.is_within_working_hours(campaign.get("schedule") or {}):
        return "outside_working_hours"
    remember_schedule = getattr(type(db), "note_schedule", None)
    if callable(remember_schedule):
        remember_schedule(db, campaign.get("schedule") or {})
    capability = sequence_capability_map().get(node_type, {})
    if not capability.get("live_enabled"):
        return "action_disabled"
    if capability.get("channel") == "linkedin":
        if not await sender_is_ready(db, workspace_id, account):
            return "paid_access_required"
        if node_type in {"send_message", "voice_note"} or lead.get("last_action_at"):
            reason = await require_fresh_inbox(db, workspace_id, account)
            if reason:
                return reason
    elif not await get_active_entitlement(db, workspace_id):
        return "paid_access_required"
    if node_type in {'has_data_in_column', 'if_email_available'}:
        saved = current_lead.get('identifiers')
        if (any(current_lead.get(key) is not None and not isinstance(current_lead[key], str) for key in
                ('email', 'phone', 'linkedin_url', 'linkedin_urn', 'member_urn'))
                or saved is not None and (not isinstance(saved, dict)
                    or any(value is not None and not isinstance(value, str) for value in saved.values()))):
            return 'condition_identity_review_required'
    from outreach.core.lead_importer import check_compound_suppression
    if await check_compound_suppression(workspace_id, [current_lead], db):
        return "lead_suppressed"
    if capability.get("channel") == "linkedin":
        if await _recipient_has_reply(db, workspace_id, expected["sender_id"], current_lead):
            return "lead_suppressed"
    return None


async def _recipient_has_reply(db, workspace_id: str, sender_id: str, lead: dict) -> bool:
    from outreach.core.lead_importer import normalize_linkedin_url
    identities = []
    saved = lead.get("identifiers") or {}
    members = {value for value in (lead.get("linkedin_urn"), lead.get("member_urn"), saved.get("member_urn")) if value}
    if members:
        identities.append({"lead_urn": {"$in": sorted(members)}})
    urls = set()
    for value in (lead.get("linkedin_url"), saved.get("normalized_url")):
        profile_url = normalize_linkedin_url(value or "")
        if profile_url:
            bare = profile_url.replace("https://www.linkedin.com/", "https://linkedin.com/")
            urls.update((bare, bare.replace("https://linkedin.com/", "https://www.linkedin.com/")))
    if urls:
        identities.append({"lead_profile_url": {"$in": sorted(urls)}})
    if not identities:
        return False
    from outreach.core.restore_reply_stops import has_reply_stop
    if await has_reply_stop(db, workspace_id, sender_id, members, urls):
        return True
    # Fence existing conversations even before their first reply. A reply
    # update then conflicts with dispatch instead of hiding behind a negative
    # already-replied query. Excessive matches conservatively suppress work.
    threads = await db.outreach_inbox_threads.find({"workspace_id": workspace_id,
        "account_id": sender_id, "$or": identities}).limit(101).to_list(length=101)
    return len(threads) > 100 or any(thread.get("has_lead_reply") or
        any(message.get("sender_type") == "lead" for message in thread.get("messages") or []) for thread in threads)


async def _advance_lead(db, lead: dict, updates: dict, *, unset: dict | None = None) -> bool:
    """CAS advancement cannot erase a reply observed during preparation/submission."""
    from outreach.core.search_sources import SEARCH_PROVENANCE_QUERY, unverified_search_lead
    if unverified_search_lead(lead):
        return False
    query = {"id": lead["id"], "workspace_id": lead["workspace_id"],
             "campaign_id": lead["campaign_id"], "current_node_id": lead.get("current_node_id"),
             "execution_state": lead.get("execution_state"), "$nor": [SEARCH_PROVENANCE_QUERY]}
    if not lead.get("has_replied"):
        query["has_replied"] = {"$ne": True}
    if "authorized_revision" in lead:
        query["authorized_revision"] = lead["authorized_revision"]
    if lead.get("execution_claim_token"):
        query["execution_claim_token"] = lead["execution_claim_token"]
    if lead.get('connection_wait_required') or lead.get('connection_wait_id'):
        query.update({'connection_wait_id': lead.get('connection_wait_id'), 'connection_wait_revision': lead.get('connection_wait_revision')})
    if await validate_dispatch_context():
        return False
    update = {"$set": updates, **({"$unset": unset} if unset else {})}
    if lead.get('connection_wait_required') or lead.get('connection_wait_id'):
        from outreach.core.connection_waits import advance_scoped
        return await advance_scoped(db, lead, query, update)
    result = await db.outreach_leads.update_one(query, update)
    return getattr(result, "matched_count", 0) == 1


async def _pause_uncertain(db, lead: dict, operation_id: str, reason: str, *,
                           expected_revision: int | None = None, expected_node_id: str | None = None) -> dict[str, Any]:
    """Quarantine an ambiguous action without scheduling an automatic retry."""
    now = datetime.now(timezone.utc)
    safe_reason = reason[:180]
    changed = await db.outreach_tasks.update_one(
        {"id": operation_id, "workspace_id": lead["workspace_id"], "status": {"$in": ["preparing", "dispatching"]}},
        {"$set": {"status": "uncertain", "reason": safe_reason, "updated_at": now}},
    )
    if getattr(changed, "matched_count", 0) == 0:
        current_task = await db.outreach_tasks.find_one({"id": operation_id, "workspace_id": lead["workspace_id"]})
        if not isinstance(current_task, dict) or current_task.get("status") != "uncertain":
            return {"status": "action_uncertain", "reason": safe_reason}
    revision = expected_revision if expected_revision is not None else lead.get("authorized_revision")
    revision_filter = {"authorized_revision": revision} if isinstance(revision, int) else {}
    campaign_revision_filter = {"authorization_revision": revision} if isinstance(revision, int) else {}
    node_id = expected_node_id if expected_node_id is not None else lead.get("current_node_id")
    from outreach.core.search_sources import SEARCH_PROVENANCE_QUERY
    await db.outreach_leads.update_one(
        {"id": lead["id"], "workspace_id": lead["workspace_id"], "campaign_id": lead["campaign_id"],
         "current_node_id": node_id, **revision_filter, "has_replied": {"$ne": True},
         "execution_state": {"$nin": ["replied", "bounced", "finished"]}, "$nor": [SEARCH_PROVENANCE_QUERY]},
        {"$set": {"execution_state": LeadExecutionState.WAITING_TRIGGER,
                  "failure_reason": safe_reason, "next_action_due_at": None, "updated_at": now}},
    )
    await db.outreach_campaigns.update_one(
        {"id": lead["campaign_id"], "workspace_id": lead["workspace_id"], "status": "active", **campaign_revision_filter},
        {"$set": {"status": "paused", "pause_reason": "An action outcome needs manual reconciliation before resuming.",
                  "updated_at": now}, "$inc": {"authorization_revision": 1},
         "$addToSet": {"pause_reasons": "unknown_outcome"}},
    )
    return {"status": "action_uncertain", "action": operation_id.split(":")[-1], "reason": safe_reason}


async def _claim_operation(db, lead: dict, account: dict, node_type: str, operation_id: str,
                           owner_token: str, intent_id: str) -> str:
    """One atomic pre-send claim per lead/node; existing dispatches never resend."""
    now = datetime.now(timezone.utc)
    try:
        await db.outreach_tasks.insert_one({
            "id": operation_id, "workspace_id": lead["workspace_id"],
            "user_id": account.get("user_id"), "campaign_id": lead["campaign_id"],
            "lead_id": lead["id"], "account_id": account["id"],
            "task_type": node_type, "status": "preparing", "owner_token": owner_token, "intent_id": intent_id,
            "claim_expires_at": now + timedelta(seconds=CLAIM_SECONDS),
            "created_at": now, "updated_at": now,
        })
        return "new"
    except DuplicateKeyError:
        existing = await db.outreach_tasks.find_one({"id": operation_id, "workspace_id": lead["workspace_id"]})
        if existing and existing.get("status") in {"completed", "accepted", "skipped"}:
            return str(existing["status"])
        if existing and existing.get("status") in {"preparing", "not_submitted"}:
            reclaimed = await db.outreach_tasks.update_one(
                {"id": operation_id, "workspace_id": lead["workspace_id"], "$or": [
                    {"status": "not_submitted"},
                    {"status": "preparing", "claim_expires_at": {"$lte": now}},
                ]},
                {"$set": {"status": "preparing", "owner_token": owner_token, "intent_id": intent_id,
                          "claim_expires_at": now + timedelta(seconds=CLAIM_SECONDS), "updated_at": now}},
            )
            return "new" if reclaimed.matched_count == 1 else "busy"
        return "uncertain"


async def _safe_action(awaitable) -> dict[str, Any]:
    try:
        result = await awaitable
        return result if isinstance(result, dict) else {"status": "uncertain"}
    except RequestDenied:
        raise
    except Exception as exc:
        logger.error("Outreach provider result uncertain (%s)", type(exc).__name__)
        return {"status": "uncertain"}


async def _defer_operation(db, lead, operation_id, intent_id, owner, reason, *, after_marker=False):
    outbox = ExecutionOutbox(db)
    if after_marker:
        changed = await outbox.abort_before_call(lead["workspace_id"], intent_id, owner, reason)
    else:
        changed = await outbox.defer(lead["workspace_id"], intent_id, owner, reason)
    if not changed:
        return {"status": "uncertain"} if after_marker else {"status": "action_busy", "not_submitted": True}
    await db.outreach_tasks.update_one(
        {"id": operation_id, "workspace_id": lead["workspace_id"], "owner_token": owner,
         "status": {"$in": ["preparing", "dispatching"]}},
        {"$set": {"status": "not_submitted", "defer_reason": reason}},
    )
    return {"status": reason, "not_submitted": True}


async def _approved_content(db, lead, expected, action, content, *, voice_clip=None):
    if action not in CONTENT_ACTIONS:
        return None
    service = ContentApproval(db)
    try:
        binding = await service.require_sequence(lead, expected, action, content, voice_clip=voice_clip)
    except ValueError as exc:
        raise RequestDenied("content_changed") from exc
    if not await service.allowed(binding):
        raise RequestDenied("content_approval_required")
    return binding


async def _load_voice_clip(db, binding):
    service = VoiceArtifacts(db)
    artifact_id = canonical_hash(binding)
    return await service.prepare_load(binding["workspace_id"], artifact_id)


async def _dispatch_action(db, lead: dict, expected: dict, node_type: str, operation_id: str,
                           intent_id: str, owner: str, factory, *, content: Any = None,
                           skip_empty_post: bool = False, voice_clip=None) -> dict:
    """Lazy call after current ownership, final authority checks, and evidence."""
    outbox = ExecutionOutbox(db)
    workspace_id, sender_id = expected["workspace_id"], expected["sender_id"]
    try:
        approval_binding = await _approved_content(db, lead, expected, node_type, content, voice_clip=voice_clip)
    except RequestDenied as exc:
        return await _defer_operation(db, lead, operation_id, intent_id, owner, exc.reason)

    async def require_captured_approval(current):
        binding = await _approved_content(current, lead, expected, node_type, content, voice_clip=voice_clip)
        if binding != approval_binding:
            raise RequestDenied("content_changed")

    guard = SenderExecution(db)
    if not await guard.acquire(workspace_id, sender_id, owner):
        return await _defer_operation(db, lead, operation_id, intent_id, owner, "sender_busy")
    try:
        blocked = await _preflight_dispatch(db, lead, expected, node_type)
        if not blocked:
            try:
                await require_captured_approval(db)
            except RequestDenied as exc:
                blocked = exc.reason
        if blocked:
            return await _defer_operation(db, lead, operation_id, intent_id, owner, blocked)
        if not await guard.begin(workspace_id, sender_id, owner):
            return await _defer_operation(db, lead, operation_id, intent_id, owner, "sender_busy")
        if not await outbox.begin_submission(workspace_id, intent_id, owner, content_hash=canonical_hash(content), expected=expected):
            return {"status": "action_busy", "not_submitted": True}
        promoted = await db.outreach_tasks.update_one(
            {"id": operation_id, "workspace_id": workspace_id, "owner_token": owner, "status": "preparing"},
            {"$set": {"status": "dispatching", "updated_at": datetime.now(timezone.utc)}},
        )
        if getattr(promoted, "matched_count", 0) == 0:
            await outbox.finish(workspace_id, intent_id, owner, "unknown_outcome")
            return {"status": "uncertain"}
        # Evidence writes may yield. Re-check after them, then linearize local
        # reply suppression on the lead record immediately before the call.
        blocked = await _preflight_dispatch(db, lead, expected, node_type)
        if not blocked:
            try:
                await require_captured_approval(db)
            except RequestDenied as exc:
                blocked = exc.reason
        if not blocked:
            permitted = await db.outreach_leads.update_one(
                {"id": lead["id"], "workspace_id": workspace_id, "campaign_id": expected["campaign_id"],
                 "current_node_id": lead.get("current_node_id"), "execution_state": lead.get("execution_state"),
                 "authorized_revision": expected["revision"], "assigned_account_id": sender_id,
                 "sequence_version": expected["sequence_version"],
                 "has_replied": {"$ne": True}, "do_not_contact": {"$ne": True}, "is_suppressed": {"$ne": True}},
                {"$set": {"submission_owner_token": owner}},
            )
            if getattr(permitted, "matched_count", 0) == 0:
                blocked = "lead_changed"
        if blocked:
            return await _defer_operation(db, lead, operation_id, intent_id, owner, blocked, after_marker=True)
        async def validate_subrequest():
            reason = await _preflight_dispatch(db, lead, expected, node_type)
            if not reason:
                try:
                    await require_captured_approval(db)
                except RequestDenied as exc:
                    reason = exc.reason
            return reason

        async def authorize_subrequest(current):
            reason = await _preflight_dispatch(current, lead, expected, node_type, authorizing=True)
            if not reason:
                try:
                    await require_captured_approval(current)
                except RequestDenied as exc:
                    reason = exc.reason
            return reason
        with request_parent(owner, validate_subrequest, approval_binding=approval_binding,
                transaction_validator=authorize_subrequest) as parent:
            try:
                result = await _safe_action(factory())
            except RequestDenied as exc:
                if parent.mutation_attempted:
                    result = {"status": "uncertain"}
                else:
                    return await _defer_operation(db, lead, operation_id, intent_id, owner, exc.reason, after_marker=True)
        if (skip_empty_post and result.get("status") == "failed"
                and str(result.get("error") or "").lower().startswith(("no post found", "no recent post found"))):
            result = {"status": "skipped"}
        result_status = result.get("status")
        outcome = ("request_observed" if result_status in {"viewed", "found", "not_found", "skipped"} else
                   "provider_accepted" if result_status in _CONFIRMED_STATUSES else
                   "failed" if node_type == "send_email" and result_status == "failed" else "unknown_outcome")
        try:
            recorded = await outbox.finish(workspace_id, intent_id, owner, outcome,
                                           provider_message_id=result.get("provider_message_id"),
                                           provider_thread_id=result.get("provider_thread_id"),
                                           provider_result_status=result_status,
                                           provider_recipient_urn=result.get('provider_recipient_urn'),
                                           provider_request_id=result.get('provider_request_id'))
        except Exception as exc:
            logger.error("Execution evidence save failed (%s)", type(exc).__name__)
            return {"status": "uncertain"}
        return result if recorded else {"status": "uncertain"}
    finally:
        # A process crash cannot execute this release: in-flight ownership stays
        # latched for reconciliation instead of becoming another send permit.
        physical_unknown = await unresolved_physical(db, workspace_id, sender_id, owner)
        if not physical_unknown:
            await guard.release(workspace_id, sender_id, owner)


class SequenceExecutor:
    """
    Executes a single step in a lead's outreach sequence.
    """

    @staticmethod
    async def execute_lead_step(lead_id: str, db: AsyncIOMotorDatabase, *, workspace_id: str | None = None) -> dict[str, Any]:
        try:
            return await SequenceExecutor._execute_lead_step(lead_id, db, workspace_id=workspace_id)
        except RequestDenied as exc:
            logger.info("Lead step execution deferred lead_id=%s workspace_id=%s reason=%s", lead_id, workspace_id, exc.reason)
            return {"status": "request_deferred", "reason": exc.reason, "retry_after": exc.retry_after, "not_submitted": True}

    @staticmethod
    async def _execute_lead_step(lead_id: str, db: AsyncIOMotorDatabase, *, workspace_id: str | None = None) -> dict[str, Any]:
        job_reason = await validate_dispatch_context()
        if job_reason:
            return {"status": job_reason, "not_submitted": True}
        lead = await db.outreach_leads.find_one({"id": lead_id, **({"workspace_id": workspace_id} if workspace_id else {})})
        if not lead:
            return {"status": "lead_not_found"}
        from outreach.core.search_sources import unverified_search_lead
        if unverified_search_lead(lead):
            return {"status": "search_source_review_required", "not_submitted": True}

        if lead.get("execution_state") in (
            LeadExecutionState.FINISHED,
            LeadExecutionState.BOUNCED,
            LeadExecutionState.FAILED,
            LeadExecutionState.WAITING_TRIGGER,
            "paused",
        ):
            return {"status": "terminal_state", "state": lead.get("execution_state")}
        if lead.get("execution_state") == LeadExecutionState.REPLIED or lead.get("has_replied"):
            return {"status": "terminal_state", "state": LeadExecutionState.REPLIED}

        due_reason = due_block_reason(lead, datetime.now(timezone.utc))
        if due_reason:
            return {"status": due_reason, "not_submitted": True}

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
        if campaign.get("pause_reasons"):
            return {"status": "campaign_paused"}

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
        sequence = await load_sequence(db, workspace_id, lead["campaign_id"], campaign=campaign)
        if not sequence or "compiled_dag" not in sequence:
            return {"status": "sequence_not_configured"}

        compiled = sequence["compiled_dag"]
        try:
            checked_compiled(compiled)
        except DAGValidationError as exc:
            logger.warning("Compiled DAG validation failed for lead_id=%s workspace_id=%s (%s)", lead_id, workspace_id, type(exc).__name__)
            return {"status": "sequence_review_required", "not_submitted": True,
                    "reason": "Review the saved execution graph before starting new work."}
        nodes_lookup = compiled.get("nodes", {})
        root_node_ids = compiled.get("root_node_ids", [])

        # Determine current node
        curr_node_id = lead.get("current_node_id")
        if not isinstance(curr_node_id, str) or not curr_node_id or curr_node_id not in nodes_lookup:
            return {"status": "sequence_review_required", "not_submitted": True,
                    "reason": "Review the saved current step before starting new work."}

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
        try:
            validate_pinned_sequence(sequence)
            wait_started = waiting_start(lead, node_type, datetime.now(timezone.utc))
        except DAGValidationError as exc:
            logger.warning("Pinned sequence validation failed for lead_id=%s workspace_id=%s (%s)", lead_id, workspace_id, type(exc).__name__)
            return {"status": "sequence_review_required", "not_submitted": True,
                    "reason": "Review and save a valid sequence revision before starting new work."}
        if contains_ai_prompt_token(node.get("config", {})):
            reason = "AI prompt tokens are not generated by the live campaign runner. Replace this step with finished message copy."
            await _advance_lead(db, lead, {
                    "execution_state": LeadExecutionState.FAILED,
                    "failure_reason": reason,
                    "updated_at": datetime.now(timezone.utc),
                })
            return {"status": "action_failed", "action": node_type, "reason": reason}

        # Pre-dispatch Dripify LinkedIn delivery & variable safety checks (Video #13 & #15):
        # 1. Alternative message resolution & missing profile variable check
        # 2. Connection request note > 300 characters check
        _, precheck_config = select_step_variant({"id": curr_node_id, **node}, lead)
        if node_type in (SequenceNodeType.CONNECTION_REQUEST, SequenceNodeType.SEND_MESSAGE, SequenceNodeType.INMAIL):
            alt_template = precheck_config.get("alternative_message") or precheck_config.get("fallback") or ""
            if node_type == SequenceNodeType.CONNECTION_REQUEST:
                primary_tpl = precheck_config.get("note", "")
            elif node_type == SequenceNodeType.INMAIL:
                primary_tpl = precheck_config.get("body") or precheck_config.get("message") or "Hi {{first_name}}"
            else:
                primary_tpl = precheck_config.get("body", "Hi {{first_name}}")
            strict_vars = bool(precheck_config.get("require_all_variables"))
            resolved_msg = resolve_step_message_with_alternative(
                primary_tpl,
                alt_template,
                lead,
                strict_missing_check=strict_vars,
            ) if primary_tpl else {"text": "", "used_alternative": False, "missing_variables": [], "failed_missing_variable": False}
            if resolved_msg.get("failed_missing_variable"):
                missing_list = ", ".join(resolved_msg.get("missing_variables") or [])
                reason = f"Missing profile variable ({missing_list}) on lead profile and no alternative message set."
                await _advance_lead(db, lead, {
                    "execution_state": LeadExecutionState.FAILED,
                    "failure_code": "missing_profile_variable",
                    "failure_reason": reason[:180],
                    "next_action_due_at": None,
                    "updated_at": datetime.now(timezone.utc),
                })
                return {
                    "status": "action_failed",
                    "action": node_type,
                    "failure_code": "missing_profile_variable",
                    "reason": reason[:180],
                }
            if node_type == SequenceNodeType.CONNECTION_REQUEST and len(resolved_msg.get("text") or "") > 300:
                reason = f"Connection request note exceeds LinkedIn's 300-character limit ({len(resolved_msg['text'])} chars)."
                await _advance_lead(db, lead, {
                    "execution_state": LeadExecutionState.FAILED,
                    "failure_code": "note_exceeds_300_chars",
                    "failure_reason": reason[:180],
                    "next_action_due_at": None,
                    "updated_at": datetime.now(timezone.utc),
                })
                return {
                    "status": "action_failed",
                    "action": node_type,
                    "failure_code": "note_exceeds_300_chars",
                    "reason": reason[:180],
                }

        from outreach.tasks.connection_recheck import recheck_connection
        connection_result = await recheck_connection(db, lead, campaign, sequence, account, node_type)
        if connection_result is not None:
            return connection_result

        if node_type in (SequenceNodeType.HAS_DATA_IN_COLUMN, SequenceNodeType.IF_EMAIL_AVAILABLE):
            from outreach.core.sequence_conditions import decide
            return await decide(db, lead)

        if node_type == SequenceNodeType.ADD_TAG:
            _, effective_config = select_step_variant({"id": curr_node_id, **node}, lead)
            tag_val = str(effective_config.get("tag_name") or effective_config.get("auto_tag") or "").strip()
            existing_tags = list(lead.get("tags") or [])
            if tag_val and tag_val not in existing_tags:
                existing_tags.append(tag_val)
            now_done = datetime.now(timezone.utc)
            next_node_id = node.get("next_default")
            transition = successor_fields(compiled, next_node_id, now_done)
            next_due = transition["next_action_due_at"]
            tag_updates: dict[str, Any] = {
                **transition,
                "tags": existing_tags,
                "last_action_taken": SequenceNodeType.ADD_TAG,
                "last_action_at": now_done,
                "updated_at": now_done,
            }
            if not await _advance_lead(db, lead, tag_updates):
                return {"status": "lead_changed", "action": SequenceNodeType.ADD_TAG}
            return {
                "status": "success",
                "action": SequenceNodeType.ADD_TAG,
                "tag_applied": tag_val,
                "next_node_id": next_node_id,
                "next_action_due_at": next_due.isoformat() if next_due else None,
            }

        # Email-only sequences must not require (or decrypt) LinkedIn cookies.
        voyager = None
        if capability["channel"] == "linkedin":
            prepared_proxy = await prepare_proxy(account["proxy"], workspace_id) if account.get("proxy") else None
            proxy_url = prepared_proxy.url if prepared_proxy else None
            voyager = VoyagerClient(
                **(await account_session(account)),
                proxy_url=proxy_url,
                request_envelope=RequestEnvelope(db, workspace_id, account["id"], credential_generation(account), "sequence", proxy_url,
                    operation_id=dispatch_intent_id() or f'{lead_id}:{curr_node_id}',
                    prepared_proxy=prepared_proxy, campaign_limits=campaign.get("limits") or {},
                    authority_validator=lambda: _preflight_dispatch(db, lead, authorization_snapshot(campaign, account, sequence), node_type),
                    transaction_validator=lambda current: _preflight_dispatch(current, lead, authorization_snapshot(campaign, account, sequence), node_type)),
            )

        # Connection and reply branches are conditions to wait for, not an
        # immediate check after sending. Keep the lead on this node until the
        # signal arrives or the seven-day branch timeout expires.
        waiting_field = "waiting_for_connection_at" if node_type in (SequenceNodeType.CONNECTION_REQUEST, SequenceNodeType.IF_CONNECTED) else (
            "waiting_for_reply_at" if node_type in (SequenceNodeType.SEND_MESSAGE, SequenceNodeType.VOICE_NOTE) else None
        )
        if waiting_field and wait_started is not None:
            branch_signal = (
                await voyager.check_connection_status_strict(lead.get("linkedin_urn") or lead["linkedin_url"])
                if node_type in (SequenceNodeType.CONNECTION_REQUEST, SequenceNodeType.IF_CONNECTED)
                else bool(lead.get("has_replied"))
            )
            if node_type in (SequenceNodeType.SEND_MESSAGE, SequenceNodeType.VOICE_NOTE) and not branch_signal:
                if await require_fresh_inbox(db, workspace_id, account):
                    branch_signal = None
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
                    reason = "The condition could not be verified before its deadline. Review this lead manually."
                    await _advance_lead(db, lead, {"execution_state": LeadExecutionState.WAITING_TRIGGER,
                                  "next_action_due_at": None, "failure_reason": reason, "updated_at": now})
                    return {"status": "condition_needs_review", "reason": reason}
                next_check = now + timedelta(hours=1)
                await _advance_lead(db, lead, {"execution_state": LeadExecutionState.WAITING_DELAY,
                              "next_action_due_at": next_check, "updated_at": now})
                return {"status": "condition_unknown", "next_check_at": next_check.isoformat()}
            if branch_signal or now >= timeout_at:
                next_node_id = branches.get("positive") if branch_signal else branches.get("negative")
                updates: dict[str, Any] = {
                    **successor_fields(compiled, next_node_id, now),
                    "updated_at": now,
                }
                if node_type in (SequenceNodeType.CONNECTION_REQUEST, SequenceNodeType.IF_CONNECTED) and branch_signal:
                    newly_connected = not lead.get("is_connected")
                    updates["is_connected"] = True
                    updates["accepted_at"] = lead.get("accepted_at") or now
                    if newly_connected:
                        try:
                            from outreach.core.event_outbox import record_outbox_event
                            from outreach.core.event_definitions import WebhookEvent

                            lead_display_name = (
                                f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
                                or lead.get("name")
                                or "Prospect"
                            )
                            await record_outbox_event(
                                db=db,
                                workspace_id=workspace_id,
                                event_type=WebhookEvent.CONNECTION_ACCEPTED,
                                aggregate_id=lead_id,
                                dedupe_key=f"lead.connection_accepted:{lead_id}",
                                data={
                                    "lead_id": lead_id,
                                    "lead_name": lead_display_name,
                                    "campaign_id": lead.get("campaign_id"),
                                    "channel": "linkedin",
                                    "linkedin_url": lead.get("linkedin_url"),
                                    "sender_account_id": assigned_account_id,
                                },
                            )
                        except Exception as outbox_err:
                            logger.warning("Failed to record connection accepted outbox event for lead %s: %s", lead_id, outbox_err)
                if not await _advance_lead(db, lead, updates, unset={waiting_field: ""}):
                    return {"status": "lead_changed"}
                return {"status": "branch_advanced", "next_node_id": next_node_id, "condition_met": bool(branch_signal)}

            next_check = min(now + timedelta(hours=24), timeout_at)
            await _advance_lead(db, lead, {
                    "execution_state": LeadExecutionState.WAITING_DELAY,
                    "next_action_due_at": next_check,
                    "updated_at": datetime.now(timezone.utc),
                })
            return {"status": "waiting_for_condition", "next_check_at": next_check.isoformat()}

        # 6. Execute Action with Rate Limiting
        action_name = node_type
        campaign_limits = campaign.get("limits") or {}
        expected_authorization = authorization_snapshot(campaign, account, sequence)
        action_result: dict[str, Any] | None = None
        claim_state = "none"
        operation_owner = str(uuid.uuid4())
        intent_id = ""
        operation_id = f"{lead_id}:{curr_node_id}"
        if node_type not in (SequenceNodeType.IF_CONNECTED, SequenceNodeType.OPEN_PROFILE_CHECK):
            import inspect
            tasks_col = getattr(db, "outreach_tasks", None)
            find_one = getattr(tasks_col, "find_one", None) if tasks_col is not None else None
            existing = None
            if callable(find_one):
                res = find_one({"id": operation_id, "workspace_id": workspace_id}, {"status": 1, "intent_id": 1, "claim_expires_at": 1})
                if inspect.isawaitable(res):
                    existing = await res
                elif isinstance(res, dict):
                    existing = res
            if isinstance(existing, dict) and existing.get("intent_id") and existing.get("status") in {"preparing", "dispatching"}:
                intent_record = await db.outreach_intents.find_one({"_id": existing["intent_id"], "workspace_id": workspace_id})
                if isinstance(intent_record, dict) and intent_record.get("status") == "executed":
                    from outreach.core.execution_recovery import recover_intent
                    await recover_intent(db, intent_record)
                    existing = await db.outreach_tasks.find_one({"id": operation_id, "workspace_id": workspace_id})
            if isinstance(existing, dict):
                if existing.get("status") in {"completed", "accepted", "skipped"}:
                    claim_state = str(existing["status"])
                    action_result = {"status": "skipped" if claim_state == "skipped" else "confirmed"}
                elif existing.get("status") not in {"preparing", "not_submitted"}:
                    from outreach.core.paid_access import _utc
                    expiry = _utc(existing.get("claim_expires_at"))
                    if existing.get("intent_id") and existing.get("status") == "dispatching" and expiry and expiry > datetime.now(timezone.utc):
                        return {"status": "action_busy"}
                    return await _pause_uncertain(
                        db, lead, operation_id, "An earlier attempt may already have sent this action. Review before resuming.",
                    )

        if action_result is None:
            if node_type not in (SequenceNodeType.IF_CONNECTED, SequenceNodeType.OPEN_PROFILE_CHECK):
                blocked = await _preflight_dispatch(db, lead, expected_authorization, node_type)
                if blocked:
                    return {"status": blocked, "action": node_type}
            if node_type == SequenceNodeType.SEND_EMAIL:
                from outreach.core.email_finder import is_lead_email_available
                from outreach.core.mailbox_connection import get_ready_mailbox

                if not await is_lead_email_available(db, workspace_id, lead):
                    return {"status": "action_failed", "action": node_type,
                            "reason": "This lead has no valid, unsuppressed email address."}
                if not await get_ready_mailbox(db, workspace_id, account["id"]):
                    return {"status": "mailbox_unavailable", "action": node_type}
                config = node.get("config") or {}
                from outreach.core.mailbox_delivery import render_email_body
                try:
                    mailbox = await get_ready_mailbox(db, workspace_id, account["id"])
                    await _approved_content(db, lead, expected_authorization, node_type, {
                        "subject": interpolate_template(config.get("subject") or "", lead).strip(),
                        "body": render_email_body(interpolate_template(config.get("body") or "", lead)),
                        "sender_email": (mailbox or {}).get("email") or ""})
                except RequestDenied as exc:
                    return {"status": exc.reason, "action": node_type, "not_submitted": True}

            if node_type not in (SequenceNodeType.IF_CONNECTED, SequenceNodeType.OPEN_PROFILE_CHECK):
                outbox = ExecutionOutbox(db)
                intent = await outbox.ensure(
                    workspace_id=workspace_id, campaign_id=lead["campaign_id"], lead_id=lead_id,
                    sender_id=account["id"], node_id=curr_node_id, action_kind=node_type,
                    sequence_version=sequence.get("version", 1),
                    authorization_revision=campaign.get("authorization_revision", 0),
                    credential_generation=expected_authorization["credential_generation"],
                    legacy_operation_id=operation_id, enrollment_id=lead.get("enrollment_id"),
                )
                intent_id = intent["_id"]
                if dispatch_intent_id() and intent_id != dispatch_intent_id():
                    return {"status": "stale_job", "not_submitted": True}
                if not await outbox.claim(workspace_id, intent_id, operation_owner):
                    if intent.get("status") == "unknown_outcome":
                        return await _pause_uncertain(db, lead, operation_id, "An earlier submission requires outcome review.")
                    return {"status": "action_busy"}
                claim_state = await _claim_operation(db, lead, account, node_type, operation_id, operation_owner, intent_id)
                if claim_state == "busy":
                    await outbox.defer(workspace_id, intent_id, operation_owner, "action_busy")
                    return {"status": "action_busy"}
                if claim_state == "uncertain":
                    return await _pause_uncertain(
                        db, lead, operation_id, "An earlier attempt may already have sent this action. Review before resuming.",
                    )
                if claim_state in {"completed", "accepted", "skipped"}:
                    action_result = {"status": "skipped" if claim_state == "skipped" else "confirmed"}

        selected_variant_id, effective_config = select_step_variant({"id": curr_node_id, **node}, lead)

        if node_type == SequenceNodeType.VISIT_PROFILE:
            if action_result is None:
                action_result = await _dispatch_action(db, lead, expected_authorization, node_type, operation_id,
                    intent_id, operation_owner, lambda: voyager.visit_profile(lead["linkedin_url"]))

        elif node_type == SequenceNodeType.CONNECTION_REQUEST:
            if action_result is None:
                note_template = effective_config.get("note", "")
                alt_template = effective_config.get("alternative_message") or effective_config.get("fallback") or ""
                resolved_note = resolve_step_message_with_alternative(note_template, alt_template, lead) if note_template else {"text": "", "used_alternative": False}
                custom_note = resolved_note["text"]
                action_result = await _dispatch_action(db, lead, expected_authorization, node_type, operation_id,
                    intent_id, operation_owner, lambda: voyager.send_connection_invite(
                    lead.get("linkedin_urn") or lead["linkedin_url"], custom_note,
                ), content=custom_note)

        elif node_type == SequenceNodeType.SEND_MESSAGE:
            if action_result is None:
                body_template = effective_config.get("body", "Hi {{first_name}}")
                alt_template = effective_config.get("alternative_message") or effective_config.get("fallback") or ""
                resolved_body = resolve_step_message_with_alternative(body_template, alt_template, lead)
                msg_body = resolved_body["text"]
                attachment_url = effective_config.get("attachment_url")
                attachment_name = effective_config.get("attachment_name")
                action_result = await _dispatch_action(db, lead, expected_authorization, node_type, operation_id,
                    intent_id, operation_owner, lambda: voyager.send_direct_message(
                    lead.get("linkedin_urn") or lead["linkedin_url"], msg_body,
                    **({"attachment_url": attachment_url, "attachment_name": attachment_name} if attachment_url else {}),
                ), content=msg_body)

        elif node_type == SequenceNodeType.LIKE_LAST_POST:
            if action_result is None:
                action_config = effective_config
                action_result = await _dispatch_action(db, lead, expected_authorization, node_type, operation_id,
                    intent_id, operation_owner, lambda: voyager.like_last_post(
                    lead.get("linkedin_urn") or lead["linkedin_url"],
                    max_age_days=action_config.get("max_post_age_days", 30),
                ), skip_empty_post=action_config.get("skip_if_no_posts", True))

        elif node_type == SequenceNodeType.FOLLOW:
            if action_result is None:
                action_result = await _dispatch_action(db, lead, expected_authorization, node_type, operation_id,
                    intent_id, operation_owner, lambda: voyager.follow_profile(
                    lead.get("linkedin_urn") or lead["linkedin_url"],
                ))

        elif node_type == SequenceNodeType.ENDORSE_SKILLS:
            if action_result is None:
                skill_name = effective_config.get("skill_name") or lead.get("top_skill") or None
                action_result = await _dispatch_action(db, lead, expected_authorization, node_type, operation_id,
                    intent_id, operation_owner, lambda: voyager.endorse_top_skill(
                    lead.get("linkedin_urn") or lead["linkedin_url"],
                    skill_name=skill_name,
                ))

        elif node_type == SequenceNodeType.WITHDRAW_INVITE:
            if action_result is None:
                action_result = await _dispatch_action(db, lead, expected_authorization, node_type, operation_id,
                    intent_id, operation_owner, lambda: voyager.withdraw_invitation(
                    lead.get("linkedin_urn") or lead["linkedin_url"],
                ))

        elif node_type == SequenceNodeType.COMMENT_LAST_POST:
            if action_result is None:
                action_config = effective_config
                comment_template = action_config.get("comment") or action_config.get("comment_template") or action_config.get("body") or "Great insights on this, {{first_name}}!"
                comment_body = interpolate_template(comment_template, lead)
                action_result = await _dispatch_action(db, lead, expected_authorization, node_type, operation_id,
                    intent_id, operation_owner, lambda: voyager.comment_last_post(
                    lead.get("linkedin_urn") or lead["linkedin_url"],
                    comment_text=comment_body,
                    max_age_days=action_config.get("max_post_age_days", 30),
                ), content=comment_body, skip_empty_post=action_config.get("skip_if_no_posts", True))

        elif node_type == SequenceNodeType.INMAIL:
            if action_result is None:
                action_config = effective_config
                subject_template = action_config.get("subject") or "Quick question, {{first_name}}"
                body_template = action_config.get("body") or action_config.get("message") or "Hi {{first_name}}"
                alt_template = action_config.get("alternative_message") or action_config.get("fallback") or ""
                inmail_subject = interpolate_template(subject_template, lead).strip()
                resolved_inmail = resolve_step_message_with_alternative(body_template, alt_template, lead)
                inmail_body = resolved_inmail["text"]
                attachment_url = action_config.get("attachment_url")
                attachment_name = action_config.get("attachment_name")
                action_result = await _dispatch_action(db, lead, expected_authorization, node_type, operation_id,
                    intent_id, operation_owner, lambda: voyager.send_inmail(
                    lead.get("linkedin_urn") or lead["linkedin_url"],
                    inmail_subject,
                    inmail_body,
                    **({"attachment_url": attachment_url, "attachment_name": attachment_name} if attachment_url else {}),
                ), content={"subject": inmail_subject, "body": inmail_body})

        elif node_type == SequenceNodeType.OPEN_PROFILE_CHECK:
            open_signal = lead.get("is_open_profile")
            if open_signal is None and voyager is not None:
                open_signal = await voyager.check_open_profile(lead.get("linkedin_urn") or lead["linkedin_url"])
            now = datetime.now(timezone.utc)
            if open_signal is None:
                reason = "Open Profile eligibility could not be verified. Review this lead manually."
                await _advance_lead(db, lead, {
                    "execution_state": LeadExecutionState.WAITING_TRIGGER,
                    "next_action_due_at": None,
                    "failure_reason": reason,
                    "updated_at": now,
                })
                return {"status": "condition_needs_review", "reason": reason}
            branches = node.get("branches", {})
            next_node_id = branches.get("positive") if open_signal else branches.get("negative")
            updates = {
                **successor_fields(compiled, next_node_id, now),
                "is_open_profile": bool(open_signal),
                "updated_at": now,
            }
            if not await _advance_lead(db, lead, updates):
                return {"status": "lead_changed"}
            return {"status": "branch_advanced", "next_node_id": next_node_id, "condition_met": bool(open_signal)}

        elif node_type == SequenceNodeType.VOICE_NOTE:
            if action_result is None:
                try:
                    base_binding = await sequence_binding(db, workspace_id, lead["id"])
                    if not base_binding or base_binding["action"] != "voice_note":
                        raise ValueError("Current step changed")
                    clip = await _load_voice_clip(db, base_binding)
                    artifact, audio_bytes = clip.document, clip.audio
                except Exception as exc:
                    logger.error("Prepared voice unavailable (%s)", type(exc).__name__)
                    action_result = await _defer_operation(db, lead, operation_id, intent_id, operation_owner, "voice_preparation_required")
                else:
                    action_result = await _dispatch_action(db, lead, expected_authorization, node_type, operation_id,
                        intent_id, operation_owner, lambda: voyager.send_voice_note(
                        recipient_urn=lead.get("linkedin_urn") or lead["linkedin_url"],
                        audio_bytes=audio_bytes,
                        transcript=base_binding["content"]["body"],
                    ), content={**base_binding["content"], "audio_digest": artifact["audio_digest"],
                        "voice_artifact_id": artifact["_id"], "voice_artifact_generation": artifact["generation_id"]}, voice_clip=clip)

        elif node_type == SequenceNodeType.FIND_EMAIL:
            if action_result is None:
                from outreach.core.email_finder import find_lead_email

                action_result = await _dispatch_action(db, lead, expected_authorization, node_type, operation_id,
                    intent_id, operation_owner, lambda: find_lead_email(db, workspace_id=workspace_id, lead_id=lead_id,
                        sender_account_id=account["id"], operation_id=operation_id))

        elif node_type == SequenceNodeType.SEND_EMAIL:
            if action_result is None:
                from outreach.core.mailbox_delivery import send_outreach_email, render_email_body
                from outreach.core.mailbox_connection import get_ready_mailbox

                config = node.get("config") or {}
                subject = config.get("subject") or ""
                body = config.get("body") or ""
                if not isinstance(subject, str) or not subject.strip() or not isinstance(body, str) or not body.strip():
                    action_result = await _defer_operation(db, lead, operation_id, intent_id, operation_owner, "content_invalid")
                else:
                    mailbox = await get_ready_mailbox(db, workspace_id, account["id"])
                    action_result = await _dispatch_action(db, lead, expected_authorization, node_type, operation_id,
                        intent_id, operation_owner, lambda: send_outreach_email(
                        db, workspace_id=workspace_id, sender_account_id=account["id"],
                        lead_id=lead_id, to_email=lead["email"],
                        subject=interpolate_template(subject, lead),
                        body=interpolate_template(body, lead), operation_id=operation_id,
                    ), content={"subject": interpolate_template(subject, lead).strip(), "body": render_email_body(interpolate_template(body, lead)),
                        "sender_email": (mailbox or {}).get("email") or ""})
        elif node_type == SequenceNodeType.IF_CONNECTED:
            # Branch evaluation below performs the connection check; this node
            # intentionally has no outbound action and consumes no daily quota.
            action_result = {"status": "condition_checked"}

        elif node_type == SequenceNodeType.REPLY_TO_COMMENT:
            if action_result is None:
                action_config = effective_config
                reply_template = action_config.get("reply_text") or action_config.get("comment") or action_config.get("body") or "Thanks for your comment, {{first_name}}!"
                reply_body = interpolate_template(reply_template, lead)
                action_result = await _dispatch_action(db, lead, expected_authorization, node_type, operation_id,
                    intent_id, operation_owner, lambda: voyager.comment_last_post(
                    lead.get("linkedin_urn") or lead["linkedin_url"],
                    comment_text=reply_body,
                    max_age_days=action_config.get("max_post_age_days", 30),
                ), content=reply_body, skip_empty_post=action_config.get("skip_if_no_posts", True))

        elif node_type == SequenceNodeType.IF_OPENED_MESSAGE:
            opened_signal = bool(lead.get("has_opened_message") or lead.get("has_replied"))
            now = datetime.now(timezone.utc)
            branches = node.get("branches", {})
            next_node_id = branches.get("positive") if opened_signal else branches.get("negative")
            updates = {
                **successor_fields(compiled, next_node_id, now),
                "updated_at": now,
            }
            if not await _advance_lead(db, lead, updates):
                return {"status": "lead_changed"}
            return {"status": "branch_advanced", "next_node_id": next_node_id, "condition_met": opened_signal}

        else:
            reason = f"Unsupported sequence step: {node_type}"
            await _advance_lead(db, lead, {
                    "execution_state": LeadExecutionState.FAILED,
                    "failure_reason": reason,
                    "updated_at": datetime.now(timezone.utc),
                })
            return {"status": "unsupported_action", "action": node_type}

        result_status = (action_result or {}).get("status")
        if (action_result or {}).get("not_submitted"):
            return {"status": result_status, "action": node_type, "not_submitted": True}
        if node_type != SequenceNodeType.IF_CONNECTED:
            status_code = action_result.get("status_code") or action_result.get("http_status")
            resp_text = str(action_result.get("text") or action_result.get("error") or "")
            if (node_type == SequenceNodeType.CONNECTION_REQUEST
                    and isinstance(status_code, int)
                    and SafetyShield.is_weekly_invite_limit_error(status_code, resp_text)):
                await SafetyShield.record_weekly_invite_limit(
                    account["id"], resp_text or f"Weekly invite limit (HTTP {status_code})", db,
                    workspace_id=workspace_id,
                )
                return {"status": "weekly_invite_limit_reached", "action": node_type, "not_submitted": True}
            if (node_type not in (SequenceNodeType.FIND_EMAIL, SequenceNodeType.SEND_EMAIL)
                    and isinstance(status_code, int)
                    and SafetyShield.should_trip_circuit_breaker(status_code, resp_text)):
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
                    {"id": operation_id, "workspace_id": workspace_id, "status": "dispatching", "owner_token": operation_owner},
                    {"$set": {"status": "failed", "reason": reason, "updated_at": datetime.now(timezone.utc)}},
                )
                await _advance_lead(db, lead, {"execution_state": LeadExecutionState.FAILED,
                              "failure_reason": reason, "next_action_due_at": None,
                              "updated_at": datetime.now(timezone.utc)})
                return {"status": "action_failed", "action": node_type, "reason": reason}
            if result_status not in _CONFIRMED_STATUSES:
                return await _pause_uncertain(
                    db, lead, operation_id, "The provider did not confirm this action. Review its outcome before resuming.",
                )
            if claim_state == "new":
                recorded_status = "accepted" if node_type == SequenceNodeType.SEND_EMAIL else (
                    "skipped" if result_status == "skipped" else "completed"
                )
                task_updates: dict[str, Any] = {
                    "status": recorded_status,
                    "provider_message_id": action_result.get("provider_message_id"),
                    "provider_thread_id": action_result.get("provider_thread_id"),
                    "updated_at": datetime.now(timezone.utc),
                }
                if selected_variant_id is not None:
                    task_updates["variant_id"] = selected_variant_id
                try:
                    confirmation = await db.outreach_tasks.update_one(
                        {"id": operation_id, "workspace_id": workspace_id, "status": "dispatching", "owner_token": operation_owner},
                        {"$set": task_updates},
                    )
                    if getattr(confirmation, "matched_count", 0) == 0:
                        return await _pause_uncertain(db, lead, operation_id, "Action reporting changed; review its saved execution evidence.")
                except Exception as exc:
                    logger.error("Outreach action confirmation could not be recorded (%s)", type(exc).__name__)
                    return await _pause_uncertain(
                        db, lead, operation_id, "The action may have completed, but confirmation was not saved.",
                    )

        if node_type == SequenceNodeType.CONNECTION_REQUEST and node.get("branches"):
            auto_tag_val = str(effective_config.get("auto_tag") or "").strip()
            existing_tags = list(lead.get("tags") or [])
            if auto_tag_val and auto_tag_val not in existing_tags:
                existing_tags.append(auto_tag_val)
            if lead.get('_id') is not None and lead.get('enrollment_id') and campaign.get('sequence_version_id'):
                from outreach.core.connection_waits import begin_wait, ConnectionWaitUnavailable
                from outreach.core.suppression import SuppressionUnavailable
                from outreach.core.restore_epoch import EpochUnavailable
                try:
                    retained = await begin_wait(db, workspace_id, lead_id)
                except (ConnectionWaitUnavailable, SuppressionUnavailable, EpochUnavailable):
                    return {'status': 'connection_wait_review_required'}
                if retained:
                    if auto_tag_val:
                        await _advance_lead(db, lead, {"tags": existing_tags})
                    return {'status': 'success', 'action': action_name, 'waiting_for': 'connection', 'connection_wait_id': retained['_id']}
            waiting_since = datetime.now(timezone.utc)
            invite_wait_fields: dict[str, Any] = {
                "waiting_for_connection_at": waiting_since,
                "execution_state": LeadExecutionState.WAITING_DELAY,
                "next_action_due_at": waiting_since + timedelta(hours=24),
                "last_action_taken": action_name,
                "last_action_at": waiting_since,
                "updated_at": waiting_since,
            }
            if auto_tag_val:
                invite_wait_fields["tags"] = existing_tags
            if not await _advance_lead(db, lead, invite_wait_fields):
                return {"status": "lead_changed", "action": action_name}
            return {"status": "success", "action": action_name, "waiting_for": "connection"}

        if node_type in (SequenceNodeType.SEND_MESSAGE, SequenceNodeType.VOICE_NOTE) and node.get("branches"):
            auto_tag_val = str(effective_config.get("auto_tag") or "").strip()
            existing_tags = list(lead.get("tags") or [])
            if auto_tag_val and auto_tag_val not in existing_tags:
                existing_tags.append(auto_tag_val)
            waiting_since = datetime.now(timezone.utc)
            msg_wait_fields: dict[str, Any] = {
                "waiting_for_reply_at": waiting_since,
                "execution_state": LeadExecutionState.WAITING_DELAY,
                "next_action_due_at": waiting_since + timedelta(hours=24),
                "last_action_taken": action_name,
                "last_action_at": waiting_since,
                "updated_at": waiting_since,
            }
            if auto_tag_val:
                msg_wait_fields["tags"] = existing_tags
            if not await _advance_lead(db, lead, msg_wait_fields):
                return {"status": "lead_changed", "action": action_name}
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
                    await _advance_lead(db, lead, {"execution_state": LeadExecutionState.WAITING_DELAY,
                                  "waiting_for_connection_at": lead.get("waiting_for_connection_at") or now,
                                  "next_action_due_at": next_check, "updated_at": now})
                    return {"status": "condition_unknown", "next_check_at": next_check.isoformat()}
            else:
                branch_signal = bool(lead.get("has_replied"))
            if branch_signal:
                next_node_id = branches.get("positive")
                if node_type == SequenceNodeType.IF_CONNECTED:
                    newly_connected = not lead.get("is_connected")
                    if not await _advance_lead(db, lead, {
                        "is_connected": True,
                        "accepted_at": lead.get("accepted_at") or datetime.now(timezone.utc),
                    }):
                        return {"status": "lead_changed"}
                    if newly_connected:
                        try:
                            from outreach.core.event_outbox import record_outbox_event
                            from outreach.core.event_definitions import WebhookEvent

                            lead_display_name = (
                                f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
                                or lead.get("name")
                                or "Prospect"
                            )
                            await record_outbox_event(
                                db=db,
                                workspace_id=workspace_id,
                                event_type=WebhookEvent.CONNECTION_ACCEPTED,
                                aggregate_id=lead_id,
                                dedupe_key=f"lead.connection_accepted:{lead_id}",
                                data={
                                    "lead_id": lead_id,
                                    "lead_name": lead_display_name,
                                    "campaign_id": lead.get("campaign_id"),
                                    "channel": "linkedin",
                                    "linkedin_url": lead.get("linkedin_url"),
                                    "sender_account_id": assigned_account_id,
                                },
                            )
                        except Exception as outbox_err:
                            logger.warning("Failed to record connection accepted outbox event for lead %s: %s", lead_id, outbox_err)
            else:
                if node_type == SequenceNodeType.IF_CONNECTED and not lead.get("waiting_for_connection_at"):
                    waiting_since = datetime.now(timezone.utc)
                    await _advance_lead(db, lead, {
                            "waiting_for_connection_at": waiting_since,
                            "execution_state": LeadExecutionState.WAITING_DELAY,
                            "next_action_due_at": waiting_since + timedelta(hours=24),
                            "updated_at": waiting_since,
                        })
                    return {"status": "waiting_for_condition", "next_check_at": (waiting_since + timedelta(hours=24)).isoformat()}
                next_node_id = branches.get("negative")
        else:
            next_node_id = node.get("next_default")

        transition = successor_fields(compiled, next_node_id, datetime.now(timezone.utc))
        next_due = transition['next_action_due_at']
        now_done = datetime.now(timezone.utc)
        update_fields: dict[str, Any] = {
            **transition, "last_action_taken": action_name,
            "last_action_at": now_done, "updated_at": now_done,
        }
        if node_type == SequenceNodeType.WITHDRAW_INVITE:
            update_fields["withdrawn_at"] = now_done
        if selected_variant_id is not None:
            existing_variants = dict(lead.get("ab_variants_assigned") or {})
            existing_variants[curr_node_id] = selected_variant_id
            update_fields["ab_variants_assigned"] = existing_variants

        auto_tag_val = str(effective_config.get("auto_tag") or "").strip()
        if auto_tag_val:
            existing_tags = list(lead.get("tags") or [])
            if auto_tag_val not in existing_tags:
                existing_tags.append(auto_tag_val)
            update_fields["tags"] = existing_tags

        if not await _advance_lead(db, lead, update_fields):
            return {"status": "lead_changed", "action": action_name}
        return {
            "status": "success",
            "action": action_name,
            "next_node_id": next_node_id,
            "next_action_due_at": next_due.isoformat() if next_due else None,
        }
