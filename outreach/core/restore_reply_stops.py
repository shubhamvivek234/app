"""Selected sender-specific LinkedIn negatives; no synthetic reply history.

Manifests contain private recipient identifiers. Origin, outside-backup storage
and completeness are operator responsibilities, not established by the digest.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re
from typing import Any

from bson import ObjectId
from pymongo.read_concern import ReadConcern
from outreach.core import restore_epoch as epoch, suppression
from outreach.core.authorization import canonical_hash
from outreach.core.lead_importer import normalize_linkedin_url
from outreach.core.restore_exclusions import (MAX_BYTES, digest, unique_object, reject_constant,
                                             native_date, text_date, format_date, review_guard)

LIMIT = 100
FIELDS = ('member_urn', 'normalized_url')


def identity(field: str, value: Any) -> None:
    """Only stable supported LinkedIn member identifiers and profile URLs."""
    if field == 'normalized_url':
        from outreach.core.restore_suppressions import identity as canonical_identity
        canonical_identity(field, value)
        return
    if (field != 'member_urn' or not isinstance(value, str) or
            not re.fullmatch(r'urn:li:(?:member|person|fsd_profile|fs_miniProfile):[A-Za-z0-9_-]{1,180}', value)):
        raise ValueError('A supported LinkedIn recipient identity is required')


async def sender_identity(db: Any, workspace: str, sender: str) -> str:
    """Bind the app sender ID to its current stored LinkedIn mapping; never remap."""
    epoch.reference(sender)
    rows = await db.outreach_accounts.find({'workspace_id': workspace, 'id': sender}).limit(2).to_list(length=2)
    if len(rows) != 1 or rows[0].get('is_deleted') or rows[0].get('status') == 'deleted':
        raise ValueError('Exactly one current stored sender identity is required')
    identity('member_urn', rows[0].get('linkedin_urn'))
    return canonical_hash(['linkedin_sender_v1', workspace, sender, rows[0]['linkedin_urn']])


@dataclass(frozen=True)
class Fact:
    sender_id: str
    sender_identity_digest: str
    field: str
    value: str
    blocked_at: datetime
    record_digest: str

    @property
    def key(self) -> str:
        return canonical_hash([self.sender_id, self.field, self.value])

    def document(self) -> dict:
        return {'sender_id': self.sender_id, 'sender_identity_digest': self.sender_identity_digest,
                'field': self.field, 'value': self.value,
                'blocked_at': format_date(self.blocked_at), 'record_digest': self.record_digest}


@dataclass(frozen=True)
class Manifest:
    source_digest: str
    guard_digest: str
    facts: tuple[Fact, ...]

    @property
    def facts_digest(self) -> str:
        return canonical_hash([fact.document() for fact in self.facts])


def parse(raw: bytes) -> Manifest:
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_BYTES:
        raise ValueError('A bounded reply-stop manifest is required')
    try:
        doc = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object, parse_constant=reject_constant)
        if (not isinstance(doc, dict) or set(doc) != {'version', 'workspace_guard_digest', 'facts'}
                or type(doc['version']) is not int or doc['version'] != 1
                or not isinstance(doc['facts'], list) or not 1 <= len(doc['facts']) <= LIMIT):
            raise ValueError('Unsupported reply-stop manifest')
        digest(doc['workspace_guard_digest'])
        facts = []
        for row in doc['facts']:
            if (not isinstance(row, dict) or set(row) != {'sender_id', 'sender_identity_digest', 'field', 'value', 'blocked_at', 'record_digest'}
                    or row['field'] not in FIELDS):
                raise ValueError('Unsupported reply-stop fact')
            identity(row['field'], row['value']); digest(row['record_digest'])
            epoch.reference(row['sender_id']); digest(row['sender_identity_digest'])
            facts.append(Fact(row['sender_id'], row['sender_identity_digest'], row['field'], row['value'], text_date(row['blocked_at']), row['record_digest']))
        if len({fact.key for fact in facts}) != len(facts):
            raise ValueError('Duplicate selected reply-stop facts are unavailable')
        senders = {}
        for fact in facts:
            if senders.setdefault(fact.sender_id, fact.sender_identity_digest) != fact.sender_identity_digest:
                raise ValueError('Selected sender identity changed')
        return Manifest(hashlib.sha256(raw).hexdigest(), doc['workspace_guard_digest'],
                        tuple(sorted(facts, key=lambda fact: fact.key)))
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        raise ValueError('Reply-stop manifest is unavailable or unproven') from exc


async def export_manifest(db: Any, workspace: str, thread_records: list[str],
                          *, workers_drained: bool = False) -> dict:
    """Export selected stored replies, not an atomic/complete or authenticated inventory."""
    epoch.reference(workspace)
    if workers_drained is not True:
        raise ValueError('All source writers and caches must be drained')
    async def require_open():
        guard = await db.outreach_suppression_guards.with_options(read_concern=ReadConcern('majority')).find_one(
            suppression.guard_scope(workspace))
        if guard and guard.get('erasure_state'):
            raise ValueError('Closed workspaces cannot export recipient data')
    await require_open()
    if (not isinstance(thread_records, list) or not 1 <= len(thread_records) <= LIMIT
            or any(not isinstance(ref, str) for ref in thread_records) or len(set(thread_records)) != len(thread_records)):
        raise ValueError('Bounded distinct original thread references are required')
    facts = []
    # Each read uses majority concern; the drain assertion is not a database lock.
    majority = db.with_options(read_concern=ReadConcern('majority'))
    for reference in thread_records:
        epoch.reference(reference)
        ids = [reference]
        if ObjectId.is_valid(reference): ids.append(ObjectId(reference))
        rows = await majority.outreach_inbox_threads.find(
            {'workspace_id': workspace, '_id': {'$in': ids}}).limit(2).to_list(length=2)
        if len(rows) != 1:
            raise ValueError('Exactly one original thread is required')
        row = rows[0]
        if row.get('is_demo') or 'restore_provenance' in row or row.get('has_lead_reply') is not True:
            raise ValueError('An original stored LinkedIn reply is required')
        sender = row.get('account_id'); proof = await sender_identity(majority, workspace, sender)
        identity('member_urn', row.get('lead_urn'))
        messages = row.get('messages')
        if not isinstance(messages, list) or not messages or any(not isinstance(m, dict) for m in messages):
            raise ValueError('Original stored reply evidence is required')
        dates = [native_date(m.get('timestamp')) for m in messages if m.get('sender_type') == 'lead']
        if not dates:
            raise ValueError('A stored native reply timestamp is required')
        date = min(dates)
        record = canonical_hash(['outreach_inbox_threads', type(row['_id']).__name__, str(row['_id'])])
        values = [('member_urn', row['lead_urn'])]
        if row.get('lead_profile_url'):
            url = normalize_linkedin_url(row['lead_profile_url'])
            identity('normalized_url', url); values.append(('normalized_url', url))
        facts.extend(Fact(sender, proof, field, value, date, record).document() for field, value in values)
        if len(facts) > LIMIT:
            raise ValueError('Expanded reply-stop facts exceed capacity')
    document = {'version': 1, 'workspace_guard_digest': suppression.guard_scope(workspace)['_id'], 'facts': facts}
    parse(json.dumps(document, sort_keys=True).encode())
    await require_open()
    return document


def scope(workspace: str, fact: Fact) -> dict:
    return {'_id': canonical_hash(['restore_reply_stop_v1', workspace, fact.sender_id, fact.field, fact.value]),
            'workspace_id': workspace}


async def target_rows(db: Any, workspace: str, fact: Fact) -> list[dict]:
    rows = await db.outreach_reply_stops.find(scope(workspace, fact)).limit(2).to_list(length=2)
    if len(rows) > 1:
        raise ValueError('Duplicate target reply stops require review')
    for row in rows:
        native_date(row.get('created_at'))
        if any(row.get(key) != value for key, value in {
            'channel': 'linkedin', 'sender_id': fact.sender_id, 'sender_identity_digest': fact.sender_identity_digest,
            'field': fact.field, 'value': fact.value, 'restore_provenance': 'selected_reply_stop'}.items()):
            raise ValueError('Restored reply-stop identity changed')
    return rows


async def has_reply_stop(db: Any, workspace: str, sender: str, members: set, urls: set) -> bool:
    """Negative blocks survive later sender identity changes; no positive proof here."""
    identities = []
    if members: identities.append({'field': 'member_urn', 'value': {'$in': sorted(members)}})
    if urls: identities.append({'field': 'normalized_url', 'value': {'$in': sorted(urls)}})
    if not identities: return False
    return bool(await db.outreach_reply_stops.find_one({'workspace_id': workspace, 'sender_id': sender,
                                                       '$or': identities}))


class RestoreReplyStops:
    def __init__(self, db: Any) -> None:
        self.db = db

    async def _view(self, db: Any, workspace: str, manifest: Manifest, captured: tuple[str, str]) -> tuple[dict, epoch.EpochProof]:
        if manifest.guard_digest != suppression.guard_scope(workspace)['_id']:
            raise ValueError('Reply-stop manifest scope differs')
        from outreach.core.erasure import workspace_is_open
        if not await workspace_is_open(db, workspace):
            raise ValueError('Closed workspaces cannot restore recipient data')
        proof = await epoch.require(db, workspace, captured=captured)
        if not proof.digest:
            raise ValueError('A prepared stopped restore epoch is required')
        guard = await db.outreach_suppression_guards.find_one(suppression.guard_scope(workspace))
        sender_proofs = {}
        for fact in manifest.facts:
            if fact.sender_id not in sender_proofs:
                sender_proofs[fact.sender_id] = await sender_identity(db, workspace, fact.sender_id)
            if sender_proofs[fact.sender_id] != fact.sender_identity_digest:
                raise ValueError('Selected sender identity differs')
        rows = [epoch.stable(await target_rows(db, workspace, fact)) for fact in manifest.facts]
        proof.assert_live()
        if not epoch.flags_off(): raise ValueError('Execution flags changed')
        return {'execution_epoch': proof.digest, 'source_digest': manifest.source_digest, 'facts_digest': manifest.facts_digest,
                'guard': review_guard(guard), 'senders': sender_proofs, 'rows': rows}, proof

    async def inspect(self, workspace: str, raw: bytes) -> dict:
        epoch.reference(workspace); manifest = parse(raw)
        view, _ = await self._view(self.db, workspace, manifest, epoch.policy())
        return {'workspace_id': workspace, 'digest': canonical_hash(view), 'source_digest': manifest.source_digest,
                'selected_fact_count': len(manifest.facts), 'missing_fact_count': sum(not rows for rows in view['rows']),
                'activation_allowed': False, 'reply_history_restored': False}

    async def apply(self, workspace: str, raw: bytes, *, operator: str, evidence_digest: str,
                    source_digest: str, review_digest: str, workers_drained: bool = False) -> dict:
        epoch.reference(workspace); epoch.reference(operator)
        for value in (evidence_digest, source_digest, review_digest): digest(value)
        manifest = parse(raw)
        if workers_drained is not True or not epoch.flags_off() or manifest.source_digest != source_digest:
            raise ValueError('Exact source, disabled flags and all-writer/cache drain are required')
        captured = epoch.policy()
        async def transaction(current):
            from outreach.core.dispatch_authority import AuthorityDatabase
            db = (AuthorityDatabase(current.database, current.session, 'restore_reply_stop_import')
                  if isinstance(current, suppression.SuppressionDatabase) else current)
            view, proof = await self._view(db, workspace, manifest, captured)
            journal_scope = {'_id': canonical_hash(['restore_reply_stops_v1', workspace, proof.digest, source_digest]),
                             'workspace_id': workspace, 'execution_epoch': proof.digest, 'source_digest': source_digest}
            saved = await db.outreach_restore_reply_stops.find_one(journal_scope)
            review = {'operator_digest': canonical_hash(operator), 'evidence_digest': evidence_digest,
                      'review_digest': review_digest, 'facts_digest': manifest.facts_digest}
            result = {'applied': True, 'activation_allowed': False, 'reply_history_restored': False,
                      'selected_fact_count': len(manifest.facts)}
            if saved:
                if any(saved.get(key) != value for key, value in review.items()) or not all(view['rows']):
                    raise ValueError('Original reply-stop review or current blocks are unavailable')
            else:
                if canonical_hash(view) != review_digest:
                    raise ValueError('Reply-stop inspection changed')
                for fact in manifest.facts:
                    values = {'created_at': fact.blocked_at, 'restore_provenance': 'selected_reply_stop',
                              'channel': 'linkedin', 'sender_id': fact.sender_id,
                              'sender_identity_digest': fact.sender_identity_digest,
                              'field': fact.field, 'value': fact.value}
                    await current.outreach_reply_stops.update_one(scope(workspace, fact), {'$setOnInsert': values}, upsert=True)
                after, _ = await self._view(db, workspace, manifest, captured)
                if not all(after['rows']): raise ValueError('Selected reply-stop facts could not be retained')
                await current.outreach_restore_reply_stops.insert_one({**journal_scope, **review,
                    'version': 1, 'fact_count': len(manifest.facts), 'applied_at': epoch.now(),
                    'activation_allowed': False, 'reply_history_restored': False})
            proof.assert_live()
            if not epoch.flags_off(): raise ValueError('Execution flags changed')
            return {**result, 'recovered': bool(saved)}
        return await suppression.mutate_suppression(self.db, workspace, transaction)
