"""Private drained mailbox/Hunter conversion; no provider calls or execution grant."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)
from datetime import datetime, timezone
import os
from typing import Any
from outreach.core import suppression
from outreach.core.authorization import canonical_hash
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.credential_migration import CredentialMigration, _stable
from outreach.core.dispatch_authority import AuthorityDatabase
from outreach.core.paid_access import live_actions_enabled
from outreach.core.provider_custody import material_digest, seal_mailbox_tokens, seal_finder_key
from outreach.core.session_custody import custody_mode
from utils.encryption import decrypt_strict

class ProviderCredentialMigration:
    def __init__(self, db: Any) -> None:
        self.db = db

    async def _snapshot(self, current: Any, workspace: str, kind: str, sender: str | None) -> dict:
        if kind not in {'mailbox', 'finder'} or (kind == 'mailbox' and not sender) or (kind == 'finder' and sender is not None):
            raise CustodyUnavailable('Exact provider custody scope is required')
        accounts = await current.outreach_accounts.find({'workspace_id': workspace}).sort('id', 1).limit(6).to_list(length=6)
        senders = [row.get('id') for row in accounts]
        snapshots = [await CredentialMigration(self.db)._snapshot(current, workspace, item) for item in senders if isinstance(item, str) and item]
        mailboxes = await current.outreach_mailboxes.find({'workspace_id': workspace}).sort('sender_account_id', 1).limit(6).to_list(length=6)
        resource = (next((row for row in mailboxes if row.get('sender_account_id') == sender), None) if kind == 'mailbox'
            else await current.outreach_hunter_credentials.find_one({'workspace_id': workspace}))
        pending = await current.outreach_mailbox_connection_jobs.find_one({'workspace_id': workspace,
            'status': {'$in': ['pending', 'queued', 'running', 'review_required']}})
        state = await current.outreach_mailbox_oauth_states.find_one({'workspace_id': workspace})
        sync_job = await current.outreach_mailbox_sync_jobs.find_one({'workspace_id': workspace, 'status': {'$in': ['queued', 'running']}})
        physical = await current.outreach_physical_requests.find_one({'workspace_id': workspace,
            'status': {'$in': ['preparing', 'in_flight', 'unknown_outcome']}})
        email = await current.outreach_email_operations.find_one({'workspace_id': workspace,
            'status': {'$in': ['dispatching', 'uncertain', 'accepted']}})
        finder = await current.outreach_email_discoveries.find_one({'workspace_id': workspace,
            'status': {'$in': ['dispatching', 'uncertain']}})
        return {'senders': senders, 'senders_state': snapshots, 'mailboxes': [_stable(row) for row in mailboxes],
            'resource': _stable(resource), 'pending': _stable(pending), 'state': _stable(state),
            'physical': _stable(physical), 'email': _stable(email), 'finder': _stable(finder), 'sync_job': _stable(sync_job),
            'mode': custody_mode(), 'environment': os.getenv('OUTREACH_CUSTODY_ENVIRONMENT_ID', '')}

    @staticmethod
    def _blockers(snapshot: dict, kind: str, sender: str | None) -> list[str]:
        blockers = []
        senders = snapshot['senders']
        if (len(senders) > 5 or len(snapshot['mailboxes']) > 5 or len(set(senders)) != len(senders)
                or len(snapshot['senders_state']) != len(senders)):
            blockers.append('pilot_capacity_or_identity_gap')
        if kind == 'mailbox' and sender not in senders: blockers.append('sender_missing')
        for row in snapshot['senders_state']:
            blockers.extend(CredentialMigration._blockers(row))
        for row in snapshot['mailboxes']:
            if any(row.get(name) for name in ('refresh_state', 'refresh_lease_nonce', 'refresh_lease_until', 'sync_lease_nonce', 'sync_lease_id', 'sync_lease_until')):
                blockers.append('mailbox_work_held')
        if not snapshot['resource']: blockers.append('credential_missing')
        blockers.extend(name + '_unfinished' for name in ('pending', 'state', 'physical', 'email', 'finder', 'sync_job') if snapshot[name])
        return sorted(set(blockers))

    async def inspect(self, workspace: str, kind: str, sender: str | None = None) -> dict:
        snapshot = await self._snapshot(self.db, workspace, kind, sender)
        return {'workspace_id': workspace, 'kind': kind, 'sender_id': sender, 'digest': canonical_hash(snapshot),
            'blockers': self._blockers(snapshot, kind, sender)}

    async def migrate(self, workspace: str, kind: str, sender: str | None, operator: str, expected_digest: str,
            *, workers_drained: bool = False) -> dict:
        if (workers_drained is not True or not operator or not operator.strip() or not expected_digest
                or live_actions_enabled() or custody_mode() != 'kms_v1'):
            raise CustodyUnavailable('Stopped execution and identified drained provider migration are required')
        key = canonical_hash(['provider-custody-v1', workspace, kind, sender, expected_digest])
        scope = {'_id': key, 'workspace_id': workspace}
        collection = 'outreach_mailboxes' if kind == 'mailbox' else 'outreach_hunter_credentials'
        resource_scope = {'workspace_id': workspace, **({'sender_account_id': sender} if kind == 'mailbox' else {})}
        async def saved_result(current: Any, receipt: dict) -> dict:
            row = await getattr(current, collection).find_one(resource_scope)
            return {'status': 'completed', 'migration_id': key,
                'current_matches': bool(row and material_digest(row, kind) == receipt['after_digest'])}
        receipt = await self.db.outreach_credential_migrations.find_one(scope)
        if receipt: return await saved_result(self.db, receipt)
        async def verify(current: Any) -> dict:
            fenced = AuthorityDatabase(current.database, current.session, key) if isinstance(current, suppression.SuppressionDatabase) else current
            snapshot = await self._snapshot(fenced, workspace, kind, sender)
            if canonical_hash(snapshot) != expected_digest or self._blockers(snapshot, kind, sender):
                raise CustodyUnavailable('Drained provider inspection changed')
            return snapshot
        snapshot = await suppression.mutate_suppression(self.db, workspace, verify)
        row = snapshot['resource']
        try:
            raw = ({'access_token': decrypt_strict(row.get('access_token_enc') or ''),
                'refresh_token': decrypt_strict(row.get('refresh_token_enc') or '')} if kind == 'mailbox'
                else decrypt_strict(row.get('api_key_enc') or ''))
        except (ValueError, OSError):
            raise CustodyUnavailable('Legacy provider credentials require reconnection or separate provenance review') from None
        encrypted = (await seal_mailbox_tokens(raw, row, workspace, sender, generation=row.get('custody_generation')) if kind == 'mailbox'
            else await seal_finder_key(raw, workspace, generation=row.get('credential_generation')))
        del raw
        async def apply(current: Any) -> dict:
            existing = await current.outreach_credential_migrations.find_one(scope)
            if existing: return await saved_result(current, existing)
            fresh = await verify(current)
            if custody_mode() != 'kms_v1' or live_actions_enabled(): raise CustodyUnavailable('Custody configuration changed')
            changed = await getattr(current, collection).update_one(resource_scope, {'$set': encrypted})
            if changed.matched_count != 1: raise CustodyUnavailable('Provider custody owner changed')
            await current.outreach_credential_migrations.insert_one({**scope, 'kind': kind, 'sender_id': sender,
                'status': 'completed', 'operator': operator.strip(), 'workers_drained': True, 'before_digest': expected_digest,
                'after_digest': material_digest({**fresh['resource'], **encrypted}, kind), 'at': datetime.now(timezone.utc),
                'target_environment_digest': canonical_hash(snapshot['environment'])})
            return {'status': 'completed', 'migration_id': key, 'current_matches': True}
        return await suppression.mutate_suppression(self.db, workspace, apply)
