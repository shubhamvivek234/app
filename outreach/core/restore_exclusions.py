"""Restore selected deletion denies; never activate, purge or certify completeness.

Source authenticity and storage outside backups are operator responsibilities.
The byte digest proves integrity, not origin. Global UID tombstones intentionally
use digest identity rather than a tenant filter, with the exact import session.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any

from pymongo.read_concern import ReadConcern
from outreach.core import restore_epoch as epoch, suppression
from outreach.core.authorization import canonical_hash

MAX_BYTES = 65536
MAX_IDENTITIES = 100
DATE = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z\Z')
ORIGINAL_STATES = frozenset({'stopped', 'purging', 'erased'})


def native_date(value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError('Original deletion time is unavailable')
    result = epoch.stable(value)
    if result.year < 1970 or result > epoch.now():
        raise ValueError('Original deletion time is unavailable')
    return result


def text_date(value: Any) -> datetime:
    if not isinstance(value, str) or not DATE.fullmatch(value):
        raise ValueError('Original UTC millisecond deletion time is required')
    return native_date(datetime.strptime(value, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc))


def format_date(value: Any) -> str:
    return native_date(value).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def digest(value: Any) -> None:
    if not isinstance(value, str) or not epoch.HEX.fullmatch(value):
        raise ValueError('A SHA-256 digest is required')


def unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate source fields are unavailable')
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise ValueError('Nonfinite source values are unavailable')


@dataclass(frozen=True)
class Manifest:
    source_digest: str
    guard_digest: str
    deletion_state: str
    requested_at: datetime
    identities: tuple[tuple[str, datetime], ...]

    @property
    def identity_set_digest(self) -> str:
        return canonical_hash([identity for identity, _ in self.identities])

    @property
    def facts_digest(self) -> str:
        return canonical_hash([self.guard_digest, self.deletion_state, self.requested_at, self.identities])


def parse(raw: bytes) -> Manifest:
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_BYTES:
        raise ValueError('A bounded deletion manifest is required')
    try:
        doc = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object, parse_constant=reject_constant)
        if (not isinstance(doc, dict) or set(doc) != {'version', 'workspace_guard_digest',
                'deletion_state', 'requested_at', 'identities'} or type(doc['version']) is not int
                or doc['version'] != 1 or doc['deletion_state'] not in ORIGINAL_STATES
                or not isinstance(doc['identities'], list) or not 1 <= len(doc['identities']) <= MAX_IDENTITIES):
            raise ValueError('Unsupported deletion manifest')
        digest(doc['workspace_guard_digest'])
        requested = text_date(doc['requested_at'])
        identities = []
        for row in doc['identities']:
            if not isinstance(row, dict) or set(row) != {'identity_digest', 'requested_at'}:
                raise ValueError('Unsupported identity exclusion')
            digest(row['identity_digest'])
            identities.append((row['identity_digest'], text_date(row['requested_at'])))
        if len({identity for identity, _ in identities}) != len(identities):
            raise ValueError('Duplicate identity exclusions are unavailable')
        return Manifest(hashlib.sha256(raw).hexdigest(), doc['workspace_guard_digest'],
                        doc['deletion_state'], requested, tuple(sorted(identities)))
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        raise ValueError('Deletion manifest is unavailable or unproven') from exc


async def export_manifest(db: Any, workspace: str, identities: list[str]) -> dict:
    """Export only selected, already-retained majority-visible negative facts."""
    epoch.reference(workspace)
    if not isinstance(identities, list) or not 1 <= len(identities) <= MAX_IDENTITIES:
        raise ValueError('Bounded selected identity digests are required')
    for identity in identities:
        digest(identity)
    if len(set(identities)) != len(identities):
        raise ValueError('Distinct selected identity digests are required')
    guard = await db.outreach_suppression_guards.with_options(read_concern=ReadConcern('majority')).find_one(
        suppression.guard_scope(workspace))
    if not guard or guard.get('erasure_state') not in ORIGINAL_STATES:
        raise ValueError('An original workspace deletion exclusion is required')
    rows = await db.account_erasure_tombstones.with_options(read_concern=ReadConcern('majority')).find(
        {'_id': {'$in': identities}}).sort('_id', 1).limit(MAX_IDENTITIES + 1).to_list(length=MAX_IDENTITIES + 1)
    if {row['_id'] for row in rows} != set(identities) or len(rows) != len(identities):
        raise ValueError('All selected original identity exclusions are required')
    return {'version': 1, 'workspace_guard_digest': suppression.guard_scope(workspace)['_id'],
            'deletion_state': guard['erasure_state'], 'requested_at': format_date(guard.get('erasure_requested_at')),
            'identities': [{'identity_digest': row['_id'], 'requested_at': format_date(row.get('requested_at'))}
                           for row in rows]}


def raw_database(db: Any) -> tuple[Any, dict]:
    from outreach.core.dispatch_authority import AuthorityDatabase
    if isinstance(db, (suppression.SuppressionDatabase, AuthorityDatabase)):
        return db.database, {'session': db.session}
    return db, {}


def review_guard(row: dict | None) -> dict | None:
    if row is None:
        return None
    return epoch.stable({key: value for key, value in row.items() if key not in {'revision', 'updated_at'}})


class RestoreExclusions:
    def __init__(self, db: Any) -> None:
        self.db = db

    async def _view(self, db: Any, workspace: str, manifest: Manifest,
                    captured: tuple[str, str]) -> tuple[dict, epoch.EpochProof]:
        if manifest.guard_digest != suppression.guard_scope(workspace)['_id']:
            raise ValueError('Deletion manifest scope differs from the target workspace')
        proof = await epoch.require(db, workspace, captured=captured)
        if not proof.digest:
            raise ValueError('A prepared stopped restore epoch is required')
        raw, options = raw_database(db)
        guard = await db.outreach_suppression_guards.find_one(suppression.guard_scope(workspace))
        rows = await raw.account_erasure_tombstones.find({'_id': {'$in': [i for i, _ in manifest.identities]}},
            **options).sort('_id', 1).limit(MAX_IDENTITIES + 1).to_list(length=MAX_IDENTITIES + 1)
        for row in rows:
            native_date(row.get('requested_at'))
        proof.assert_live()
        if not epoch.flags_off():
            raise ValueError('Execution flags changed')
        return {'execution_epoch': proof.digest, 'source_digest': manifest.source_digest,
                'identity_set_digest': manifest.identity_set_digest, 'facts_digest': manifest.facts_digest,
                'guard': review_guard(guard), 'identities': epoch.stable(rows)}, proof

    async def inspect(self, workspace: str, raw: bytes) -> dict:
        epoch.reference(workspace)
        manifest = parse(raw)
        view, _ = await self._view(self.db, workspace, manifest, epoch.policy())
        return {'workspace_id': workspace, 'digest': canonical_hash(view), 'source_digest': manifest.source_digest,
                'selected_identity_count': len(manifest.identities),
                'missing_identity_count': len(manifest.identities) - len(view['identities']),
                'workspace_closed': bool((view['guard'] or {}).get('erasure_state')),
                'activation_allowed': False, 'purged': False}

    async def apply(self, workspace: str, raw: bytes, *, operator: str, evidence_digest: str,
                    source_digest: str, review_digest: str, workers_drained: bool = False) -> dict:
        epoch.reference(workspace); epoch.reference(operator)
        for value in (evidence_digest, source_digest, review_digest):
            digest(value)
        manifest = parse(raw)
        if workers_drained is not True or not epoch.flags_off() or manifest.source_digest != source_digest:
            raise ValueError('Exact source, disabled flags and all-writer/cache drain are required')
        captured = epoch.policy()
        async def apply_transaction(current):
            from outreach.core.dispatch_authority import AuthorityDatabase
            db = (AuthorityDatabase(current.database, current.session, 'restore_exclusion_import')
                  if isinstance(current, suppression.SuppressionDatabase) else current)
            view, proof = await self._view(db, workspace, manifest, captured)
            scope = {'_id': canonical_hash(['restore_exclusions_v1', workspace, proof.digest, source_digest]),
                     'workspace_id': workspace, 'execution_epoch': proof.digest, 'source_digest': source_digest}
            saved = await db.outreach_restore_exclusions.find_one(scope)
            result = {'applied': True, 'activation_allowed': False, 'purged': False,
                      'selected_identity_count': len(manifest.identities)}
            if saved:
                if (saved.get('operator_digest') != canonical_hash(operator) or saved.get('evidence_digest') != evidence_digest
                        or saved.get('review_digest') != review_digest or saved.get('identity_set_digest') != manifest.identity_set_digest
                        or saved.get('facts_digest') != manifest.facts_digest):
                    raise ValueError('Original restore exclusion review differs')
                if not (view['guard'] or {}).get('erasure_state') or len(view['identities']) != len(manifest.identities):
                    raise ValueError('Saved exclusions are no longer present; keep restore stopped')
                proof.assert_live()
                if not epoch.flags_off():
                    raise ValueError('Execution flags changed')
                return {**result, 'recovered': True}
            if canonical_hash(view) != review_digest:
                raise ValueError('Restore exclusion inspection changed')
            raw_db, options = raw_database(current)
            for identity, requested in manifest.identities:
                await raw_db.account_erasure_tombstones.update_one({'_id': identity},
                    {'$setOnInsert': {'requested_at': requested}}, upsert=True, **options)
            if not (view['guard'] or {}).get('erasure_state'):
                await current.outreach_suppression_guards.update_one(suppression.guard_scope(workspace), {'$set': {
                    'erasure_state': 'restore_excluded', 'erasure_requested_at': manifest.requested_at}})
            after, _ = await self._view(db, workspace, manifest, captured)
            if not (after['guard'] or {}).get('erasure_state') or len(after['identities']) != len(manifest.identities):
                raise ValueError('Deletion exclusions could not be retained')
            await current.outreach_restore_exclusions.insert_one({**scope, 'version': 1,
                'operator_digest': canonical_hash(operator), 'evidence_digest': evidence_digest,
                'review_digest': review_digest, 'identity_set_digest': manifest.identity_set_digest,
                'facts_digest': manifest.facts_digest, 'identity_count': len(manifest.identities),
                'applied_at': epoch.now(), 'activation_allowed': False, 'purged': False})
            proof.assert_live()
            if not epoch.flags_off():
                raise ValueError('Execution flags changed')
            return {**result, 'recovered': False}
        from outreach.core.erasure import _control
        return await _control(self.db, workspace, apply_transaction)
