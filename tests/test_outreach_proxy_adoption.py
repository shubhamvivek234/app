"""Legacy review requires retained original facts; it supplies no missing owner."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from outreach.core import proxy_adoption as adoption
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.proxy_custody import prepare_proxy
from outreach.core.webshare_provisioning import managed_webshare_valid
from tests.test_outreach_webshare_migration import webshare_db, scoped, ASSET, EVIDENCE

pytestmark = pytest.mark.asyncio


def legacy(row):
    for field in ('managed_webshare_version', 'import_basis_digest', 'request_digest'):
        row.pop(field, None)


@pytest_asyncio.fixture
async def legacy_db(webshare_db):
    db = webshare_db
    legacy(db.outreach_proxy_inventory.docs[0])
    db.account_proxy_ip_guards.docs.clear()
    return db


async def adopt(db, view=None, **changes):
    service = adoption.ProxyAdoption(db)
    view = view or await service.inspect('w', ASSET)
    options = {'workers_drained': True}
    options.update(changes)
    return await service.adopt('w', ASSET, 'operator', EVIDENCE, view['digest'], **options)


async def test_adoption_keeps_original_purchase_password_lease_cookie_and_stop(legacy_db):
    db = legacy_db
    original = deepcopy(db.outreach_proxy_inventory.docs[0])
    lease = deepcopy(db.outreach_proxy_leases.docs)
    view = await adoption.ProxyAdoption(db).inspect('w', ASSET)
    assert not view['blockers'] and not view['activation_allowed']
    for secret in ('191.116.125.248', 'private-password', 'gAAAAA'):
        assert secret not in str(view)
    result = await adopt(db, view)
    assert result['current_matches'] and result['configuration_matches'] and not result['activation_allowed']
    row = db.outreach_proxy_inventory.docs[0]
    for field in ('host', 'port', 'username', 'country_code', 'provider_order_id', 'verified_by',
                  'evidence_digest', 'verified_at', 'expires_at', 'credential_generation'):
        assert row[field] == original[field]
    assert await managed_webshare_valid(db, row, 'w')
    account = db.outreach_accounts.docs[0]
    prepared = await prepare_proxy(account['proxy'], 'w')
    assert prepared.matches(row, 'w') and prepared.matches(account['proxy_config'], 'w')
    assert 'private-password' in prepared.url
    assert account['credential_generation'] == 'cookie-original' and account['status'] == 'paused'
    assert db.outreach_proxy_leases.docs == lease and db.outreach_sender_execution.docs[0]['permission']['latched']
    receipt = db.outreach_proxy_adoptions.docs[0]
    for secret in ('191.116.125.248', 'private-password', 'uc1:', 'gAAAAA', 'cookie-original'):
        assert secret not in str(receipt)
    assert receipt['provenance'] == 'retained_legacy_evidence_storage_adoption'


@pytest.mark.parametrize('issue', ['owner', 'original_owner', 'order', 'plan', 'resource', 'original_evidence',
    'original_operator', 'verified_at', 'dedicated', 'term', 'plaintext', 'scoped', 'lease', 'alias',
    'active', 'permission', 'held', 'closed', 'existing_managed', 'drain', 'foreign_account', 'foreign_claim'])
async def test_incomplete_or_changed_legacy_evidence_denies_before_key_work(legacy_db, monkeypatch, issue):
    db = legacy_db
    row = db.outreach_proxy_inventory.docs[0]
    if issue == 'owner': row['workspace_id'] = 'other'
    if issue == 'original_owner': row.pop('last_workspace_id')
    if issue in ('order', 'plan', 'resource'): row.pop({'order':'provider_order_id', 'plan':'provider_plan_id', 'resource':'provider_resource_id'}[issue])
    if issue == 'original_evidence': row['evidence_digest'] = ''
    if issue == 'original_operator': row.pop('verified_by')
    if issue == 'verified_at': row['verified_at'] = []
    if issue == 'dedicated': row['dedicated_isp_confirmed'] = False
    if issue == 'term': row['expires_at'] = datetime.now(timezone.utc) - timedelta(seconds=1)
    if issue in ('plaintext', 'scoped'):
        row['password_enc'] = 'unproven' if issue == 'plaintext' else 'uc1:unproven'
        for name in ('proxy', 'proxy_config'): db.outreach_accounts.docs[0][name]['password_enc'] = row['password_enc']
    if issue == 'lease': db.outreach_proxy_leases.docs[0]['country_code'] = 'US'
    if issue == 'alias': db.outreach_accounts.docs[0]['proxy']['username'] = 'replacement'
    if issue == 'active': db.outreach_accounts.docs[0]['status'] = 'active'
    if issue == 'permission': db.outreach_sender_execution.docs[0]['permission']['latched'] = False
    if issue == 'held': db.outreach_physical_requests.docs.append({'workspace_id':'w', 'sender_id':'a', 'status':'unknown_outcome'})
    if issue == 'closed': monkeypatch.setattr(adoption.erasure, 'workspace_is_open', AsyncMock(return_value=False))
    if issue == 'existing_managed': row['managed_webshare_version'] = 1
    if issue == 'foreign_account': db.outreach_accounts.docs.append({'workspace_id':'other', 'id':'foreign', 'proxy':deepcopy(db.outreach_accounts.docs[0]['proxy'])})
    if issue == 'foreign_claim':
        from outreach.core.proxy_identity import identity
        db.account_proxy_ip_guards.docs.append(identity(row['host'], 'other', ASSET, row['provider']))
    seal = AsyncMock(side_effect=AssertionError('No key work'))
    monkeypatch.setattr(adoption, 'seal_proxy_password', seal)
    with pytest.raises(CustodyUnavailable): await adopt(db, workers_drained=issue != 'drain')
    seal.assert_not_awaited()
    assert not db.outreach_proxy_adoptions.docs


async def test_missing_legacy_crypto_generation_allocates_only_proxy_generation(legacy_db):
    db = legacy_db
    row = db.outreach_proxy_inventory.docs[0]
    row.pop('credential_generation'); row.pop('custody_workspace_id')
    for name in ('proxy', 'proxy_config'):
        db.outreach_accounts.docs[0][name].pop('credential_generation')
        db.outreach_accounts.docs[0][name].pop('custody_workspace_id')
    assert (await adopt(db))['current_matches']
    assert row['credential_generation'] and row['custody_workspace_id'] == 'w'
    assert db.outreach_accounts.docs[0]['credential_generation'] == 'cookie-original'


async def test_exact_receipt_retry_and_replacement_never_open_original(legacy_db, monkeypatch):
    db = legacy_db
    view = await adoption.ProxyAdoption(db).inspect('w', ASSET)
    result = await adopt(db, view)
    monkeypatch.setattr(adoption, 'decrypt_strict', lambda *args: (_ for _ in ()).throw(AssertionError('No opening')))
    monkeypatch.setattr(adoption, 'seal_proxy_password', AsyncMock(side_effect=AssertionError('No key work')))
    assert await adopt(db, view) == result
    with pytest.raises(CustodyUnavailable):
        await adoption.ProxyAdoption(db).adopt('w', ASSET, 'other', EVIDENCE, view['digest'], workers_drained=True)
    db.outreach_proxy_inventory.docs[0]['password_enc'] = 'replacement'
    assert not (await adopt(db, view))['current_matches']


async def test_adopted_lineage_cannot_be_removed_and_renewal_keeps_original_root(legacy_db):
    from tests.test_outreach_proxy_lifecycle import change
    db = legacy_db
    await adopt(db)
    row = db.outreach_proxy_inventory.docs[0]
    original_basis = row['import_basis_digest']
    assert (await change(db))['current_matches'] and row['root_import_basis_digest'] == original_basis
    assert await managed_webshare_valid(db, row, 'w')
    for name in ('proxy_adoption_id', 'proxy_adoption_source_digest'): row.pop(name)
    assert not await managed_webshare_valid(db, row, 'w')


async def test_failed_seal_keeps_permanent_exclusion_without_managed_capacity(legacy_db, monkeypatch):
    monkeypatch.setattr(adoption, 'seal_proxy_password', AsyncMock(side_effect=CustodyUnavailable('Unavailable')))
    with pytest.raises(CustodyUnavailable): await adopt(legacy_db)
    assert legacy_db.account_proxy_ip_guards.docs and not legacy_db.outreach_proxy_adoptions.docs
    assert not await managed_webshare_valid(legacy_db, legacy_db.outreach_proxy_inventory.docs[0], 'w')


@pytest.mark.parametrize('field', ['password', 'proxy_url', 'unknown_nested_credentials'])
async def test_unknown_or_plaintext_source_shape_is_not_partially_adopted(legacy_db, monkeypatch, field):
    legacy_db.outreach_proxy_inventory.docs[0][field] = 'unprotected-legacy-secret'
    seal = AsyncMock(side_effect=AssertionError('No key work'))
    monkeypatch.setattr(adoption, 'seal_proxy_password', seal)
    with pytest.raises(CustodyUnavailable): await adopt(legacy_db)
    seal.assert_not_awaited()


@pytest.mark.parametrize('field,value', [('proxy_adoption_id','c'*64), ('proxy_adoption_source_digest',None)])
async def test_partial_or_changed_adoption_proof_cannot_be_used(legacy_db, field, value):
    await adopt(legacy_db)
    row = legacy_db.outreach_proxy_inventory.docs[0]
    row[field] = value
    assert not await managed_webshare_valid(legacy_db, row, 'w')


@pytest.mark.parametrize('alias', ['proxy', 'proxy_config'])
async def test_embedded_plaintext_or_unknown_source_fields_deny_before_claim(legacy_db, monkeypatch, alias):
    legacy_db.outreach_accounts.docs[0][alias]['password'] = 'unprotected-legacy-secret'
    seal = AsyncMock(side_effect=AssertionError('No key work'))
    monkeypatch.setattr(adoption, 'seal_proxy_password', seal)
    with pytest.raises(CustodyUnavailable): await adopt(legacy_db)
    seal.assert_not_awaited()
    assert not legacy_db.account_proxy_ip_guards.docs


@pytest.mark.parametrize('field,value', [('status',{'password':'unprotected-secret'}), ('assigned_at','unprotected-secret')])
async def test_embedded_metadata_cannot_carry_alternate_secrets(legacy_db, field, value):
    legacy_db.outreach_accounts.docs[0]['proxy'][field] = value
    with pytest.raises(CustodyUnavailable): await adopt(legacy_db)
    assert not legacy_db.account_proxy_ip_guards.docs


async def test_valid_native_alias_metadata_is_preserved(legacy_db):
    from outreach.models import ProxyStatus
    row = legacy_db.outreach_accounts.docs[0]['proxy']
    stored = adoption._time(datetime.now(timezone.utc))
    row.update(status=ProxyStatus.HEALTHY.value, assigned_at=stored, last_health_check=stored)
    before = {field:row[field] for field in ('status','assigned_at','last_health_check')}
    assert (await adopt(legacy_db))['current_matches']
    assert all(legacy_db.outreach_accounts.docs[0]['proxy'][field] == value for field,value in before.items())


async def test_unreadable_original_fernet_keeps_claim_and_never_seals(legacy_db, monkeypatch):
    row = legacy_db.outreach_proxy_inventory.docs[0]
    row['password_enc'] = 'gAAAAAunreadable'
    for name in ('proxy', 'proxy_config'): legacy_db.outreach_accounts.docs[0][name]['password_enc'] = row['password_enc']
    seal = AsyncMock(side_effect=AssertionError('No key work'))
    monkeypatch.setattr(adoption,'seal_proxy_password',seal)
    with pytest.raises(CustodyUnavailable): await adopt(legacy_db)
    seal.assert_not_awaited()
    assert legacy_db.account_proxy_ip_guards.docs and not legacy_db.outreach_proxy_adoptions.docs


@pytest.mark.parametrize('field', ['verified_at', 'expires_at'])
async def test_original_provider_dates_require_native_database_dates_before_claim(legacy_db, monkeypatch, field):
    row = legacy_db.outreach_proxy_inventory.docs[0]
    row[field] = row[field].isoformat()
    seal = AsyncMock(side_effect=AssertionError('No key work'))
    monkeypatch.setattr(adoption, 'seal_proxy_password', seal)
    with pytest.raises(CustodyUnavailable): await adopt(legacy_db)
    seal.assert_not_awaited()
    assert not legacy_db.account_proxy_ip_guards.docs
