"""Read-only, bounded campaign admission advice shared with launch.

This is a sequential observation, never an execution permission or health proof.
Key access and final transactional worker authority remain separate.
"""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any

from outreach.core import session_custody
from outreach.core.dag_compiler import DAGCompiler, DAGValidationError, contains_ai_prompt_token
from outreach.core.paid_access import _utc, get_active_entitlement, sender_is_ready
from outreach.core.proxy_custody import proxy_digest, proxy_record, _context as proxy_context
from outreach.core.sequence_capabilities import sequence_capability_map
from outreach.core.sequence_preview import analyze_sequence, same_execution_graph
from outreach.core.sequence_versions import load_sequence
from outreach.core import sequence_continuity
from outreach.core.workspace_scope import workspace_scope
from outreach.models import DailyLimits

UNRESOLVED = ['in_flight', 'unknown_outcome', 'uncertain', 'resolving', 'held_outcome', 'projection_pending']
RESUMABLE = {'operator_pause', 'billing_expired', 'sender_unavailable', 'sender_stopped',
             'sequence_changed', 'restore_review', 'unknown_outcome'}


@dataclass
class Assessment:
    report: dict
    sequence: dict | None
    accounts: list[dict]
    limits: dict
    warmup: dict
    code: int = 409


def launch_parameters(campaign: dict, request: Any) -> tuple[dict, dict]:
    """Apply the exact prospective launch values without storing them."""
    campaign, updates = dict(campaign), {}
    if request:
        if request.name:
            updates['name'] = request.name
        if request.sender_account_ids is not None:
            updates['sender_account_ids'] = request.sender_account_ids
        if request.schedule is not None:
            schedule = request.schedule.model_dump() if hasattr(request.schedule, 'model_dump') else request.schedule
            if isinstance(schedule, list):
                schedule = {'timezone': request.timezone or 'UTC', 'days': schedule}
            elif isinstance(schedule, dict) and request.timezone:
                schedule = {**schedule, 'timezone': request.timezone}
            updates['schedule'] = schedule
        if request.daily_limits is not None:
            updates['limits'] = request.daily_limits.model_dump() if hasattr(request.daily_limits, 'model_dump') else request.daily_limits
        if getattr(request, 'integrations', None) is not None and isinstance(request.integrations, dict):
            updates['integrations'] = dict(request.integrations)
    campaign.update(updates)
    return campaign, updates


def _material(account: dict, workspace: str) -> bool:
    """Check stored material; scoped key availability deliberately stays unknown."""
    from outreach.core.inbox_freshness import credential_generation
    from utils.encryption import decrypt_strict
    cookie = account.get('session_cookie_enc') or account.get('encrypted_session_cookie') or account.get('li_at_enc')
    js = account.get('jsession_id') or account.get('jsession_id_enc')
    proxy = proxy_record(account.get('proxy') or {})
    values = [(cookie, 'session_li_at'), (js, 'session_jsession'), (proxy.get('password_enc'), 'proxy_password')]
    mode = session_custody.custody_mode()
    for value, purpose in values:
        if not isinstance(value, str) or not value or len(value) > 60000:
            return False
        if mode == 'kms_v1':
            context = (proxy_context(proxy, workspace) if purpose == 'proxy_password' else
                       session_custody.context(workspace, account['id'], credential_generation(account), purpose))
            session_custody.configured_custody().inspect(value, context)
        else:
            if purpose == 'session_jsession' and not value.startswith(('gAAAAA', 'uc1:')):
                plain = value
            else:
                if not value.startswith('gAAAAA'):
                    return False
                plain = decrypt_strict(value)
            plain = plain.strip().strip('"')
            if purpose == 'session_li_at':
                plain = plain.removeprefix('li_at=')
            if not plain or len(plain) > 8192 or plain.startswith(('mock_', 'test_')) or any(ord(c) < 32 or ord(c) == 127 for c in plain):
                return False
    return True


async def _assess(db: Any, workspace: str, campaign: dict, warmup_reader: Any,
                  auto_claim: str | None, stamp: datetime) -> Assessment:
    from outreach.core.restore_epoch import positive, EpochUnavailable
    from outreach.core.rate_limiter import OutboundRateLimiter
    scope = workspace_scope(workspace)
    cid = campaign['id']
    campaign_scope = {**scope, 'campaign_id': cid, 'campaign_id.0': {'$exists': False}}
    checklist, blockers, codes = [], [], []

    def check(identity: str, name: str, passed: bool, success: str, failure: str, code: int = 409) -> None:
        message = success if passed else failure
        checklist.append({'id': identity, 'name': name, 'passed': bool(passed), 'message': message})
        if not passed:
            blockers.append(message)
            codes.append(code)

    paid = await get_active_entitlement(db, workspace, stamp)
    check('entitlement', 'Paid Pilot Entitlement', bool(paid and paid.get('workspace_id') == workspace),
          'Workspace has an active paid pilot period', 'A verified paid outreach period is required to launch campaigns', 402)
    seq = await load_sequence(db, workspace, cid, campaign=campaign)
    nodes, edges = (seq or {}).get('nodes', []), (seq or {}).get('edges', [])
    compiled, sequence_reason = None, 'Campaign has no configured sequence steps'
    capabilities = sequence_capability_map()
    if seq and seq.get('workspace_id') == workspace and seq.get('campaign_id') == cid and not seq.get('is_deleted') and isinstance(nodes, list) and 0 < len(nodes) <= 100 and isinstance(edges, list) and len(edges) <= 200:
        try:
            candidate = DAGCompiler.validate_and_compile(nodes, edges)
            analysis = analyze_sequence(candidate)
            if not analysis['valid']:
                sequence_reason = next(item['message'] for item in analysis['issues'] if item['severity'] == 'error')
            elif 'compiled_dag' in seq and not same_execution_graph(seq['compiled_dag'], candidate):
                sequence_reason = 'Saved sequence and execution graph differ; review and save a new revision'
            else:
                compiled = candidate
        except (ValueError, TypeError, KeyError, DAGValidationError):
            sequence_reason = 'Sequence DAG structure is invalid'
    check('sequence', 'Sequence Capabilities & DAG', compiled is not None,
          f'Sequence compiled successfully ({len(nodes) if isinstance(nodes, list) else 0} steps)', sequence_reason, 400)
    types = {node['type'] for node in compiled['nodes'].values()} if compiled else set()
    needs_linkedin = not types or any(capabilities.get(kind, {}).get('channel') == 'linkedin' for kind in types)
    needs_mailbox = 'send_email' in types
    check('policy', 'Execution Features', bool(compiled and all(capabilities.get(kind, {}).get('live_enabled') for kind in types)),
          'Required sequence features are enabled', 'One or more sequence features are not enabled for live execution', 403)

    revision = campaign.get('authorization_revision', 0)
    reasons = campaign.get('pause_reasons') or []
    allowed = {'draft', 'paused'} | ({'warming_up'} if auto_claim else set())
    state_ok = (type(revision) is int and revision >= 0 and not campaign.get('sequence_edit_pending')
                and isinstance(reasons, list) and all(isinstance(reason, str) and reason in RESUMABLE for reason in reasons)
                and isinstance(campaign.get('status'), str) and campaign['status'] in allowed)
    if campaign.get('status') == 'warming_up':
        state_ok = state_ok and campaign.get('auto_launch_enabled') is True and campaign.get('auto_launch_claim_id') == auto_claim
    claim_expiry = campaign.get('launch_claim_expires_at')
    if campaign.get('launch_claim_token') and claim_expiry is None:
        state_ok = False
    if claim_expiry is not None:
        deadline = _utc(claim_expiry) if isinstance(claim_expiry, (datetime, str)) else None
        state_ok = state_ok and deadline is not None and deadline <= stamp
    check('campaign', 'Campaign Activation State', state_ok,
          'Campaign can request activation', 'Campaign state, revision or activation ownership requires review')
    try:
        await positive(db, workspace)
        epoch_ok = True
    except EpochUnavailable:
        epoch_ok = False
    check('restore', 'Restore Admission', epoch_ok, 'No installed restore hold observed',
          'Restore reconciliation and explicit activation are required')

    senders = campaign.get('sender_account_ids')
    sender_shape = isinstance(senders, list) and 0 < len(senders) <= 5 and all(isinstance(s, str) and 0 < len(s) <= 256 for s in senders)
    senders = list(dict.fromkeys(senders)) if sender_shape else []
    accounts = await db.outreach_accounts.find({**scope, 'id': {'$in': senders}, 'id.0': {'$exists': False}, 'status': 'active', 'is_deleted': {'$ne': True}}).to_list(length=6) if senders else []
    sender_ok = bool(senders and len(accounts) == len(senders) and {a['id'] for a in accounts} == set(senders))
    for account in accounts:
        cooldown = account.get('cooldown_until')
        deadline = _utc(cooldown) if isinstance(cooldown, (datetime, str)) else None
        fence = account.get('connection_finalization')
        if (account.get('stop_reason') or (cooldown is not None and (deadline is None or deadline > stamp))
                or (fence is not None and (not isinstance(fence, dict) or fence.get('state') != 'closed'
                    or fence.get('completion') != 'verified_install'))):
            sender_ok = False
    check('senders', 'Assigned Sender Accounts', sender_ok, f'{len(accounts)} active sender account(s) assigned',
          'One or more selected sender accounts are inactive, missing or ambiguous', 400)
    proxy_ok, material_ok = sender_ok, sender_ok
    for account in accounts:
        sender = account['id']
        slot = await db.outreach_sender_slots.find_one({**scope, 'sender_id': sender, 'sender_id.0': {'$exists': False}})
        if not slot:
            proxy_ok = False
        if not needs_linkedin:
            continue
        proxy = account.get('proxy')
        try:
            if not isinstance(proxy, dict) or any(not isinstance(proxy.get(key), str) or not proxy[key] for key in ('proxy_id', 'provider', 'host', 'username')) or type(proxy.get('port')) is not int or not 1 <= proxy['port'] <= 65535 or proxy['host'] in {'127.0.0.1', 'localhost'}:
                proxy_ok = False
                material_ok = False
                continue
            asset = await db.outreach_proxy_inventory.find_one({'_id': proxy['proxy_id']})
            lease = await db.outreach_proxy_leases.find_one({**scope, '_id': proxy['proxy_id'], 'sender_id': sender, 'sender_id.0': {'$exists': False}})
            if (not await sender_is_ready(db, workspace, account, stamp) or not asset or not lease
                    or asset.get('workspace_id') != workspace or proxy_digest(asset) != proxy_digest(proxy)
                    or lease.get('country_code') != account.get('country_code') or lease.get('provider') != proxy.get('provider')):
                proxy_ok = False
            material_ok = _material(account, workspace) and material_ok
        except (ValueError, TypeError, KeyError, AttributeError):
            proxy_ok = False
            material_ok = False
    check('proxies', 'Sender Resource Assignment', proxy_ok, 'Stored sender slots, proxy leases, bindings and provider terms match' if needs_linkedin else 'Stored sender slots match; LinkedIn proxy not required',
          'A selected sender slot, proxy assignment or provider term is unavailable', 400)
    check('credentials', 'Stored Session Material', material_ok or (sender_ok and not needs_linkedin),
          'Stored material passed local checks; remote authentication and scoped key access are not verified' if needs_linkedin else 'LinkedIn session material is not required',
          'Stored session or proxy credentials are unavailable; reconnect the sender', 400)

    mailbox_ok = True
    mailbox_reason = 'Sequence has email steps but one or more senders lack a verified mailbox'
    if needs_mailbox:
        from outreach.core.mailbox_connection import get_ready_mailbox, is_email_send_pilot_allowed
        mailbox_ok = sender_ok and is_email_send_pilot_allowed(workspace)
        if not is_email_send_pilot_allowed(workspace):
            mailbox_reason = 'Email sequence steps are not enabled for this workspace in the current pilot'
        for account in accounts:
            mailbox = await get_ready_mailbox(db, workspace, account['id'])
            mailbox_ok = bool(mailbox_ok and mailbox and mailbox.get('workspace_id') == workspace and mailbox.get('sender_account_id') == account['id'])
    check('mailboxes', 'Email Mailbox Readiness', mailbox_ok, 'Stored mailbox state meets the launch check' if needs_mailbox else 'Not required (no email steps in sequence)', mailbox_reason, 400)
    count = await db.outreach_leads.count_documents({**campaign_scope, 'execution_state': {'$ne': 'staged'}})
    check('leads', 'Enrolled Prospects', type(count) is int and count > 0, f'{count} prospect(s) enrolled in campaign', 'Enroll at least one prospect before launching', 400)
    from outreach.core.search_sources import SEARCH_PROVENANCE_QUERY, UNVERIFIED_LEAD
    source_hold = await db.outreach_leads.find_one({**campaign_scope,
        'execution_state': {'$ne': 'staged'}, **SEARCH_PROVENANCE_QUERY})
    check('lead_sources', 'Prospect Source Review', not source_hold,
          'No retained unverified search provenance found', UNVERIFIED_LEAD, 409)
    # A new revision cannot silently migrate a conversation to another sender
    # or restart progress at the root after its old step was removed. Terminal
    # and staged records do not participate in the resumed sequence.
    outstanding = {**campaign_scope, 'has_replied': {'$ne': True},
                   'execution_state': {'$nin': ['staged', 'replied', 'finished', 'bounced', 'failed']}}
    actionable = await db.outreach_leads.find_one(outstanding)
    check('actionable_leads', 'Actionable Prospects', bool(actionable),
          'At least one prospect has outstanding campaign work',
          'Enroll at least one new prospect with outstanding work before launching', 400)
    progress_fields = ('last_action_at', 'last_action_taken',
                       'waiting_for_connection_at', 'waiting_for_reply_at')
    root_ids = list(compiled['root_node_ids']) if compiled else []
    sender_conflict = await db.outreach_leads.find_one({**outstanding, '$or': [
        {'assigned_account_id': {'$type': 'array'}},
        {'assigned_account_id': {'$nin': [None, *senders]}},
        {'assigned_account_id': None, '$or': [
            # Only a queued, unacted root can receive its first sender. Missing
            # optional audit fields alone do not prove a later/waiting lead fresh.
            {'execution_state': {'$type': 'array'}},
            {'execution_state': {'$ne': 'queued'}},
            {'current_node_id': {'$nin': [None, *root_ids]}},
            *[{field: {'$type': 'array'}} for field in progress_fields],
            *[{field: {'$ne': None}} for field in progress_fields],
        ]},
    ]})
    check('lead_senders', 'Prospect Sender Continuity', not sender_conflict,
          'Outstanding prospects retain a selected sender or await their first assignment',
          'Outstanding prospects are assigned to a removed or invalid sender; restore the original sender or request a reviewed migration')
    node_ids = list(compiled['nodes']) if compiled else []
    progress_conflict = await db.outreach_leads.find_one({**outstanding, '$or': [
        {'current_node_id': {'$type': 'array'}},
        {'current_node_id': {'$nin': [None, *node_ids]}},
        {'current_node_id': None, '$or': [
            {field: {'$ne': None}} for field in progress_fields
        ]},
    ]})
    check('lead_progress', 'Prospect Sequence Continuity', not progress_conflict,
          'Outstanding prospect steps still exist in this sequence',
          'Outstanding prospects reference missing or invalid sequence progress; restore the original steps or request a reviewed migration')
    version = sequence_continuity.current_version(seq) if isinstance(seq, dict) else None
    version_conflict = (await db.outreach_leads.find_one(sequence_continuity.version_conflicts(
        workspace, cid, version, root_ids, node_ids))) if version is not None else True
    check('lead_versions', 'Prospect Version Continuity', not version_conflict,
          'Retained progress keeps its current version; unacted queued roots can receive an initial binding',
          sequence_continuity.VERSION_HOLD)
    check('schedule', 'Working Schedule Window', OutboundRateLimiter.has_valid_working_window(campaign.get('schedule')),
          'A valid working-hours window is configured; execution waits for that window', 'Configure a valid working-hours schedule window', 400)
    try:
        limits = DailyLimits.model_validate(campaign.get('limits') or {}).model_dump()
        limits_ok = True
    except ValueError:
        limits, limits_ok = {}, False
    check('limits', 'Daily Limits', limits_ok, 'Daily limits are valid', 'Daily limits are invalid', 400)

    selected = {'$or': [{'campaign_id': cid}, {'sender_id': {'$in': senders}}, {'account_id': {'$in': senders}},
                        {'assigned_account_id': {'$in': senders}}, {'sender_account_id': {'$in': senders}}]}
    hold = False
    for name, extra in (
        ('outreach_tasks', {'status': {'$in': UNRESOLVED + ['preparing', 'dispatching']}}),
        ('outreach_intents', {'$or': [{'status': {'$in': UNRESOLVED}}, {'status': 'executed', 'projection_reconciled': {'$ne': True}}]}),
        ('outreach_physical_requests', {'status': {'$in': UNRESOLVED + ['preparing', 'possible']}}),
        ('outreach_manual_actions', {'$or': [{'status': {'$in': UNRESOLVED + ['preparing']}}, {'status': 'resolved', 'cleanup_complete': {'$ne': True}}]}),
        ('outreach_email_operations', {'status': {'$in': UNRESOLVED + ['dispatching']}}),
        ('outreach_email_discoveries', {'status': {'$in': UNRESOLVED + ['dispatching']}}),
        ('outreach_connection_jobs', {'status': {'$in': ['queued', 'running', 'finalizing', 'repairing']}}),
        ('outreach_connection_locks', {}),
    ):
        query = {'$and': [scope, selected, extra]}
        if name == 'outreach_connection_locks':
            query = {**scope, '_id': {'$in': senders}}
        if await getattr(db, name).find_one(query):
            hold = True
    from outreach.core.execution_permission import ExecutionPermission
    for sender in senders:
        states = await db.outreach_sender_execution.find({**scope, 'sender_id': sender}).to_list(length=2)
        if len(states) > 1:
            hold = True
        for state in states:
            permission = state.get('permission')
            if (state.get('sender_id') != sender or state.get('_id') != ExecutionPermission.scope(workspace, sender)['_id']
                    or state.get('status') != 'idle' or state.get('owner_token') or state.get('physical_request_token')
                    or (permission is not None and (not isinstance(permission, dict) or permission.get('latched') is not False or permission.get('stop_reason')))):
                hold = True
    check('provenance', 'Selected Work Holds', not hold, 'No selected unresolved work was observed in the checked collections', 'Selected work has unfinished or uncertain outcomes requiring operator review')
    warmup = await warmup_reader(cid, workspace, db, now=stamp, required_list_id=campaign.get('auto_launch_list_id') if auto_claim else None)
    warmup_ok = not (warmup['linked_lists_count'] and warmup['missing_count']) and (not auto_claim or warmup['ready'])
    check('warmup', 'Engage Warm-Up', warmup_ok, 'Warm-up admission passed; any remaining manual cooldown delays execution', 'The linked Engage cohort needs confirmed engagement or its automatic cooldown has not elapsed')
    variables = set()
    for node in nodes if isinstance(nodes, list) else []:
        for value in (node.get('config') or {}).values() if isinstance(node, dict) and isinstance(node.get('config') or {}, dict) else []:
            if isinstance(value, str):
                variables.update(re.findall(r'\{\{([a-zA-Z0-9_]+)\}\}', value))
    report = {'campaign_id': cid, 'status': campaign.get('status'), 'can_launch': not blockers, 'blockers': blockers,
              'checklist': checklist, 'checked_at': stamp.isoformat(), 'execution_ready': False,
              'execution_checks': [
                  {'id': 'content', 'status': 'pending', 'message': 'Exact recipient and revision-bound content approval is checked after allocation'},
                  {'id': 'permission', 'status': 'unknown', 'message': 'Fresh execution permission, inbox/reply evidence and health evidence are checked by workers'},
                  {'id': 'credentials', 'status': 'unknown', 'message': 'Remote authentication, scoped key access and provider availability are not verified by this checklist'}],
              'summary': {'leads_count': count, 'senders_count': len(senders), 'nodes_count': len(nodes) if isinstance(nodes, list) else 0,
                  'variables_detected': sorted(variables), 'branch_paths': [f"{edge.get('source')} → {edge.get('target')} ({edge.get('label') or 'next'})" for edge in edges if isinstance(edge, dict)] if isinstance(edges, list) else []}}
    return Assessment(report, {**seq, 'compiled_dag': compiled} if seq and compiled else None, accounts, limits, warmup, codes[0] if codes else 409)


async def assess(db: Any, workspace: str, campaign: dict, warmup_reader: Any,
                 *, auto_claim: str | None = None, now: datetime | None = None) -> Assessment:
    try:
        return await asyncio.wait_for(_assess(db, workspace, campaign, warmup_reader, auto_claim, now or datetime.now(timezone.utc)), timeout=10)
    except Exception:
        # An incomplete read cannot produce a green checklist or raw database errors.
        message = 'Launch prerequisites could not be verified; retry or request operator review'
        return Assessment({'campaign_id': campaign.get('id'), 'status': campaign.get('status'), 'can_launch': False,
            'execution_ready': False, 'execution_checks': [], 'blockers': [message], 'checklist': [
                {'id': 'verification', 'name': 'Launch Verification', 'passed': False, 'message': message}], 'summary': {}}, None, [], {}, {}, 503)
