"""Outside-backup epoch admission and private stopped restore preparation.

This slice intentionally has no restore activation path. Installed epochs hold
positive execution even when configuration is removed; receipt/erasure controls
remain separate. A fleet drain and external epoch rotation are operator duties.
"""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

from dataclasses import dataclass
from datetime import datetime, timezone
import os
import re
from typing import Any

from outreach.core.authorization import canonical_hash
from outreach.core import suppression

HEX = re.compile(r'[a-f0-9]{64}\Z')
LIMIT = 100
FLAGS = ('OUTREACH_LIVE_ACTIONS_ENABLED', 'OUTREACH_INTEGRATIONS_ENABLED',
         'OUTREACH_VOICE_STUDIO_ENABLED', 'OUTREACH_VOICE_PREPARATION_ENABLED',
         'OUTREACH_HEALTH_MONITOR_ENABLED')
# Every inspected row contributes to the exact private review, including unknown
# and received jobs that must not be rewritten as cancelled or not submitted.
COLLECTIONS = ('outreach_sender_execution', 'outreach_execution_permissions',
    'outreach_campaigns', 'outreach_health_controls', 'outreach_mailboxes',
    'outreach_voices', 'outreach_webhooks', 'outreach_integrations',
    'outreach_manual_actions', 'outreach_sequence_jobs', 'outreach_import_jobs',
    'outreach_inbox_jobs', 'outreach_connection_jobs', 'outreach_mailbox_connection_jobs',
    'outreach_mailbox_oauth_states', 'outreach_mailbox_sync_jobs',
    'outreach_voice_preparation_jobs', 'outreach_voice_studio_jobs',
    'outreach_webhook_deliveries')
QUEUED = frozenset({'queued', 'pending', 'retry', 'awaiting_approval'})


class EpochUnavailable(ValueError):
    """Restore admission or positive activation is unavailable."""


def now() -> datetime:
    value = datetime.now(timezone.utc)
    return value.replace(microsecond=value.microsecond // 1000 * 1000)


def policy() -> tuple[str, str]:
    return (os.getenv('OUTREACH_RESTORE_FENCING_ENABLED', 'false'),
            os.getenv('OUTREACH_EXECUTION_EPOCH', ''))


def flags_off() -> bool:
    # Malformed settings cannot establish a stopped-fleet review.
    return all(os.getenv(name, 'false') == 'false' for name in FLAGS)


def reference(value: str) -> None:
    if (not isinstance(value, str) or not 1 <= len(value) <= 256
            or value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError('A bounded operator or workspace reference is required')


def stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: stable(item) for key, item in value.items() if key != 'dispatch_fence_revision'}
    if isinstance(value, (list, tuple)):
        return [stable(item) for item in value]
    if isinstance(value, datetime):
        value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return value.replace(microsecond=value.microsecond // 1000 * 1000)
    return value


def root_scope(workspace: str) -> dict:
    return {'_id': canonical_hash(['execution_epoch_root', workspace]), 'workspace_id': workspace, 'kind': 'root'}


def journal_scope(workspace: str, digest: str) -> dict:
    return {'_id': canonical_hash(['execution_epoch_journal', workspace, digest]),
            'workspace_id': workspace, 'kind': 'journal', 'execution_epoch': digest}


@dataclass(frozen=True)
class EpochProof:
    captured: tuple[str, str]
    digest: str | None = None

    def live(self) -> bool:
        if policy() != self.captured:
            return False
        flag, anchor = self.captured
        return ((flag == 'false' and anchor == '' and self.digest is None)
                or (flag == 'true' and bool(HEX.fullmatch(anchor))
                    and self.digest == canonical_hash(['execution_epoch_v1', anchor])))

    def assert_live(self) -> None:
        if not self.live():
            raise EpochUnavailable('Restore epoch configuration changed')

    def fields(self) -> dict:
        return {'execution_epoch': self.digest} if self.digest else {}


async def require(db: Any, workspace: str, *, record: dict | None = None,
                  captured: tuple[str, str] | None = None) -> EpochProof:
    """Prove original epoch admission, never synthesize a stamp on old work."""
    reference(workspace)
    captured = policy() if captured is None else captured
    root = await db.outreach_execution_epochs.find_one(root_scope(workspace))
    flag, anchor = captured
    if flag == 'false' and anchor == '' and root is None:
        proof = EpochProof(captured)
        if record is not None and record.get('execution_epoch') is not None:
            raise EpochUnavailable('Original execution epoch is unavailable')
    else:
        if flag != 'true' or not HEX.fullmatch(anchor):
            raise EpochUnavailable('Restore epoch configuration is unavailable')
        digest = canonical_hash(['execution_epoch_v1', anchor])
        scope = journal_scope(workspace, digest)
        journal = await db.outreach_execution_epochs.find_one(scope)
        if (not isinstance(root, dict) or root.get('version') != 1
                or root.get('execution_epoch') != digest or root.get('status') != 'prepared_stopped'
                or root.get('journal_id') != scope['_id'] or not isinstance(journal, dict)
                or journal.get('version') != 1 or journal.get('after_digest') != canonical_hash(stable(root))):
            raise EpochUnavailable('Restore epoch has not been prepared')
        if record is not None and record.get('execution_epoch') != digest:
            raise EpochUnavailable('Original execution epoch is unavailable')
        proof = EpochProof(captured, digest)
    if not proof.live():
        raise EpochUnavailable('Restore epoch configuration changed')
    return proof


async def positive(db: Any, workspace: str, *, captured: tuple[str, str] | None = None) -> EpochProof:
    """Positive provider/installation work stays held until an activation slice.

    True legacy deployments remain compatible. An anchor, installed root, bad
    configuration or restored/missing admission always fails closed.
    """
    proof = await require(db, workspace, captured=captured)
    if proof.digest:
        raise EpochUnavailable('Restored execution requires reconciliation and explicit activation')
    return proof


class RestoreEpoch:
    def __init__(self, db: Any) -> None:
        self.db = db

    async def _snapshot(self, db: Any, workspace: str) -> dict:
        from outreach.core.erasure import workspace_is_open
        view = {'workspace_id': workspace, 'policy_digest': canonical_hash(policy()),
                'flags_off': flags_off(), 'workspace_open': await workspace_is_open(db, workspace),
                'root': stable(await db.outreach_execution_epochs.find_one(root_scope(workspace)))}
        for name in COLLECTIONS:
            view[name] = stable(await getattr(db, name).find({'workspace_id': workspace})
                .sort('_id', 1).limit(LIMIT + 1).to_list(length=LIMIT + 1))
        return view

    @staticmethod
    def _blockers(view: dict) -> list[str]:
        reasons = []
        if not view['flags_off']: reasons.append('execution_flags_enabled_or_malformed')
        if not view['workspace_open']: reasons.append('workspace_closed')
        root = view['root']
        if root is not None and (not isinstance(root, dict) or set(root) != {
                '_id', 'workspace_id', 'kind', 'version', 'execution_epoch', 'status', 'journal_id', 'prepared_at'}):
            reasons.append('original_root_shape_unproven')
        for name in COLLECTIONS:
            if len(view[name]) > LIMIT: reasons.append(name + '_capacity_exceeded')
            if any('_id' not in row for row in view[name]): reasons.append(name + '_identity_unavailable')
        return reasons

    async def inspect(self, workspace: str) -> dict:
        reference(workspace)
        view = await self._snapshot(self.db, workspace)
        return {'workspace_id': workspace, 'digest': canonical_hash(view),
            'blockers': self._blockers(view), 'activation_allowed': False,
            'counts': {name: len(view[name]) for name in COLLECTIONS},
            'root_epoch': (view['root'] or {}).get('execution_epoch')}

    async def prepare(self, workspace: str, operator: str, evidence_digest: str, review_digest: str,
                      *, workers_drained: bool = False) -> dict:
        reference(workspace); reference(operator)
        captured = policy()
        if (workers_drained is not True or not flags_off() or captured[0] != 'true'
                or not HEX.fullmatch(captured[1]) or not isinstance(evidence_digest, str)
                or not HEX.fullmatch(evidence_digest) or not isinstance(review_digest, str)
                or not HEX.fullmatch(review_digest)):
            raise ValueError('Exact review, external epoch, disabled flags and all-writer/cache drain are required')
        digest = canonical_hash(['execution_epoch_v1', captured[1]])
        journal_id = journal_scope(workspace, digest)

        async def apply(current):
            from outreach.core.dispatch_authority import AuthorityDatabase
            db = (AuthorityDatabase(current.database, current.session, 'restore_epoch_prepare')
                  if isinstance(current, suppression.SuppressionDatabase) else current)
            saved = await db.outreach_execution_epochs.find_one(journal_id)
            if saved:
                if (saved.get('operator') != operator or saved.get('evidence_digest') != evidence_digest
                        or saved.get('review_digest') != review_digest):
                    raise ValueError('Restore epoch was already reviewed with different evidence')
                root = await db.outreach_execution_epochs.find_one(root_scope(workspace))
                matching = bool(root and root.get('execution_epoch') == digest
                                and saved.get('after_digest') == canonical_hash(stable(root)))
                if policy() != captured or not flags_off():
                    raise ValueError('Restore configuration changed')
                return {'prepared': matching, 'execution_epoch': digest, 'activation_allowed': False, 'recovered': True}
            view = await self._snapshot(db, workspace)
            if self._blockers(view) or canonical_hash(view) != review_digest:
                raise ValueError('Restore review changed or exceeds the bounded pilot capacity')
            stamp = now()
            # Stops and journal/root installation share the same majority transaction.
            # No owner, receipt, credential, budget or provider resource is released.
            for name in COLLECTIONS:
                for row in view[name]:
                    update = self._stop(name, row, stamp)
                    if update:
                        changed = await getattr(db, name).update_one({'_id': row['_id'], 'workspace_id': workspace}, update)
                        if changed.matched_count != 1:
                            raise ValueError('Restore stop authority changed')
            root = {**root_scope(workspace), 'version': 1, 'execution_epoch': digest,
                    'status': 'prepared_stopped', 'journal_id': journal_id['_id'], 'prepared_at': stamp}
            await current.outreach_execution_epochs.update_one(root_scope(workspace), {'$set': root}, upsert=True)
            await current.outreach_execution_epochs.insert_one({**journal_id, 'version': 1,
                'operator': operator, 'evidence_digest': evidence_digest, 'review_digest': review_digest,
                'before_digest': canonical_hash(view['root']), 'after_digest': canonical_hash(stable(root)),
                'prepared_at': stamp, 'counts': {name: len(view[name]) for name in COLLECTIONS}})
            if policy() != captured or not flags_off():
                raise ValueError('Restore configuration changed')
            return {'prepared': True, 'execution_epoch': digest, 'activation_allowed': False, 'recovered': False}
        return await suppression.mutate_suppression(self.db, workspace, apply)

    @staticmethod
    def _stop(name: str, row: dict, stamp: datetime) -> dict | None:
        if name == 'outreach_sender_execution':
            return {'$set': {'permission.latched': True, 'permission.expires_at': stamp,
                'permission.stop_reason': 'restore_epoch_prepared'}, '$inc': {'permission_revision': 1}}
        if name == 'outreach_execution_permissions':
            return {'$set': {'latched': True, 'expires_at': stamp, 'stop_reason': 'restore_epoch_prepared'}}
        if name == 'outreach_campaigns' and row.get('status') in {'active', 'warming_up'}:
            return {'$set': {'status': 'paused', 'auto_launch_enabled': False,
                'pause_reason': 'restore_epoch_prepared'}, '$inc': {'authorization_revision': 1}}
        if name == 'outreach_health_controls' and row.get('status') == 'armed':
            return {'$set': {'status': 'stopped', 'stopped_at': stamp, 'stop_reason': 'restore_epoch_prepared'}}
        if name == 'outreach_mailboxes' and row.get('status') == 'active':
            return {'$set': {'status': 'disconnected', 'restore_review_required': True}}
        if name == 'outreach_voices':
            return {'$set': {'studio_review_required': True, 'restore_review_required': True}, '$inc': {'revision': 1}}
        if name in {'outreach_webhooks', 'outreach_integrations'}:
            return {'$set': {'active': False, 'restore_review_required': True}}
        if name.endswith('_jobs') or name == 'outreach_manual_actions' or name == 'outreach_webhook_deliveries':
            evidence = ('owner', 'owner_token', 'lease_id', 'receipt', 'possible_at', 'physical_request_token',
                        'generation_started_at', 'exchange_possible_at', 'exchange_submitted_at', 'submission_started_at',
                        'submitted_at', 'receipt_digest', 'attempt', 'generation_count', 'installation_receipt')
            stages = row.get('stages') or {}
            never_submitted = (isinstance(stages, dict) and all(
                isinstance(stage, dict) and stage.get('status') == 'pending'
                and not any(stage.get(key) is not None for key in evidence) for stage in stages.values())
                and row.get('exchange_state') in {None, 'pending'}
                and not any(row.get(key) is not None for key in evidence))
            if row.get('status') in QUEUED and never_submitted:
                return {'$set': {'status': 'cancelled', 'cancelled_at': stamp, 'stop_reason': 'restore_epoch_prepared'}}
        return None
