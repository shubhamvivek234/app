"""Reviewed Webshare conversion never supplies missing purchase/assignment proof."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from outreach.core import proxy_migration as migration
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.proxy_custody import prepare_proxy
from outreach.core.sender_execution import SenderExecution
from outreach.core.webshare_provisioning import import_webshare_proxy, managed_webshare_valid
from tests.outreach_memory import Database
from tests.test_outreach_session_custody import scoped
from tests.test_outreach_proxy_migration import proxy_db

pytestmark = pytest.mark.asyncio
ASSET = 'webshare:plan:resource'
EVIDENCE = 'b' * 64


@pytest_asyncio.fixture
async def webshare_db(scoped, monkeypatch):
    for flag in ('OUTREACH_LIVE_ACTIONS_ENABLED', 'OUTREACH_INTEGRATIONS_ENABLED',
                 'OUTREACH_VOICE_STUDIO_ENABLED', 'OUTREACH_VOICE_PREPARATION_ENABLED'):
        monkeypatch.setenv(flag, 'false')
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'legacy_fernet')
    db = Database()
    await import_webshare_proxy(db, proxy_url='http://operator:private-password@191.116.125.248:12323',
        country_code='IN', plan_id='plan', resource_id='resource', provider_order_id='order',
        workspace_id='w', expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        verified_by='operator', evidence_digest='a' * 64, dedicated_isp_confirmed=True)
    row = db.outreach_proxy_inventory.docs[0]
    proxy = {key: row[key] for key in ('provider', 'host', 'port', 'username', 'password_enc',
        'country_code', 'credential_generation', 'custody_workspace_id')} | {'proxy_id': ASSET}
    db.outreach_proxy_leases.docs.append({'_id':ASSET, 'workspace_id':'w', 'sender_id':'a',
        'provider':'webshare_plan', 'country_code':'IN', 'reservation_job_id':'original'})
    db.outreach_accounts.docs.append({'id':'a', 'workspace_id':'w', 'status':'paused',
        'proxy':deepcopy(proxy), 'proxy_config':deepcopy(proxy), 'credential_generation':'cookie-original'})
    db.outreach_sender_execution.docs.append({**SenderExecution.scope('w','a'), 'status':'idle',
        'permission':{'latched':True}})
    monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE', 'kms_v1')
    return db


async def convert(db, view=None, **changes):
    service = migration.ProxyMigration(db)
    view = view or await service.inspect('w', ASSET)
    args = dict(workers_drained=True, evidence_digest=EVIDENCE)
    args.update(changes)
    return await service.migrate('w',ASSET,'operator',view['digest'], **args)


async def test_proven_webshare_migration_preserves_basis_term_lease_and_stopped_authority(webshare_db):
    db=webshare_db; before=deepcopy(db.outreach_proxy_inventory.docs[0]); lease=deepcopy(db.outreach_proxy_leases.docs)
    view=await migration.ProxyMigration(db).inspect('w', ASSET)
    assert not view['blockers'] and not view['activation_allowed']
    assert 'gAAAAA' not in str(view) and '191.116.125.248' not in str(view)
    result=await convert(db, view)
    assert result['current_matches'] and result['configuration_matches'] and not result['activation_allowed']
    after=db.outreach_proxy_inventory.docs[0]
    assert after['import_basis_digest']==before['import_basis_digest']
    assert after['credential_generation']==before['credential_generation'] and after['expires_at']==before['expires_at']
    assert await managed_webshare_valid(db,after,'w')
    account=db.outreach_accounts.docs[0]; prepared=await prepare_proxy(account['proxy'],'w')
    assert prepared.matches(after,'w') and prepared.matches(account['proxy_config'],'w')
    assert account['status']=='paused' and account['credential_generation']=='cookie-original'
    assert db.outreach_proxy_leases.docs==lease and db.outreach_sender_execution.docs[0]['permission']['latched']
    receipt=db.outreach_credential_migrations.docs[0]
    assert receipt['provenance']=='strict_fernet_storage_conversion' and receipt['evidence_digest']==EVIDENCE
    assert 'private-password' not in str(receipt) and 'uc1:' not in str(receipt) and 'operator' not in receipt


@pytest.mark.parametrize('problem', ['basis','guard','term','legacy','lease_provider','lease_country',
    'owner','generation','alias','active','held','evidence','drain','scoped','plaintext','closed',
    'studio','preparation','integrations'])
async def test_unproven_or_unsafe_asset_denies_before_sealing(webshare_db,monkeypatch,problem):
    db=webshare_db; row=db.outreach_proxy_inventory.docs[0]; account=db.outreach_accounts.docs[0]
    if problem=='basis':row['import_basis_digest']='c'*64
    if problem=='guard':db.account_proxy_ip_guards.docs.clear()
    if problem=='term':row['expires_at']=datetime.now(timezone.utc)
    if problem=='legacy':row.pop('managed_webshare_version')
    if problem=='lease_provider':db.outreach_proxy_leases.docs[0]['provider']='iproyal_static'
    if problem=='lease_country':db.outreach_proxy_leases.docs[0]['country_code']='US'
    if problem=='owner':row['last_workspace_id']='other'
    if problem=='generation':row['credential_generation']='replacement'
    if problem=='alias':account['proxy_config']['username']='replacement'
    if problem=='active':account['status']='active'
    if problem=='held':db.outreach_physical_requests.docs.append({'workspace_id':'w','sender_id':'a','status':'unknown_outcome'})
    if problem in {'scoped','plaintext'}:
        row['password_enc']='uc1:unproven' if problem=='scoped' else 'unproven-plaintext'
        account['proxy']['password_enc']=account['proxy_config']['password_enc']=row['password_enc']
    if problem=='closed':monkeypatch.setattr(migration.erasure,'workspace_is_open',AsyncMock(return_value=False))
    flag={'studio':'OUTREACH_VOICE_STUDIO_ENABLED','preparation':'OUTREACH_VOICE_PREPARATION_ENABLED',
          'integrations':'OUTREACH_INTEGRATIONS_ENABLED'}.get(problem)
    if flag:monkeypatch.setenv(flag,'true')
    seal=AsyncMock(side_effect=AssertionError('No key work')); monkeypatch.setattr(migration,'seal_proxy_password',seal)
    with pytest.raises(CustodyUnavailable):
        await convert(db, evidence_digest='' if problem=='evidence' else EVIDENCE, workers_drained=problem!='drain')
    seal.assert_not_awaited(); assert not db.outreach_credential_migrations.docs


@pytest.mark.parametrize('field', ['OUTREACH_KMS_ROLE_ID','OUTREACH_KMS_KEY_ARN','OUTREACH_CUSTODY_ENVIRONMENT_ID'])
async def test_policy_change_after_sealing_denies_install(webshare_db,monkeypatch,field):
    db=webshare_db; seal=migration.seal_proxy_password; original=db.outreach_proxy_inventory.docs[0]['password_enc']
    async def changed(*args,**kwargs):
        result=await seal(*args,**kwargs);monkeypatch.setenv(field,'replacement');return result
    monkeypatch.setattr(migration,'seal_proxy_password',changed)
    with pytest.raises(CustodyUnavailable):await convert(db)
    assert db.outreach_proxy_inventory.docs[0]['password_enc']==original and not db.outreach_credential_migrations.docs


async def test_saved_receipt_is_bound_and_retries_do_not_open_original_or_seal(webshare_db,monkeypatch):
    db=webshare_db; service=migration.ProxyMigration(db);view=await service.inspect('w',ASSET)
    first=await convert(db,view)
    def denied(*args,**kwargs):raise AssertionError('No original credential opening')
    monkeypatch.setattr(migration,'decrypt_strict',denied)
    monkeypatch.setattr(migration,'seal_proxy_password',AsyncMock(side_effect=AssertionError('No key work')))
    assert await convert(db,view)==first
    with pytest.raises(CustodyUnavailable):await convert(db,view,evidence_digest='c'*64)
    with pytest.raises(CustodyUnavailable):await service.migrate('w',ASSET,'other',view['digest'],workers_drained=True,evidence_digest=EVIDENCE)
    db.outreach_proxy_inventory.docs[0]['expires_at']+=timedelta(days=1)
    assert not (await convert(db,view))['current_matches']
    monkeypatch.setenv('OUTREACH_KMS_ROLE_ID','replacement')
    assert not (await convert(db,view))['configuration_matches']


async def test_concurrent_saved_receipt_wins_before_original_digest_and_key_work(webshare_db,monkeypatch):
    db=webshare_db; service=migration.ProxyMigration(db);view=await service.inspect('w',ASSET)
    mutate=migration.suppression.mutate_suppression; first=True
    async def interrupted(db,workspace,callback):
        nonlocal first
        if first:
            first=False
            await convert(db,view)
        return await mutate(db,workspace,callback)
    monkeypatch.setattr(migration.suppression,'mutate_suppression',interrupted)
    assert (await convert(db,view))['current_matches']
    assert len(db.outreach_credential_migrations.docs)==1


async def test_unused_proven_asset_can_convert_without_creating_sender_or_lease(webshare_db):
    db=webshare_db;db.outreach_accounts.docs.clear();db.outreach_proxy_leases.docs.clear();db.outreach_sender_execution.docs.clear()
    assert (await convert(db))['current_matches']
    assert not db.outreach_accounts.docs and not db.outreach_proxy_leases.docs and not db.outreach_sender_execution.docs


async def test_true_older_iproyal_receipt_preserves_default_codec_timestamp_hash(proxy_db,monkeypatch):
    from outreach.core.authorization import canonical_hash
    from outreach.core.proxy_custody import proxy_digest
    db=proxy_db; service=migration.ProxyMigration(db);view=await service.inspect('w','iproyal:p')
    await service.migrate('w','iproyal:p','operator',view['digest'],workers_drained=True)
    account=db.outreach_accounts.docs[0]
    for name in ('proxy','proxy_config'):
        account[name]['assigned_at']=datetime(2026,10,8,1,2,3,456000)
    old=canonical_hash({'inventory':proxy_digest(db.outreach_proxy_inventory.docs[0]),
        'accounts':[{key:account.get(key) for key in ('id','proxy','proxy_config')}]})
    receipt=db.outreach_credential_migrations.docs[0]
    for field in ('material_version','operator_digest','target_policy_digest','evidence_digest'):
        receipt.pop(field,None)
    receipt.update(operator='operator',after_digest=old)
    monkeypatch.setattr(migration,'seal_proxy_password',AsyncMock(side_effect=AssertionError('No key work')))
    result=await service.migrate('w','iproyal:p','operator',view['digest'],workers_drained=True)
    assert result['current_matches'] and not result['configuration_matches']


@pytest.mark.parametrize('field,value', [('verified_by','replacement'), ('evidence_digest','c'*64),
    ('dedicated_isp_confirmed',False), ('provider_resource_id','replacement'), ('status','expired')])
async def test_receipt_metadata_does_not_match_changed_original_manual_basis(webshare_db,field,value):
    db=webshare_db;view=await migration.ProxyMigration(db).inspect('w',ASSET);await convert(db,view)
    db.outreach_proxy_inventory.docs[0][field]=value
    assert not (await convert(db,view))['current_matches']


@pytest.mark.parametrize('field,value', [('expires_at',[]), ('custody_workspace_id',[]),
    ('provider',[]), ('password_enc',[])])
async def test_malformed_asset_is_denied_before_keys(webshare_db,field,value,monkeypatch):
    db=webshare_db;db.outreach_proxy_inventory.docs[0][field]=value
    view=await migration.ProxyMigration(db).inspect('w',ASSET)
    assert view['blockers']
    seal=AsyncMock(side_effect=AssertionError('No key work'));monkeypatch.setattr(migration,'seal_proxy_password',seal)
    with pytest.raises(CustodyUnavailable):await convert(db,view)
    seal.assert_not_awaited()
