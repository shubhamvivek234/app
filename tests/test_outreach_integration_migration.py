"""Drained strict encrypted integration migration, outside transaction key work."""
from datetime import timedelta
from unittest.mock import AsyncMock
import pytest
from outreach.core import integration_custody as custody, integration_migration as migration, session_custody
from outreach.core.credential_custody import CustodyUnavailable
from outreach.core.integration_delivery import now
from tests.test_outreach_integration_delivery import integration_db
from tests.test_outreach_session_custody import scoped
from tests.test_outreach_integration_review import EVIDENCE
from utils.encryption import encrypt

pytestmark=pytest.mark.asyncio

async def legacy(db,monkeypatch,kind='webhook'):
    row=await custody.collection(db,kind).find_one({'workspace_id':'w',**({'id':'hook'} if kind=='webhook' else {'provider':kind})})
    raw='strict-signing-secret' if kind=='webhook' else 'https://hooks.slack.com/services/T1/B2/private-token' if kind=='slack' else 'strict-crm-token'
    await custody.collection(db,kind).update_one({'_id':row['_id']},{'$set':{custody.FIELDS[kind]:encrypt(raw)}})
    monkeypatch.setenv('OUTREACH_INTEGRATIONS_ENABLED','false')
    return raw

@pytest.mark.parametrize('kind',['webhook','slack','hubspot'])
async def test_migration_preserves_key_generation_and_stops_source(integration_db,monkeypatch,kind):
    db=integration_db;raw=await legacy(db,monkeypatch,kind);resource='hook' if kind=='webhook' else kind
    before=await custody.collection(db,kind).find_one(custody.resource_scope('w',kind,resource))
    service=migration.IntegrationMigration(db);view=await service.inspect('w',kind,resource)
    result=await service.migrate('w',kind,resource,'operator',EVIDENCE,view['review_digest'],workers_drained=True)
    assert result['current_matches'] and not result['activation_allowed']
    after=await custody.collection(db,kind).find_one(custody.resource_scope('w',kind,resource))
    assert after['credential_generation']==before['credential_generation']
    assert (await custody.prepare(after,'w',kind)).value==raw
    assert after['status']=='paused' and after['integration_review_required']
    assert raw not in str(db.outreach_credential_migrations.docs)

async def test_receipt_retry_skips_all_secret_work_and_cannot_repeat_stop(integration_db,monkeypatch,scoped):
    db=integration_db;await legacy(db,monkeypatch);service=migration.IntegrationMigration(db);view=await service.inspect('w','webhook','hook')
    first=await service.migrate('w','webhook','hook','operator',EVIDENCE,view['review_digest'],workers_drained=True)
    opening=AsyncMock(side_effect=AssertionError('No secret'));monkeypatch.setattr(migration,'decrypt_strict',opening)
    sealing=AsyncMock(side_effect=AssertionError('No key service'));monkeypatch.setattr(scoped,'seal',sealing)
    assert await service.migrate('w','webhook','hook','operator',EVIDENCE,view['review_digest'],workers_drained=True)==first
    await db.outreach_webhooks.update_one({'id':'hook'},{'$set':{'credential_generation':'replacement'}})
    assert not (await service.migrate('w','webhook','hook','operator',EVIDENCE,view['review_digest'],workers_drained=True))['current_matches']
    opening.assert_not_awaited();sealing.assert_not_awaited()

@pytest.mark.parametrize('problem',['plaintext','scoped','drain','flag','mode','closed','hold','changed','policy'])
async def test_unsafe_or_unproven_migration_denies(integration_db,monkeypatch,scoped,problem):
    db=integration_db
    if problem!='scoped':await legacy(db,monkeypatch)
    else:monkeypatch.setenv('OUTREACH_INTEGRATIONS_ENABLED','false')
    service=migration.IntegrationMigration(db);view=await service.inspect('w','webhook','hook')
    if problem=='plaintext':await db.outreach_webhooks.update_one({'id':'hook'},{'$set':{'secret_enc':'plaintext-secret'}})
    if problem=='flag':monkeypatch.setenv('OUTREACH_INTEGRATIONS_ENABLED','true')
    if problem=='mode':monkeypatch.setenv('OUTREACH_CREDENTIAL_CUSTODY_MODE','legacy_fernet')
    if problem=='closed':monkeypatch.setattr(migration.erasure,'workspace_is_open',AsyncMock(return_value=False))
    if problem=='hold':await db.outreach_webhook_deliveries.insert_one({'workspace_id':'w','id':'held','destination_type':'webhook','destination_id':'hook','status':'review_required'})
    if problem=='changed':await db.outreach_webhooks.update_one({'id':'hook'},{'$set':{'credential_generation':'replacement'}})
    if problem=='policy':monkeypatch.setenv('OUTREACH_KMS_ROLE_ID','replacement')
    with pytest.raises(ValueError):await service.migrate('w','webhook','hook','operator',EVIDENCE,view['review_digest'],workers_drained=problem!='drain')
    assert not db.outreach_credential_migrations.docs

async def test_missing_type_legacy_unknown_blocks_migration(integration_db,monkeypatch):
    db=integration_db;await legacy(db,monkeypatch)
    await db.outreach_webhook_deliveries.insert_one({'_id':'old','id':'old','workspace_id':'w','destination_id':'hook','status':'review_required'})
    service=migration.IntegrationMigration(db);view=await service.inspect('w','webhook','hook')
    assert 'original_delivery_outcome_unresolved' in view['blockers']
    with pytest.raises(ValueError):await service.migrate('w','webhook','hook','operator',EVIDENCE,view['review_digest'],workers_drained=True)
