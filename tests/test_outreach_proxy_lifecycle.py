"""Externally performed Webshare changes require stopped, exact original review."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from outreach.core import proxy_lifecycle as lifecycle
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.proxy_custody import prepare_proxy
from outreach.core.webshare_provisioning import managed_webshare_valid
from tests.test_outreach_webshare_migration import webshare_db, scoped, ASSET, EVIDENCE, convert

pytestmark=pytest.mark.asyncio


async def change(db, operation='renew', view=None, **options):
    service=lifecycle.ProxyLifecycle(db)
    view=view or await service.inspect('w',ASSET,operation)
    kwargs=dict(workers_drained=True)
    if operation=='renew':kwargs['expires_at']=datetime.now(timezone.utc)+timedelta(days=60)
    else:kwargs['password_supplier']=lambda:'changed-private-password'
    kwargs.update(options)
    return await service.apply('w',ASSET,operation,'operator',EVIDENCE,'provider-change-1',view['digest'],**kwargs)


async def test_renewal_is_metadata_only_and_retains_original_purchase_and_credentials(webshare_db,monkeypatch):
    db=webshare_db;await convert(db)
    before=deepcopy(db.outreach_proxy_inventory.docs[0]);account=deepcopy(db.outreach_accounts.docs[0])
    lease=deepcopy(db.outreach_proxy_leases.docs)
    seal=AsyncMock(side_effect=AssertionError('No key work on renewal'));monkeypatch.setattr(lifecycle,'seal_proxy_password',seal)
    result=await change(db);after=db.outreach_proxy_inventory.docs[0]
    assert result['current_matches'] and not result['activation_allowed']
    assert after['expires_at']>before['expires_at'] and after['password_enc']==before['password_enc']
    assert after['credential_generation']==before['credential_generation']
    assert after['root_import_basis_digest']==before['import_basis_digest']
    assert after['provider_order_id']==before['provider_order_id'] and after['evidence_digest']==before['evidence_digest']
    assert db.outreach_accounts.docs[0]==account and db.outreach_proxy_leases.docs==lease
    assert await managed_webshare_valid(db,after,'w')
    assert db.outreach_sender_execution.docs[0]['permission']['latched']
    seal.assert_not_awaited()


@pytest.mark.parametrize('mode',['legacy_fernet','kms_v1'])
async def test_rotation_preserves_transport_term_and_cookie_identity_but_changes_proxy_generation(webshare_db,monkeypatch,mode):
    db=webshare_db
    if mode=='kms_v1':await convert(db)
    else:monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE',mode)
    before=deepcopy(db.outreach_proxy_inventory.docs[0]);lease=deepcopy(db.outreach_proxy_leases.docs)
    assert (await change(db,'rotate'))['current_matches']
    after=db.outreach_proxy_inventory.docs[0];account=db.outreach_accounts.docs[0]
    assert after['credential_generation']!=before['credential_generation'] and after['expires_at']==before['expires_at']
    for field in ('host','port','username','country_code','provider_order_id','provider_plan_id','provider_resource_id'):
        assert after[field]==before[field]
    assert account['credential_generation']=='cookie-original' and account['status']=='paused'
    assert db.outreach_proxy_leases.docs==lease
    prepared=await prepare_proxy(account['proxy'],'w')
    assert 'changed-private-password' in prepared.url and prepared.matches(after,'w')
    assert prepared.matches(account['proxy_config'],'w') and await managed_webshare_valid(db,after,'w')
    assert 'changed-private-password' not in str(db.outreach_proxy_lifecycle_reviews.docs)


async def test_expired_original_term_can_be_renewed_with_new_evidence_but_cannot_rotate(webshare_db,monkeypatch):
    from outreach.core.webshare_provisioning import _basis
    db=webshare_db;monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet')
    row=db.outreach_proxy_inventory.docs[0];row['expires_at']=datetime.now(timezone.utc)-timedelta(days=1)
    row['import_basis_digest']=_basis(row)
    supplier=Mock(return_value='secret')
    with pytest.raises(CustodyUnavailable):await change(db,'rotate',password_supplier=supplier)
    supplier.assert_not_called()
    assert (await change(db))['current_matches'] and await managed_webshare_valid(db,row,'w')


@pytest.mark.parametrize('issue',['proof','claim','owner','lease','alias','active','held','lock','job','closed','drain',
    'live','studio','preparation','integrations','format','policy'])
async def test_unsafe_change_denies_before_password_input_or_key_work(webshare_db,monkeypatch,issue):
    db=webshare_db;await convert(db);service=lifecycle.ProxyLifecycle(db)
    view=await service.inspect('w',ASSET,'rotate');row=db.outreach_proxy_inventory.docs[0]
    if issue=='proof':row.pop('managed_webshare_version')
    if issue=='claim':db.account_proxy_ip_guards.docs.clear()
    if issue=='owner':row['workspace_id']='other'
    if issue=='lease':db.outreach_proxy_leases.docs[0]['sender_id']='other'
    if issue=='alias':db.outreach_accounts.docs[0]['proxy_config']['username']='replacement'
    if issue=='active':db.outreach_accounts.docs[0]['status']='active'
    if issue=='held':db.outreach_physical_requests.docs.append({'workspace_id':'w','sender_id':'a','status':'unknown_outcome'})
    if issue=='lock':db.outreach_connection_locks.docs.append({'_id':'a','workspace_id':'w'})
    if issue=='job':db.outreach_connection_jobs.docs.append({'workspace_id':'w','proxy_id':ASSET,'status':'queued'})
    if issue=='closed':monkeypatch.setattr(lifecycle.erasure,'workspace_is_open',AsyncMock(return_value=False))
    if issue=='format':row['password_enc']='plaintext'
    if issue=='policy':monkeypatch.setenv('OUTREACH_KMS_ROLE_ID','replacement')
    flag={'live':'OUTREACH_LIVE_ACTIONS_ENABLED','studio':'OUTREACH_VOICE_STUDIO_ENABLED',
        'preparation':'OUTREACH_VOICE_PREPARATION_ENABLED','integrations':'OUTREACH_INTEGRATIONS_ENABLED'}.get(issue)
    if flag:monkeypatch.setenv(flag,'true')
    supplier=Mock(return_value='changed-private-password');seal=AsyncMock(side_effect=AssertionError('No key'))
    monkeypatch.setattr(lifecycle,'seal_proxy_password',seal)
    with pytest.raises(CustodyUnavailable):await change(db,'rotate',view,password_supplier=supplier,workers_drained=issue!='drain')
    supplier.assert_not_called();seal.assert_not_awaited();assert not db.outreach_proxy_lifecycle_reviews.docs


@pytest.mark.parametrize('target',[datetime.now(timezone.utc)-timedelta(days=1),datetime.now(timezone.utc)+timedelta(days=5),
    datetime.now(timezone.utc)+timedelta(days=400),datetime(2026,10,8),[], 'not-a-date'])
async def test_invalid_target_term_denies_without_change(webshare_db,monkeypatch,target):
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet')
    before=deepcopy(webshare_db.outreach_proxy_inventory.docs)
    with pytest.raises(CustodyUnavailable):await change(webshare_db,expires_at=target)
    assert webshare_db.outreach_proxy_inventory.docs==before


async def test_exact_rotation_receipt_retry_skips_hidden_input_and_resealing(webshare_db,monkeypatch):
    db=webshare_db;await convert(db);service=lifecycle.ProxyLifecycle(db);view=await service.inspect('w',ASSET,'rotate')
    first=await change(db,'rotate',view)
    supplier=Mock(side_effect=AssertionError('No password input'));seal=AsyncMock(side_effect=AssertionError('No key'))
    monkeypatch.setattr(lifecycle,'seal_proxy_password',seal)
    assert await change(db,'rotate',view,password_supplier=supplier)==first
    with pytest.raises(CustodyUnavailable):
        await service.apply('w',ASSET,'rotate','other',EVIDENCE,'provider-change-1',view['digest'],
            workers_drained=True,password_supplier=supplier)
    db.outreach_accounts.docs[0]['proxy']['credential_generation']='replacement'
    assert not (await change(db,'rotate',view,password_supplier=supplier))['current_matches']
    supplier.assert_not_called();seal.assert_not_awaited()


async def test_renewal_chain_preserves_root_and_cannot_reuse_one_provider_reference(webshare_db,monkeypatch):
    db=webshare_db;monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet')
    await change(db);first=deepcopy(db.outreach_proxy_inventory.docs[0]);service=lifecycle.ProxyLifecycle(db)
    view=await service.inspect('w',ASSET,'renew')
    with pytest.raises(CustodyUnavailable):await change(db,view=view,expires_at=datetime.now(timezone.utc)+timedelta(days=90))
    await service.apply('w',ASSET,'renew','operator',EVIDENCE,'provider-change-2',view['digest'],workers_drained=True,
        expires_at=datetime.now(timezone.utc)+timedelta(days=90))
    after=db.outreach_proxy_inventory.docs[0]
    assert after['root_import_basis_digest']==first['root_import_basis_digest'] and after['proxy_lifecycle_revision']==2
    assert len(db.outreach_proxy_lifecycle_reviews.docs)==2 and await managed_webshare_valid(db,after,'w')
    db.outreach_proxy_lifecycle_reviews.docs.clear()
    assert not await managed_webshare_valid(db,after,'w')
    with pytest.raises(CustodyUnavailable):await change(db,'rotate')


async def test_legacy_renewal_then_scoped_migration_keeps_lifecycle_proof(webshare_db,monkeypatch):
    db=webshare_db;monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet');await change(db)
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','kms_v1')
    assert (await convert(db))['current_matches'] and await managed_webshare_valid(db,db.outreach_proxy_inventory.docs[0],'w')


@pytest.mark.parametrize('password',['','x'*257,'x\nsecret','😀'*100])
async def test_invalid_new_password_cannot_reach_key_service(webshare_db,monkeypatch,password):
    db=webshare_db;await convert(db);seal=AsyncMock(side_effect=AssertionError('No key'));monkeypatch.setattr(lifecycle,'seal_proxy_password',seal)
    with pytest.raises(CustodyUnavailable):await change(db,'rotate',password_supplier=lambda:password)
    seal.assert_not_awaited()


async def test_deleted_lineage_fields_cannot_relabel_reviewed_asset_as_original_import(webshare_db,monkeypatch):
    db=webshare_db;monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet');await change(db)
    row=db.outreach_proxy_inventory.docs[0]
    for field in ('root_import_basis_digest','proxy_lifecycle_revision','proxy_lifecycle_review_id'):
        row.pop(field)
    assert not await managed_webshare_valid(db,row,'w')
    with pytest.raises(CustodyUnavailable):await change(db,'rotate')


@pytest.mark.parametrize('timing',['proof','readback'])
@pytest.mark.parametrize('drift',['policy','flag'])
async def test_final_pure_configuration_checks_follow_every_readback_await(webshare_db,monkeypatch,timing,drift):
    db=webshare_db;await convert(db)
    async def flip():
        monkeypatch.setenv('OUTREACH_KMS_ROLE_ID' if drift=='policy' else 'OUTREACH_LIVE_ACTIONS_ENABLED',
            'replacement' if drift=='policy' else 'true')
    if timing=='proof':
        original=lifecycle.valid_history
        async def proof(*args,**kwargs):
            result=await original(*args,**kwargs);await flip();return result
        monkeypatch.setattr(lifecycle,'valid_history',proof)
    else:
        original=lifecycle.ProxyLifecycle._saved
        async def readback(self,*args,**kwargs):
            result=await original(self,*args,**kwargs);await flip();return result
        monkeypatch.setattr(lifecycle.ProxyLifecycle,'_saved',readback)
    with pytest.raises(CustodyUnavailable):await change(db,'rotate')


async def test_saved_renewal_can_be_inspected_after_target_term_expires_without_new_install(webshare_db,monkeypatch):
    db=webshare_db;monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet')
    view=await lifecycle.ProxyLifecycle(db).inspect('w',ASSET,'renew')
    target=datetime.now(timezone.utc)+timedelta(days=60)
    first=await change(db,view=view,expires_at=target)
    monkeypatch.setattr(lifecycle,'now',lambda:datetime.now(timezone.utc)+timedelta(days=90))
    assert await change(db,view=view,expires_at=target)==first


@pytest.mark.parametrize('field,value',[('root_import_basis_digest','c'*64),('proxy_lifecycle_revision',True),
    ('proxy_lifecycle_review_id','c'*64),('root_import_basis_digest',None)])
async def test_corrupted_lineage_cannot_be_used_or_rotated(webshare_db,monkeypatch,field,value):
    db=webshare_db;monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet');await change(db)
    row=db.outreach_proxy_inventory.docs[0];row[field]=value
    assert not await managed_webshare_valid(db,row,'w')
    supplier=Mock(side_effect=AssertionError('No password input'))
    with pytest.raises(CustodyUnavailable):await change(db,'rotate',password_supplier=supplier)
    supplier.assert_not_called()
