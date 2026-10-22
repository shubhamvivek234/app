"""Bounded stopped local financial/proxy inspection; never reconciliation approval."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)
from collections import Counter
from datetime import datetime
import json
from typing import Any
from outreach.core import restore_epoch as epoch, suppression
from outreach.core.authorization import canonical_hash
from outreach.core.proxy_identity import identity
from outreach.core.restore_exclusions import raw_database
from outreach.core import restore_uncertainty

FIELDS = {
    'outreach_entitlements': ('_id', 'status', 'seats', 'paid_through', 'last_invoice_id', 'is_revoked', 'payment_source'),
    'outreach_payment_receipts': ('_id', 'seats', 'paid_through', 'source', 'verified_at'),
    'outreach_access_requests': ('_id', 'status', 'seats', 'country_code'),
    'outreach_proxy_inventory': ('_id', 'workspace_id', 'last_workspace_id', 'provider', 'host', 'expires_at', 'status', 'country_code', 'credential_generation', 'import_basis_digest',
        'root_import_basis_digest', 'proxy_lifecycle_revision', 'proxy_lifecycle_review_id',
        'proxy_adoption_id', 'proxy_adoption_source_digest', 'provider_plan_id', 'provider_resource_id',
        'provider_order_id', 'custody_workspace_id', 'managed_webshare_version', 'dedicated_isp_confirmed',
        'verified_by', 'verified_at', 'evidence_digest'),
    'outreach_proxy_adoptions': ('_id', 'proxy_id', 'status', 'source_digest', 'adopted_basis_digest'),
    'outreach_proxy_lifecycle_reviews': ('_id', 'proxy_id', 'status', 'revision',
        'root_import_basis_digest', 'after_basis_digest', 'generation_digest'),
    'outreach_proxy_leases': ('_id', 'sender_id', 'provider', 'country_code'),
    'outreach_accounts': ('_id', 'id', 'credential_generation', 'proxy.proxy_id', 'proxy.credential_generation'),
    'outreach_email_operations': ('_id', 'status'),
    'outreach_email_discoveries': ('_id', 'status'),
    'outreach_physical_requests': ('_id', 'status', 'mutation'),
    **restore_uncertainty.FIELDS,
}
LIMIT = 100
MAX_METADATA_BYTES = 65536


def metadata(row: dict, fields: tuple[str, ...]) -> dict:
    """Defense in depth: fakes/raw adapters may ignore Mongo projection."""
    result = {}
    for field in fields:
        current = row
        for part in field.split('.'):
            if not isinstance(current, dict) or part not in current:
                break
            current = current[part]
        else:
            result[field] = current
    return epoch.stable(result)


def native_date(value: Any) -> datetime | None:
    return epoch.stable(value) if isinstance(value, datetime) else None


def valid_reference(value: Any) -> bool:
    """Reject malformed local identities before reporting matching links."""
    try:
        epoch.reference(value)
        return True
    except ValueError:
        return False


class RestoreInventory:
    def __init__(self, db: Any) -> None:
        self.db = db

    async def inspect(self, workspace: str, *, workers_drained: bool = False) -> dict:
        epoch.reference(workspace)
        if workers_drained is not True or not epoch.flags_off():
            raise ValueError('Stopped flags and an all-writer/cache drain assertion are required')
        captured = epoch.policy()

        async def snapshot(current):
            from outreach.core.dispatch_authority import AuthorityDatabase
            authority = (AuthorityDatabase(current.database, current.session, 'restore_inventory')
                         if isinstance(current, suppression.SuppressionDatabase) else current)
            proof = await epoch.require(authority, workspace, captured=captured)
            if not proof.digest:
                raise ValueError('A matching prepared stopped restore epoch is required')
            raw, options = raw_database(current)
            view = {'execution_epoch': proof.digest, 'records': {}, 'invoice_bindings': [], 'ip_bindings': []}
            for name, fields in FIELDS.items():
                query = ({'$or': [{'workspace_id': workspace}, {'last_workspace_id': workspace}]}
                         if name == 'outreach_proxy_inventory' else {'workspace_id': workspace})
                rows = await getattr(raw, name).find(query, {field: 1 for field in fields}, **options).sort('_id', 1).limit(
                    LIMIT + 1).to_list(length=LIMIT + 1)
                if len(rows) > LIMIT:
                    raise ValueError('Inventory exceeds bounded review capacity')
                view['records'][name] = [metadata(row, fields) for row in rows]
            findings = Counter()
            for receipt in view['records']['outreach_payment_receipts']:
                term = native_date(receipt.get('paid_through'))
                reference = receipt.get('_id')
                if (not isinstance(reference, str) or not 1 <= len(reference) <= 256 or term is None
                        or type(receipt.get('seats')) is not int or not 1 <= receipt['seats'] <= 5):
                    findings['payment_receipt_unproven'] += 1
                    continue
                guard = await raw.account_invoice_guards.find_one(
                    {'_id': canonical_hash(['verified_invoice', reference])},
                    {'_id': 1, 'binding_digest': 1, 'restore_reuse_blocked': 1}, **options)
                guard = metadata(guard, ('_id', 'binding_digest', 'restore_reuse_blocked')) if guard else None
                view['invoice_bindings'].append(guard)
                if not guard:
                    findings['invoice_binding_missing'] += 1
                elif guard.get('binding_digest') != canonical_hash([workspace, receipt['seats'], term]):
                    findings['invoice_binding_mismatch'] += 1
                else:
                    findings['local_invoice_binding_matches'] += 1
                if guard and 'restore_reuse_blocked' in guard:
                    findings['invoice_restore_blocked'] += 1
            for asset in view['records']['outreach_proxy_inventory']:
                try:
                    if asset.get('provider') not in {'iproyal_static', 'webshare_plan'}:
                        raise ValueError('Unsupported provider')
                    if asset.get('workspace_id') not in (None, workspace):
                        raise ValueError('Ambiguous current asset scope')
                    binding = identity(asset.get('host'), workspace, asset.get('_id'), asset['provider'])
                except (ValueError, TypeError):
                    findings['proxy_identity_unproven'] += 1
                    continue
                guard = await raw.account_proxy_ip_guards.find_one({'_id': binding['_id']},
                    {'_id': 1, 'binding_digest': 1, 'restore_reuse_blocked': 1}, **options)
                guard = metadata(guard, ('_id', 'binding_digest', 'restore_reuse_blocked')) if guard else None
                view['ip_bindings'].append(guard)
                if not guard: findings['ip_binding_missing'] += 1
                elif guard.get('binding_digest') != binding['binding_digest']: findings['ip_binding_mismatch'] += 1
                else: findings['local_ip_binding_matches'] += 1
                if guard and 'restore_reuse_blocked' in guard: findings['ip_restore_blocked'] += 1
                expiry = native_date(asset.get('expires_at'))
                if expiry is None: findings['proxy_term_unproven'] += 1
                elif expiry <= epoch.now(): findings['proxy_term_expired'] += 1
            assets = {canonical_hash(row.get('_id')) for row in view['records']['outreach_proxy_inventory']}
            for lease in view['records']['outreach_proxy_leases']:
                if canonical_hash(lease.get('_id')) not in assets: findings['lease_asset_missing'] += 1
            from outreach.core.proxy_lifecycle_proof import material
            from outreach.core.proxy_migration import HEX
            for asset in view['records']['outreach_proxy_inventory']:
                if asset.get('provider') != 'webshare_plan':
                    continue
                verified = native_date(asset.get('verified_at'))
                expiry = native_date(asset.get('expires_at'))
                provider_refs = ('provider_plan_id', 'provider_resource_id', 'provider_order_id')
                import_valid = (all(valid_reference(asset.get(key)) and len(asset[key]) <= 128
                                    for key in provider_refs)
                    and all(':' not in asset[key] for key in ('provider_plan_id', 'provider_resource_id'))
                    and asset.get('_id') == f"webshare:{asset.get('provider_plan_id')}:{asset.get('provider_resource_id')}"
                    and asset.get('workspace_id') == asset.get('last_workspace_id') == asset.get('custody_workspace_id') == workspace
                    and type(asset.get('managed_webshare_version')) is int and asset['managed_webshare_version'] == 1
                    and asset.get('dedicated_isp_confirmed') is True
                    and valid_reference(asset.get('verified_by')) and valid_reference(asset.get('credential_generation'))
                    and all(isinstance(asset.get(key), str) and HEX.fullmatch(asset[key])
                            for key in ('evidence_digest', 'import_basis_digest'))
                    and verified is not None and expiry is not None and verified <= epoch.now() < expiry
                    and verified < expiry)
                findings['local_webshare_import_metadata_consistent' if import_valid else 'webshare_import_metadata_review_required'] += 1
                adoptions = [row for row in view['records']['outreach_proxy_adoptions']
                             if row.get('proxy_id') == asset.get('_id')]
                basis = asset.get('root_import_basis_digest', asset.get('import_basis_digest'))
                adoption_valid = (asset.get('workspace_id') == workspace
                    and ('last_workspace_id' not in asset or asset['last_workspace_id'] == workspace)
                    and valid_reference(asset.get('_id'))
                    and all(isinstance(asset.get(key), str) and HEX.fullmatch(asset[key])
                            for key in ('proxy_adoption_id', 'proxy_adoption_source_digest'))
                    and isinstance(basis, str) and HEX.fullmatch(basis) and len(adoptions) == 1)
                if adoption_valid:
                    receipt = adoptions[0]
                    adoption_valid = (receipt.get('_id') == asset['proxy_adoption_id']
                        and receipt.get('status') == 'completed'
                        and receipt.get('source_digest') == asset['proxy_adoption_source_digest']
                        and receipt.get('adopted_basis_digest') == basis)
                findings['local_webshare_adoption_matches' if adoption_valid else 'webshare_adoption_review_required'] += 1
                revision = asset.get('proxy_lifecycle_revision')
                reviews = [row for row in view['records']['outreach_proxy_lifecycle_reviews']
                           if row.get('proxy_id') == asset.get('_id') and row.get('revision') == revision]
                valid = (asset.get('workspace_id') == workspace
                    and ('last_workspace_id' not in asset or asset['last_workspace_id'] == workspace)
                    and type(revision) is int and 1 <= revision <= 1_000_000
                    and all(isinstance(asset.get(key), str) and HEX.fullmatch(asset[key]) for key in
                            ('import_basis_digest', 'root_import_basis_digest', 'proxy_lifecycle_review_id'))
                    and valid_reference(asset.get('_id')) and valid_reference(asset.get('credential_generation'))
                    and len(reviews) == 1)
                if valid:
                    receipt = reviews[0]
                    valid = (receipt.get('_id') == asset['proxy_lifecycle_review_id']
                        and receipt.get('status') == 'completed' and type(receipt.get('revision')) is int
                        and receipt.get('root_import_basis_digest') == asset['root_import_basis_digest']
                        and receipt.get('after_basis_digest') == material(asset)
                        and receipt.get('generation_digest') == canonical_hash(asset['credential_generation']))
                findings['local_webshare_lifecycle_matches' if valid else 'webshare_lifecycle_review_required'] += 1
            leases = view['records']['outreach_proxy_leases']
            sender_counts = Counter(canonical_hash(row.get('sender_id')) for row in leases)
            for lease in leases:
                if not valid_reference(lease.get('_id')):
                    findings['lease_asset_identity_unproven'] += 1
                    continue
                sender_id = lease.get('sender_id')
                if not valid_reference(sender_id):
                    findings['lease_sender_identity_unproven'] += 1
                    continue
                if sender_counts[canonical_hash(sender_id)] > 1:
                    findings['lease_sender_multiple_assets'] += 1
                candidates = [row for row in view['records']['outreach_proxy_inventory']
                              if row.get('_id') == lease.get('_id')]
                if len(candidates) != 1:
                    continue  # Existing missing-asset finding remains; no ownership is inferred.
                asset = candidates[0]
                if (asset.get('workspace_id') not in (None, workspace)
                        or ('last_workspace_id' in asset and asset['last_workspace_id'] != workspace)):
                    findings['lease_asset_scope_unproven'] += 1
                    continue
                country = asset.get('country_code')
                if (asset.get('provider') not in ('iproyal_static', 'webshare_plan')
                        or not isinstance(country, str) or len(country) != 2
                        or not country.isascii() or not country.isalpha() or country != country.upper()
                        or lease.get('provider') != asset.get('provider') or lease.get('country_code') != country):
                    findings['lease_provider_country_mismatch'] += 1
                    continue
                senders = [row for row in view['records']['outreach_accounts'] if row.get('id') == sender_id]
                if not senders:
                    findings['lease_sender_review_required'] += 1
                    continue  # A pending reservation may have no installed account.
                if len(senders) != 1:
                    findings['lease_sender_ambiguous'] += 1
                    continue
                sender = senders[0]
                if sender.get('proxy.proxy_id') != lease.get('_id'):
                    findings['lease_sender_proxy_mismatch'] += 1
                    continue
                generation = asset.get('credential_generation')
                if (not valid_reference(generation)
                        or sender.get('proxy.credential_generation') != generation):
                    findings['lease_credential_generation_mismatch'] += 1
                    continue
                if sender_counts[canonical_hash(sender_id)] == 1:
                    findings['local_lease_links_match'] += 1
            senders = view['records']['outreach_accounts']
            account_ids = Counter(canonical_hash(row.get('id')) for row in senders)
            proxy_ids = Counter(canonical_hash(row.get('proxy.proxy_id')) for row in senders)
            for sender in senders:
                sender_id = sender.get('id')
                proxy_id = sender.get('proxy.proxy_id')
                if not valid_reference(sender_id) or not valid_reference(proxy_id):
                    findings['sender_assignment_identity_unproven'] += 1
                    continue
                if account_ids[canonical_hash(sender_id)] != 1:
                    findings['sender_identity_ambiguous'] += 1
                    continue
                if proxy_ids[canonical_hash(proxy_id)] != 1:
                    findings['sender_proxy_shared'] += 1
                    continue
                candidates = [row for row in view['records']['outreach_proxy_inventory'] if row.get('_id') == proxy_id]
                if (len(candidates) != 1 or candidates[0].get('workspace_id') not in (None, workspace)
                        or ('last_workspace_id' in candidates[0] and candidates[0]['last_workspace_id'] != workspace)):
                    findings['sender_proxy_asset_review_required'] += 1
                    continue
                asset = candidates[0]
                assignments = [row for row in leases if row.get('_id') == proxy_id]
                country = asset.get('country_code')
                if (len(assignments) != 1 or assignments[0].get('sender_id') != sender_id
                        or sender_counts[canonical_hash(sender_id)] != 1
                        or asset.get('provider') not in ('iproyal_static', 'webshare_plan')
                        or not isinstance(country, str) or len(country) != 2
                        or not country.isascii() or not country.isalpha() or country != country.upper()
                        or assignments[0].get('provider') != asset.get('provider')
                        or assignments[0].get('country_code') != country):
                    findings['sender_proxy_lease_review_required'] += 1
                    continue
                generation = asset.get('credential_generation')
                if not valid_reference(generation) or sender.get('proxy.credential_generation') != generation:
                    findings['sender_proxy_generation_review_required'] += 1
                    continue
                findings['local_sender_assignment_links_match'] += 1
            for entitlement in view['records']['outreach_entitlements']:
                term = native_date(entitlement.get('paid_through'))
                invoice = entitlement.get('last_invoice_id')
                if entitlement.get('status') != 'active' or entitlement.get('is_revoked'):
                    findings['entitlement_stopped'] += 1
                if term is not None and term <= epoch.now():
                    findings['entitlement_term_expired'] += 1
                if (not isinstance(invoice, str) or not 1 <= len(invoice) <= 256 or term is None
                        or type(entitlement.get('seats')) is not int or not 1 <= entitlement['seats'] <= 5
                        or entitlement.get('payment_source') != 'manual_verified_invoice'):
                    findings['entitlement_payment_unproven'] += 1
                    continue
                receipts = [row for row in view['records']['outreach_payment_receipts']
                            if row.get('_id') == invoice]
                if not receipts:
                    findings['entitlement_receipt_missing'] += 1
                elif (len(receipts) != 1 or type(receipts[0].get('seats')) is not int
                        or receipts[0].get('seats') != entitlement['seats']
                        or native_date(receipts[0].get('paid_through')) != term
                        or receipts[0].get('source') != 'manual_verified_invoice'):
                    findings['entitlement_receipt_mismatch'] += 1
                else:
                    findings['local_entitlement_receipt_matches'] += 1
            for request in view['records']['outreach_physical_requests']:
                status = request.get('status')
                if status == 'preparing':
                    findings['physical_preparing_review'] += 1
                elif status in ('in_flight', 'unknown_outcome'):
                    findings['physical_outcome_unresolved'] += 1
                elif status == 'response_received':
                    findings['physical_received_review'] += 1
                elif (status not in ('not_submitted', 'read_failed')
                      or (status == 'read_failed' and request.get('mutation') is not False)):
                    findings['physical_state_unproven'] += 1
            for collection, prefix, results in (
                    ('outreach_email_operations', 'email_operation', ('accepted', 'failed')),
                    ('outreach_email_discoveries', 'finder_operation', ('found', 'not_found', 'failed'))):
                for operation in view['records'][collection]:
                    state = operation.get('status')
                    if state in ('dispatching', 'uncertain'):
                        findings[prefix + '_unresolved'] += 1
                    elif state in results:
                        findings[prefix + '_recorded_result_review'] += 1
                    elif state != 'not_submitted':
                        findings[prefix + '_state_unproven'] += 1
            findings.update(restore_uncertainty.findings(view['records']))
            view['findings'] = dict(findings)
            if len(json.dumps(view, sort_keys=True, default=str, allow_nan=False).encode()) > MAX_METADATA_BYTES:
                raise ValueError('Inventory metadata exceeds bounded review capacity')
            proof.assert_live()
            if not epoch.flags_off(): raise ValueError('Stopped configuration changed')
            return {'workspace_id': workspace, 'execution_epoch': proof.digest, 'digest': canonical_hash(view),
                'counts': {name: len(rows) for name, rows in view['records'].items()}, 'findings': dict(findings),
                'inspected_at': epoch.now().isoformat(), 'activation_allowed': False, 'completeness_verified': False,
                'provider_ownership_verified': False,
                'external_review_required': ['financial_facts', 'provider_resources', 'source_completeness']}
        result = await suppression.mutate_suppression(self.db, workspace, snapshot)
        if epoch.policy() != captured or not epoch.flags_off():
            raise ValueError('Stopped configuration changed after inspection')
        return result
