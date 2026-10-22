"""Selected permanent physical-IP reuse exclusions; never provider ownership proof."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)
from dataclasses import dataclass
import hashlib
import json
from typing import Any
from pymongo.read_concern import ReadConcern
from outreach.core import restore_epoch as epoch, suppression
from outreach.core.authorization import canonical_hash
from outreach.core.proxy_identity import touch_restore_fence
from outreach.core.restore_exclusions import (MAX_BYTES, MAX_IDENTITIES, digest, unique_object,
                                             reject_constant, raw_database, review_guard)


@dataclass(frozen=True)
class Manifest:
    source_digest: str
    guard_digest: str
    ips: tuple[tuple[str, str], ...]

    @property
    def facts_digest(self) -> str:
        return canonical_hash(self.ips)


def parse(raw: bytes) -> Manifest:
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_BYTES:
        raise ValueError('A bounded IP exclusion manifest is required')
    try:
        doc = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object, parse_constant=reject_constant)
        if (not isinstance(doc, dict) or set(doc) != {'version', 'workspace_guard_digest', 'ips'}
                or type(doc['version']) is not int or doc['version'] != 1
                or not isinstance(doc['ips'], list) or not 1 <= len(doc['ips']) <= MAX_IDENTITIES):
            raise ValueError('Unsupported IP exclusion manifest')
        digest(doc['workspace_guard_digest']); ips = []
        for fact in doc['ips']:
            if not isinstance(fact, dict) or set(fact) != {'ip_digest', 'binding_digest'}:
                raise ValueError('Unsupported IP exclusion fact')
            digest(fact['ip_digest']); digest(fact['binding_digest'])
            ips.append((fact['ip_digest'], fact['binding_digest']))
        if len({identity for identity, _ in ips}) != len(ips):
            raise ValueError('Duplicate IP exclusion facts are unavailable')
        return Manifest(hashlib.sha256(raw).hexdigest(), doc['workspace_guard_digest'], tuple(sorted(ips)))
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        raise ValueError('IP exclusion manifest is unavailable or unproven') from exc


async def export_manifest(db: Any, workspace: str, ip_digests: list[str], *, workers_drained: bool = False) -> dict:
    """Read selected global hashes; workspace selects review scope, not ownership."""
    epoch.reference(workspace)
    if (workers_drained is not True or not isinstance(ip_digests, list)
            or not 1 <= len(ip_digests) <= MAX_IDENTITIES):
        raise ValueError('Bounded selected IP digests and source drain are required')
    for identity in ip_digests: digest(identity)
    if len(set(ip_digests)) != len(ip_digests):
        raise ValueError('Distinct selected IP digests are required')
    collection = db.account_proxy_ip_guards.with_options(read_concern=ReadConcern('majority'))
    facts = []
    for identity in ip_digests:
        row = await collection.find_one({'_id': identity})
        if not row or 'restore_reuse_blocked' in row:
            raise ValueError('An original retained IP binding is required')
        digest(row.get('binding_digest'))
        facts.append({'ip_digest': identity, 'binding_digest': row['binding_digest']})
    document = {'version': 1, 'workspace_guard_digest': suppression.guard_scope(workspace)['_id'], 'ips': facts}
    parse(json.dumps(document, sort_keys=True).encode())
    return document


class RestoreProxyExclusions:
    def __init__(self, db: Any) -> None:
        self.db = db

    async def _view(self, db: Any, workspace: str, manifest: Manifest,
                    captured: tuple[str, str]) -> tuple[dict, epoch.EpochProof]:
        if manifest.guard_digest != suppression.guard_scope(workspace)['_id']:
            raise ValueError('IP exclusion review scope differs')
        proof = await epoch.require(db, workspace, captured=captured)
        if not proof.digest: raise ValueError('A prepared stopped restore epoch is required')
        guard = await db.outreach_suppression_guards.find_one(suppression.guard_scope(workspace))
        raw, options = raw_database(db)
        if options:
            for identity, _ in manifest.ips:
                await touch_restore_fence(raw, identity, **options)
        rows = await raw.account_proxy_ip_guards.find({'_id': {'$in': [identity for identity, _ in manifest.ips]}},
                                                     **options).sort('_id', 1).limit(MAX_IDENTITIES + 1).to_list(length=MAX_IDENTITIES + 1)
        expected = dict(manifest.ips)
        for row in rows:
            if (row.get('binding_digest') != expected[row['_id']]
                    or 'restore_reuse_blocked' in row and row['restore_reuse_blocked'] is not True):
                raise ValueError('Retained IP binding or reuse block changed')
            if options:
                fenced = await raw.account_proxy_ip_guards.update_one({'_id': row['_id'], 'binding_digest': row['binding_digest']},
                    {'$inc': {'dispatch_fence_revision': 1}}, **options)
                if fenced.matched_count != 1: raise ValueError('IP exclusion authority changed')
        proof.assert_live()
        if not epoch.flags_off(): raise ValueError('Execution flags changed')
        return {'execution_epoch': proof.digest, 'source_digest': manifest.source_digest,
                'facts_digest': manifest.facts_digest, 'guard': review_guard(guard), 'ips': epoch.stable(rows)}, proof

    async def inspect(self, workspace: str, raw: bytes) -> dict:
        epoch.reference(workspace); manifest = parse(raw)
        view, _ = await self._view(self.db, workspace, manifest, epoch.policy())
        return {'workspace_id': workspace, 'digest': canonical_hash(view), 'source_digest': manifest.source_digest,
                'selected_ip_count': len(manifest.ips),
                'missing_block_count': len(manifest.ips) - sum(row.get('restore_reuse_blocked') is True for row in view['ips']),
                'activation_allowed': False, 'assets_restored': False}

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
            db = (AuthorityDatabase(current.database, current.session, 'restore_proxy_import')
                  if isinstance(current, suppression.SuppressionDatabase) else current)
            view, proof = await self._view(db, workspace, manifest, captured)
            scope = {'_id': canonical_hash(['restore_proxy_exclusions_v1', workspace, proof.digest, source_digest]),
                     'workspace_id': workspace, 'execution_epoch': proof.digest, 'source_digest': source_digest}
            saved = await db.outreach_restore_proxy_exclusions.find_one(scope)
            review = {'operator_digest': canonical_hash(operator), 'evidence_digest': evidence_digest,
                      'review_digest': review_digest, 'facts_digest': manifest.facts_digest}
            if saved:
                if (any(saved.get(key) != value for key, value in review.items())
                        or len(view['ips']) != len(manifest.ips)
                        or not all(row.get('restore_reuse_blocked') is True for row in view['ips'])):
                    raise ValueError('Original IP review or current reuse blocks are unavailable')
            else:
                if canonical_hash(view) != review_digest: raise ValueError('IP exclusion inspection changed')
                raw_db, options = raw_database(current)
                for identity, binding in manifest.ips:
                    await raw_db.account_proxy_ip_guards.update_one({'_id': identity}, {
                        '$setOnInsert': {'binding_digest': binding}, '$set': {'restore_reuse_blocked': True}}, upsert=True, **options)
                after, _ = await self._view(db, workspace, manifest, captured)
                if (len(after['ips']) != len(manifest.ips)
                        or not all(row.get('restore_reuse_blocked') is True for row in after['ips'])):
                    raise ValueError('Selected IP reuse blocks could not be retained')
                await current.outreach_restore_proxy_exclusions.insert_one({**scope, **review, 'version': 1,
                    'ip_count': len(manifest.ips), 'applied_at': epoch.now(),
                    'activation_allowed': False, 'assets_restored': False})
            proof.assert_live()
            if not epoch.flags_off(): raise ValueError('Execution flags changed')
            return {'applied': True, 'recovered': bool(saved), 'selected_ip_count': len(manifest.ips),
                    'activation_allowed': False, 'assets_restored': False}
        from outreach.core.erasure import _control
        return await _control(self.db, workspace, transaction)
