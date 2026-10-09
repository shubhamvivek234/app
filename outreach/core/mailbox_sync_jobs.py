"""Durable read-only inbox jobs. HTTP and key services never run in transactions.

Saved responses can be replayed locally. Missing read responses require a new
physical attempt/allowance; unlike OAuth mutations, a bounded GET may be retried.
"""
from __future__ import annotations

import base64
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import secrets
from typing import Any, Callable

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from outreach.core import mailbox_sync as sync, session_custody, suppression
from outreach.core.authorization import canonical_hash
from outreach.core.mailbox_connection import MailboxUnavailable, _deadlines_live, is_shutting_down
from outreach.core.mailbox_jobs import _fenced
from outreach.core.paid_access import _utc
from outreach.core.provider_custody import MailboxAccess, mailbox_identity, prepare_mailbox_access
from utils.encryption import encrypt, decrypt_strict

ACTIVE = ['queued', 'running']
LEASE = timedelta(minutes=2)
JOB_LIFETIME = timedelta(minutes=10)
POLL_INTERVAL = timedelta(seconds=120)
DAILY_READ_LIMIT = 1000
MAX_JOB_READS = 600
MAX_RESPONSE_BYTES = 2_000_000
MAX_CACHE_BYTES = 8_000_000
MAX_ATTEMPTS = 5


def now() -> datetime:
    return datetime.now(timezone.utc)


def scope(job: dict) -> dict:
    return {'workspace_id': job['workspace_id'], '_id': job['_id']}


def basis(mailbox: dict) -> str:
    """Token refresh may change material, but never the account/cursor basis."""
    return canonical_hash([mailbox_identity(mailbox), mailbox.get('custody_generation'),
        mailbox.get('history_id'), mailbox.get('delta_url')])


def policy_stamp() -> str:
    return canonical_hash([session_custody.custody_mode(), os.getenv('OUTREACH_CUSTODY_ENVIRONMENT_ID', '').strip()])


def allowed(workspace: str) -> bool:
    return sync.is_mailbox_sync_pilot_allowed(workspace) and not is_shutting_down()


async def validate(current: Any, job: dict, owner: str | None = None, *, paid: bool = True) -> tuple[dict, dict, list]:
    from outreach.core.restore_epoch import positive
    await positive(current, job['workspace_id'])
    query = {**scope(job), 'status': 'running' if owner else {'$in': ACTIVE}}
    if owner: query['owner'] = owner
    fenced = _fenced(current, owner or job['_id'])
    row = await fenced.outreach_mailbox_sync_jobs.find_one(query)
    mailbox = await fenced.outreach_mailboxes.find_one({'workspace_id': job['workspace_id'],
        'sender_account_id': job['sender_account_id'], 'status': 'active'})
    # Inbox catchup does not require a fresh inbox or an unexpired old bearer.
    from outreach.core.dispatch_authority import AuthorityDatabase
    if isinstance(fenced, AuthorityDatabase): fenced.deadlines.clear()
    if (not row or not mailbox or row.get('basis') != basis(mailbox) or row.get('basis') != job['basis']
            or row.get('policy_stamp') != policy_stamp() or not allowed(job['workspace_id'])
            or not _utc(row.get('deadline')) or _utc(row['deadline']) <= now()
            or owner and (not _utc(row.get('lease_until')) or _utc(row['lease_until']) <= now())):
        raise MailboxUnavailable('Mailbox sync owner, cursor or policy changed')
    if paid and not await sync._paid_sender(fenced, job['workspace_id'], job['sender_account_id']):
        raise MailboxUnavailable('Paid mailbox sync authority ended')
    from outreach.core.dispatch_authority import AuthorityDatabase
    deadlines = list(fenced.deadlines) if isinstance(fenced, AuthorityDatabase) else []
    return row, mailbox, [*deadlines, row['deadline'], *([row['lease_until']] if owner else [])]


async def ensure_job(db: Any, workspace: str, sender: str) -> dict | None:
    if not allowed(workspace): return None
    async def ensure(current):
        fenced = _fenced(current, 'mailbox-sync-selection')
        mailbox = await fenced.outreach_mailboxes.find_one({'workspace_id': workspace, 'sender_account_id': sender, 'status': 'active'})
        if not mailbox or not await sync._paid_sender(fenced, workspace, sender): return None
        existing = await current.outreach_mailbox_sync_jobs.find_one({'workspace_id': workspace, 'sender_account_id': sender,
            'status': {'$in': ACTIVE}})
        if existing: return existing
        started = now(); job_id = secrets.token_urlsafe(20)
        row = {'_id': job_id, 'workspace_id': workspace, 'sender_account_id': sender, 'provider': mailbox['provider'],
            'basis': basis(mailbox), 'identity_digest': mailbox_identity(mailbox), 'policy_stamp': policy_stamp(),
            'status': 'queued', 'created_at': started, 'coverage_started_at': started, 'deadline': started + JOB_LIFETIME,
            'next_publish_at': started, 'next_recovery_at': started + LEASE,
            'attempts': 0, 'projected': 0, 'replies': 0, 'bounces': 0, 'cache_bytes': 0,
            'bootstrap': not bool(mailbox.get('history_id') if mailbox['provider'] == 'gmail' else mailbox.get('delta_url'))}
        row['next_cleanup_at'] = row['deadline']
        await current.outreach_mailbox_sync_jobs.insert_one(row)
        return row
    return await suppression.mutate_suppression(db, workspace, ensure)


async def _claim(db: Any, workspace: str, job_id: str, owner: str) -> dict | None:
    async def claim(current):
        job = await current.outreach_mailbox_sync_jobs.find_one({'workspace_id': workspace, '_id': job_id, 'status': 'queued'})
        if not job: return None
        await validate(current, job)
        if job['attempts'] >= MAX_ATTEMPTS: raise MailboxUnavailable('Mailbox sync recovery limit reached')
        changed = await current.outreach_mailbox_sync_jobs.update_one({**scope(job), 'status': 'queued'}, {'$set': {
            'status': 'running', 'owner': owner, 'lease_until': now() + LEASE, 'next_recovery_at': now() + LEASE}, '$inc': {'attempts': 1}})
        if changed.matched_count != 1: return None
        return await current.outreach_mailbox_sync_jobs.find_one(scope(job))
    return await suppression.mutate_suppression(db, workspace, claim)


async def _crypt(job: dict, key: str, data: str, *, opening: bool = False) -> str:
    if job['policy_stamp'] != policy_stamp(): raise MailboxUnavailable('Mailbox cache custody changed')
    binding = canonical_hash([job['_id'], job['basis'], key])
    if session_custody.custody_mode() == 'kms_v1':
        custody = session_custody.configured_custody()
        context = session_custody.context(job['workspace_id'], job['sender_account_id'], binding, 'mailbox_sync_key')
        key = bytearray()
        try:
            if opening:
                if len(data) > 4_000_000: raise MailboxUnavailable('Mailbox cache envelope exceeds bound')
                envelope = json.loads(data)
                key.extend(base64.b64decode(await custody.open(envelope['wrapped_key'], context), validate=True))
                if len(key) != 32: raise MailboxUnavailable('Mailbox cache key is unavailable')
                return AESGCM(bytes(key)).decrypt(base64.b64decode(envelope['nonce'], validate=True),
                    base64.b64decode(envelope['ciphertext'], validate=True), binding.encode()).decode()
            if len(data.encode()) > 2_700_000: raise MailboxUnavailable('Mailbox cache payload exceeds bound')
            key.extend(os.urandom(32)); nonce = os.urandom(12)
            wrapped = await custody.seal(base64.b64encode(bytes(key)).decode(), context)
            ciphertext = AESGCM(bytes(key)).encrypt(nonce, data.encode(), binding.encode())
            return json.dumps({'wrapped_key': wrapped, 'nonce': base64.b64encode(nonce).decode(),
                'ciphertext': base64.b64encode(ciphertext).decode()}, separators=(',', ':'))
        finally:
            key[:] = bytes(len(key))
    if opening:
        payload = json.loads(decrypt_strict(data))
        if payload.get('binding') != binding: raise MailboxUnavailable('Mailbox cache binding changed')
        return payload['value']
    return encrypt(json.dumps({'binding': binding, 'value': data}, separators=(',', ':')))


class SyncReadAccess:
    """One worker's ordered request cache and physical-read permit."""
    def __init__(self, db: Any, job: dict, owner: str, token: MailboxAccess | None = None) -> None:
        self.db, self.job, self.owner, self.token = db, job, owner, token
        self.index = 0
        self.request = None
        from outreach.core.restore_epoch import policy
        self.epoch_policy = policy()

    async def authorize(self) -> list:
        from outreach.core.restore_epoch import positive
        request = self.request
        if not request: raise MailboxUnavailable('Mailbox read reference is unavailable')
        async def authorize(current):
            await positive(current, self.job['workspace_id'], captured=self.epoch_policy)
            row, mailbox, deadlines = await validate(current, self.job, self.owner)
            if (not self.token.secret.matches(mailbox, self.job['workspace_id'], self.job['sender_account_id'])
                    or not _utc(mailbox.get('token_expires_at')) or _utc(mailbox['token_expires_at']) <= now()):
                raise MailboxUnavailable('Mailbox read credential changed')
            day = now().date().isoformat()
            key = canonical_hash(['mailbox-read', self.job['workspace_id'], self.job['sender_account_id'], day])
            budget_scope = {'workspace_id': self.job['workspace_id'], '_id': key}
            budget = await current.outreach_mailbox_read_budgets.find_one(budget_scope)
            if budget and budget.get('used', DAILY_READ_LIMIT) >= DAILY_READ_LIMIT:
                raise MailboxUnavailable('Mailbox daily physical-read allowance exhausted')
            if row.get('physical_reads', 0) >= MAX_JOB_READS:
                raise MailboxUnavailable('Mailbox job physical-read allowance exhausted')
            await current.outreach_mailbox_read_budgets.update_one(budget_scope, {'$inc': {'used': 1}, '$setOnInsert': {
                'sender_account_id': self.job['sender_account_id'], 'day': day}}, upsert=True)
            await current.outreach_mailbox_sync_jobs.update_one({**scope(self.job), 'status': 'running', 'owner': self.owner},
                {'$inc': {'physical_reads': 1}})
            await current.outreach_mailbox_sync_reads.insert_one({**request, 'status': 'possible', 'mutation': False,
                'submitted_at': now(), 'owner': self.owner, 'basis': self.job['basis']})
            return [*deadlines, mailbox['token_expires_at']]
        return await suppression.mutate_suppression(self.db, self.job['workspace_id'], authorize)

    def assert_live(self, deadlines: list) -> None:
        from outreach.core.restore_epoch import EpochProof
        if not EpochProof(self.epoch_policy).live():
            raise MailboxUnavailable('Restore epoch changed after commit')
        if not _deadlines_live(deadlines) or not allowed(self.job['workspace_id']) or not self.token.secret.policy_matches():
            raise MailboxUnavailable('Mailbox read authorization expired after commit')

    async def get(self, url: str, *, params: dict | None = None) -> httpx.Response:
        index = self.index; self.index += 1
        if index >= MAX_JOB_READS: raise MailboxUnavailable('Mailbox request count exceeded')
        request_digest = canonical_hash([url, params])
        logical = {'workspace_id': self.job['workspace_id'], 'job_id': self.job['_id'], 'request_index': index,
            'request_digest': request_digest}
        cached = await self.db.outreach_mailbox_sync_reads.find_one({**logical, 'status': 'received'})
        if cached:
            raw = json.loads(await _crypt(self.job, cached['_id'], cached['response_enc'], opening=True))
            content = base64.b64decode(raw['content'], validate=True)
            if hashlib.sha256(content).hexdigest() != cached['response_digest'] or len(content) > MAX_RESPONSE_BYTES:
                raise MailboxUnavailable('Mailbox saved response changed')
            return httpx.Response(raw['http_status'], content=content)
        request_id = canonical_hash([self.job['_id'], index, self.job['attempts'], self.owner])
        self.request = {'_id': request_id, **logical, 'sender_account_id': self.job['sender_account_id']}
        if self.token is None:
            async def parent_preflight(current):
                _, _, deadlines = await validate(current, self.job, self.owner)
                return deadlines
            await suppression.mutate_suppression(self.db, self.job['workspace_id'], parent_preflight)
            mailbox = await self.db.outreach_mailboxes.find_one({'workspace_id': self.job['workspace_id'],
                'sender_account_id': self.job['sender_account_id'], 'status': 'active'})
            if not mailbox or basis(mailbox) != self.job['basis']: raise MailboxUnavailable('Mailbox read basis changed')
            await sync.get_mailbox_access_token(self.db, mailbox, parent_preflight=parent_preflight,
                parent_allowed=lambda: allowed(self.job['workspace_id']) and self.job['policy_stamp'] == policy_stamp())
            # Capture actual material after refresh/opening. A fully cached
            # recovery never invokes refresh or opens bearer credentials.
            mailbox = await self.db.outreach_mailboxes.find_one({'workspace_id': self.job['workspace_id'],
                'sender_account_id': self.job['sender_account_id'], 'status': 'active'})
            if not mailbox or basis(mailbox) != self.job['basis']: raise MailboxUnavailable('Mailbox changed during refresh')
            self.token = MailboxAccess(await prepare_mailbox_access(mailbox, self.job['workspace_id'], self.job['sender_account_id']), self.db)
        async with sync.httpx.AsyncClient(timeout=25, follow_redirects=False) as client:
            deadlines = await self.authorize()
            self.assert_live(deadlines)
            timeout = min(25, *(max(0, (_utc(deadline) - now()).total_seconds()) for deadline in deadlines))
            async with asyncio.timeout(timeout):
                async with client.stream('GET', url, params=params, headers={'Authorization': 'Bearer ' + self.token.secret.value,
                        'Accept-Encoding': 'identity'}) as incoming:
                    if incoming.headers.get('content-encoding', '').strip().lower() not in {'', 'identity'}:
                        raise MailboxUnavailable('Encoded mailbox responses require a bounded adapter')
                    content = bytearray()
                    async for chunk in incoming.aiter_raw(chunk_size=65536):
                        if len(content) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise MailboxUnavailable('Mailbox response exceeds cache bound')
                        content.extend(chunk)
                    response = httpx.Response(incoming.status_code, content=bytes(content))
        payload = json.dumps({'http_status': response.status_code, 'content': base64.b64encode(response.content).decode()}, separators=(',', ':'))
        encrypted = await _crypt(self.job, request_id, payload)
        async def receipt(current):
            row, _, _ = await validate(current, self.job, self.owner)
            if row.get('cache_bytes', 0) + len(response.content) > MAX_CACHE_BYTES:
                raise MailboxUnavailable('Mailbox response cache allowance exceeded')
            changed = await current.outreach_mailbox_sync_reads.update_one({'workspace_id': self.job['workspace_id'],
                '_id': request_id, 'status': 'possible', 'owner': self.owner, 'basis': self.job['basis']}, {'$set': {
                    'status': 'received', 'http_status': response.status_code, 'response_enc': encrypted,
                    'response_digest': hashlib.sha256(response.content).hexdigest(), 'received_at': now()}})
            if changed.matched_count != 1: raise MailboxUnavailable('Mailbox response owner changed')
            await current.outreach_mailbox_sync_jobs.update_one({**scope(self.job), 'status': 'running', 'owner': self.owner},
                {'$inc': {'cache_bytes': len(response.content)}})
        try:
            await suppression.mutate_suppression(self.db, self.job['workspace_id'], receipt)
        except Exception:
            saved = await self.db.outreach_mailbox_sync_reads.find_one({'workspace_id': self.job['workspace_id'],
                '_id': request_id, 'owner': self.owner, 'status': 'received', 'response_enc': encrypted})
            if not saved: raise
        return response


async def _collect(mailbox: dict, job: dict, access: SyncReadAccess) -> tuple[list, dict]:
    if not job['bootstrap']:
        messages, cursor = await (sync._gmail_messages(mailbox, access) if mailbox['provider'] == 'gmail' else sync._graph_messages(mailbox, access))
        return messages, {'history_id' if mailbox['provider'] == 'gmail' else 'delta_url': cursor}
    if mailbox['provider'] == 'gmail':
        payload = sync._response_json(await sync._provider_get(sync.GMAIL_BASE + '/profile', access))
        if not payload.get('historyId'): raise MailboxUnavailable('Gmail history cursor is unavailable')
        return [], {'history_id': str(payload['historyId'])}
    url = sync.GRAPH_BASE + '/mailFolders/inbox/messages/delta'
    params = {'changeType': 'created', '$select': 'id,from,receivedDateTime,internetMessageId,internetMessageHeaders,subject',
        '$filter': 'receivedDateTime ge ' + _utc(job['coverage_started_at']).isoformat().replace('+00:00', 'Z'), '$top': '100'}
    # Initial messages are not attributed; only a complete baseline permits
    # future sends. The filter timestamp is immutable across recovery.
    for page in range(sync.MAX_SYNC_PAGES):
        payload = sync._response_json(await sync._provider_get(url, access, params=params if page == 0 else None))
        delta = payload.get('@odata.deltaLink')
        if delta and sync._safe_graph_delta_url(delta): return [], {'delta_url': delta}
        url = payload.get('@odata.nextLink')
        if not url or not sync._safe_graph_delta_url(url): break
    raise MailboxUnavailable('Microsoft baseline cursor is incomplete')


async def finish_job(db: Any, job: dict, owner: str, cursor: dict) -> dict:
    async def finish(current):
        from outreach.core.restore_epoch import positive
        epoch = await positive(current, job['workspace_id'])
        row, mailbox, _ = await validate(current, job, owner)
        changed = await current.outreach_mailboxes.update_one(sync._mailbox_snapshot_filter(mailbox), {'$set': {
            **cursor, 'sync_status': 'healthy', 'last_sync_at': row['coverage_started_at'], 'sync_completed_at': now(),
            'last_sync_job_id': job['_id']}, '$unset': {'sync_error': ''}})
        if changed.matched_count != 1: raise MailboxUnavailable('Mailbox cursor changed during completion')
        await current.outreach_mailbox_sync_jobs.update_one({**scope(job), 'status': 'running', 'owner': owner}, {'$set': {
            'status': 'completed', 'completed_at': now(), 'cursor_digest': canonical_hash(cursor),
            'cache_scrubbed_at': now()}, '$unset': {'lease_until': ''}})
        await current.outreach_mailbox_sync_reads.update_many({'workspace_id': job['workspace_id'], 'job_id': job['_id']},
            {'$unset': {'response_enc': ''}})
        epoch.assert_live()
        return {'status': 'healthy', 'replies': row['replies'], 'bounces': row['bounces']}
    try: return await suppression.mutate_suppression(db, job['workspace_id'], finish)
    except Exception:
        saved = await db.outreach_mailbox_sync_jobs.find_one({**scope(job), 'status': 'completed', 'owner': owner,
            'cursor_digest': canonical_hash(cursor)})
        if saved: return {'status': 'healthy', 'replies': saved['replies'], 'bounces': saved['bounces']}
        raise


async def _fail(db: Any, job: dict, owner: str) -> None:
    async def fail(current):
        row = await current.outreach_mailbox_sync_jobs.find_one({**scope(job), 'status': 'running', 'owner': owner})
        if not row: return
        mailbox = await current.outreach_mailboxes.find_one({'workspace_id': job['workspace_id'],
            'sender_account_id': job['sender_account_id'], 'status': 'active'})
        same = bool(mailbox and basis(mailbox) == job['basis'])
        retry = same and _utc(row['deadline']) > now() and row['attempts'] < MAX_ATTEMPTS
        await current.outreach_mailbox_sync_reads.update_many({'workspace_id': job['workspace_id'], 'job_id': job['_id'],
            'owner': owner, 'status': 'possible'}, {'$set': {'status': 'read_interrupted', 'interrupted_at': now()}})
        await current.outreach_mailbox_sync_jobs.update_one({**scope(job), 'status': 'running', 'owner': owner}, {'$set': {
            'status': 'queued' if retry else 'failed', 'next_publish_at': now() + timedelta(seconds=30),
            'next_recovery_at': now() + timedelta(seconds=30), 'error': 'Reply synchronization needs attention'}, '$unset': {'lease_until': ''}})
        if same:
            await current.outreach_mailboxes.update_one(sync._mailbox_snapshot_filter(mailbox), {'$set': {
                'sync_status': 'stale', 'sync_error': 'Reply synchronization needs attention'}})
    await suppression.mutate_suppression(db, job['workspace_id'], fail)


async def execute_job(db: Any, workspace: str, job_id: str) -> dict:
    from outreach.core.restore_epoch import positive
    await positive(db, workspace)
    owner = secrets.token_urlsafe(18)
    job = None
    try:
        job = await _claim(db, workspace, job_id, owner)
        if not job: return {'status': 'already_claimed'}
        mailbox = await db.outreach_mailboxes.find_one({'workspace_id': workspace, 'sender_account_id': job['sender_account_id'], 'status': 'active'})
        if not mailbox or basis(mailbox) != job['basis']: raise MailboxUnavailable('Mailbox changed during sync')
        access = SyncReadAccess(db, job, owner)
        messages, cursor = await _collect(mailbox, job, access)
        for index, message in enumerate(messages):
            async def project(current):
                row, current_mailbox, _ = await validate(current, job, owner)
                if row['projected'] > index: return
                if row['projected'] != index: raise MailboxUnavailable('Mailbox projection progress changed')
                result = await sync._mark_inbound(current, current_mailbox, message)
                await current.outreach_mailbox_sync_jobs.update_one({**scope(job), 'status': 'running', 'owner': owner,
                    'projected': index}, {'$inc': {'projected': 1, 'replies': int(result.get('status') == 'reply'),
                        'bounces': int(result.get('status') == 'bounce')}})
            await suppression.mutate_suppression(db, workspace, project)
        return await finish_job(db, job, owner, cursor)
    except Exception:
        if job:
            try: await _fail(db, job, owner)
            except suppression.SuppressionUnavailable: pass  # stopped tenant belongs to erasure
        return {'status': 'stale'}


async def _postpone(db: Any, row: dict, field: str) -> None:
    from outreach.core.erasure import _control
    async def backoff(current):
        await current.outreach_mailbox_sync_jobs.update_one({**scope(row), 'status': row['status'],
            'owner': row['owner'] if 'owner' in row else {'$exists': False},
            field: row[field] if field in row else {'$exists': False}}, {'$set': {field: now() + timedelta(minutes=5)}})
    await _control(db, row['workspace_id'], backoff)


async def publish_due(db: Any, publish: Callable[[str, str], None]) -> dict:
    counts = {'published': 0, 'failed': 0}
    if is_shutting_down(): return counts
    rows = await db.outreach_mailbox_sync_jobs.find({'status': 'queued', 'next_publish_at': {'$lte': now()}}).sort('next_publish_at', 1).limit(50).to_list(length=50)
    for row in rows:
        if is_shutting_down(): break
        if not allowed(row['workspace_id']):
            await _postpone(db, row, 'next_publish_at'); continue
        async def claim(current):
            changed = await current.outreach_mailbox_sync_jobs.update_one({**scope(row), 'status': 'queued',
                'next_publish_at': row['next_publish_at']}, {'$set': {'next_publish_at': now() + timedelta(seconds=30)}})
            return changed.modified_count == 1
        try:
            if not await suppression.mutate_suppression(db, row['workspace_id'], claim): continue
        except suppression.SuppressionUnavailable:
            await _postpone(db, row, 'next_publish_at'); continue
        try: publish(row['_id'], row['workspace_id']); counts['published'] += 1
        except Exception: counts['failed'] += 1
    return counts


async def recover_due(db: Any) -> dict:
    count = 0
    if is_shutting_down(): return {'recovered': 0}
    rows = await db.outreach_mailbox_sync_jobs.find({'status': {'$in': ACTIVE}, '$or': [
        {'next_recovery_at': {'$lte': now()}}, {'status': 'running', 'lease_until': {'$lte': now()}}]
    }).sort('next_recovery_at', 1).limit(50).to_list(length=50)
    for row in rows:
        async def recover(current):
            fresh = await current.outreach_mailbox_sync_jobs.find_one({**scope(row), 'status': row['status'],
                'owner': row['owner'] if 'owner' in row else {'$exists': False}})
            if not fresh: return False
            if fresh['status'] == 'running' and _utc(fresh.get('lease_until')) and _utc(fresh['lease_until']) > now(): return False
            if fresh['status'] == 'queued' and _utc(fresh['deadline']) > now():
                await current.outreach_mailbox_sync_jobs.update_one(scope(row), {'$set': {'next_recovery_at': now() + timedelta(seconds=30)}})
                return False
            if fresh['status'] == 'running':
                await _fail(current, fresh, fresh['owner']); return True
            await current.outreach_mailbox_sync_jobs.update_one(scope(row), {'$set': {'status': 'failed', 'error': 'Mailbox sync deadline expired'}})
            return True
        try: count += bool(await suppression.mutate_suppression(db, row['workspace_id'], recover))
        except suppression.SuppressionUnavailable: await _postpone(db, row, 'next_recovery_at')
    return {'recovered': count}


async def cleanup_due(db: Any) -> dict:
    """Scrub terminal cache bytes after the fixed deadline; retain read evidence."""
    from outreach.core.erasure import _control
    if is_shutting_down(): return {'cleaned': 0}
    rows = await db.outreach_mailbox_sync_jobs.find({'status': {'$in': ['failed', 'stopped']},
        'cache_scrubbed_at': {'$exists': False}, 'next_cleanup_at': {'$lte': now()}}
    ).sort('next_cleanup_at', 1).limit(50).to_list(length=50)
    count = 0
    for row in rows:
        if is_shutting_down(): break
        async def scrub(current):
            fresh = await current.outreach_mailbox_sync_jobs.find_one({**scope(row), 'status': row['status'],
                'owner': row['owner'] if 'owner' in row else {'$exists': False}, 'basis': row['basis'],
                'cache_scrubbed_at': {'$exists': False}, 'deadline': {'$lte': now()}})
            if not fresh: return False
            await current.outreach_mailbox_sync_reads.update_many({'workspace_id': row['workspace_id'], 'job_id': row['_id']},
                {'$unset': {'response_enc': ''}})
            await current.outreach_mailbox_sync_jobs.update_one(scope(row), {'$set': {'cache_scrubbed_at': now()}})
            return True
        count += bool(await _control(db, row['workspace_id'], scrub))
    return {'cleaned': count}
