"""Manually verified Webshare assets have immutable tenant/term/physical proof."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from tests.outreach_memory import Database
from outreach.core.managed_proxy import ManagedProxyUnavailable, reserve_sender_proxy, import_iproyal_proxy
from outreach.core.webshare_provisioning import import_webshare_proxy, managed_webshare_valid

pytestmark = pytest.mark.asyncio
NOW = datetime(2026, 10, 8, tzinfo=timezone.utc)
URL = 'http://pilot:private-password@191.116.125.248:12323'


@pytest.fixture(autouse=True)
def local_encryption(monkeypatch):
    from cryptography.fernet import Fernet
    from utils import encryption
    monkeypatch.setattr(encryption, '_fernet', Fernet(Fernet.generate_key()))


def arguments(**changes):
    return dict(proxy_url=URL, country_code='IN', plan_id='plan-1', resource_id='proxy-1',
                provider_order_id='order-1', workspace_id='w', expires_at=NOW + timedelta(days=30),
                verified_by='operator', evidence_digest='a' * 64, dedicated_isp_confirmed=True,
                now=NOW, **changes)


async def imported(db=None):
    db = db or Database()
    result = await import_webshare_proxy(db, **arguments())
    return db, result, await db.outreach_proxy_inventory.find_one({'_id': result['proxy_id']})


async def test_import_encrypts_without_provider_calls_and_returns_no_secret():
    db, result, row = await imported()
    assert result['provider'] == 'webshare_plan'
    assert 'private-password' not in str(result) + str(row)
    assert row['password_enc'] and row['workspace_id'] == 'w'
    assert await managed_webshare_valid(db, row, 'w', now=NOW)
    guards = db.account_proxy_ip_guards.docs
    assert len(guards) == 1 and set(guards[0]) == {'_id', 'binding_digest'}
    assert '191.116' not in str(guards) and 'operator' not in str(guards)


async def test_exact_retry_keeps_original_secret_generation_and_does_not_seal(monkeypatch):
    db, result, row = await imported()
    seal = AsyncMock(side_effect=AssertionError('retry must not seal'))
    monkeypatch.setattr('outreach.core.webshare_provisioning.seal_proxy_password', seal)
    retry = arguments()
    retry['proxy_url'] = URL.replace('private-password', 'ignored-new-password')
    retry['now'] = NOW + timedelta(minutes=1)
    assert (await import_webshare_proxy(db, **retry))['status'] == 'already_imported'
    assert await db.outreach_proxy_inventory.find_one({'_id': result['proxy_id']}) == row
    seal.assert_not_awaited()


@pytest.mark.parametrize('field,value', [('workspace_id','other'), ('plan_id','other'),
    ('resource_id','other'), ('provider_order_id','other'), ('country_code','US'),
    ('expires_at',NOW+timedelta(days=31))])
async def test_same_ip_cannot_be_relabelled(field, value):
    db, _, _ = await imported()
    args = arguments(); args[field] = value
    with pytest.raises(ValueError): await import_webshare_proxy(db, **args)
    assert len(db.outreach_proxy_inventory.docs) == 1


@pytest.mark.parametrize('provider_first', ['webshare', 'iproyal'])
async def test_cross_provider_import_cannot_alias_physical_ip(provider_first):
    db = Database()
    iproyal = dict(proxy_url=URL.replace(':12323', ':23456'), country_code='IN',
        provider_order_id='royal', workspace_id='other', expires_at=NOW+timedelta(days=30), now=NOW)
    if provider_first == 'webshare':
        await imported(db)
        with pytest.raises(ValueError): await import_iproyal_proxy(db, **iproyal)
    else:
        await import_iproyal_proxy(db, **iproyal)
        with pytest.raises(ValueError): await import_webshare_proxy(db, **arguments())


async def test_legacy_alias_and_permanent_claim_survive_inventory_deletion():
    legacy = Database(outreach_proxy_inventory=[{'_id':'old', 'host':'191.116.125.248', 'last_workspace_id':'other'}])
    with pytest.raises(ValueError): await import_webshare_proxy(legacy, **arguments())
    db, _, _ = await imported()
    db.outreach_proxy_inventory.docs.clear()
    args = arguments(); args['workspace_id'] = 'other'
    with pytest.raises(ValueError): await import_webshare_proxy(db, **args)


@pytest.mark.parametrize('field,value', [('workspace_id','other'), ('provider','iproyal_static'),
    ('host','8.8.8.8'), ('expires_at',NOW+timedelta(days=31)), ('credential_generation','replacement'),
    ('managed_webshare_version',None), ('country_code','US')])
async def test_immutable_import_basis_rejects_replacement(field, value):
    db, _, row = await imported()
    row[field] = value
    assert not await managed_webshare_valid(db, row, 'w', now=NOW)


async def test_reserve_reconnect_is_exact_sender_and_unknown_legacy_is_blocked():
    db, result, row = await imported()
    proxy = await reserve_sender_proxy(db, 'w', 'sender', 'IN', now=NOW, reservation_job_id='job')
    assert proxy.proxy_id == result['proxy_id']
    assert (await reserve_sender_proxy(db, 'w', 'sender', 'IN', now=NOW)).proxy_id == proxy.proxy_id
    assert db.outreach_proxy_leases.docs[0]['reservation_job_id'] == 'job'
    with pytest.raises(ManagedProxyUnavailable): await reserve_sender_proxy(db, 'w', 'second', 'IN', now=NOW)
    db.outreach_proxy_inventory.docs[0].pop('managed_webshare_version')
    with pytest.raises(ManagedProxyUnavailable): await reserve_sender_proxy(db, 'w', 'sender', 'IN', now=NOW)


@pytest.mark.parametrize('change', [ {'dedicated_isp_confirmed':False}, {'evidence_digest':'not-a-hash'},
    {'proxy_url':'http://u:p@127.0.0.1:123'}, {'expires_at':NOW}, {'verified_by':''} ])
async def test_invalid_manual_evidence_denies_before_key_work(change, monkeypatch):
    seal = AsyncMock(); monkeypatch.setattr('outreach.core.webshare_provisioning.seal_proxy_password', seal)
    args = arguments(); args.update(change)
    with pytest.raises(ValueError): await import_webshare_proxy(Database(), **args)
    seal.assert_not_awaited()


async def test_failed_sealing_keeps_exclusion_without_capacity(monkeypatch):
    db = Database()
    original = __import__('outreach.core.webshare_provisioning', fromlist=['seal_proxy_password']).seal_proxy_password
    monkeypatch.setattr('outreach.core.webshare_provisioning.seal_proxy_password', AsyncMock(side_effect=RuntimeError('key unavailable')))
    with pytest.raises(RuntimeError): await import_webshare_proxy(db, **arguments())
    assert not db.outreach_proxy_inventory.docs and len(db.account_proxy_ip_guards.docs) == 1
    monkeypatch.setattr('outreach.core.webshare_provisioning.seal_proxy_password', original)
    args = arguments(); args['workspace_id'] = 'other'
    with pytest.raises(ValueError): await import_webshare_proxy(db, **args)
    assert (await import_webshare_proxy(db, **arguments()))['status'] == 'imported'


async def test_scope_cutover_blocks_old_import_and_does_not_rewrap(monkeypatch):
    db, _, row = await imported()
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','kms_v1')
    assert not await managed_webshare_valid(db,row,'w',now=NOW)
    with pytest.raises(ValueError): await import_webshare_proxy(db, **arguments())
    with pytest.raises(ManagedProxyUnavailable): await reserve_sender_proxy(db,'w','sender','IN',now=NOW)


@pytest.mark.parametrize('operation', ['seal','open'])
async def test_key_policy_change_during_await_rejects_secret(operation,monkeypatch):
    from outreach.core import proxy_custody
    # Fixture-independent stand-in: the awaited boundary changes actual policy.
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','kms_v1')
    monkeypatch.setenv('OUTREACH_CUSTODY_ENVIRONMENT_ID','old-environment')
    async def change(*args):
        monkeypatch.setenv('OUTREACH_KMS_ROLE_ID','replacement-role')
        return 'uc1:encrypted' if operation == 'seal' else 'private-password'
    from types import SimpleNamespace
    monkeypatch.setattr(proxy_custody.session_custody,'configured_custody',lambda: SimpleNamespace(seal=change,open=change))
    row={'proxy_id':'webshare:plan:resource','provider':'webshare_plan','host':'191.116.125.248',
        'port':12323,'username':'u','country_code':'IN','credential_generation':'g','custody_workspace_id':'w','password_enc':'uc1:encrypted'}
    with pytest.raises(proxy_custody.CustodyUnavailable,match='policy changed'):
        if operation == 'seal': await proxy_custody.seal_proxy_password('private-password',row,'w')
        else: await proxy_custody.prepare_proxy(row,'w')


async def test_prepared_proxy_rejects_same_mode_key_policy_rotation(monkeypatch):
    from outreach.core import proxy_custody
    db, _, row = await imported()
    prepared=await proxy_custody.prepare_proxy(row,'w')
    monkeypatch.setenv('OUTREACH_KMS_ROLE_ID','different-role')
    assert not prepared.matches(row,'w')


async def test_existing_iproyal_same_id_cannot_poison_original_owner_claim(monkeypatch):
    import hashlib
    proxy_id='iproyal:'+hashlib.sha256(b'191.116.125.248:12323').hexdigest()[:24]
    db=Database(outreach_proxy_inventory=[{'_id':proxy_id,'provider':'iproyal_static',
        'last_workspace_id':'original','host':'191.116.125.248','port':12323,'username':'pilot','country_code':'IN'}])
    seal=AsyncMock(side_effect=AssertionError('no key access'))
    monkeypatch.setattr('outreach.core.managed_proxy.seal_proxy_password',seal)
    with pytest.raises(ValueError,match='ownership review'):
        await import_iproyal_proxy(db,URL,'IN','order','other',NOW+timedelta(days=30),now=NOW)
    assert not db.account_proxy_ip_guards.docs
    seal.assert_not_awaited()
