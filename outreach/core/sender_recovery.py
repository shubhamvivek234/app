"""Recover a proven cooled-down connection without restarting execution."""
import asyncio
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote, urlsplit

from outreach.core import session_custody, suppression
from outreach.core.authorization import canonical_hash
from outreach.core.dispatch_authority import AuthorityDatabase
from outreach.core.integration_control import stable
from outreach.core.paid_access import _utc, get_active_entitlement, live_actions_enabled, sender_is_ready
from outreach.core.proxy_custody import policy, prepare_proxy, proxy_digest
from outreach.core.workspace_scope import workspace_scope

RECOVERABLE_REASONS = {'rate_limited_429', 'commercial_limit', 'proxy_unhealthy'}


def _eligible(account: dict[str, Any], stamp: datetime) -> None:
    if (account.get('is_deleted') or not isinstance(account.get('status'), str)
            or account['status'] not in {'checkpoint', 'checkpoint_detected'}
            or not isinstance(account.get('stop_reason'), str) or account['stop_reason'] not in RECOVERABLE_REASONS):
        raise ValueError('This sender requires reconnection or operator review, not circuit-breaker resume')
    cooldown = account.get('cooldown_until')
    if not isinstance(cooldown, (str, datetime)) or (deadline := _utc(cooldown)) is None:
        raise ValueError('The original platform cooldown requires operator review')
    if deadline > stamp:
        raise ValueError('Sender is under mandatory platform cooldown; wait before resuming')
    fence = account.get('connection_finalization')
    if fence is not None and (not isinstance(fence, dict) or fence.get('state') != 'closed'
                             or fence.get('completion') != 'verified_install'):
        raise ValueError('Connection installation requires operator review')


async def _current_checks(db: Any, workspace: str, account: dict, stamp: datetime) -> list[datetime | None]:
    from outreach.core.restore_epoch import positive
    proxy = account.get('proxy') or {}
    if not isinstance(proxy, dict):
        raise ValueError('The original proxy assignment requires operator review')
    if (not isinstance(account.get('country_code'), str) or len(account['country_code']) != 2
            or any(not isinstance(proxy.get(field), str) or not proxy[field] for field in ('proxy_id', 'provider', 'host', 'username'))
            or type(proxy.get('port')) is not int or not 1 <= proxy['port'] <= 65535):
        raise ValueError('The original proxy transport metadata requires operator review')
    proof = await positive(db, workspace)
    paid = await get_active_entitlement(db, workspace, stamp)
    if (not paid or paid.get('workspace_id') != workspace
            or not await sender_is_ready(db, workspace, {**account, 'status': 'active'}, stamp)):
        raise ValueError('Paid access, live policy or the original assigned proxy is unavailable')
    asset = await db.outreach_proxy_inventory.find_one({'_id': proxy.get('proxy_id')})
    lease = await db.outreach_proxy_leases.find_one({'_id': proxy.get('proxy_id'), **workspace_scope(workspace),
                                                 'sender_id': account['id'], 'sender_id.0': {'$exists': False}})
    slot = await db.outreach_sender_slots.find_one({**workspace_scope(workspace), 'sender_id': account['id'],
                                                 'sender_id.0': {'$exists': False}})
    if (not asset or proxy_digest(asset) != proxy_digest(proxy) or not lease or not slot
            or lease.get('country_code') != account.get('country_code')
            or lease.get('provider') != proxy.get('provider')):
        raise ValueError('The original proxy assignment changed; reconnect or request operator review')
    states = await db.outreach_sender_execution.find({**workspace_scope(workspace), 'sender_id': account['id']}).limit(2).to_list(length=2)
    if len(states) > 1:
        raise ValueError('Multiple sender authorities require operator review')
    state = states[0] if states else None
    permission = (state or {}).get('permission')
    from outreach.core.inbox_freshness import credential_generation
    from outreach.core.execution_permission import ExecutionPermission, MAX_PERMISSION_SECONDS
    issued = _utc(permission.get('issued_at')) if isinstance(permission, dict) and isinstance(permission.get('issued_at'), (str, datetime)) else None
    expiry = _utc(permission.get('expires_at')) if isinstance(permission, dict) and isinstance(permission.get('expires_at'), (str, datetime)) else None
    if state and (state.get('sender_id') != account['id'] or state.get('owner_token') or state.get('physical_request_token')
                  or state.get('_id') != ExecutionPermission.scope(workspace, account['id'])['_id']
                  or state.get('status') != 'idle' or not isinstance(permission, dict)
                  or permission.get('latched') is not False or permission.get('stop_reason')
                  or permission.get('credential_generation') != credential_generation(account)
                  or not issued or not expiry or expiry > stamp
                  or not 0 < (expiry - issued).total_seconds() <= MAX_PERMISSION_SECONDS):
        raise ValueError('Sender ownership or execution hold requires operator review')
    unresolved = ['in_flight', 'unknown_outcome', 'uncertain', 'resolving', 'held_outcome', 'projection_pending']
    for name, query in (
        ('outreach_physical_requests', {'sender_id': account['id'], 'status': {'$in': unresolved}}),
        ('outreach_intents', {'sender_id': account['id'], 'status': {'$in': unresolved}}),
        ('outreach_tasks', {'$or': [{'account_id': account['id']}, {'assigned_account_id': account['id']}],
                            'status': {'$in': unresolved}}),
        ('outreach_manual_actions', {'account_id': account['id'], '$or': [
            {'status': {'$in': unresolved + ['preparing']}}, {'status': 'resolved', 'cleanup_complete': {'$ne': True}}]}),
        ('outreach_connection_jobs', {'sender_id': account['id'], 'status': {'$in': ['queued', 'running', 'finalizing', 'repairing']}}),
        ('outreach_connection_locks', {'_id': account['id']}),
        ('outreach_health_controls', {'sender_id': account['id'], 'status': 'armed'}),
    ):
        if await getattr(db, name).find_one({**workspace_scope(workspace), **query}):
            raise ValueError('Unfinished sender work requires operator review')
    proof.assert_live()
    return [_utc(paid['paid_through']), _utc(asset['expires_at'])]


async def resume_connection(db: Any, workspace: str, sender: str, *, force: bool = False) -> dict:
    from outreach.core.restore_epoch import policy as epoch_policy
    if force:
        raise ValueError('Platform cooldown overrides are unavailable; reconnect or request operator review')
    scope = {'id': sender, 'id.0': {'$exists': False}, **workspace_scope(workspace)}
    account = await db.outreach_accounts.find_one(scope)
    if not account:
        raise ValueError('Sender account not found')
    _eligible(account, datetime.now(timezone.utc))
    await _current_checks(db, workspace, account, datetime.now(timezone.utc))
    captured, captured_epoch = policy(), epoch_policy()
    def material_policy_current() -> bool:
        return captured == policy() and captured_epoch == epoch_policy() and live_actions_enabled()
    try:
        cookie = account.get('session_cookie_enc') or account.get('encrypted_session_cookie') or account.get('li_at_enc')
        password = (account.get('proxy') or {}).get('password_enc')
        # Legacy plaintext fallback cannot prove installed credential custody.
        if any(not isinstance(value, str) or not value.startswith(('gAAAAA', 'uc1:')) for value in (cookie, password)):
            raise ValueError('Unproven stored material')
        if not material_policy_current():
            raise ValueError('Recovery policy changed')
        material = await asyncio.wait_for(session_custody.account_session(account), timeout=5)
        for key in ('li_at', 'jsession_id'):
            value = material.get(key)
            if not isinstance(value, str) or len(value) > 8192 or any(ord(char) < 32 or ord(char) == 127 for char in value):
                raise ValueError('Unusable stored material')
            value = value.strip().strip('"')
            if key == 'li_at':
                value = value.removeprefix('li_at=')
            if not value or value.startswith(('mock_', 'test_')):
                raise ValueError('Unusable stored material')
        del material, value
        if not material_policy_current():
            raise ValueError('Recovery policy changed')
        prepared = await asyncio.wait_for(prepare_proxy(account['proxy'], workspace), timeout=5)
        transport = urlsplit(prepared.url)
        if not transport.username or not transport.password:
            raise ValueError('Unusable stored proxy material')
        password = unquote(transport.password)
        if len(password) > 8192 or any(ord(char) < 32 or ord(char) == 127 for char in password):
            raise ValueError('Unusable stored proxy material')
        del transport, password
    except Exception:
        raise ValueError('Stored session or proxy credentials are unavailable; reconnect the sender') from None
    if not material_policy_current() or not prepared.current(prepared.url):
        raise ValueError('Credential configuration changed; reload the sender')
    digest = canonical_hash(stable(account))

    async def apply(current: suppression.SuppressionDatabase) -> dict:
        authority = AuthorityDatabase(current.database, current.session, 'sender_connection_resume')
        latest = await authority.outreach_accounts.find_one(scope)
        stamp = datetime.now(timezone.utc)
        if not latest or canonical_hash(stable(latest)) != digest:
            raise ValueError('Sender changed during recovery; reload its current state')
        _eligible(latest, stamp)
        deadlines = await _current_checks(authority, workspace, latest, stamp)
        def final_check() -> None:
            if (captured != policy() or captured_epoch != epoch_policy() or not live_actions_enabled()
                    or not prepared.matches(latest.get('proxy') or {}, workspace) or any(
                        deadline is None or deadline <= datetime.now(timezone.utc) for deadline in deadlines)):
                raise ValueError('Recovery policy or paid/provider term changed')
        final_check()
        changed = await current.outreach_accounts.update_one({**scope, '_id': latest['_id'],
            'status': latest['status'], 'stop_reason': latest['stop_reason'], 'cooldown_until': latest['cooldown_until']},
            {'$set': {'status': 'active', 'stop_reason': None, 'stopped_at': None, 'cooldown_until': None,
                      'error_details': None, 'updated_at': stamp}})
        if changed.matched_count != 1:
            raise ValueError('Sender changed before recovery completed')
        final_check()
        return {'sender_id': sender, 'status': 'active', 'tasks_resumed': 0,
                'campaigns_resumed': False, 'execution_permission_granted': False}
    return await suppression.mutate_suppression(db, workspace, apply)
