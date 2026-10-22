"""Private original-delivery review; no HTTP, key opening, replay or activation."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)
import re
from typing import Any
from outreach.core import integration_control as ctl, integration_custody as custody
from outreach.core.authorization import canonical_hash
from outreach.core.integration_delivery import _crm_basis, _utc, identity, now, receipt_digest

REVIEWABLE = {'preparing', 'possible', 'received', 'held_received', 'review_required', 'leased'}
DECISIONS = {'stop_local', 'use_receipt'}


def receipt_valid(job: dict) -> bool:
    """Only a current original attempt can supply a received-outcome proof."""
    try:
        receipt = job.get('receipt')
        if (job.get('custody_protocol_version') != 2 or job.get('status') not in {'received', 'held_received', 'review_required'}
                or not isinstance(receipt, dict)
                or identity(job) != job.get('immutable_digest') or type(job.get('attempt')) is not int or job['attempt'] < 1
                or receipt_digest(receipt) != job.get('receipt_digest')
                or type(receipt.get('status_code')) is not int or not 100 <= receipt['status_code'] <= 599):
            return False
        possible, received, expiry = [_utc(value) for value in (
            job.get('possible_at'), receipt.get('received_at'), job.get('authorization_expires_at'))]
        if not possible or not received or not expiry or not possible <= received <= min(expiry, now()): return False
        owner = job.get('lease_id')
        if not owner:
            proofs = [entry for entry in job.get('attempt_receipts', []) if entry.get('attempt') == job['attempt']
                and entry.get('receipt_digest') == job['receipt_digest'] and entry.get('receipt') == receipt
                and _utc(entry.get('possible_at')) == possible and _utc(entry.get('authorization_expires_at')) == expiry
                and isinstance(entry.get('owner'), str) and entry['owner'].strip()]
            if len(proofs) != 1: return False
            owner = proofs[0]['owner']
        return isinstance(owner, str) and bool(owner.strip())
    except (TypeError, ValueError, AttributeError):
        return False


def outcome(job: dict) -> str:
    if receipt_valid(job): return 'received'
    return ('not_called' if job.get('custody_protocol_version') == 2 and job.get('status') == 'preparing'
        and job.get('attempt') == 0 and not job.get('possible_at') and not job.get('receipt') else 'unknown')


class IntegrationReview:
    def __init__(self, db: Any) -> None:
        self.db = db

    @staticmethod
    def scope(workspace: str, job_id: str) -> dict:
        ctl.reference(workspace); ctl.reference(job_id)
        return {'workspace_id': workspace, 'id': job_id}

    async def _snapshot(self, current: Any, workspace: str, job_id: str) -> dict:
        job = await current.outreach_webhook_deliveries.find_one(self.scope(workspace, job_id))
        if not job: raise ValueError('Integration delivery reference is unavailable')
        kind = job.get('destination_type')
        if kind is None and job.get('custody_protocol_version') != 2:
            kind = 'webhook'
        view = await ctl.snapshot(current, workspace, kind, job.get('destination_id'))
        if job.get('destination_type') is None and not view['source']:
            destination = job.get('target_url_enc') or job.get('target_url')
            secret = job.get('secret_enc')
            if (not isinstance(destination, str) or not 1 <= len(destination) <= 16384
                    or not isinstance(secret, str) or not 1 <= len(secret) <= 60000):
                raise ValueError('Legacy webhook destination is unproven')
        view['job'] = ctl.stable(job)
        view['basis'] = None
        if job.get('custody_protocol_version') == 2 and job.get('destination_type') == 'hubspot':
            try: view['basis'] = ctl.stable(await _crm_basis(current, workspace, job.get('lead_id'), job.get('portal_id')))
            except (ValueError, TypeError): pass
        return view

    @staticmethod
    def _blockers(view: dict) -> list[str]:
        job = view['job']; reasons = ctl.blockers(view, job['id'])
        if job.get('status') not in REVIEWABLE: reasons.append('not_awaiting_review')
        if job.get('custody_protocol_version') == 2:
            if (identity(job) != job.get('immutable_digest') or any(not isinstance(job.get(key), str)
                    or not ctl.HEX.fullmatch(job[key]) for key in ('credential_digest', 'policy_digest'))):
                reasons.append('original_binding_unproven')
            # A projected ambiguous receipt has a saved attempt owner rather
            # than an active worker lease. All other owners need proven expiry.
            projected = not job.get('lease_id') and receipt_valid(job)
            lease = _utc(job.get('leased_until'))
            if not projected and (not lease or lease > now() or not job.get('lease_id')):
                reasons.append('worker_lease_live_or_unproven')
        else:
            lease = _utc(job.get('leased_until') or job.get('lease_until'))
            if lease and lease > now(): reasons.append('legacy_worker_lease_live')
        return sorted(set(reasons))

    @staticmethod
    def _usable(view: dict) -> bool:
        job, basis = view['job'], view['basis']
        if (not view['workspace_open'] or not receipt_valid(job) or not 200 <= job['receipt']['status_code'] < 300
                or ctl.material(view['source'], view['workspace_id'], view['kind']) != job['credential_digest']
                or view['policy'] != job['policy_digest']): return False
        if view['kind'] == 'hubspot':
            remote = job['receipt'].get('external_id')
            return bool(isinstance(remote, str) and re.fullmatch(r'[0-9]{1,64}', remote) and basis
                and basis['lead_digest'] == job.get('lead_digest') and basis['mapping_digest'] == job.get('mapping_digest'))
        return True

    async def inspect(self, workspace: str, job_id: str) -> dict:
        saved = await self.db.outreach_integration_reviews.find_one(self.scope(workspace, job_id))
        if saved:
            job = await self.db.outreach_webhook_deliveries.find_one(self.scope(workspace, job_id)) or {}
            return {'workspace_id': workspace, 'delivery_id': job_id, 'status': job.get('status', 'unavailable'),
                'review_status': saved['status'], 'outcome_at_review': saved['outcome_at_review'],
                'review_digest': saved['inspection_digest'], 'blockers': [], 'allowed_decisions': [],
                'review_saved': True, 'activation_allowed': False}
        view = await self._snapshot(self.db, workspace, job_id); job = view['job']
        blockers = self._blockers(view)
        decisions = [] if blockers or saved else ['stop_local']
        if not blockers and not saved and self._usable(view): decisions.append('use_receipt')
        return {'workspace_id': workspace, 'delivery_id': job_id, 'status': job['status'],
            'outcome_at_review': outcome(job), 'review_digest': canonical_hash(view), 'blockers': blockers,
            'allowed_decisions': decisions, 'review_saved': bool(saved), 'activation_allowed': False}

    @staticmethod
    def _saved(row: dict, decision: str, operator: str, evidence: str, digest: str) -> dict:
        if any(row.get(key) != value for key, value in {'decision': decision,
                'operator_digest': canonical_hash(operator.strip()), 'evidence_digest': canonical_hash(evidence.strip()),
                'inspection_digest': digest}.items()): raise ValueError('A different integration review is already saved')
        return {key: row[key] for key in ('status', 'delivery_id', 'outcome_at_review', 'activation_allowed')}

    async def resolve(self, workspace: str, job_id: str, decision: str, operator: str, evidence: str, *,
                      workers_drained: bool = False, expected_digest: str) -> dict:
        ctl.require_review(operator, evidence, expected_digest, workers_drained)
        if decision not in DECISIONS: raise ValueError('Unsupported integration review decision')
        job_scope = self.scope(workspace, job_id)
        journal_scope = {'workspace_id': workspace, 'id': job_id}
        async def apply(current: Any) -> dict:
            existing = await current.outreach_integration_reviews.find_one(journal_scope)
            if existing: return self._saved(existing, decision, operator, evidence, expected_digest)
            view = await self._snapshot(ctl.fenced(current), workspace, job_id); job = view['job']
            if canonical_hash(view) != expected_digest or self._blockers(view): raise ValueError('Integration inspection changed')
            if decision == 'use_receipt' and not self._usable(view): raise ValueError('An intact original success receipt is required')
            at = now(); state = outcome(job)
            await ctl.stop(current, view, operator.strip(), 'integration_operator_review')
            if decision == 'use_receipt' and view['kind'] == 'hubspot':
                basis = view['basis']
                await current.outreach_external_mappings.update_one(basis['mapping_scope'], {'$set': {
                    'external_id': job['receipt']['external_id'], 'synced_at': job['receipt']['received_at'],
                    'status': 'synced', 'integration_delivery_id': job_id}}, upsert=True)
            if not ctl.flags_off() or view['policy'] != custody.policy_digest(): raise ValueError('Integration control configuration changed')
            status = 'review_completed' if decision == 'use_receipt' else 'review_stopped'
            changes = {'updated_at': at, 'operator_review_id': canonical_hash(['integration_review', workspace, job_id])}
            if decision == 'use_receipt': changes.update(status='review_completed', active_slot=None, delivered_at=job['receipt']['received_at'], response_status=job['receipt']['status_code'])
            elif state == 'not_called': changes.update(status='cancelled', active_slot=None)
            else: changes['status'] = 'review_required'  # Unknown CRM slots remain permanently reserved.
            changed = await current.outreach_webhook_deliveries.update_one({**job_scope, '_id': job['_id'],
                'status': job['status'], 'lease_id': job.get('lease_id')}, {'$set': changes,
                '$unset': {'secret_enc': '', 'target_url_enc': '', 'target_url': '', 'access_token_enc': ''}})
            if changed.matched_count != 1: raise ValueError('Original integration owner changed')
            journal = {**journal_scope, '_id': changes['operator_review_id'], 'delivery_id': job_id, 'status': status,
                'decision': decision, 'operator_digest': canonical_hash(operator.strip()), 'evidence_digest': canonical_hash(evidence.strip()),
                'inspection_digest': expected_digest, 'original_job_digest': canonical_hash(job), 'original_status': job['status'],
                'original_owner_digest': canonical_hash(job.get('lease_id')), 'credential_digest': job.get('credential_digest'),
                'receipt_digest': job.get('receipt_digest'), 'possible_at': job.get('possible_at'),
                'received_at': job['receipt'].get('received_at') if isinstance(job.get('receipt'), dict) else None,
                'at': at, 'workers_drained': True,
                'outcome_at_review': state, 'provenance': 'saved_provider_receipt' if decision == 'use_receipt' else 'operator_local_stop',
                'activation_allowed': False}
            await current.outreach_integration_reviews.insert_one(journal)
            if not ctl.flags_off() or view['policy'] != custody.policy_digest(): raise ValueError('Integration control configuration changed')
            return self._saved(journal, decision, operator, evidence, expected_digest)
        return await ctl.control(self.db, workspace, apply)
