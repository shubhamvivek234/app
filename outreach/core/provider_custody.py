"""Scoped mailbox/OAuth/finder material prepared outside database authorization."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime, timezone
import hmac
import uuid
import os

from outreach.core import session_custody
from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import CustodyUnavailable, PREFIX
from utils.encryption import decrypt_strict, encrypt

MAILBOX_IDENTITY = ('provider', 'provider_user_id', 'email', 'connection_job_id')
MAILBOX_MATERIAL = ('workspace_id', 'sender_account_id', *MAILBOX_IDENTITY, 'custody_generation',
    'access_token_enc', 'refresh_token_enc', 'token_expires_at')
FINDER_MATERIAL = ('workspace_id', 'credential_generation', 'custody_workspace_id', 'api_key_enc')
HELD_REFRESH = frozenset({'possible', 'unknown'})


def custody_stamp() -> tuple[str, str]:
    return session_custody.custody_mode(), os.getenv('OUTREACH_CUSTODY_ENVIRONMENT_ID', '').strip()


def mailbox_identity(record: dict) -> str:
    return canonical_hash([record.get(name) for name in MAILBOX_IDENTITY])


def material_digest(record: dict, kind: str) -> str:
    names = MAILBOX_MATERIAL if kind == 'mailbox' else FINDER_MATERIAL
    values = {name: record.get(name) for name in names}
    expiry = values.get('token_expires_at')
    if isinstance(expiry, datetime):
        expiry = expiry.replace(tzinfo=timezone.utc) if expiry.tzinfo is None else expiry.astimezone(timezone.utc)
        values['token_expires_at'] = expiry.replace(microsecond=expiry.microsecond // 1000 * 1000)
    return canonical_hash(values)


def _context(record: dict, workspace: str, sender: str | None, purpose: str):
    if record.get('workspace_id') != workspace:
        raise CustodyUnavailable('Provider credential workspace changed')
    if purpose.startswith('mailbox_'):
        if record.get('sender_account_id') != sender or record.get('provider') not in {'gmail', 'microsoft'}:
            raise CustodyUnavailable('Mailbox credential identity changed')
        generation = record.get('custody_generation')
        if any(not isinstance(record.get(name), str) or not record[name] for name in (*MAILBOX_IDENTITY, 'custody_generation')):
            raise CustodyUnavailable('Mailbox credential context is unavailable')
        version = canonical_hash([generation, mailbox_identity(record)])
        resource = sender
    elif purpose == 'finder_key':
        generation = record.get('credential_generation')
        if not isinstance(generation, str) or not generation or record.get('custody_workspace_id') != workspace:
            raise CustodyUnavailable('Finder credential context is unavailable')
        version = generation
        resource = canonical_hash(['hunter', workspace])
    else:
        if record.get('sender_account_id') != sender or record.get('provider') not in {'gmail', 'microsoft'} or not record.get('id'):
            raise CustodyUnavailable('Pending OAuth credential context is unavailable')
        version = canonical_hash([record['id'], record['provider']])
        resource = sender
    return session_custody.context(workspace, resource, version, purpose)


async def _seal(value: str, record: dict, workspace: str, sender: str | None, purpose: str) -> str:
    if not isinstance(value, str) or not value:
        raise CustodyUnavailable('Complete provider credentials are required')
    if session_custody.custody_mode() == 'kms_v1':
        return await session_custody.configured_custody().seal(value, _context(record, workspace, sender, purpose))
    return encrypt(value)


async def _open(value: str, record: dict, workspace: str, sender: str | None, purpose: str) -> str:
    if session_custody.custody_mode() == 'kms_v1':
        return await session_custody.configured_custody().open(value, _context(record, workspace, sender, purpose))
    if str(value or '').startswith(PREFIX):
        raise CustodyUnavailable('Scoped provider credentials cannot use legacy custody')
    try: return decrypt_strict(value)
    except (ValueError, OSError): raise CustodyUnavailable('Provider credential opening is unavailable') from None


@dataclass(frozen=True)
class PreparedSecret:
    workspace_id: str
    sender_id: str | None
    kind: str
    identity_digest: str
    binding_digest: str
    scoped: bool
    value: str = field(repr=False)
    _value_digest: str = field(repr=False)
    environment_digest: str = field(repr=False)

    def policy_matches(self) -> bool:
        return (self.scoped == (session_custody.custody_mode() == 'kms_v1')
            and self.environment_digest == canonical_hash(os.getenv('OUTREACH_CUSTODY_ENVIRONMENT_ID', '').strip())
            and hmac.compare_digest(self._value_digest, canonical_hash(self.value)))

    def matches(self, record: dict, workspace: str, sender: str | None = None) -> bool:
        return bool(self.workspace_id == workspace and self.sender_id == sender and record.get('workspace_id') == workspace
            and (self.kind != 'mailbox' or record.get('sender_account_id') == sender and record.get('refresh_state') not in HELD_REFRESH)
            and self.policy_matches()
            and hmac.compare_digest(self.binding_digest, material_digest(record, self.kind)))


async def seal_mailbox_tokens(tokens: dict, record: dict, workspace: str, sender: str, *, generation: str | None = None) -> dict:
    row = deepcopy(record); row['custody_generation'] = generation or str(uuid.uuid4())
    result = {'custody_generation': row['custody_generation']}
    for name in ('access_token', 'refresh_token'):
        result[name + '_enc'] = await _seal(tokens.get(name), row, workspace, sender, 'mailbox_' + name)
    return result


async def prepare_mailbox_access(record: dict, workspace: str, sender: str) -> PreparedSecret:
    row = deepcopy(record)
    scoped = session_custody.custody_mode() == 'kms_v1'
    environment = canonical_hash(os.getenv('OUTREACH_CUSTODY_ENVIRONMENT_ID', '').strip())
    if row.get('refresh_state') in HELD_REFRESH:
        raise CustodyUnavailable('Mailbox refresh outcome requires reconnection or review')
    value = await _open(row.get('access_token_enc'), row, workspace, sender, 'mailbox_access_token')
    return PreparedSecret(workspace, sender, 'mailbox', mailbox_identity(row), material_digest(row, 'mailbox'),
        scoped, value, canonical_hash(value), environment)


async def open_mailbox_refresh(record: dict, workspace: str, sender: str) -> str:
    row = deepcopy(record)
    return await _open(row.get('refresh_token_enc'), row, workspace, sender, 'mailbox_refresh_token')


async def seal_finder_key(value: str, workspace: str, *, generation: str | None = None) -> dict:
    row = {'workspace_id': workspace, 'custody_workspace_id': workspace, 'credential_generation': generation or str(uuid.uuid4())}
    return {**row, 'api_key_enc': await _seal(value, row, workspace, None, 'finder_key')}


async def prepare_finder_key(record: dict, workspace: str) -> PreparedSecret:
    row = deepcopy(record)
    scoped = session_custody.custody_mode() == 'kms_v1'
    environment = canonical_hash(os.getenv('OUTREACH_CUSTODY_ENVIRONMENT_ID', '').strip())
    value = await _open(row.get('api_key_enc'), row, workspace, None, 'finder_key')
    return PreparedSecret(workspace, None, 'finder', canonical_hash(['hunter', workspace]), material_digest(row, 'finder'),
        scoped, value, canonical_hash(value), environment)


async def seal_oauth_secret(value: str, record: dict, workspace: str, sender: str, purpose: str) -> str:
    if purpose not in {'oauth_code', 'oauth_pkce'}: raise CustodyUnavailable('OAuth credential purpose is invalid')
    return await _seal(value, deepcopy(record), workspace, sender, purpose)


async def open_oauth_secret(value: str, record: dict, workspace: str, sender: str, purpose: str) -> str:
    if purpose not in {'oauth_code', 'oauth_pkce'}: raise CustodyUnavailable('OAuth credential purpose is invalid')
    return await _open(value, deepcopy(record), workspace, sender, purpose)


@dataclass(frozen=True)
class MailboxAccess:
    secret: PreparedSecret
    database: Any = field(repr=False, compare=False)

    async def authorize(self) -> None:
        """Database-only read preflight; this does not claim durable sync HTTP receipts."""
        from outreach.core import suppression
        from outreach.core.dispatch_authority import AuthorityDatabase
        from outreach.core.mailbox_connection import _paid_sender, _control_allowed, _utc, _deadlines_live
        async def check(current):
            fenced = (AuthorityDatabase(current.database, current.session, self.secret.binding_digest)
                if isinstance(current, suppression.SuppressionDatabase) else current)
            row = await fenced.outreach_mailboxes.find_one({'workspace_id': self.secret.workspace_id,
                'sender_account_id': self.secret.sender_id, 'status': 'active'})
            if isinstance(fenced, AuthorityDatabase): fenced.deadlines.clear()
            if (not row or not self.secret.matches(row, self.secret.workspace_id, self.secret.sender_id)
                    or not _control_allowed(self.secret.workspace_id)
                    or not _utc(row.get('token_expires_at')) or _utc(row['token_expires_at']) <= datetime.now(timezone.utc)
                    or not await _paid_sender(fenced, self.secret.workspace_id, self.secret.sender_id)):
                raise CustodyUnavailable('Mailbox authorization changed')
            return ([*fenced.deadlines, row['token_expires_at']] if isinstance(fenced, AuthorityDatabase)
                else [row['token_expires_at']])
        deadlines = await suppression.mutate_suppression(self.database, self.secret.workspace_id, check)
        if not _deadlines_live(deadlines) or not self.secret.policy_matches() or not _control_allowed(self.secret.workspace_id):
            raise CustodyUnavailable('Mailbox authorization expired after commit')
