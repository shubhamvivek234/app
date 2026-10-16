"""Original invite waits and guarded late-connected path changes; no transport."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import re
from typing import Any

from bson import BSON
from outreach.core.authorization import authorization_snapshot, canonical_hash, dispatch_block_reason
from outreach.core.connection_evidence import recipient_key
from outreach.core.execution_permission import ExecutionPermission
from outreach.core.dispatch_authority import AuthorityDatabase
from outreach.core.inbox_freshness import credential_generation
from outreach.core.paid_access import live_actions_enabled, sender_is_ready
from outreach.core.restore_epoch import positive, EpochUnavailable
from outreach.core.sequence_contract import DAGValidationError
from outreach.core.sequence_preview import validate_pinned_sequence, successor_fields, timeout_days
from outreach.core.sequence_versions import load_sequence
from outreach.core.suppression import mutate_suppression, SuppressionUnavailable, SuppressionDatabase

HEX = re.compile(r'[0-9a-f]{64}')
READ_SECONDS = 60
MAX_ROWS = 200
IDENTITY_FIELDS = ('linkedin_url', 'linkedin_urn', 'member_urn', 'sales_lead_urn', 'vanity_name')
BIND_FIELDS = ('workspace_id', 'campaign_id', 'lead_id', 'sender_id', 'enrollment_id', 'sequence_version',
               'authorization_revision', 'credential_generation', 'sequence_digest', 'sequence_version_id',
               'lead_native', 'campaign_native', 'sender_native', 'sequence_native', 'recipient_basis',
               'lead_authority_ref', 'campaign_authority_ref', 'sender_authority_ref')


class ConnectionWaitUnavailable(ValueError):
    """A retained wait never becomes new authority by guessing missing data."""


def utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    try:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def native(row: dict) -> str:
    if not isinstance(row, dict) or '_id' not in row:
        raise ConnectionWaitUnavailable('native_identity_missing')
    return hashlib.sha256(BSON.encode({'_id': row['_id']})).hexdigest()


def negative_region(compiled: dict, origin: str) -> list[str]:
    compiled = validate_pinned_sequence({'compiled_dag': compiled})
    node = compiled['nodes'].get(origin)
    if not node or node['type'] != 'connection_request':
        raise ConnectionWaitUnavailable('original_invite_required')
    def reachable(start: str | None) -> set[str]:
        seen, pending = set(), [start] if start else []
        while pending:
            identity = pending.pop()
            if identity in seen:
                continue
            seen.add(identity)
            target = compiled['nodes'][identity]
            pending.extend(value for value in [target['next_default'], *target['branches'].values()] if value)
        return seen
    return sorted(reachable(node['branches'].get('negative')) - reachable(node['branches'].get('positive')))


def capture_binding(lead: dict, campaign: dict, sequence: dict, account: dict) -> dict:
    values = [lead.get(key) for key in IDENTITY_FIELDS]
    identifiers = lead.get('identifiers', {})
    if identifiers is None:
        identifiers = {}
    if not isinstance(identifiers, dict):
        raise ConnectionWaitUnavailable('recipient_identity_malformed')
    values += [identifiers.get(key) for key in ('normalized_url', 'member_urn', 'sales_lead_urn', 'vanity_name')]
    if any(value is not None and (not isinstance(value, str) or len(value) > 2048) for value in values):
        raise ConnectionWaitUnavailable('recipient_identity_malformed')
    enrollment = lead.get('enrollment_id')
    pointer = campaign.get('sequence_version_id')
    if any(not isinstance(value, str) or not value for value in
            (lead.get('workspace_id'), lead.get('id'), campaign.get('id'), account.get('id'))):
        raise ConnectionWaitUnavailable('original_context_malformed')
    if (not isinstance(enrollment, str) or not 1 <= len(enrollment) <= 200 or enrollment.startswith('legacy:')
            or not isinstance(pointer, str) or not pointer or sequence.get('_id') != pointer
            or type(sequence.get('version')) is not int or sequence['version'] < 1
            or type(campaign.get('authorization_revision')) is not int or campaign['authorization_revision'] < 1):
        raise ConnectionWaitUnavailable('original_enrollment_or_version_missing')
    expected = authorization_snapshot(campaign, account, sequence)
    reason = dispatch_block_reason(lead, campaign, account, sequence, expected)
    if reason:
        raise ConnectionWaitUnavailable(reason)
    validate_pinned_sequence(sequence)
    return {'workspace_id': lead['workspace_id'], 'campaign_id': campaign['id'], 'lead_id': lead['id'],
        'sender_id': account['id'], 'enrollment_id': enrollment, 'sequence_version': sequence['version'],
        'authorization_revision': campaign['authorization_revision'], 'credential_generation': credential_generation(account),
        'sequence_digest': canonical_hash(sequence['compiled_dag']), 'sequence_version_id': pointer,
        'lead_native': native(lead), 'campaign_native': native(campaign), 'sender_native': native(account),
        'sequence_native': native(sequence), 'recipient_basis': canonical_hash(values),
        'lead_authority_ref': canonical_hash(lead['_id']), 'campaign_authority_ref': canonical_hash(campaign['_id']),
        'sender_authority_ref': canonical_hash(account['_id'])}


async def one(db: Any, name: str, workspace: str, query: dict) -> dict | None:
    rows = await getattr(db, name).find({'workspace_id': workspace, **query}).limit(2).to_list(length=2)
    if len(rows) > 1:
        raise ConnectionWaitUnavailable('ambiguous_identity')
    return rows[0] if rows else None


async def context(db: Any, workspace: str, lead_id: str) -> tuple[dict, dict, dict, dict]:
    lead = await one(db, 'outreach_leads', workspace, {'id': lead_id, 'id.0': {'$exists': False}})
    if not lead:
        raise ConnectionWaitUnavailable('lead_missing')
    campaign = await one(db, 'outreach_campaigns', workspace, {'id': lead.get('campaign_id'), 'id.0': {'$exists': False}})
    account = await one(db, 'outreach_accounts', workspace, {'id': lead.get('assigned_account_id'), 'id.0': {'$exists': False}})
    sequence = await load_sequence(db, workspace, lead.get('campaign_id'), campaign=campaign) if campaign else None
    if not all(isinstance(row, dict) for row in (campaign, sequence, account)):
        raise ConnectionWaitUnavailable('original_context_missing')
    return lead, campaign, sequence, account


def validate_scope(scope: dict, lead: dict, campaign: dict, sequence: dict, account: dict) -> None:
    if (not isinstance(scope, dict) or type(scope.get('version')) is not int or scope['version'] != 1 or type(scope.get('revision')) is not int
            or scope['revision'] < 1 or not isinstance(scope.get('status'), str) or scope['status'] not in {'waiting', 'negative_active', 'redirected', 'terminal', 'held'}
            or lead.get('connection_wait_required') is not True or lead.get('connection_wait_id') != scope.get('_id')
            or type(lead.get('connection_wait_revision')) is not int or lead['connection_wait_revision'] != scope['revision']
            or not isinstance(scope.get('_id'), str) or not HEX.fullmatch(scope['_id'])
            or not recipient_key(scope.get('recipient_urn')) or not isinstance(scope.get('origin_node_id'), str)):
        raise ConnectionWaitUnavailable('connection_wait_review_required')
    binding = capture_binding(lead, campaign, sequence, account)
    if any(scope.get(key) != binding[key] for key in BIND_FIELDS):
        raise ConnectionWaitUnavailable('original_wait_context_changed')
    node = sequence['compiled_dag']['nodes'].get(scope.get('origin_node_id'), {})
    if (node.get('type') != 'connection_request' or scope.get('negative_nodes') != negative_region(sequence['compiled_dag'], scope['origin_node_id'])
            or scope.get('positive_target') != (node.get('branches') or {}).get('positive')
            or scope.get('negative_target') != (node.get('branches') or {}).get('negative')):
        raise ConnectionWaitUnavailable('original_wait_graph_changed')
    started, deadline = utc(scope.get('wait_started_at')), utc(scope.get('wait_deadline_at'))
    if not started or not deadline or deadline != started + timedelta(days=timeout_days(node)):
        raise ConnectionWaitUnavailable('original_wait_timing_changed')
    if scope['_id'] != canonical_hash(['connection-wait-v1', binding, scope['origin_node_id'],
            scope.get('invite_intent_id'), scope.get('invite_attempt_id')]):
        raise ConnectionWaitUnavailable('original_wait_identity_changed')


async def validate_proof(db: Any, scope: dict, now: datetime) -> None:
    proof = await original_invite(db, {key: scope[key] for key in BIND_FIELDS}, scope['origin_node_id'], now)
    expected = {'intent_id': scope.get('invite_intent_id'), 'attempt_id': scope.get('invite_attempt_id'),
        'request_id': scope.get('invite_request_id'), 'recipient_urn': scope.get('recipient_urn'),
        'confirmed_at': utc(scope.get('wait_started_at'))}
    if not proof or proof != expected:
        raise ConnectionWaitUnavailable('original_invite_changed')


async def admission(db: Any, workspace: str, account: dict, now: datetime) -> None:
    await positive(db, workspace)
    if (not live_actions_enabled() or not await sender_is_ready(db, workspace, account, now)
            or not await ExecutionPermission(db).allowed(workspace, account['id'], credential_generation(account), 'sequence', now=now)):
        raise ConnectionWaitUnavailable('original_source_permission_required')


async def original_invite(db: Any, binding: dict, origin: str, now: datetime) -> dict | None:
    workspace = binding['workspace_id']
    identity = canonical_hash([workspace, binding['enrollment_id'], binding['sequence_version'], origin, 'connection_request'])
    intent = await one(db, 'outreach_intents', workspace, {'_id': identity})
    if not intent:
        return None
    attempt = intent.get('attempt')
    if (intent.get('status') != 'executed' or intent.get('action_kind') != 'connection_request' or intent.get('node_id') != origin
            or intent.get('logical_dedup_key') != identity or intent.get('legacy_operation_id') != binding['lead_id'] + ':' + origin
            or not isinstance(attempt, dict) or 'resolution' in intent
            or attempt.get('outcome') != 'provider_accepted' or attempt.get('provider_result_status') != 'invite_sent'
            or attempt.get('owner_token') != intent.get('claim_token') or attempt.get('sender_id') != binding['sender_id']
            or not isinstance(attempt.get('id'), str) or not attempt['id']
            or not isinstance(attempt.get('owner_token'), str) or not attempt['owner_token']
            or not isinstance(attempt.get('provider_request_id'), str) or not attempt['provider_request_id']
            or type(attempt.get('invite_contract_version')) is not int or attempt['invite_contract_version'] != 1
            or not recipient_key(attempt.get('provider_recipient_urn'))):
        return None
    for key in ('campaign_id', 'lead_id', 'sender_id', 'enrollment_id', 'sequence_version', 'authorization_revision', 'credential_generation'):
        if type(intent.get(key)) is not type(binding[key]) or intent.get(key) != binding[key]:
            return None
    completed, possible = utc(attempt.get('completed_at')), utc(attempt.get('possible_submission_at'))
    receipt = await one(db, 'outreach_physical_requests', workspace, {'_id': attempt.get('provider_request_id')})
    if (not completed or not possible or not possible <= completed <= now or not receipt
            or receipt.get('sender_id') != binding['sender_id'] or receipt.get('credential_generation') != binding['credential_generation']
            or receipt.get('owner_token') != attempt['owner_token'] or receipt.get('source') != 'sequence'
            or receipt.get('logical_operation_id') not in {identity, binding['lead_id'] + ':' + origin}
            or receipt.get('action') != 'invite' or receipt.get('mutation') is not True
            or receipt.get('status') != 'response_received' or type(receipt.get('http_status')) is not int or receipt['http_status'] not in (200, 201)
            or not isinstance(receipt.get('dispatch_authorization'), dict) or receipt['dispatch_authorization'].get('mode') != 'transaction'
            or receipt.get('endpoint_digest') != canonical_hash(['POST', '/voyager/api/growth/normInvitations'])):
        return None
    fact = receipt.get('connection_fact')
    refs = receipt['dispatch_authorization'].get('authority_refs')
    if (not isinstance(refs, list) or not all(any(isinstance(row, dict) and row.get('collection') == collection
            and row.get('id_hash') == binding[key] and row.get('native_hash') == binding[native_key] for row in refs)
            for collection, key, native_key in (('outreach_leads', 'lead_authority_ref', 'lead_native'),
                ('outreach_campaigns', 'campaign_authority_ref', 'campaign_native'), ('outreach_accounts', 'sender_authority_ref', 'sender_native')))):
        return None
    physical_time = utc(receipt.get('completed_at'))
    if (not isinstance(fact, dict) or type(fact.get('version')) is not int or fact['version'] != 1 or fact.get('kind') != 'invite_target'
            or fact.get('recipient_urn') != attempt['provider_recipient_urn'] or fact.get('connected') is not None
            or utc(fact.get('observed_at')) != physical_time or not physical_time
            or not possible <= physical_time <= completed):
        return None
    return {'intent_id': intent['_id'], 'attempt_id': attempt['id'], 'request_id': receipt['_id'],
            'recipient_urn': attempt['provider_recipient_urn'], 'confirmed_at': completed}


def lead_filter(lead: dict) -> dict:
    return {'workspace_id': lead['workspace_id'], '_id': lead['_id'], 'id': lead['id'], 'campaign_id': lead['campaign_id'],
        'enrollment_id': lead['enrollment_id'], 'current_node_id': lead.get('current_node_id'),
        'execution_state': lead.get('execution_state'), 'authorized_revision': lead.get('authorized_revision'),
        'sequence_version': lead.get('sequence_version'), 'assigned_account_id': lead.get('assigned_account_id'),
        'has_replied': {'$ne': True}, 'do_not_contact': {'$ne': True}, 'is_suppressed': {'$ne': True},
        'execution_claim_token': lead.get('execution_claim_token'),
        'connection_wait_id': lead.get('connection_wait_id'), 'connection_wait_revision': lead.get('connection_wait_revision')}


async def begin_wait(db: Any, workspace: str, lead_id: str, *, now: datetime | None = None) -> dict | None:
    """Only an original modern invite receipt creates the atomic wait/reference."""
    now = now or datetime.now(timezone.utc)
    now = now.replace(microsecond=now.microsecond // 1000 * 1000)
    # Compatibility: older unbound receipts retain ordinary waits, not F6 authority.
    lead, campaign, sequence, account = await context(db, workspace, lead_id)
    if not lead.get('enrollment_id') or not campaign.get('sequence_version_id'):
        return None
    binding = capture_binding(lead, campaign, sequence, account)
    origin = lead.get('current_node_id')
    node = sequence['compiled_dag']['nodes'].get(origin, {})
    if node.get('type') != 'connection_request' or not node.get('branches'):
        return None
    evidence = await original_invite(db, binding, origin, now)
    if not evidence:
        identity = canonical_hash([workspace, binding['enrollment_id'], binding['sequence_version'], origin, 'connection_request'])
        original = await one(db, 'outreach_intents', workspace, {'_id': identity})
        attempt = (original or {}).get('attempt')
        if isinstance(attempt, dict) and any(attempt.get(key) is not None for key in
                ('invite_contract_version', 'provider_recipient_urn', 'provider_request_id')):
            raise ConnectionWaitUnavailable('original_invite_review_required')
        return None
    identifier = canonical_hash(['connection-wait-v1', binding, origin, evidence['intent_id'], evidence['attempt_id']])
    async def apply(current: Any) -> dict:
        writer = current
        current = AuthorityDatabase(current.database, current.session, identifier)
        current_lead, parent, frozen, sender = await context(current, workspace, lead_id)
        await admission(current, workspace, sender, now)
        if capture_binding(current_lead, parent, frozen, sender) != binding:
            raise ConnectionWaitUnavailable('original_wait_context_changed')
        proof = await original_invite(current, binding, origin, now)
        if proof != evidence or current_lead.get('current_node_id') != origin:
            raise ConnectionWaitUnavailable('original_invite_changed')
        saved = await one(current, 'outreach_connection_waits', workspace, {'_id': identifier})
        if saved:
            validate_scope(saved, current_lead, parent, frozen, sender)
            return saved
        if current_lead.get('connection_wait_required') or current_lead.get('connection_wait_id'):
            raise ConnectionWaitUnavailable('original_wait_already_bound')
        started = evidence['confirmed_at']
        scope = {'_id': identifier, 'version': 1, 'revision': 1, **binding,
            'origin_node_id': origin, 'recipient_urn': evidence['recipient_urn'],
            'invite_intent_id': evidence['intent_id'], 'invite_attempt_id': evidence['attempt_id'], 'invite_request_id': evidence['request_id'],
            'wait_started_at': started, 'wait_deadline_at': started + timedelta(days=timeout_days(node)),
            'positive_target': node['branches'].get('positive'), 'negative_target': node['branches'].get('negative'),
            'negative_nodes': negative_region(frozen['compiled_dag'], origin), 'status': 'waiting', 'created_at': now}
        await writer.outreach_connection_waits.insert_one(scope)
        result = await current.outreach_leads.update_one(lead_filter(current_lead), {'$set': {
            'connection_wait_required': True, 'connection_wait_id': identifier, 'connection_wait_revision': 1,
            'waiting_for_connection_at': started, 'execution_state': 'waiting_delay',
            'next_action_due_at': min(now + timedelta(hours=24), max(now, scope['wait_deadline_at'])),
            'last_action_taken': 'connection_request', 'last_action_at': started, 'updated_at': now}})
        if result.matched_count != 1:
            raise ConnectionWaitUnavailable('original_lead_changed')
        return scope
    return await mutate_suppression(db, workspace, apply)


def read_operation(scope: dict, lead: dict) -> str:
    from outreach.tasks.sequence_dispatch import dispatch_job_id
    return canonical_hash(['connection-recheck-v1', scope['_id'], scope['revision'], lead.get('current_node_id'),
        dispatch_job_id() or lead.get('execution_claim_token')])


def read_context(scope: dict, lead: dict) -> dict:
    from outreach.tasks.sequence_dispatch import dispatch_job_id
    return {'scope_id': scope['_id'], 'scope_revision': scope['revision'], 'lead_native': scope['lead_native'],
        'node_id': lead.get('current_node_id'), 'dispatch_key': dispatch_job_id() or lead.get('execution_claim_token'),
        'operation_id': read_operation(scope, lead)}


async def scope_guard(db: Any, lead: dict, campaign: dict, sequence: dict, account: dict,
                      *, for_observation: bool = False, now: datetime | None = None) -> str | None:
    if not lead.get('connection_wait_required') and not lead.get('connection_wait_id'):
        return None
    now = now or datetime.now(timezone.utc)
    now = now.replace(microsecond=now.microsecond // 1000 * 1000)
    try:
        scope = await one(db, 'outreach_connection_waits', lead['workspace_id'], {'_id': lead.get('connection_wait_id')})
        validate_scope(scope, lead, campaign, sequence, account)
        await validate_proof(db, scope, now)
        if scope['status'] in {'held', 'terminal'}:
            return 'connection_wait_review_required'
        if scope['status'] == 'waiting' and lead.get('current_node_id') != scope['origin_node_id']:
            return 'connection_wait_review_required'
        if scope['status'] == 'redirected' and (lead.get('current_node_id') in scope['negative_nodes'] or lead.get('current_node_id') == scope['origin_node_id']):
            return 'connection_wait_review_required'
        if scope['status'] == 'negative_active' and lead.get('current_node_id') not in scope['negative_nodes']:
            return None  # Shared joins are outside this original negative wait.
        if scope['status'] == 'negative_active' and lead.get('current_node_id') in scope['negative_nodes'] and not for_observation:
            from outreach.core.connection_observations import saved_positive
            if await saved_positive(db, scope, lead, now):
                return 'connection_recheck_required'
            read = scope.get('last_read')
            if not isinstance(read, dict):
                return 'connection_recheck_required'
            at = utc(read.get('observed_at'))
            if (not at or not timedelta(0) <= now - at <= timedelta(seconds=READ_SECONDS)
                    or read.get('operation_id') != read_operation(scope, lead) or read.get('connected') is not False):
                return 'connection_recheck_required'
            from outreach.core.connection_observations import validate_observation
            if not isinstance(read.get('request_id'), str) or not read['request_id']:
                return 'connection_recheck_required'
            receipt = await one(db, 'outreach_physical_requests', lead['workspace_id'], {'_id': read['request_id']})
            if (validate_observation(receipt or {}, scope, lead, now) is not False
                    or utc(receipt.get('completed_at')) != at or receipt.get('logical_operation_id') != read['operation_id']):
                return 'connection_recheck_required'
            if isinstance(db, AuthorityDatabase):
                db.note_connection_deadline(at + timedelta(seconds=READ_SECONDS))
        if not for_observation and lead.get('current_node_id') != scope['origin_node_id']:
            kind = sequence['compiled_dag']['nodes'].get(lead.get('current_node_id'), {}).get('type')
            if kind in {'visit_profile', 'if_connected'}:
                return 'original_recipient_transport_required'
            if kind in {'connection_request', 'send_message', 'voice_note', 'like_last_post'} and (
                    recipient_key(lead.get('linkedin_urn')) != recipient_key(scope['recipient_urn'])):
                return 'original_recipient_transport_required'
        return None
    except (ConnectionWaitUnavailable, DAGValidationError, TypeError, KeyError, AttributeError, OverflowError):
        return 'connection_wait_review_required'


async def negative_work(db: Any, scope: dict, lead: dict, sequence: dict, now: datetime) -> tuple[list[dict], list[dict], list[dict]]:
    """Cancel only exact unsubmitted work; preserve proven safe predecessors."""
    workspace = scope['workspace_id']
    nodes = sequence['compiled_dag']['nodes']
    current_node = lead.get('current_node_id')
    def precedes(start: str) -> bool:
        seen, pending = set(), [start]
        while pending:
            identity = pending.pop()
            if identity in seen:
                continue
            seen.add(identity)
            if identity == current_node:
                return start != current_node
            node = nodes[identity]
            pending.extend(value for value in [node['next_default'], *node['branches'].values()] if value)
        return False
    intents = await db.outreach_intents.find({'workspace_id': workspace, 'lead_id': scope['lead_id'],
        'enrollment_id': scope['enrollment_id'], 'sequence_version': scope['sequence_version'],
        'node_id': {'$in': scope['negative_nodes']}}).limit(MAX_ROWS + 1).to_list(length=MAX_ROWS + 1)
    operations = [scope['lead_id'] + ':' + identity for identity in scope['negative_nodes']]
    tasks = await db.outreach_tasks.find({'workspace_id': workspace, 'id': {'$in': operations}}).limit(MAX_ROWS + 1).to_list(length=MAX_ROWS + 1)
    jobs = await db.outreach_sequence_jobs.find({'workspace_id': workspace,
        'stamp.connection_wait_id': scope['_id'], 'stamp.lead_id': scope['lead_id'],
        'stamp.node_id': {'$in': scope['negative_nodes']}, 'status': {'$in': ['queued', 'processing']}}).limit(MAX_ROWS + 1).to_list(length=MAX_ROWS + 1)
    if any(len(rows) > MAX_ROWS for rows in (intents, tasks, jobs)):
        raise ConnectionWaitUnavailable('negative_history_overflow')
    safe, pending_intents, by_id, owners_by_id, historical_owners = {}, [], {}, {}, {}
    for intent in intents:
        node_id = intent.get('node_id')
        if not isinstance(node_id, str) or node_id not in scope['negative_nodes']:
            raise ConnectionWaitUnavailable('negative_intent_scope_requires_review')
        kind = nodes[node_id]['type']
        identity = canonical_hash([workspace, scope['enrollment_id'], scope['sequence_version'], node_id, kind])
        if (intent.get('_id') != identity or intent.get('logical_dedup_key') != identity
                or intent.get('legacy_operation_id') != scope['lead_id'] + ':' + node_id or intent.get('action_kind') != kind
                or any(type(intent.get(key)) is not type(scope[key]) or intent.get(key) != scope[key] for key in
                    ('workspace_id', 'campaign_id', 'lead_id', 'sender_id', 'enrollment_id', 'sequence_version', 'authorization_revision', 'credential_generation'))
                or identity in by_id or 'resolution' in intent):
            raise ConnectionWaitUnavailable('negative_intent_scope_requires_review')
        by_id[identity] = intent
        history = intent.get('attempt_history', [])
        if not isinstance(history, list) or len(history) > MAX_ROWS:
            raise ConnectionWaitUnavailable('negative_attempt_history_requires_review')
        historical_owners[identity] = set()
        for earlier in history:
            start = utc(earlier.get('possible_submission_at')) if isinstance(earlier, dict) else None
            end = utc(earlier.get('completed_at')) if isinstance(earlier, dict) else None
            if (not isinstance(earlier, dict) or earlier.get('outcome') != 'not_submitted'
                    or earlier.get('sender_id') != scope['sender_id'] or not isinstance(earlier.get('id'), str) or not earlier['id']
                    or not isinstance(earlier.get('owner_token'), str) or not earlier['owner_token']
                    or not start or not end or not utc(scope['wait_started_at']) <= start <= end <= now):
                raise ConnectionWaitUnavailable('negative_attempt_history_requires_review')
            historical_owners[identity].add(earlier['owner_token'])
        owners_by_id[identity] = historical_owners[identity] | ({intent['claim_token']} if isinstance(intent.get('claim_token'), str) else set())
        attempt = intent.get('attempt')
        if intent.get('status') == 'executed':
            allowed = {'visit_profile': {'viewed'}, 'like_last_post': {'liked', 'skipped'}}
            at = utc((attempt or {}).get('completed_at')) if isinstance(attempt, dict) else None
            possible = utc((attempt or {}).get('possible_submission_at')) if isinstance(attempt, dict) else None
            if (not precedes(node_id) or kind not in allowed or not isinstance(attempt, dict)
                    or attempt.get('outcome') not in {'request_observed', 'provider_accepted'}
                    or attempt.get('provider_result_status') not in allowed[kind]
                    or not isinstance(attempt.get('id'), str) or not attempt['id']
                    or not isinstance(attempt.get('owner_token'), str) or not attempt['owner_token']
                    or attempt['owner_token'] != intent.get('claim_token') or attempt.get('sender_id') != scope['sender_id']
                    or not at or not possible or not utc(scope['wait_started_at']) <= possible <= at <= now):
                raise ConnectionWaitUnavailable('negative_action_evidence_requires_review')
            safe[identity] = intent
        elif (intent.get('status') in {'pending', 'claimed'} and attempt is None
                and (intent.get('claim_token') is None or isinstance(intent['claim_token'], str) and bool(intent['claim_token']))
                and (intent.get('status') != 'claimed' or intent.get('claim_token'))):
            pending_intents.append(intent)
        else:
            raise ConnectionWaitUnavailable('negative_action_evidence_requires_review')
    pending_tasks, task_ids, safe_tasks = [], set(), set()
    for task in tasks:
        intent_id = task.get('intent_id')
        intent = by_id.get(intent_id) if isinstance(intent_id, str) else None
        if (not intent or not isinstance(task.get('id'), str) or task['id'] in task_ids
                or task['id'] != intent['legacy_operation_id'] or task.get('task_type') != intent['action_kind']
                or task.get('campaign_id') != scope['campaign_id'] or task.get('lead_id') != scope['lead_id']
                or task.get('account_id') != scope['sender_id'] or not isinstance(task.get('owner_token'), str)
                or not task['owner_token'] or not (task['owner_token'] == intent.get('claim_token')
                    or task.get('status') == 'not_submitted' and task['owner_token'] in historical_owners[intent_id])):
            raise ConnectionWaitUnavailable('negative_task_evidence_requires_review')
        task_ids.add(task['id'])
        if intent_id in safe and task.get('status') in {'completed', 'skipped'}:
            safe_tasks.add(intent_id)
        elif intent_id not in safe and task.get('status') in {'preparing', 'not_submitted'}:
            pending_tasks.append(task)
        else:
            raise ConnectionWaitUnavailable('negative_task_evidence_requires_review')
    if set(safe) != safe_tasks:
        raise ConnectionWaitUnavailable('negative_completed_task_requires_review')
    owners = sorted(set().union(*owners_by_id.values())) if owners_by_id else []
    physical = await db.outreach_physical_requests.find({'workspace_id': workspace, 'sender_id': scope['sender_id'],
        'mutation': True, '$or': [{'owner_token': {'$in': owners}}, {'logical_operation_id': {'$in': [*by_id, *operations]}}]}).limit(MAX_ROWS + 1).to_list(length=MAX_ROWS + 1)
    if len(physical) > MAX_ROWS:
        raise ConnectionWaitUnavailable('negative_physical_evidence_requires_review')
    for row in physical:
        matches = [intent for intent in intents if isinstance(row.get('owner_token'), str) and row['owner_token'] in owners_by_id[intent['_id']]
            and row.get('logical_operation_id') in {intent['_id'], intent['legacy_operation_id']}]
        if len(matches) != 1 or row.get('mutation') is not True or row.get('sender_id') != scope['sender_id']:
            raise ConnectionWaitUnavailable('negative_physical_evidence_requires_review')
        intent = matches[0]
        history = row.get('non_call_history', [])
        if not isinstance(history, list) or len(history) > MAX_ROWS:
            raise ConnectionWaitUnavailable('negative_physical_history_requires_review')
        for earlier in history:
            if (not isinstance(earlier, dict) or earlier.get('status') != 'not_submitted'
                    or earlier.get('workspace_id') != workspace or earlier.get('sender_id') != scope['sender_id']
                    or earlier.get('credential_generation') != scope['credential_generation'] or earlier.get('source') != 'sequence'
                    or earlier.get('mutation') is not True or not isinstance(earlier.get('owner_token'), str)
                    or earlier['owner_token'] not in owners_by_id[intent['_id']]
                    or earlier.get('logical_operation_id') not in {intent['_id'], intent['legacy_operation_id']}):
                raise ConnectionWaitUnavailable('negative_physical_history_requires_review')
        if row.get('owner_token') in historical_owners[intent['_id']]:
            if row.get('status') != 'not_submitted':
                raise ConnectionWaitUnavailable('negative_physical_evidence_requires_review')
            continue
        if intent['_id'] in safe:
            at = utc(row.get('completed_at'))
            action, path = ('like', '/voyager/api/feed/reactions') if intent['action_kind'] == 'like_last_post' else ('visit', '/voyager/api/identity/profiles/view')
            if (row.get('status') != 'response_received' or not at or at > utc(intent['attempt']['completed_at'])
                    or row.get('source') != 'sequence' or row.get('credential_generation') != scope['credential_generation']
                    or type(row.get('http_status')) is not int or not 200 <= row['http_status'] < 300
                    or row.get('action') != action or row.get('endpoint_digest') != canonical_hash(['POST', path])):
                raise ConnectionWaitUnavailable('negative_physical_evidence_requires_review')
        elif row.get('status') != 'not_submitted':
            raise ConnectionWaitUnavailable('negative_physical_evidence_requires_review')
    for job in jobs:
        stamp = job.get('stamp')
        condition_job = isinstance(stamp, dict) and isinstance(stamp.get('node_id'), str) and nodes.get(stamp['node_id'], {}).get('type') == 'has_data_in_column'
        if condition_job:
            from outreach.core.sequence_conditions import field_job_bound
            if (not field_job_bound(job) or stamp['condition_native_ids'] !=
                    [scope[key] for key in ('lead_native', 'campaign_native', 'sequence_native', 'sender_native')]):
                raise ConnectionWaitUnavailable('negative_condition_job_requires_review')
        if (not isinstance(stamp, dict) or job.get('_id') != canonical_hash([workspace, stamp])
                or any(type(stamp.get(key)) is not type(scope[key]) or stamp.get(key) != scope[key] for key in
                    ('campaign_id', 'lead_id', 'sender_id', 'enrollment_id', 'sequence_version', 'credential_generation', 'sequence_digest', 'authorization_revision'))
                or type(stamp.get('campaign_revision')) is not int or stamp['campaign_revision'] != scope['authorization_revision']
                or stamp.get('connection_wait_id') != scope['_id'] or type(stamp.get('connection_wait_revision')) is not int
                or stamp['connection_wait_revision'] != scope['revision'] or stamp.get('lead_native_digest') != scope['lead_native']
                or not isinstance(stamp.get('node_id'), str) or stamp['node_id'] not in scope['negative_nodes']
                or stamp.get('lead_node_id') != stamp['node_id']
                or job.get('status') == 'processing' and (not isinstance(job.get('owner'), str) or not job['owner'])
                or (job.get('intent_id') not in {row['_id'] for row in pending_intents}
                    and not (job.get('intent_id') is None and (condition_job or nodes.get(stamp.get('node_id'), {}).get('type') in {'if_email_available', 'if_connected'})))):
            raise ConnectionWaitUnavailable('negative_job_scope_requires_review')
    return pending_intents, pending_tasks, jobs


async def advance_scoped(db: Any, original_lead: dict, query: dict, update: dict) -> bool:
    """Order even condition-only advancement with original fact publication."""
    workspace = original_lead['workspace_id']
    async def advance(writer: Any) -> bool:
        current = AuthorityDatabase(writer.database, writer.session, original_lead['connection_wait_id'])
        from outreach.tasks.sequence_dispatch import validate_dispatch_context
        if await validate_dispatch_context(current):
            return False
        lead, campaign, sequence, account = await context(current, workspace, original_lead['id'])
        if native(lead) != native(original_lead):
            return False
        now = datetime.now(timezone.utc)
        await admission(current, workspace, account, now)
        from outreach.core.lead_importer import check_compound_suppression
        from outreach.tasks.sequence_executor import _recipient_has_reply
        if await check_compound_suppression(workspace, [lead], current) or await _recipient_has_reply(current, workspace, account['id'], lead):
            return False
        scope = await one(current, 'outreach_connection_waits', workspace, {'_id': lead.get('connection_wait_id')})
        validate_scope(scope, lead, campaign, sequence, account)
        from outreach.core.connection_observations import saved_positive
        if scope['status'] == 'negative_active' and lead.get('current_node_id') in scope['negative_nodes']:
            positive_id = await saved_positive(current, scope, lead, now)
            if positive_id:
                await apply_observation(writer, workspace, lead['id'], scope['_id'], positive_id, now=now)
                return False
        if await scope_guard(current, lead, campaign, sequence, account, now=now):
            return False
        changed = await current.outreach_leads.update_one({**query, '_id': lead['_id']}, update)
        return changed.matched_count == 1
    try:
        return await mutate_suppression(db, workspace, advance)
    except (ConnectionWaitUnavailable, DAGValidationError, SuppressionUnavailable, EpochUnavailable,
            TypeError, KeyError, AttributeError, OverflowError):
        return False


async def apply_observation(db: Any, workspace: str, lead_id: str, scope_id: str,
                            request_id: str | None, *, now: datetime | None = None) -> dict:
    """Serialize a received observation with negative action authorization."""
    now = now or datetime.now(timezone.utc)
    now = now.replace(microsecond=now.microsecond // 1000 * 1000)
    async def apply(current: Any) -> dict:
        current = AuthorityDatabase(current.database, current.session, scope_id)
        original = await one(current, 'outreach_connection_waits', workspace, {'_id': scope_id})
        if original and original.get('status') == 'redirected':
            source = await one(current, 'outreach_leads', workspace, {'id': lead_id})
            if (source and native(source) == original.get('lead_native') and source.get('enrollment_id') == original.get('enrollment_id')
                    and source.get('connection_wait_id') == scope_id and isinstance(original.get('redirect_receipt'), dict)):
                return {'status': 'connection_redirected', 'receipt': original['redirect_receipt'], 'recovered': True}
            raise ConnectionWaitUnavailable('original_redirect_reference_changed')
        lead, campaign, sequence, account = await context(current, workspace, lead_id)
        scope = await one(current, 'outreach_connection_waits', workspace, {'_id': scope_id})
        validate_scope(scope, lead, campaign, sequence, account)
        await validate_proof(current, scope, now)
        if scope['status'] == 'redirected':
            return {'status': 'connection_redirected', 'receipt': scope['redirect_receipt'], 'recovered': True}
        if scope['status'] not in {'waiting', 'negative_active'}:
            return {'status': 'connection_wait_review_required'}
        node_id = lead.get('current_node_id')
        on_origin = scope['status'] == 'waiting' and node_id == scope['origin_node_id']
        on_negative = scope['status'] == 'negative_active' and node_id in scope['negative_nodes']
        if not on_origin and not on_negative:
            return {'status': 'connection_scope_not_eligible'}
        await admission(current, workspace, account, now)
        # Reply/DNC/erasure/source/epoch stops outrank a redirect.
        from outreach.core.lead_importer import check_compound_suppression
        from outreach.tasks.sequence_executor import _recipient_has_reply
        if await check_compound_suppression(workspace, [lead], current) or await _recipient_has_reply(current, workspace, account['id'], lead):
            raise ConnectionWaitUnavailable('lead_suppressed')
        receipt = await one(current, 'outreach_physical_requests', workspace, {'_id': request_id}) if request_id else None
        from outreach.core.connection_observations import validate_observation, saved_positive
        # A competing worker's saved positive always outranks a later negative
        # or unavailable read, including the original deadline-exit revision.
        recovered_positive = await saved_positive(current, scope, lead, now)
        effective_request_id = recovered_positive or request_id
        if effective_request_id != request_id:
            receipt = await one(current, 'outreach_physical_requests', workspace, {'_id': effective_request_id})
        at = utc((receipt or {}).get('completed_at'))
        operation = read_operation(scope, lead)
        connected = validate_observation(receipt or {}, scope, lead, now) if effective_request_id is not None else None
        if connected is not True and effective_request_id is not None and receipt.get('logical_operation_id') != operation:
            raise ConnectionWaitUnavailable('connection_observation_unavailable')
        last_read = {'request_id': effective_request_id, 'observed_at': at, 'operation_id': operation, 'connected': connected}
        if connected is None:
            hold = not on_origin or now >= utc(scope['wait_deadline_at'])
            status = 'held' if hold else scope['status']
            updates = {'execution_state': 'waiting_trigger' if hold else 'waiting_delay',
                'next_action_due_at': None if hold else now + timedelta(hours=1), 'updated_at': now}
            result = {'status': 'connection_wait_review_required' if hold else 'condition_unknown'}
        elif connected is False and (on_negative or now < utc(scope['wait_deadline_at'])):
            if on_negative:
                changed = await current.outreach_connection_waits.update_one({'workspace_id': workspace, '_id': scope_id, 'revision': scope['revision']}, {'$set': {'last_read': last_read}})
                if changed.matched_count != 1:
                    raise ConnectionWaitUnavailable('original_wait_changed')
                return {'status': 'connection_negative_confirmed'}
            status = scope['status']
            updates = {'execution_state': 'waiting_delay', 'next_action_due_at': min(now + timedelta(hours=24), utc(scope['wait_deadline_at'])), 'updated_at': now}
            result = {'status': 'waiting_for_condition'}
        else:
            target = scope['positive_target'] if connected else scope['negative_target']
            if connected and on_negative:
                try:
                    intents, tasks, jobs = await negative_work(current, scope, lead, sequence, now)
                except ConnectionWaitUnavailable as exc:
                    await current.outreach_connection_waits.update_one({'workspace_id': workspace, '_id': scope_id, 'revision': scope['revision']}, {'$set': {'status': 'held', 'last_read': last_read, 'hold_reason': str(exc)}})
                    changed = await current.outreach_leads.update_one(lead_filter(lead), {'$set': {
                        'execution_state': 'waiting_trigger', 'next_action_due_at': None,
                        'failure_reason': 'Review the earlier negative-path action before redirecting this sequence.', 'updated_at': now}})
                    if changed.matched_count != 1:
                        raise ConnectionWaitUnavailable('original_lead_changed')
                    return {'status': 'connection_wait_review_required', 'reason': str(exc)}
                for intent in intents:
                    changed = await current.outreach_intents.update_one({'workspace_id': workspace, '_id': intent['_id'],
                        'status': intent['status'], 'attempt': None, 'claim_token': intent.get('claim_token')},
                        {'$set': {'status': 'canceled', 'cancellation_reason': 'original_connection_redirect', 'updated_at': now}})
                    if changed.matched_count != 1:
                        raise ConnectionWaitUnavailable('negative_intent_changed')
                for task in tasks:
                    changed = await current.outreach_tasks.update_one({'workspace_id': workspace, '_id': task['_id'],
                        'status': task['status'], 'owner_token': task.get('owner_token'), 'intent_id': task['intent_id']},
                        {'$set': {'status': 'cancelled', 'cancellation_reason': 'original_connection_redirect', 'updated_at': now}})
                    if changed.matched_count != 1:
                        raise ConnectionWaitUnavailable('negative_task_changed')
                for job in jobs:
                    changed = await current.outreach_sequence_jobs.update_one({'workspace_id': workspace, '_id': job['_id'],
                        'status': job['status'], 'owner': job.get('owner')},
                        {'$set': {'status': 'superseded', 'result_status': 'original_connection_redirect', 'completed_at': now}})
                    if changed.matched_count != 1:
                        raise ConnectionWaitUnavailable('negative_job_changed')
            status = 'redirected' if connected else 'negative_active' if target else 'terminal'
            updates = {**successor_fields(sequence['compiled_dag'], target, now), 'updated_at': now,
                'connection_wait_revision': scope['revision'] + 1}
            if connected:
                updates['is_connected'] = True
            result = {'status': 'connection_redirected' if connected else 'branch_advanced'}
        values = {'status': status, 'last_read': last_read}
        if connected is True:
            values['redirect_receipt'] = {'request_id': effective_request_id, 'observed_connected_at': at, 'redirected_at': now,
                'from_node_id': node_id, 'next_node_id': scope['positive_target'], 'next_action_due_at': updates['next_action_due_at']}
            result['receipt'] = values['redirect_receipt']
        revision_change = 1 if 'connection_wait_revision' in updates else 0
        changed = await current.outreach_connection_waits.update_one({'workspace_id': workspace, '_id': scope_id, 'revision': scope['revision']},
            {'$set': values, **({'$inc': {'revision': 1}} if revision_change else {})})
        if changed.matched_count != 1:
            raise ConnectionWaitUnavailable('original_wait_changed')
        lead_update = {'$set': updates}
        if 'connection_wait_revision' in updates:
            lead_update['$unset'] = {'waiting_for_connection_at': '', 'execution_claim_token': '', 'execution_claimed_at': ''}
        changed = await current.outreach_leads.update_one(lead_filter(lead), lead_update)
        if changed.matched_count != 1:
            raise ConnectionWaitUnavailable('original_lead_changed')
        return result
    try:
        return await mutate_suppression(db, workspace, apply)
    except (ConnectionWaitUnavailable, DAGValidationError, EpochUnavailable, SuppressionUnavailable, TypeError, KeyError, AttributeError, OverflowError):
        if isinstance(db, SuppressionDatabase):
            raise  # The caller owns this transaction; never commit partial nested writes.
        return {'status': 'connection_wait_review_required'}
