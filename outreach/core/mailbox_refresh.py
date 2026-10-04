"""Worker refresh with exact credential capture and durable uncertainty fencing."""
from __future__ import annotations
from copy import deepcopy
from datetime import timedelta, timezone
import secrets
from typing import Any
from pymongo import ReturnDocument

from outreach.core import suppression
from outreach.core.dispatch_authority import AuthorityDatabase
from outreach.core.provider_custody import (MailboxAccess, HELD_REFRESH, material_digest,
    prepare_mailbox_access, open_mailbox_refresh, seal_mailbox_tokens, custody_stamp)
from outreach.core.oauth_app_custody import prepare_app_secret


async def get_access(db: Any, mailbox: dict, *, parent_preflight=None, parent_allowed=None) -> str | MailboxAccess:
    from outreach.core import mailbox_connection as connection
    now = connection.datetime.now(timezone.utc)
    workspace, sender = mailbox['workspace_id'], mailbox['sender_account_id']
    scope = {'workspace_id': workspace, 'sender_account_id': sender}
    if not connection._control_allowed(workspace) or not await connection._paid_sender(db, workspace, sender):
        raise connection.MailboxUnavailable('Paid sender access is unavailable')
    current = await db.outreach_mailboxes.find_one({**scope, 'status': 'active'})
    if (not current or current.get('connection_job_id') != mailbox.get('connection_job_id')
            or not current.get('access_token_enc') or not current.get('refresh_token_enc')
            or current.get('refresh_state') in HELD_REFRESH):
        raise connection.MailboxUnavailable('Mailbox is no longer active or requires refresh review')
    mailbox = deepcopy(current)
    async def prepared(row):
        secret = await prepare_mailbox_access(row, workspace, sender)
        fresh = await db.outreach_mailboxes.find_one({**scope, 'status': 'active'})
        if not fresh or not connection._control_allowed(workspace) or not secret.matches(fresh, workspace, sender):
            raise connection.MailboxUnavailable('Mailbox changed during credential opening')
        if secret.scoped and (not connection._utc(fresh.get('token_expires_at'))
                or connection._utc(fresh['token_expires_at']) <= connection.datetime.now(timezone.utc)):
            raise connection.MailboxUnavailable('Mailbox access custody expired')
        return MailboxAccess(secret, db) if secret.scoped else secret.value
    expiry = connection._utc(mailbox.get('token_expires_at'))
    if expiry and expiry > now + timedelta(minutes=5):
        try: return await prepared(mailbox)
        except ValueError: raise connection.MailboxUnavailable('Encrypted mailbox credentials are unavailable') from None
    nonce = secrets.token_urlsafe(18)
    identity = {name: mailbox.get(name) if name in mailbox else {'$exists': False}
        for name in ('connection_job_id', 'provider', 'provider_user_id', 'email', 'custody_generation', 'oauth_app_identity_digest', 'access_token_enc', 'refresh_token_enc')}
    owned = {**scope, **identity, 'refresh_lease_nonce': nonce}
    claimed = await db.outreach_mailboxes.find_one_and_update({**scope, 'status': 'active', **identity,
        'refresh_state': {'$nin': sorted(HELD_REFRESH)}, '$or': [
            {'refresh_lease_until': {'$lt': now}}, {'refresh_lease_until': {'$exists': False}}]},
        {'$set': {'refresh_lease_nonce': nonce, 'refresh_lease_until': now + timedelta(seconds=45), 'refresh_state': 'preparing'}},
        return_document=ReturnDocument.AFTER)
    if not claimed: raise connection.MailboxTransientError('Mailbox token refresh is already in progress')
    basis = material_digest(claimed, 'mailbox')
    custody = custody_stamp()
    possible = False
    finished = False
    try:
        config = connection._provider_config(claimed['provider'])
        app_secret = await prepare_app_secret(config, mailbox=claimed)
        refresh = await open_mailbox_refresh(claimed, workspace, sender)
        payload = {'client_id': config.client_id, 'client_secret': app_secret.value,
            'refresh_token': refresh, 'grant_type': 'refresh_token'}
        if config.provider == 'microsoft': payload['scope'] = ' '.join(config.scopes)
        async def authorize(current):
            fenced = AuthorityDatabase(current.database, current.session, nonce) if isinstance(current, suppression.SuppressionDatabase) else current
            row = await fenced.outreach_mailboxes.find_one({**owned, 'status': 'active', 'refresh_state': 'preparing',
                'refresh_lease_until': {'$gt': connection.datetime.now(timezone.utc)}})
            # Refresh uses an expired token and may precede stale-inbox catchup;
            # only paid authorization and its own lease govern this control call.
            if isinstance(fenced, AuthorityDatabase): fenced.deadlines.clear()
            parent_deadlines = await parent_preflight(current) if parent_preflight else []
            if (not row or not app_secret.matches() or custody_stamp() != custody or not connection._control_allowed(workspace) or material_digest(row, 'mailbox') != basis
                    or not await connection._paid_sender(fenced, workspace, sender)):
                raise connection.MailboxUnavailable('Mailbox changed before token refresh')
            changed = await current.outreach_mailboxes.update_one({**owned, 'status': 'active', 'refresh_state': 'preparing'},
                {'$set': {'refresh_state': 'possible', 'refresh_submitted_at': connection.datetime.now(timezone.utc)}})
            if changed.matched_count != 1: raise connection.MailboxUnavailable('Mailbox refresh owner changed')
            return [*parent_deadlines, *(list(fenced.deadlines) if isinstance(fenced, AuthorityDatabase) else [])]
        # Set before possible-authorization commit: an acknowledgement loss may
        # hide a committed permit. It cannot justify clearing/reusing the slot.
        possible = True
        deadlines = await suppression.mutate_suppression(db, workspace, authorize)
        async with connection.httpx.AsyncClient(timeout=20) as client:
            if (not app_secret.matches() or custody_stamp() != custody or not connection._control_allowed(workspace) or not connection._deadlines_live(deadlines)
                    or parent_allowed and not parent_allowed()
                    or connection._utc(claimed['refresh_lease_until']) <= connection.datetime.now(timezone.utc)):
                raise connection.MailboxUnavailable('Mailbox refresh authorization expired before transport')
            response = await client.post(config.token_url, data=payload)
        if response.status_code in {400, 401}:
            await db.outreach_mailboxes.update_one({**owned, 'status': 'active'}, {'$set': {'status': 'reauth_required', 'refresh_state': 'rejected'},
                '$unset': {'access_token_enc': '', 'refresh_token_enc': '', 'refresh_lease_nonce': '', 'refresh_lease_until': ''}})
            finished = True
            raise connection.MailboxUnavailable('Mailbox authorization expired; reconnect')
        if response.status_code != 200:
            raise connection.MailboxTransientError('Mailbox provider is temporarily unavailable; refresh requires review')
        data = response.json()
        if not isinstance(data, dict) or data.get('error') or not isinstance(data.get('access_token'), str) or not data['access_token']:
            raise connection.MailboxTransientError('Mailbox token refresh returned no usable access token')
        encrypted = await seal_mailbox_tokens({'access_token': data['access_token'], 'refresh_token': data.get('refresh_token') or refresh},
            claimed, workspace, sender, generation=claimed.get('custody_generation'))
        now = connection.datetime.now(timezone.utc)
        updates = {**encrypted, 'token_expires_at': now + timedelta(seconds=max(60, int(data.get('expires_in') or 3600))), 'updated_at': now}
        async def install(current):
            if parent_preflight: await parent_preflight(current)
            fenced = AuthorityDatabase(current.database, current.session, nonce) if isinstance(current, suppression.SuppressionDatabase) else current
            row = await fenced.outreach_mailboxes.find_one({**owned, 'status': 'active', 'refresh_state': 'possible'})
            if (not row or not app_secret.matches() or custody_stamp() != custody or not connection._control_allowed(workspace) or material_digest(row, 'mailbox') != basis
                    or not await connection._paid_sender(fenced, workspace, sender)):
                raise connection.MailboxUnavailable('Mailbox changed during token refresh')
            changed = await current.outreach_mailboxes.update_one({**owned, 'status': 'active', 'refresh_state': 'possible'},
                {'$set': updates, '$unset': {'refresh_state': '', 'refresh_lease_nonce': '', 'refresh_lease_until': ''}})
            if changed.matched_count != 1: raise connection.MailboxUnavailable('Mailbox refresh owner changed')
        await suppression.mutate_suppression(db, workspace, install)
        finished = True
        return await prepared({**claimed, **updates, 'refresh_state': None})
    except Exception:
        if possible and not finished:
            # Original ciphertext remains as held evidence, not reusable auth.
            # If installation committed despite a lost acknowledgement, its
            # replacement ciphertext no longer matches owned and is preserved.
            await db.outreach_mailboxes.update_one(owned, {'$set': {'refresh_state': 'unknown', 'status': 'reauth_required'}})
        raise connection.MailboxUnavailable('Mailbox refresh requires reconnection or review') from None
    finally:
        if finished or not possible:
            await db.outreach_mailboxes.update_one(owned, {'$unset': {'refresh_lease_nonce': '', 'refresh_lease_until': '', 'refresh_state': ''}})
        # Cancelled threads/tasks after possible authorization retain durable
        # possible state even if no exception handler ran. No timeout reclaim.
