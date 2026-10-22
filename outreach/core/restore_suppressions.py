"""Selected original recipient negatives; no activation or synthetic reply history.

Manifests contain private recipient identifiers. Origin, outside-backup storage
and completeness are operator responsibilities, not established by the digest.
"""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

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
from outreach.core.email_finder import normalize_email
from outreach.core.lead_importer import normalize_linkedin_url
from outreach.core.restore_exclusions import (MAX_BYTES, digest, unique_object, reject_constant,
                                             native_date, text_date, format_date, review_guard)

LIMIT = 100
FIELDS = ('normalized_url', 'vanity_name', 'member_urn', 'sales_lead_urn', 'email')
COLLECTIONS = {'dnc': 'outreach_do_not_contact', 'email': 'outreach_email_suppressions'}


def identity(field: str, value: Any) -> None:
    """Accept only supported canonical identities, never arbitrary source fields."""
    if not isinstance(value, str) or not 1 <= len(value) <= 254:
        raise ValueError('A bounded canonical recipient identity is required')
    valid = False
    if field == 'email': valid = normalize_email(value) == value
    if field == 'normalized_url': valid = normalize_linkedin_url(value) == value
    if field == 'vanity_name': valid = bool(re.fullmatch(r'[a-z0-9._-]{1,100}', value)) and value not in {'.', '..'}
    if field == 'member_urn': valid = bool(re.fullmatch(r'urn:li:(?:member|person):[A-Za-z0-9_-]{1,180}', value))
    if field == 'sales_lead_urn':
        valid = bool(re.fullmatch(r'(?:urn:li:(?:fs_salesProfile|salesProfile):)?[A-Za-z0-9_-]{1,180}(?:,[A-Za-z0-9_-]+){0,2}', value))
    if not valid:
        raise ValueError('Recipient identity is unproven or unsupported')


@dataclass(frozen=True)
class Fact:
    kind: str
    field: str
    value: str
    blocked_at: datetime
    record_digest: str

    @property
    def key(self) -> str:
        return canonical_hash([self.kind, self.field, self.value])

    def document(self) -> dict:
        return {'kind': self.kind, 'field': self.field, 'value': self.value,
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
        raise ValueError('A bounded suppression manifest is required')
    try:
        doc = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object, parse_constant=reject_constant)
        if (not isinstance(doc, dict) or set(doc) != {'version', 'workspace_guard_digest', 'facts'}
                or type(doc['version']) is not int or doc['version'] != 1
                or not isinstance(doc['facts'], list) or not 1 <= len(doc['facts']) <= LIMIT):
            raise ValueError('Unsupported suppression manifest')
        digest(doc['workspace_guard_digest'])
        facts = []
        for row in doc['facts']:
            if (not isinstance(row, dict) or set(row) != {'kind', 'field', 'value', 'blocked_at', 'record_digest'}
                    or row['kind'] not in COLLECTIONS or row['field'] not in FIELDS
                    or row['kind'] == 'email' and row['field'] != 'email'):
                raise ValueError('Unsupported suppression fact')
            identity(row['field'], row['value']); digest(row['record_digest'])
            facts.append(Fact(row['kind'], row['field'], row['value'], text_date(row['blocked_at']), row['record_digest']))
        if len({fact.key for fact in facts}) != len(facts):
            raise ValueError('Duplicate selected suppression facts are unavailable')
        return Manifest(hashlib.sha256(raw).hexdigest(), doc['workspace_guard_digest'],
                        tuple(sorted(facts, key=lambda fact: fact.key)))
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        raise ValueError('Suppression manifest is unavailable or unproven') from exc


async def export_manifest(db: Any, workspace: str, dnc_records: list[str], email_records: list[str],
                          *, workers_drained: bool = False) -> dict:
    """Read explicitly selected original rows, not a complete or atomic inventory."""
    epoch.reference(workspace)
    if workers_drained is not True:
        raise ValueError('All source writers and caches must be drained')
    async def require_open():
        guard = await db.outreach_suppression_guards.with_options(read_concern=ReadConcern('majority')).find_one(
            suppression.guard_scope(workspace))
        if guard and guard.get('erasure_state'):
            raise ValueError('Closed workspaces cannot export recipient data')
    await require_open()
    if not isinstance(dnc_records, list) or not isinstance(email_records, list):
        raise ValueError('Selected original record references are required')
    if not 1 <= len(dnc_records) + len(email_records) <= LIMIT:
        raise ValueError('Bounded selected original records are required')
    facts = []
    for kind, references in (('dnc', dnc_records), ('email', email_records)):
        if len(set(references)) != len(references):
            raise ValueError('Distinct selected records are required')
        for reference in references:
            epoch.reference(reference)
            ids = [reference]
            if ObjectId.is_valid(reference): ids.append(ObjectId(reference))
            rows = await getattr(db, COLLECTIONS[kind]).with_options(read_concern=ReadConcern('majority')).find(
                {'workspace_id': workspace, '_id': {'$in': ids}}).limit(2).to_list(length=2)
            if len(rows) != 1 or 'restore_provenance' in rows[0]:
                raise ValueError('Exactly one original suppression row is required')
            row = rows[0]; date = native_date(row.get('created_at'))
            record = canonical_hash([COLLECTIONS[kind], type(row['_id']).__name__, str(row['_id'])])
            values = set()
            if kind == 'email':
                identity('email', row.get('email')); values.add(('email', row['email']))
            else:
                saved = row.get('identifiers') or {}
                if not isinstance(saved, dict) or set(saved) - set(FIELDS):
                    raise ValueError('Original DNC identities are unproven')
                for field in FIELDS:
                    for value in (saved.get(field), row.get('linkedin_url' if field == 'normalized_url' else field)):
                        if value is not None and value != '':
                            identity(field, value); values.add((field, value))
                if row.get('linkedin_urn'):
                    identity('member_urn', row['linkedin_urn']); values.add(('member_urn', row['linkedin_urn']))
            if not values:
                raise ValueError('An original suppression identity is required')
            for field, value in sorted(values):
                identity(field, value)
                facts.append(Fact(kind, field, value, date, record).document())
            if len(facts) > LIMIT:
                raise ValueError('Expanded suppression facts exceed capacity')
    document = {'version': 1, 'workspace_guard_digest': suppression.guard_scope(workspace)['_id'], 'facts': facts}
    # The same strict schema/capacity checks apply to source and target.
    parse(json.dumps(document, sort_keys=True).encode())
    await require_open()
    return document


def dnc_scope(workspace: str, fact: Fact) -> dict:
    return {'_id': canonical_hash(['restore_dnc_v1', workspace, fact.field, fact.value]), 'workspace_id': workspace}


def scope(workspace: str, fact: Fact) -> dict:
    return dnc_scope(workspace, fact) if fact.kind == 'dnc' else {'workspace_id': workspace, 'email': fact.value}


async def target_rows(db: Any, workspace: str, fact: Fact) -> list[dict]:
    rows = await getattr(db, COLLECTIONS[fact.kind]).find(scope(workspace, fact)).limit(2).to_list(length=2)
    if len(rows) > 1:
        raise ValueError('Duplicate target suppression rows require review')
    for row in rows:
        native_date(row.get('created_at'))
        if fact.kind == 'dnc':
            # Dedicated fact rows never become a container for changed identities.
            if (row.get('identifiers') != {fact.field: fact.value}
                    or row.get('restore_provenance') != 'selected_negative'):
                raise ValueError('Restored DNC identity changed')
            if any(row.get(field) for field in ('linkedin_url', 'vanity_name', 'member_urn', 'sales_lead_urn', 'email', 'linkedin_urn')):
                raise ValueError('Restored DNC aliases changed')
    return rows


class RestoreSuppressions:
    def __init__(self, db: Any) -> None:
        self.db = db

    async def _view(self, db: Any, workspace: str, manifest: Manifest, captured: tuple[str, str]) -> tuple[dict, epoch.EpochProof]:
        if manifest.guard_digest != suppression.guard_scope(workspace)['_id']:
            raise ValueError('Suppression manifest scope differs')
        from outreach.core.erasure import workspace_is_open
        if not await workspace_is_open(db, workspace):
            raise ValueError('Closed workspaces cannot restore recipient data')
        proof = await epoch.require(db, workspace, captured=captured)
        if not proof.digest:
            raise ValueError('A prepared stopped restore epoch is required')
        guard = await db.outreach_suppression_guards.find_one(suppression.guard_scope(workspace))
        rows = [epoch.stable(await target_rows(db, workspace, fact)) for fact in manifest.facts]
        proof.assert_live()
        if not epoch.flags_off(): raise ValueError('Execution flags changed')
        return {'execution_epoch': proof.digest, 'source_digest': manifest.source_digest, 'facts_digest': manifest.facts_digest,
                'guard': review_guard(guard), 'rows': rows}, proof

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
            db = (AuthorityDatabase(current.database, current.session, 'restore_suppression_import')
                  if isinstance(current, suppression.SuppressionDatabase) else current)
            view, proof = await self._view(db, workspace, manifest, captured)
            journal_scope = {'_id': canonical_hash(['restore_suppressions_v1', workspace, proof.digest, source_digest]),
                             'workspace_id': workspace, 'execution_epoch': proof.digest, 'source_digest': source_digest}
            saved = await db.outreach_restore_suppressions.find_one(journal_scope)
            review = {'operator_digest': canonical_hash(operator), 'evidence_digest': evidence_digest,
                      'review_digest': review_digest, 'facts_digest': manifest.facts_digest}
            result = {'applied': True, 'activation_allowed': False, 'reply_history_restored': False,
                      'selected_fact_count': len(manifest.facts)}
            if saved:
                if any(saved.get(key) != value for key, value in review.items()) or not all(view['rows']):
                    raise ValueError('Original suppression review or current exclusions are unavailable')
            else:
                if canonical_hash(view) != review_digest:
                    raise ValueError('Suppression inspection changed')
                for fact in manifest.facts:
                    values = {'created_at': fact.blocked_at, 'restore_provenance': 'selected_negative',
                              'reason': 'Restored suppression; original details retained separately'}
                    if fact.kind == 'dnc': values['identifiers'] = {fact.field: fact.value}
                    await getattr(current, COLLECTIONS[fact.kind]).update_one(scope(workspace, fact), {'$setOnInsert': values}, upsert=True)
                after, _ = await self._view(db, workspace, manifest, captured)
                if not all(after['rows']): raise ValueError('Selected suppression facts could not be retained')
                await current.outreach_restore_suppressions.insert_one({**journal_scope, **review,
                    'version': 1, 'fact_count': len(manifest.facts), 'applied_at': epoch.now(),
                    'activation_allowed': False, 'reply_history_restored': False})
            proof.assert_live()
            if not epoch.flags_off(): raise ValueError('Execution flags changed')
            return {**result, 'recovered': bool(saved)}
        return await suppression.mutate_suppression(self.db, workspace, transaction)
