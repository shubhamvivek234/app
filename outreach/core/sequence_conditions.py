"""Atomic current-field/email-policy decision and durable job receipt."""
from datetime import datetime, timezone
import re
from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from outreach.core.authorization import authorization_snapshot, credential_generation, canonical_hash
from outreach.core.connection_waits import (ConnectionWaitUnavailable, context, native, one,
    validate_scope, apply_observation)
from outreach.core.dispatch_authority import AuthorityDatabase
from outreach.core.execution_permission import ExecutionPermission
from outreach.core.field_conditions import evaluate
from outreach.core.request_guard import RequestDenied
from outreach.core.restore_epoch import EpochUnavailable
from outreach.core.sequence_contract import DAGValidationError
from outreach.core.sequence_preview import successor_fields
from outreach.core.sequence_capabilities import sequence_capability_map
from outreach.core.suppression import mutate_suppression, SuppressionUnavailable, SuppressionDatabase


CONDITION_MARKERS = {'has_data_in_column': 'field_condition_contract_version',
    'if_email_available': 'email_condition_contract_version'}


def condition_kind(job: Any) -> str | None:
    stamp = job.get('stamp') if isinstance(job, dict) else None
    if not isinstance(stamp, dict):
        return None
    kinds = [kind for kind, marker in CONDITION_MARKERS.items() if marker in stamp]
    return kinds[0] if len(kinds) == 1 else None


def condition_job_bound(job: Any) -> bool:
    """Bind a single typed condition contract to four original native parents."""
    kind = condition_kind(job)
    if kind is None:
        return False
    if not isinstance(job, dict) or not isinstance(job.get('workspace_id'), str) or not job['workspace_id']:
        return False
    stamp = job.get('stamp')
    marker = CONDITION_MARKERS[kind]
    if (not isinstance(stamp, dict) or type(stamp.get(marker)) is not int
            or stamp[marker] != 1
            or any(not isinstance(stamp.get(key), str) or not stamp[key] for key in
                ('campaign_id', 'lead_id', 'sender_id', 'enrollment_id', 'node_id', 'lead_node_id', 'credential_generation'))
            or any(type(stamp.get(key)) is not int or stamp[key] < 1 for key in
                ('sequence_version', 'authorization_revision', 'campaign_revision'))
            or stamp['enrollment_id'].startswith('legacy:')):
        return False
    native_ids = stamp.get('condition_native_ids')
    return (isinstance(native_ids, list) and len(native_ids) == 4
        and all(isinstance(item, str) and re.fullmatch(r'[a-f0-9]{64}', item) for item in native_ids)
        and isinstance(job.get('_id'), str) and job['_id'] == canonical_hash([job['workspace_id'], stamp]))


def field_job_bound(job: Any) -> bool:
    """Retain the original v2.71 stored-field contract helper."""
    return condition_kind(job) == 'has_data_in_column' and condition_job_bound(job)


def saved_result(job: Any) -> dict[str, Any] | None:
    if not condition_job_bound(job):
        return None
    receipt = job.get('condition_decision') if isinstance(job, dict) else None
    if (not isinstance(receipt, dict) or type(receipt.get('version')) is not int or receipt['version'] != 1
            or job.get('status') != 'completed' or receipt.get('status') not in ('branch_advanced', 'condition_review_required')
            or receipt.get('node_id') != job['stamp']['node_id'] or not isinstance(receipt.get('decided_at'), datetime)
            or receipt.get('status') == 'branch_advanced' and type(receipt.get('condition_met')) is not bool
            or receipt.get('status') == 'condition_review_required' and receipt.get('condition_met') is not None):
        return None
    if condition_kind(job) == 'if_email_available':
        from outreach.core.email_conditions import POLICY_VERSION
        if (receipt.get('kind') != 'if_email_available' or type(receipt.get('policy_version')) is not int
                or receipt['policy_version'] != POLICY_VERSION):
            return None
    return {'status': receipt['status'], 'condition_met': receipt.get('condition_met')}


def current_authority(current: AuthorityDatabase, kind: str = 'has_data_in_column') -> None:
    stamp = datetime.now(timezone.utc)
    if (not sequence_capability_map()[kind]['live_enabled']
            or any(stamp >= deadline for deadline in current.deadlines)
            or any(not check(stamp) for check in current.checks)):
        raise ConnectionWaitUnavailable('condition_authority_expired')


async def decide(db: AsyncIOMotorDatabase, original_lead: dict[str, Any]) -> dict[str, Any]:
    from outreach.tasks.sequence_dispatch import condition_dispatch_context, validate_dispatch_context
    from outreach.tasks.sequence_executor import _preflight_dispatch, _recipient_has_reply
    from outreach.core.connection_observations import saved_positive
    captured = condition_dispatch_context()
    if not captured:
        return {'status': 'dispatch_context_missing', 'not_submitted': True}
    _, job, owner = captured
    kind = condition_kind(job)
    if not condition_job_bound(job):
        return {'status': 'stale_job', 'not_submitted': True}
    workspace = original_lead['workspace_id']

    async def apply(writer: SuppressionDatabase) -> dict[str, Any]:
        current = AuthorityDatabase(writer.database, writer.session, job['_id'])
        if await validate_dispatch_context(current):
            return {'status': 'stale_job', 'not_submitted': True}
        lead, campaign, sequence, account = await context(current, workspace, original_lead['id'])
        if native(lead) != native(original_lead):
            raise ConnectionWaitUnavailable('condition_identity_changed')
        now = datetime.now(timezone.utc)
        now = now.replace(microsecond=now.microsecond // 1000 * 1000)
        # Saved original acceptance outranks a new negative-path data decision.
        if lead.get('connection_wait_required') or lead.get('connection_wait_id'):
            scope = await one(current, 'outreach_connection_waits', workspace, {'_id': lead.get('connection_wait_id')})
            validate_scope(scope, lead, campaign, sequence, account)
            if scope['status'] == 'negative_active' and lead['current_node_id'] in scope['negative_nodes']:
                positive_id = await saved_positive(current, scope, lead, now)
                if positive_id:
                    return await apply_observation(writer, workspace, lead['id'], scope['_id'], positive_id, now=now)
        reason = await _preflight_dispatch(current, lead, authorization_snapshot(campaign, account, sequence), kind)
        identity_hold = reason == 'condition_identity_review_required'
        if reason and not identity_hold:
            return {'status': reason, 'not_submitted': True}
        if not identity_hold and await _recipient_has_reply(current, workspace, account['id'], lead):
            return {'status': 'lead_suppressed', 'not_submitted': True}
        if not await ExecutionPermission(current).allowed(workspace, account['id'], credential_generation(account), 'sequence', now=now):
            return {'status': 'execution_permission_required', 'not_submitted': True}
        node = sequence['compiled_dag']['nodes'][lead['current_node_id']]
        if node['type'] != kind:
            raise ConnectionWaitUnavailable('condition_kind_changed')
        if identity_hold:
            decision = {'condition_met': None, 'reason': 'identity_unavailable'}
        elif kind == 'if_email_available':
            from outreach.core.email_conditions import evaluate as evaluate_email
            decision = await evaluate_email(current, workspace, lead)
        else:
            decision = evaluate(node['config'], lead)
        met = decision['condition_met']
        if met is None:
            status = 'condition_review_required'
            updates = {'execution_state': 'waiting_trigger', 'next_action_due_at': None,
                'failure_reason': 'Sequence condition needs review: ' + decision['reason'], 'updated_at': now}
        else:
            status = 'branch_advanced'
            target = node['branches'].get('positive' if met else 'negative')
            updates = {**successor_fields(sequence['compiled_dag'], target, now), 'updated_at': now}
        current_authority(current, kind)
        changed = await current.outreach_leads.update_one({'workspace_id': workspace, '_id': lead['_id'],
            'current_node_id': lead['current_node_id'], 'execution_claim_token': owner}, {'$set': updates})
        if changed.matched_count != 1:
            raise ConnectionWaitUnavailable('condition_lead_changed')
        receipt = {'version': 1, 'status': status, 'condition_met': met, 'reason': decision['reason'],
            'node_id': lead['current_node_id'], 'next_node_id': updates.get('current_node_id', lead['current_node_id']),
            'next_action_due_at': updates['next_action_due_at'], 'decided_at': now}
        if kind == 'if_email_available':
            from outreach.core.email_conditions import POLICY_VERSION
            receipt.update(kind=kind, policy_version=POLICY_VERSION)
        changed = await current.outreach_sequence_jobs.update_one({'workspace_id': workspace, '_id': job['_id'],
            'owner': owner, 'status': 'processing', 'stamp': job['stamp']}, {'$set': {
                'status': 'completed', 'condition_decision': receipt, 'result_status': status, 'completed_at': now}})
        if changed.matched_count != 1:
            raise ConnectionWaitUnavailable('condition_job_changed')
        current_authority(current, kind)
        return {'status': status, 'condition_met': met}

    try:
        return await mutate_suppression(db, workspace, apply)
    except (ConnectionWaitUnavailable, DAGValidationError, EpochUnavailable, SuppressionUnavailable,
            RequestDenied, TypeError, KeyError, AttributeError, OverflowError):
        return {'status': 'condition_authority_unavailable', 'not_submitted': True}
